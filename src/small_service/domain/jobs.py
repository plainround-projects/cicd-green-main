"""A background job that takes between 50 and 112.5 ms, as the lesson's planted timing assumption needs."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from small_service.domain.errors import InvalidJobKeyError, JobNotStartedError

MIN_JOB_SECONDS: Final = 0.05
MAX_JOB_SECONDS: Final = 0.1125
_KEY_CHARACTERS: Final = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def validate_job_key(key: str) -> str:
    """Return `key` unchanged when it is 1 to 64 characters from letters, digits, dot, dash and underscore."""
    if not 1 <= len(key) <= 64 or not set(key) <= _KEY_CHARACTERS:
        raise InvalidJobKeyError(f"job key must be 1-64 characters of letters, digits, '.', '-' or '_', got {key!r}")
    return key


def lesson_delay() -> float:
    """A random duration between 50 and 112.5 ms: the job's work."""
    return random.uniform(MIN_JOB_SECONDS, MAX_JOB_SECONDS)  # noqa: S311 - simulated work time, not a secret


@dataclass(frozen=True, slots=True)
class JobRecord:
    """What one job run left behind: how long it took and whether it finished inside the wait."""

    job_key: str
    recorded_at: datetime
    duration_ms: int
    finished: bool


class Job:
    """Runs `sleep(delay())` on a thread. `done` is set when the work ends; `wait` blocks until then."""

    def __init__(
        self,
        delay: Callable[[], float] = lesson_delay,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """`delay` picks the duration of the work and `sleep` performs it; tests replace both."""
        self._delay = delay
        self._sleep = sleep
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def done(self) -> bool:
        """True once the work has ended."""
        return self._finished.is_set()

    def start(self) -> None:
        """Begin the work on a background thread."""

        def work() -> None:
            self._sleep(self._delay())
            self._finished.set()

        self._thread = threading.Thread(target=work, name="job", daemon=True)
        self._thread.start()

    def wait(self, timeout_seconds: float) -> bool:
        """Block until the work ends or `timeout_seconds` pass. Returns whether it ended. Waiting is the fix for the
        flaky test: it takes exactly as long as the work, never a guessed number of milliseconds."""
        if self._thread is None:
            raise JobNotStartedError("start() the job before waiting for it")
        return self._finished.wait(timeout_seconds)
