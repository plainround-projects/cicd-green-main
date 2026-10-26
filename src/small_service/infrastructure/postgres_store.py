"""The `JobStore` port on PostgreSQL (sql/001_schema.sql creates the table)."""

from __future__ import annotations

from typing import Any

import psycopg

from small_service.domain.jobs import JobRecord
from small_service.infrastructure.retry import retry

_CONNECT_TIMEOUT_SECONDS = 5


class PostgresJobStore:
    """Opens a short-lived connection per call and retries connection failures with backoff."""

    def __init__(self, dsn: str) -> None:
        """`dsn` is a libpq connection URI."""
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
        return retry(
            lambda: psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS),
            retriable=(psycopg.OperationalError,),
        )

    def save(self, record: JobRecord) -> None:
        """Insert one row; the transaction commits when the connection block ends."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES (%s, %s, %s, %s)",
                (record.job_key, record.recorded_at, record.duration_ms, record.finished),
            )

    def recent(self, limit: int) -> list[JobRecord]:
        """The newest rows first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_key, recorded_at, duration_ms, finished FROM job_runs "
                "ORDER BY recorded_at DESC, id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [JobRecord(key, recorded_at, duration, finished) for key, recorded_at, duration, finished in rows]

    def ping(self) -> None:
        """Run `SELECT 1`; any error propagates."""
        with self._connect() as connection:
            connection.execute("SELECT 1")
