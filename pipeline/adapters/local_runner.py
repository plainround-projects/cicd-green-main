"""The whole pipeline on a laptop: the same jobs as .github/workflows/ci.yml, each one a `make` target.

Two variants give the lesson's before and after:

- `sequential`: a fresh virtual environment with no cache, then lint, unit tests, the integration test and the build,
  one after another.
- `parallel`: the cached environment (`.venv`, keyed by the lock file's hash), the build once, then lint, unit tests and
  the integration test at the same time. The integration test runs against the built wheel, after its checksum is
  verified. The quarantine job runs beside them and never counts.
"""

from __future__ import annotations

import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pipeline.adapters import git
from pipeline.adapters.builder import SUMS_FILE
from pipeline.adapters.process import Command, Job, Outcome, run_job, submit
from pipeline.core import runlog
from pipeline.core.checksum import parse_sums
from pipeline.core.flaky import FailedTest, parse_junit_failures

REQUIRED = ("build", "lint", "unit", "integration")
UNIT_PATHS = ("tests/unit", "tests/pipeline")
LOCK_FILE = "requirements-dev.lock"


@dataclass(frozen=True, slots=True)
class RunOptions:
    """What to run: the variant, the jobs to keep (None means all) and whether quarantined tests join the unit job."""

    variant: str
    only: frozenset[str] | None = None
    include_quarantined: bool = False


def make_job(name: str, *arguments: str) -> Job:
    """A job that is one `make` target: the pipeline file and the laptop share one definition of each job."""
    return Job(name, (Command(("make", "--no-print-directory", *arguments)),))


def unit_job(include_quarantined: bool) -> Job:
    """`make test`, with the quarantine marker filter removed when quarantined tests are wanted."""
    return make_job("unit", "test", "UNIT_MARKERS=" if include_quarantined else "UNIT_MARKERS=not flaky_quarantine")


def integration_job(wheel: Path, digest: str) -> Job:
    """`make test-artifact`: verify the wheel's checksum, install it (not the sources) and test it."""
    return make_job("integration", "test-artifact", f"WHEEL={wheel}", f"EXPECTED_SHA256={digest}")


def _read_digest(root: Path) -> tuple[Path, str]:
    sums = parse_sums((root / "dist" / SUMS_FILE).read_text())
    name, digest = next(iter(sums.items()))
    return root / "dist" / name, digest


def run_parallel(root: Path, options: RunOptions) -> list[Outcome]:
    """Build, then lint, unit and integration at the same time; the quarantine job runs beside them."""
    log_dir = root / "reports"
    wanted = options.only or frozenset({*REQUIRED, "quarantine"})
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        if "lint" in wanted:
            futures["lint"] = submit(pool, make_job("lint", "lint"), root, log_dir)
        if "unit" in wanted:
            futures["unit"] = submit(pool, unit_job(options.include_quarantined), root, log_dir)
        if "quarantine" in wanted:
            futures["quarantine"] = submit(pool, make_job("quarantine", "quarantine"), root, log_dir)
        if wanted & {"build", "integration"}:
            futures["build"] = submit(pool, make_job("build", "build"), root, log_dir)
        if "integration" in wanted:

            def integrate() -> Outcome:
                built = futures["build"].result()
                if not built.ok:
                    return Outcome("integration", False, 0.0, built.log)
                wheel, digest = _read_digest(root)
                return run_job(integration_job(wheel, digest), root, log_dir)

            futures["integration"] = pool.submit(integrate)
        outcomes = [future.result() for future in futures.values()]
    return outcomes


def sequential_job(root: Path) -> Job:
    """Everything in one job, from a cold environment, as the first version of the pipeline did."""
    venv = root / ".cache" / "baseline-venv"
    python = str(venv / "bin" / "python")

    def tool(name: str) -> str:
        return str(venv / "bin" / name)

    pytest = (python, "-m", "pytest", "-p", "no:cacheprovider", "-q")
    return Job(
        "sequential",
        (
            Command((sys.executable, "-m", "venv", "--clear", str(venv))),
            Command(
                (tool("pip"), "install", "-q", "--no-cache-dir", "--require-hashes", "-r", "requirements-dev.lock")
            ),
            Command((tool("pip"), "install", "-q", "--no-deps", "-e", ".")),
            Command((tool("ruff"), "check", ".")),
            Command((tool("ruff"), "format", "--check", ".")),
            Command((tool("mypy"),)),
            Command((tool("lint-imports"),)),
            Command((*pytest, *UNIT_PATHS, "-m", "not flaky_quarantine", "--junitxml=reports/unit.xml")),
            Command((*pytest, "tests/integration")),
            Command((python, "-m", "pipeline", "build")),
        ),
    )


def run_pipeline(root: Path, options: RunOptions, runs_csv: Path) -> tuple[list[Outcome], runlog.RunRecord]:
    """Run one variant, append its row to the run log and return the job outcomes with that row."""
    shutil.rmtree(root / "reports", ignore_errors=True)
    started = time.monotonic()
    if options.variant == "sequential":
        outcomes = [run_job(sequential_job(root), root, root / "reports")]
    else:
        outcomes = run_parallel(root, options)
    seconds = time.monotonic() - started
    required_ok = all(outcome.ok for outcome in outcomes if outcome.name in REQUIRED or outcome.name == "sequential")
    failures = _unit_failures(root)
    record = runlog.RunRecord(
        run=runlog.next_run_number(runlog.read(runs_csv)),
        commit=git.head_sha(root)[:7],
        seconds=seconds,
        result=runlog.SUCCESS if required_ok else runlog.FAILURE,
        variant=options.variant,
        failed_tests=tuple(failure.test_id for failure in failures),
        message=failures[0].message if failures else "",
    )
    runlog.append(runs_csv, record)
    return outcomes, record


def _unit_failures(root: Path) -> list[FailedTest]:
    report = root / "reports" / "unit.xml"
    return parse_junit_failures(report.read_text()) if report.exists() else []
