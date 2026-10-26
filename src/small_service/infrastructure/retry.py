"""Retry with exponential backoff and jitter, for calls that cross the network."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from small_service.infrastructure.logging import fields

_log = logging.getLogger(__name__)


def retry[T](
    operation: Callable[[], T],
    retriable: tuple[type[Exception], ...],
    attempts: int = 4,
    base_delay_seconds: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Call `operation`; on a `retriable` error wait `base * 2**attempt` plus up to 50% jitter and try again.

    The last error is raised after `attempts` tries.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be at least 1, got {attempts}")
    for attempt in range(attempts):
        try:
            return operation()
        except retriable as error:
            if attempt == attempts - 1:
                raise
            delay = base_delay_seconds * 2**attempt * (1 + jitter() / 2)
            _log.warning(
                "retrying", extra=fields(attempt=attempt + 1, delay_seconds=round(delay, 3), error=repr(error))
            )
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover - the loop always returns or raises
