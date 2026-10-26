"""Integration tests need the PostgreSQL service from docker-compose.yml: `make up` first."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

from small_service.infrastructure.postgres_store import PostgresJobStore
from small_service.infrastructure.settings import Settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def store(settings: Settings) -> PostgresJobStore:
    return PostgresJobStore(settings.dsn)


@pytest.fixture
def key_prefix(settings: Settings) -> Iterator[str]:
    """A unique job-key prefix per test, and its rows deleted afterwards, so tests never see each other's data."""
    prefix = f"it-{uuid.uuid4().hex[:8]}"
    yield prefix
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("DELETE FROM job_runs WHERE job_key LIKE %s", (f"{prefix}%",))


@pytest.fixture(scope="session")
def running_against_the_artifact() -> bool:
    return os.environ.get("ARTIFACT_TESTS") == "1"
