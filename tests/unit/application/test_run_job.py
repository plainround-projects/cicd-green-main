import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from small_service.application.run_job import JobRunner
from small_service.domain.cache import TimedCache
from small_service.domain.errors import InvalidJobKeyError
from small_service.domain.jobs import Job, JobRecord
from tests.unit.fakes import FakeClock, InMemoryJobStore

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def make_runner(
    job_factory: Callable[[], Job] = lambda: Job(delay=lambda: 0.0, sleep=lambda seconds: None),
    timeout: float = 1.0,
) -> tuple[JobRunner, InMemoryJobStore, FakeClock]:
    store = InMemoryJobStore()
    clock = FakeClock()
    cache: TimedCache[str, JobRecord] = TimedCache(30, clock)
    runner = JobRunner(
        store=store,
        cache=cache,
        job_factory=job_factory,
        now=lambda: NOW,
        monotonic=clock,
        timeout_seconds=timeout,
    )
    return runner, store, clock


def test_a_first_call_runs_the_job_and_records_it():
    runner, store, _ = make_runner()
    record, from_cache = runner.run("report")
    assert (record.job_key, record.finished, from_cache) == ("report", True, False)
    assert store.records == [record]


def test_a_repeat_call_within_the_time_to_live_is_answered_from_the_cache():
    runner, store, _ = make_runner()
    first, _ = runner.run("report")
    second, from_cache = runner.run("report")
    assert from_cache is True
    assert second == first
    assert len(store.records) == 1


def test_after_the_time_to_live_the_job_runs_again():
    runner, store, clock = make_runner()
    runner.run("report")
    clock.advance(31)
    _, from_cache = runner.run("report")
    assert from_cache is False
    assert len(store.records) == 2


def test_a_job_that_outlasts_the_timeout_is_recorded_as_unfinished():
    release = threading.Event()

    def block(seconds: float) -> None:
        release.wait()

    runner, _, _ = make_runner(job_factory=lambda: Job(delay=lambda: 1.0, sleep=block), timeout=0.01)
    record, _ = runner.run("slow")
    release.set()
    assert record.finished is False


def test_an_invalid_key_is_refused_before_anything_runs():
    runner, store, _ = make_runner()
    with pytest.raises(InvalidJobKeyError):
        runner.run("not valid!")
    assert store.records == []
