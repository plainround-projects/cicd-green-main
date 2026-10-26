"""Run commands as pipeline jobs: sequential steps, a log file per job, jobs in parallel."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Command:
    """One step: the program and its arguments, plus environment variables added to the current environment."""

    argv: tuple[str, ...]
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Job:
    """A named list of steps that run one after another and stop at the first failure."""

    name: str
    steps: tuple[Command, ...]


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a job ended and how long it took."""

    name: str
    ok: bool
    seconds: float
    log: Path


def run_job(job: Job, cwd: Path, log_dir: Path) -> Outcome:
    """Run the steps, writing each command and its output to `<log_dir>/<job>.log`."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{job.name}.log"
    started = time.monotonic()
    ok = True
    with log.open("w") as handle:
        for step in job.steps:
            handle.write(f"$ {' '.join(step.argv)}\n")
            handle.flush()
            result = subprocess.run(  # noqa: S603 - argv is built by this program, never through a shell
                step.argv,
                cwd=cwd,
                env={**os.environ, **step.env},
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                handle.write(f"\n[exit status {result.returncode}]\n")
                ok = False
                break
    return Outcome(job.name, ok, time.monotonic() - started, log)


def submit(pool: ThreadPoolExecutor, job: Job, cwd: Path, log_dir: Path) -> Future[Outcome]:
    """Start a job on the pool."""
    return pool.submit(run_job, job, cwd, log_dir)


def run_output(argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None) -> str:
    """Run one command and return its standard output; a non-zero exit raises `CalledProcessError`."""
    result = subprocess.run(  # noqa: S603
        list(argv), cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=True
    )
    return result.stdout
