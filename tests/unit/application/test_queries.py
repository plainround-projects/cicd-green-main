from datetime import UTC, datetime

import pytest

from small_service.application.queries import is_healthy, recent_runs
from small_service.domain.jobs import JobRecord
from tests.unit.fakes import InMemoryJobStore

WHEN = datetime(2026, 9, 1, tzinfo=UTC)


def test_recent_runs_returns_the_newest_first_up_to_the_limit():
    store = InMemoryJobStore()
    for index in range(4):
        store.save(JobRecord(f"job-{index}", WHEN, 60, True))
    assert [record.job_key for record in recent_runs(store, 2)] == ["job-3", "job-2"]


def test_a_limit_below_one_is_refused():
    with pytest.raises(ValueError, match="at least 1"):
        recent_runs(InMemoryJobStore(), 0)


def test_a_reachable_store_is_healthy():
    assert is_healthy(InMemoryJobStore()) is True


def test_an_unreachable_store_is_not_healthy():
    assert is_healthy(InMemoryJobStore(reachable=False)) is False
