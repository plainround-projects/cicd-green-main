"""A small time-limited cache. The clock is injected, so expiry is tested without sleeping."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from small_service.domain.errors import InvalidTtlError


@dataclass(frozen=True, slots=True)
class _Entry[V]:
    value: V
    expires_at: float


class TimedCache[K, V]:
    """Maps keys to values that expire `ttl_seconds` after they were stored. Safe to share between threads."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float]) -> None:
        """Create an empty cache. `clock` returns seconds on any monotonic scale."""
        if ttl_seconds <= 0:
            raise InvalidTtlError(f"ttl_seconds must be positive, got {ttl_seconds}")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[K, _Entry[V]] = {}
        self._lock = threading.Lock()

    def put(self, key: K, value: V) -> None:
        """Store `value`, replacing any earlier value and restarting its time to live."""
        with self._lock:
            self._entries[key] = _Entry(value, self._clock() + self._ttl_seconds)

    def get(self, key: K) -> V | None:
        """Return the stored value, or None when the key is missing or has expired (an expired entry is dropped)."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None
            return entry.value

    def purge(self) -> int:
        """Drop every expired entry and return how many were dropped."""
        with self._lock:
            now = self._clock()
            expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
            for key in expired:
                del self._entries[key]
            return len(expired)

    def __len__(self) -> int:
        """Number of stored entries, expired ones included until they are read or purged."""
        with self._lock:
            return len(self._entries)
