"""`small-service`: run a job, read the history, check health, smoke-test an installed build."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib import metadata

from small_service.application.queries import is_healthy, recent_runs
from small_service.application.run_job import JobRunner
from small_service.domain.cache import TimedCache
from small_service.domain.errors import DomainError
from small_service.domain.jobs import Job, JobRecord
from small_service.infrastructure.logging import configure_logging, fields
from small_service.infrastructure.postgres_store import PostgresJobStore
from small_service.infrastructure.settings import ConfigurationError, Settings

_log = logging.getLogger("small_service")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """The argument parser; exposed so tests can drive it."""
    parser = argparse.ArgumentParser(prog="small-service", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-job", help="run one job and record it")
    run.add_argument("key", help="job key: 1-64 characters of letters, digits, '.', '-', '_'")
    history = commands.add_parser("history", help="print the newest recorded runs")
    history.add_argument("--limit", type=int, default=5)
    commands.add_parser("health", help="exit 0 when the database answers")
    commands.add_parser("smoke", help="run a job twice (the second from the cache), read it back, print the version")
    commands.add_parser("version", help="print the installed version")
    return parser


def installed_version() -> str:
    """The version of the installed distribution: `0.1.0+g<commit>` for a pipeline build."""
    return metadata.version("cicd-green-main")


def _runner(settings: Settings) -> tuple[JobRunner, PostgresJobStore]:
    store = PostgresJobStore(settings.dsn)
    cache: TimedCache[str, JobRecord] = TimedCache(settings.cache_ttl_seconds, time.monotonic)
    runner = JobRunner(
        store=store,
        cache=cache,
        job_factory=Job,
        now=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        timeout_seconds=settings.job_timeout_seconds,
    )
    return runner, store


def _print_record(record: JobRecord, from_cache: bool) -> None:
    source = "cache" if from_cache else "run"
    print(f"{record.job_key}: finished={record.finished} duration_ms={record.duration_ms} source={source}")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the exit code instead of exiting, so tests can call it."""
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(installed_version())
        return EXIT_OK
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return EXIT_USAGE
    configure_logging(settings.log_level)
    runner, store = _runner(settings)
    try:
        return _dispatch(args, runner, store)
    except DomainError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except Exception:
        _log.exception("command failed", extra=fields(command=args.command))
        return EXIT_FAILED


def _dispatch(args: argparse.Namespace, runner: JobRunner, store: PostgresJobStore) -> int:
    if args.command == "health":
        healthy = is_healthy(store)
        print("ok" if healthy else "database unreachable")
        return EXIT_OK if healthy else EXIT_FAILED
    if args.command == "run-job":
        _print_record(*runner.run(args.key))
        return EXIT_OK
    if args.command == "history":
        for record in recent_runs(store, args.limit):
            stamp = f"{record.recorded_at:%Y-%m-%d %H:%M:%S}"
            print(f"{record.job_key}: finished={record.finished} duration_ms={record.duration_ms} at={stamp}")
        return EXIT_OK
    return _smoke(runner, store)


def _smoke(runner: JobRunner, store: PostgresJobStore) -> int:
    key = f"smoke-{int(time.time())}"
    first, first_cached = runner.run(key)
    _, second_cached = runner.run(key)
    stored = [record.job_key for record in recent_runs(store, 20)]
    ok = first.finished and not first_cached and second_cached and stored.count(key) == 1
    summary = f"first_cached={first_cached} second_cached={second_cached} stored={stored.count(key)}"
    print(f"version={installed_version()} {summary}")
    return EXIT_OK if ok else EXIT_FAILED
