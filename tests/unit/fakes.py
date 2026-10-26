"""In-memory stand-ins for the ports, shared by the unit tests."""

from __future__ import annotations

from small_service.domain.jobs import JobRecord


class InMemoryJobStore:
    """A `JobStore` that keeps records in a list and can be told to fail."""

    def __init__(self, reachable: bool = True) -> None:
        self.records: list[JobRecord] = []
        self.reachable = reachable

    def save(self, record: JobRecord) -> None:
        self.records.append(record)

    def recent(self, limit: int) -> list[JobRecord]:
        return list(reversed(self.records))[:limit]

    def ping(self) -> None:
        if not self.reachable:
            raise ConnectionError("store is down")


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
