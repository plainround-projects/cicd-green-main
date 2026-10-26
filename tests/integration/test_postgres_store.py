from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from small_service.domain.jobs import JobRecord
from small_service.infrastructure.postgres_store import PostgresJobStore

WHEN = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_the_database_answers_a_ping(store):
    store.ping()


def test_a_saved_run_is_read_back_unchanged(store, key_prefix):
    record = JobRecord(f"{key_prefix}-a", WHEN, 71, True)
    store.save(record)
    assert record in store.recent(50)


def test_recent_returns_the_newest_first(store, key_prefix):
    older = JobRecord(f"{key_prefix}-old", WHEN, 60, True)
    newer = JobRecord(f"{key_prefix}-new", WHEN + timedelta(minutes=1), 90, False)
    store.save(older)
    store.save(newer)
    mine = [record for record in store.recent(50) if record.job_key.startswith(key_prefix)]
    assert mine == [newer, older]


def test_the_schema_refuses_a_key_the_domain_would_refuse(store):
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save(JobRecord("not valid!", WHEN, 1, True))


def test_the_schema_refuses_a_negative_duration(store, key_prefix):
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save(JobRecord(f"{key_prefix}-neg", WHEN, -1, True))


def test_an_unreachable_database_is_retried_and_then_raises():
    unreachable = PostgresJobStore("postgresql://x:y@127.0.0.1:1/none")
    with pytest.raises(psycopg.OperationalError):
        unreachable.ping()
