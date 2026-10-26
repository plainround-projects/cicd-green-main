"""What the use cases need from the outside world."""

from __future__ import annotations

from typing import Protocol

from small_service.domain.jobs import JobRecord


class JobStore(Protocol):
    """Where job runs are recorded."""

    def save(self, record: JobRecord) -> None:
        """Persist one run."""

    def recent(self, limit: int) -> list[JobRecord]:
        """Return the newest runs first, at most `limit`."""

    def ping(self) -> None:
        """Raise when the store cannot be reached."""
