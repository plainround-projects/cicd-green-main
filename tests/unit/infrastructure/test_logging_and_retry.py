import io
import logging
import sys
from collections.abc import Iterator

import pytest

from small_service.infrastructure.logging import LogfmtFormatter, configure_logging, fields
from small_service.infrastructure.retry import retry


def format_record(message: str, **extra: object) -> str:
    record = logging.LogRecord("svc", logging.INFO, __file__, 1, message, None, None)
    record.fields = extra
    return LogfmtFormatter().format(record)


def test_a_record_becomes_one_logfmt_line_with_its_fields():
    line = format_record("job done", job_key="nightly", duration_ms=71)
    assert "level=INFO" in line
    assert 'msg="job done"' in line
    assert "job_key=nightly" in line
    assert "duration_ms=71" in line


def test_values_with_spaces_or_quotes_are_quoted():
    assert 'note="two words"' in format_record("m", note="two words")
    assert 'note="a=b"' in format_record("m", note="a=b")


def test_an_exception_is_attached_on_the_same_line():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("svc", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    line = LogfmtFormatter().format(record)
    assert "exc=" in line
    assert "\n" not in line


def test_configure_logging_writes_to_the_given_stream():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("svc").info("hello", extra=fields(a=1))
    assert "msg=hello a=1" in stream.getvalue()


def test_retry_returns_the_first_success_without_sleeping():
    sleeps: list[float] = []
    assert retry(lambda: 7, (ConnectionError,), sleep=sleeps.append) == 7
    assert sleeps == []


def test_retry_backs_off_exponentially_then_succeeds():
    attempts: Iterator[Exception | str] = iter([ConnectionError("a"), ConnectionError("b"), "ok"])
    sleeps: list[float] = []

    def operation() -> str:
        outcome = next(attempts)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert retry(operation, (ConnectionError,), base_delay_seconds=1.0, sleep=sleeps.append, jitter=lambda: 0.0) == "ok"
    assert sleeps == [1.0, 2.0]


def test_retry_raises_the_last_error_after_the_final_attempt():
    def always_fails() -> None:
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        retry(always_fails, (ConnectionError,), attempts=2, sleep=lambda seconds: None)


def test_retry_does_not_catch_other_errors():
    def wrong() -> None:
        raise KeyError("nope")

    with pytest.raises(KeyError):
        retry(wrong, (ConnectionError,), sleep=lambda seconds: None)


def test_retry_needs_at_least_one_attempt():
    with pytest.raises(ValueError, match="at least 1"):
        retry(lambda: 1, (ConnectionError,), attempts=0)
