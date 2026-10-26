"""`python -m pipeline <command>`: the pipeline's steps, the same on a laptop and in GitHub Actions."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from pipeline.adapters import builder, gate, git, github, local_runner
from pipeline.adapters.process import Outcome
from pipeline.core import checksum, contract, flaky, ghruns, protection, runlog, workflow
from pipeline.core.version import base_version, build_version

_log = logging.getLogger("pipeline")
ROOT = Path(__file__).resolve().parent.parent
QUARANTINE_JOBS = ("quarantine",)


def build_parser() -> argparse.ArgumentParser:
    """The argument parser; exposed so tests can drive it."""
    parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="print the version this commit would be built as")
    commands.add_parser("build", help="build the wheel once and write dist/SHA256SUMS")
    verify = commands.add_parser("verify", help="check an artifact's SHA-256 (exit 1 on a mismatch)")
    verify.add_argument("artifact", type=Path)
    verify.add_argument("--expected", required=True, help="the digest the build job reported")
    verify.add_argument("--job", default="job", help="the job name to print")
    run = commands.add_parser("run", help="run the whole pipeline locally and append a row to runs.csv")
    run.add_argument("--variant", choices=("parallel", "sequential"), default="parallel")
    run.add_argument("--only", help="comma-separated jobs to run (build, lint, unit, integration, quarantine)")
    run.add_argument("--include-quarantined", action="store_true", help="run quarantined tests inside the unit job")
    run.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    bench = commands.add_parser("bench", help="run both variants N times and print the before and after table")
    bench.add_argument("--runs", type=int, default=5)
    bench.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    report = commands.add_parser("flaky", help="find flaky tests in the run log")
    report.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    report.add_argument("--variant", help="only rows of this variant")
    importer = commands.add_parser("import-gh-runs", help="convert `gh run list --json ...` output into run-log rows")
    importer.add_argument("json_file", type=Path)
    importer.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    protect = commands.add_parser("protection", help="print (or apply) the branch-protection settings for main")
    protect.add_argument("--apply", metavar="OWNER/REPO", help="apply them with the gh CLI")
    commands.add_parser("lint-workflows", help="check every workflow against the rules in pipeline/core/workflow.py")
    commands.add_parser("check-contract", help="check the README's pipeline contract")
    status = commands.add_parser("gate", help="run the checks on a commit and, if they pass, post its green status")
    status.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="the repository holding the commit (default: here)"
    )
    status.add_argument("--remote", default="origin")
    status.add_argument("--sha", required=True)
    status.add_argument("--token", required=True, help="the remote's CI token")
    status.add_argument("--checks", default="make check", help="the checks to run on the commit, as one string")
    return parser


def _print_outcomes(outcomes: Sequence[Outcome], record: runlog.RunRecord) -> None:
    for outcome in sorted(outcomes, key=lambda item: item.name):
        required = outcome.name in local_runner.REQUIRED or outcome.name == "sequential"
        verdict = "passed" if outcome.ok else "FAILED"
        note = "(required)" if required else "(non-blocking)"
        print(
            f"{outcome.name:<12} {verdict:<7} {runlog.format_duration(outcome.seconds):>7}  {note}  log: {outcome.log}"
        )
    duration = runlog.format_duration(record.seconds)
    print(f"run {record.run}: commit {record.commit} {record.variant} {duration} {record.result}")


def _run(args: argparse.Namespace) -> int:
    only = frozenset(args.only.split(",")) if args.only else None
    options = local_runner.RunOptions(args.variant, only, args.include_quarantined)
    outcomes, record = local_runner.run_pipeline(ROOT, options, args.runs_csv)
    _print_outcomes(outcomes, record)
    return 0 if record.result == runlog.SUCCESS else 1


def _bench(args: argparse.Namespace) -> int:
    for variant in ("sequential", "parallel"):
        for _ in range(args.runs):
            outcomes, record = local_runner.run_pipeline(ROOT, local_runner.RunOptions(variant), args.runs_csv)
            _print_outcomes(outcomes, record)
    records = runlog.read(args.runs_csv)
    print(runlog.format_comparison(runlog.summarize(records, "sequential"), runlog.summarize(records, "parallel")))
    return 0


def _lint_workflows() -> int:
    problems = 0
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        document = workflow.load(path.read_text())
        required = protection.REQUIRED_CHECKS if path.name == "ci.yml" else ()
        for finding in workflow.lint(document, required, QUARANTINE_JOBS):
            print(f"{path.name}: {finding.code} {finding.message}")
            problems += 1
    for path in sorted((ROOT / ".github" / "actions").glob("*/action.yml")):
        for finding in workflow.lint_composite(workflow.load(path.read_text())):
            print(f"{path.parent.name}/action.yml: {finding.code} {finding.message}")
            problems += 1
    print("workflows ok" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    match args.command:
        case "version":
            print(
                build_version(
                    base_version((ROOT / "pyproject.toml").read_text()), git.head_sha(ROOT), git.is_dirty(ROOT)
                )
            )
        case "build":
            artifact = builder.build_wheel(ROOT, ROOT / "dist")
            print(f"build: sha256 {artifact.sha256}  dist/{artifact.path.name}")
        case "verify":
            try:
                digest = checksum.verify(args.artifact, args.expected)
            except checksum.ChecksumMismatchError as error:
                print(f"{args.job}: sha256 MISMATCH: {error}", file=sys.stderr)
                return 1
            print(f"{args.job}: sha256 {digest}  verified")
        case "run":
            return _run(args)
        case "bench":
            return _bench(args)
        case "flaky":
            records = runlog.read(args.runs_csv)
            print(
                flaky.format_report(
                    [record for record in records if not args.variant or record.variant == args.variant]
                )
            )
        case "import-gh-runs":
            for record in ghruns.parse_gh_runs(args.json_file.read_text()):
                runlog.append(args.runs_csv, record)
        case "protection":
            payload = protection.branch_protection()
            if args.apply:
                github.apply_branch_protection(args.apply, payload)
            else:
                print(json.dumps(payload, indent=2))
        case "lint-workflows":
            return _lint_workflows()
        case "check-contract":
            problems = contract.check((ROOT / "README.md").read_text())
            print("\n".join(problems) if problems else "contract ok")
            return 1 if problems else 0
        case "gate":
            if not gate.run_checks_on_commit(args.repo, args.sha, shlex.split(args.checks)):
                print(f"gate: checks failed for {args.sha[:7]}; no status posted", file=sys.stderr)
                return 1
            gate.post_green_status(args.repo, args.remote, args.sha, args.token)
            print(f"gate: checks passed; posted green status for {args.sha[:7]}")
    return 0
