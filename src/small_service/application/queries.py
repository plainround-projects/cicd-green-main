"""Read-side use cases."""

from __future__ import annotations

from small_service.application.ports import JobStore
from small_service.domain.jobs import JobRecord


def recent_runs(store: JobStore, limit: int) -> list[JobRecord]:
    """The newest `limit` runs, newest first."""
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    return store.recent(limit)


def is_healthy(store: JobStore) -> bool:
    """True when the store answers; the health command turns this into an exit code."""
    try:
        store.ping()
    except Exception:  # any failure of the store means "not healthy"; the caller logs the cause
        return False
    return True
