"""Run a job once per key within the cache's time to live and record the outcome."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from small_service.application.ports import JobStore
from small_service.domain.cache import TimedCache
from small_service.domain.jobs import Job, JobRecord, validate_job_key


class JobRunner:
    """Starts a `Job`, waits for it, stores a `JobRecord`, and caches it so a repeat call is answered from memory."""

    def __init__(
        self,
        store: JobStore,
        cache: TimedCache[str, JobRecord],
        job_factory: Callable[[], Job],
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
        timeout_seconds: float,
    ) -> None:
        """Every collaborator is passed in; nothing here reads the clock or the environment."""
        self._store = store
        self._cache = cache
        self._job_factory = job_factory
        self._now = now
        self._monotonic = monotonic
        self._timeout_seconds = timeout_seconds

    def run(self, job_key: str) -> tuple[JobRecord, bool]:
        """Return `(record, from_cache)`. A cache hit does not run or store anything."""
        key = validate_job_key(job_key)
        cached = self._cache.get(key)
        if cached is not None:
            return cached, True
        job = self._job_factory()
        started = self._monotonic()
        job.start()
        finished = job.wait(self._timeout_seconds)
        record = JobRecord(
            job_key=key,
            recorded_at=self._now(),
            duration_ms=round((self._monotonic() - started) * 1000),
            finished=finished,
        )
        self._store.save(record)
        self._cache.put(key, record)
        return record, False
