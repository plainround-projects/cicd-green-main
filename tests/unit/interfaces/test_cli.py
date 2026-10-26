from datetime import UTC, datetime

import pytest

from small_service.application.run_job import JobRunner
from small_service.domain.cache import TimedCache
from small_service.domain.jobs import Job, JobRecord
from small_service.interfaces import cli
from tests.unit.fakes import FakeClock, InMemoryJobStore


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> InMemoryJobStore:
    """Replace the PostgreSQL wiring with an in-memory store and an instant job."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    fake = InMemoryJobStore()
    clock = FakeClock()
    cache: TimedCache[str, JobRecord] = TimedCache(30, clock)
    runner = JobRunner(
        fake,
        cache,
        lambda: Job(delay=lambda: 0.0, sleep=lambda seconds: None),
        lambda: datetime(2026, 9, 1, tzinfo=UTC),
        clock,
        1.0,
    )
    monkeypatch.setattr(cli, "_runner", lambda settings: (runner, fake))
    return fake


def test_version_prints_the_installed_version_without_needing_a_database(capsys, monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == cli.installed_version()


def test_a_missing_password_exits_with_the_usage_code(capsys, monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    assert cli.main(["health"]) == cli.EXIT_USAGE
    assert "POSTGRES_PASSWORD" in capsys.readouterr().err


def test_run_job_prints_the_record_and_stores_it(store, capsys):
    assert cli.main(["run-job", "nightly"]) == 0
    assert "nightly: finished=True" in capsys.readouterr().out
    assert [record.job_key for record in store.records] == ["nightly"]


def test_an_invalid_key_exits_with_the_usage_code(store, capsys):
    assert cli.main(["run-job", "bad key"]) == cli.EXIT_USAGE
    assert "job key" in capsys.readouterr().err


def test_history_lists_the_newest_runs(store, capsys):
    cli.main(["run-job", "first"])
    cli.main(["run-job", "second"])
    capsys.readouterr()
    assert cli.main(["history", "--limit", "1"]) == 0
    assert capsys.readouterr().out.startswith("second:")


def test_health_exits_zero_when_the_store_answers(store, capsys):
    assert cli.main(["health"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_health_exits_one_when_the_store_is_down(store, capsys):
    store.reachable = False
    assert cli.main(["health"]) == cli.EXIT_FAILED
    assert "unreachable" in capsys.readouterr().out


def test_smoke_runs_twice_and_proves_the_second_came_from_the_cache(store, capsys):
    assert cli.main(["smoke"]) == 0
    assert "first_cached=False second_cached=True stored=1" in capsys.readouterr().out


def test_an_unexpected_error_exits_with_the_failure_code(store, monkeypatch):
    monkeypatch.setattr(store, "save", lambda record: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert cli.main(["run-job", "x"]) == cli.EXIT_FAILED
