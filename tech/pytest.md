# pytest and coverage

## What it is

A **test** is a small program that checks that another program does what it should. You give the code some input, run it, and **assert** (state) what the result must be. If the statement is false the test **fails**, and you learn about the mistake before a user does.

**pytest** is the tool that finds, runs and reports tests in Python. It looks for files whose names start with `test_` and, in them, functions whose names start with `test_`. It runs each one. A test **passes** if the function ends without an error and **fails** if an `assert` is false or any other error escapes. This repository pins pytest 9.1.1, pytest-cov 7.1.0 and coverage 7.17.0.

**Coverage** is a measurement of how much of the program's code the tests actually ran. If a line never ran during the tests, nothing proves it works. The `coverage` library records which lines ran; `pytest-cov` connects it to pytest.

The vocabulary used below:

- **`assert condition`** fails the test when the condition is false. pytest rewrites asserts so that a failure shows both sides of a comparison.
- **`pytest.raises(SomeError)`** is a `with` block that passes only if the code inside raises that error.
- **A fixture** is a function marked `@pytest.fixture` that prepares something a test needs (a temporary folder, a fake store). A test asks for it simply by naming it as a parameter. Code after a `yield` in a fixture runs after the test as clean-up.
- **`@pytest.mark.parametrize("x", [a, b, c])`** runs the same test once for each value.
- **A marker** (`@pytest.mark.name`) labels a test so you can select or skip groups: `-m "not flaky_quarantine"`.
- **`tmp_path`** is a built-in fixture: a fresh empty temporary folder for each test.
- **`monkeypatch`** is a built-in fixture that temporarily replaces a variable, an attribute or an environment variable and puts it back afterwards.
- **`capsys`** and **`capfd`** capture what the code prints to the screen so the test can read it.
- **A fake** is a simple stand-in object used instead of the real thing (a clock the test moves by hand, a store kept in a list). Fakes make tests fast and exact.
- **A unit test** checks one small piece alone. An **integration test** checks pieces working together with something real (here a real database). An **end-to-end (e2e) test** runs a whole scenario.

## Why this repository uses it

The pipeline's job is to run checks and decide whether `main` is safe to release. The checks are these tests. They are arranged in four groups, so each can run where it can run:

| Folder | Needs | What it proves |
|---|---|---|
| `tests/unit/` | nothing | The service's rules, its use cases (with fake collaborators), its settings, logging, retry and command line. |
| `tests/pipeline/` | nothing | The pipeline's own logic: versions, checksums, run log, flaky-test maths, workflow lint, branch-protection payload, README contract, the builder and local runner. |
| `tests/integration/` | PostgreSQL (`make up`) | The real database adapter, and the *installed wheel*. |
| `tests/e2e/` | `git`, `sh` | The "protected main" scenario in a throw-away Git repository, and the change-detection script. |

A coverage floor of 95 percent on the pure parts keeps the important logic tested.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 59 to 75 | `[tool.pytest.ini_options]` and `[tool.coverage.*]`. |
| `Makefile` | `test`, `test-domain`, `quarantine`, `test-integration`, `test-artifact`, `test-e2e`. |
| `tests/` | 17 files, about 120 tests. |
| `.github/workflows/ci.yml` | `unit`, `integration` and `quarantine` jobs call the `make` targets above. |

## How it works underneath

pytest **collects**: it walks the folders you name, imports each `test_*.py` file, and gathers `test_*` functions. It then runs each, one after another, in its own call, catching any error. For asserts it rewrites the code at import time so a failed `assert a == b` shows the values of `a` and `b`. Fixtures are resolved by name: when a test function has a parameter named `store`, pytest finds a fixture called `store`, runs it, and passes its result in. A fixture's **scope** controls how long its value lives (`scope="session"` means once for the whole run; the default is once per test).

pytest can write a **JUnit XML** report (`--junitxml=reports/unit.xml`), a standard format other tools understand; this project reads it to find which test failed ([junit-xml.md](junit-xml.md)).

Coverage works by tracing the running program and noting every line (and, with `branch = true`, every outcome of every `if`). `coverage report --fail-under=95` exits non-zero if the share is below 95 percent.

## Walkthrough of this repository's use

### The configuration (`pyproject.toml` lines 59 to 75)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs the PostgreSQL service from docker-compose.yml (make up)",
    "e2e: runs the pipeline's own scenarios (git gate, local runner) end to end",
    "flaky_quarantine: a test with a known timing flake; excluded from the required job, run by the non-blocking quarantine job",
]

[tool.coverage.run]
source = ["small_service", "pipeline"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = false
```

- **Line 60**: `testpaths = ["tests"]`: run only what is under `tests/` unless told otherwise.
- **Line 61**: `pythonpath = ["."]`: add the repository's root folder to Python's module search list, so `from tests.unit.fakes import FakeClock` works.
- **Line 62**: `addopts = "-ra --strict-markers"`: options added to every run. `-ra` prints a short summary of every test that did not simply pass (skipped, failed, errors). `--strict-markers` turns a misspelled marker into an error rather than silently selecting nothing.
- **Lines 63 to 67**: `markers` declares the three labels in use: `integration` (needs the database), `e2e` (runs the pipeline's own scenarios end to end) and `flaky_quarantine` (a test with a known timing flake, excluded from the required job and run by the non-blocking job).
- **Lines 69 to 71**: `[tool.coverage.run]`: measure the packages `small_service` and `pipeline`, with branch coverage.
- **Lines 73 to 75**: `[tool.coverage.report]`: `show_missing = true` lists the line numbers that no test ran; `skip_covered = false` keeps fully covered files in the table.

### The Make targets that run tests

Explained in [make.md](make.md): `make test` (unit and pipeline tests with a JUnit report, coverage and a 95 percent floor on `domain`, `application` and `pipeline/core`), `make test-domain` (just `tests/unit/domain`, repeatable many times), `make quarantine` (only the quarantined test), `make test-integration`, `make test-artifact` and `make test-e2e`.

### `tests/conftest.py`

```python
"""Shared fixtures."""
```

A one-line docstring: shared fixtures would go here. pytest loads any file called `conftest.py` automatically and makes its fixtures available to the tests below that folder.

### `tests/unit/fakes.py`: stand-ins shared by the unit tests

```python
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
```

- **`InMemoryJobStore`** (lines 8 to 23) implements the same methods as the real `JobStore` ([python.md](python.md): `ports.py`) but keeps records in a list. `reachable=False` makes `ping` raise `ConnectionError("store is down")`, so a test can simulate an outage. `recent` returns `list(reversed(self.records))[:limit]`: the list in reverse (newest first) cut to `limit`.
- **`FakeClock`** (lines 26 to 36) is a clock the test controls. `__call__` makes the object callable like a function (`clock()` returns `self.now`). `advance(seconds)` moves time forward. `start=1000.0` is an arbitrary starting second.

### `tests/unit/domain/test_cache.py`: the time-limited cache

```python
import threading

import pytest

from small_service.domain.cache import TimedCache
from small_service.domain.errors import InvalidTtlError
from tests.unit.fakes import FakeClock


def make_cache(ttl: float = 10.0) -> tuple[TimedCache[str, int], FakeClock]:
    clock = FakeClock()
    return TimedCache(ttl, clock), clock


def test_a_stored_value_is_returned_before_it_expires():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(9.9)
    assert cache.get("a") == 1


def test_a_value_expires_exactly_at_its_time_to_live():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(10)
    assert cache.get("a") is None


def test_reading_an_expired_value_drops_it():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(11)
    cache.get("a")
    assert len(cache) == 0


def test_a_missing_key_returns_none():
    cache, _ = make_cache()
    assert cache.get("nothing") is None


def test_putting_again_restarts_the_time_to_live():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(8)
    cache.put("a", 2)
    clock.advance(8)
    assert cache.get("a") == 2
```

- **Lines 1 to 7**: imports, including `threading` and `pytest`. **Lines 10 to 12**: `make_cache` is a helper that returns a cache and the fake clock that drives it; the test then moves time with `clock.advance`. No test sleeps.
- **`test_a_stored_value_is_returned_before_it_expires`** (15 to 19): store `"a"` with a 10-second lifetime, advance 9.9 seconds, expect the value.
- **`test_a_value_expires_exactly_at_its_time_to_live`** (22 to 26): advance exactly 10 seconds; the value is gone (`is None`). This pins the boundary: the lifetime is "until but not including" the deadline.
- **`test_reading_an_expired_value_drops_it`** (29 to 34): after 11 seconds, `get` returns nothing and the entry is deleted: `len(cache) == 0`.
- **`test_a_missing_key_returns_none`** (37 to 39): `cache, _ = make_cache()` ignores the clock with `_`.
- **`test_putting_again_restarts_the_time_to_live`** (42 to 48): store, advance 8, store again, advance 8 more (16 seconds after the first store but only 8 after the second); the second value is still there.

```python
def test_purge_drops_only_expired_entries_and_counts_them():
    cache, clock = make_cache()
    cache.put("old", 1)
    clock.advance(6)
    cache.put("new", 2)
    clock.advance(5)
    assert cache.purge() == 1
    assert cache.get("new") == 2


@pytest.mark.parametrize("ttl", [0, -1, -0.5])
def test_a_non_positive_time_to_live_is_refused(ttl):
    with pytest.raises(InvalidTtlError):
        TimedCache(ttl, FakeClock())


def test_concurrent_puts_do_not_lose_entries():
    cache, _ = make_cache()
    threads = [threading.Thread(target=cache.put, args=(f"key-{index}", index)) for index in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(cache) == 50
```

- **`test_purge_drops_only_expired_entries_and_counts_them`** (51 to 58): `old` is stored, 6 seconds pass, `new` is stored, 5 more pass: `old` is 11 seconds old (expired) and `new` is 5 seconds old. `purge()` must return 1 and `new` must survive.
- **`test_a_non_positive_time_to_live_is_refused`** (61 to 64): `@pytest.mark.parametrize("ttl", [0, -1, -0.5])` runs the test three times. Each time `with pytest.raises(InvalidTtlError): TimedCache(ttl, FakeClock())` must raise.
- **`test_concurrent_puts_do_not_lose_entries`** (67 to 74): starts 50 threads that each store a different key, waits for all of them (`thread.join()` blocks until a thread has finished) and expects 50 entries. If the cache did not lock its dictionary this could fail.

### `tests/unit/domain/test_jobs.py` and `test_jobs_timing.py`: the job

```python
import pytest

from small_service.domain.errors import InvalidJobKeyError, JobNotStartedError
from small_service.domain.jobs import MAX_JOB_SECONDS, MIN_JOB_SECONDS, Job, lesson_delay, validate_job_key


def instant_job() -> Job:
    return Job(delay=lambda: 0.0, sleep=lambda seconds: None)


def test_wait_returns_true_once_the_work_has_ended():
    job = instant_job()
    job.start()
    assert job.wait(timeout_seconds=1) is True
    assert job.done


def test_wait_returns_false_when_the_work_outlasts_the_timeout():
    job = Job(delay=lambda: 0.5)
    job.start()
    assert job.wait(timeout_seconds=0.01) is False
    assert not job.done


def test_waiting_before_starting_is_an_error():
    with pytest.raises(JobNotStartedError):
        instant_job().wait(1)


def test_the_planted_delay_is_between_50_and_112_ms():
    delays = [lesson_delay() for _ in range(500)]
    assert min(delays) >= MIN_JOB_SECONDS
    assert max(delays) <= MAX_JOB_SECONDS

```

- **Lines 7 to 8**: `instant_job()` builds a `Job` whose delay is 0 and whose `sleep` does nothing (`lambda seconds: None`).
- **`test_wait_returns_true_once_the_work_has_ended`** (11 to 15): start, wait up to 1 second, expect `True` (`is True`) and `job.done`.
- **`test_wait_returns_false_when_the_work_outlasts_the_timeout`** (18 to 22): a job whose delay is 0.5 seconds (and which really sleeps) is waited on for 0.01 seconds: `False`, and `not job.done`.
- **`test_waiting_before_starting_is_an_error`** (25 to 27): `JobNotStartedError`.
- **`test_the_planted_delay_is_between_50_and_112_ms`** (30 to 33): draw 500 random delays and check that the smallest and largest are inside the limits.

```python
def test_the_fix_for_the_flaky_test_waits_for_the_job_instead_of_sleeping_a_guess():
    # The lesson's flaky test sleeps 100 ms and then asserts. Waiting is correct for any delay the job picks.
    for _ in range(25):
        job = Job()
        job.start()
        assert job.wait(timeout_seconds=1)


@pytest.mark.parametrize("key", ["nightly-report", "a", "x" * 64, "job_1.v2-final"])
def test_valid_job_keys_are_returned_unchanged(key):
    assert validate_job_key(key) == key


@pytest.mark.parametrize("key", ["", "x" * 65, "has space", "semi;colon", "path/slash", "ünïcode", "quote'"])
def test_invalid_job_keys_are_refused(key):
    with pytest.raises(InvalidJobKeyError):
        validate_job_key(key)
```

- **`test_the_fix_for_the_flaky_test_waits_for_the_job_instead_of_sleeping_a_guess`** (36 to 41): the corrected version of the flaky test. It runs 25 real jobs and *waits* for each to finish (`job.wait(timeout_seconds=1)`), which is correct for any delay the job picks.
- **`test_valid_job_keys_are_returned_unchanged`** (44 to 46) and **`test_invalid_job_keys_are_refused`** (49 to 52) are `parametrize` tests: four valid keys including the boundaries `"a"` (1 character) and `"x" * 64` (64 characters), and seven invalid ones: empty, 65 characters, a space, a semicolon, a slash, a non-ASCII letter and a quote.

```python
"""The lesson's planted flaky test, kept as it was written and quarantined.

The job takes a random 50 to 112.5 ms and the test sleeps a fixed 100 ms, so it fails about one run in five (12.5 ms
of the 62.5 ms range). Its marker keeps it out of the required `unit` job; the non-blocking `quarantine` job runs it.
The fixed version of the same check is `test_the_fix_for_the_flaky_test_waits_for_the_job_instead_of_sleeping_a_guess`
in test_jobs.py. See docs/issues/0001-flaky-job-timing-test.md.
"""

import time

import pytest

from small_service.domain.jobs import Job


@pytest.mark.flaky_quarantine
def test_job_finishes_in_time():
    job = Job()
    job.start()
    time.sleep(0.1)  # a timing assumption: the job is usually, not always, finished by now
    assert job.done
```

- This file is the **planted flaky test**, kept as it was written. The docstring explains: the job takes a random 50 to 112.5 ms and the test sleeps a fixed 100 ms, so it fails when the job is slower than 100 ms, about one run in five (12.5 ms of a 62.5 ms range).
- **Line 16**: `@pytest.mark.flaky_quarantine` labels the test. The required `unit` job runs with `-m "not flaky_quarantine"`, so it is excluded there; the non-blocking `quarantine` job selects it.
- **Lines 17 to 21**: make a `Job`, `start()` it, `time.sleep(0.1)` (a guess) and `assert job.done`. The comment on line 20 is the lesson: a timing assumption.

### `tests/unit/application/`: the use cases

```python
from datetime import UTC, datetime

import pytest

from small_service.application.queries import is_healthy, recent_runs
from small_service.domain.jobs import JobRecord
from tests.unit.fakes import InMemoryJobStore

WHEN = datetime(2026, 9, 1, tzinfo=UTC)


def test_recent_runs_returns_the_newest_first_up_to_the_limit():
    store = InMemoryJobStore()
    for index in range(4):
        store.save(JobRecord(f"job-{index}", WHEN, 60, True))
    assert [record.job_key for record in recent_runs(store, 2)] == ["job-3", "job-2"]


def test_a_limit_below_one_is_refused():
    with pytest.raises(ValueError, match="at least 1"):
        recent_runs(InMemoryJobStore(), 0)


def test_a_reachable_store_is_healthy():
    assert is_healthy(InMemoryJobStore()) is True


def test_an_unreachable_store_is_not_healthy():
    assert is_healthy(InMemoryJobStore(reachable=False)) is False
```

- **Line 9**: `WHEN = datetime(2026, 9, 1, tzinfo=UTC)` is a fixed moment.
- **`test_recent_runs_returns_the_newest_first_up_to_the_limit`** (12 to 16): save four records named `job-0` to `job-3`; asking for 2 must give `["job-3", "job-2"]`.
- **`test_a_limit_below_one_is_refused`** (19 to 21): `pytest.raises(ValueError, match="at least 1")`; `match` checks the error message against a pattern.
- **Lines 24 to 29**: a reachable fake store is healthy (`is True`); `InMemoryJobStore(reachable=False)` is not (`is False`).

```python
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from small_service.application.run_job import JobRunner
from small_service.domain.cache import TimedCache
from small_service.domain.errors import InvalidJobKeyError
from small_service.domain.jobs import Job, JobRecord
from tests.unit.fakes import FakeClock, InMemoryJobStore

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def make_runner(
    job_factory: Callable[[], Job] = lambda: Job(delay=lambda: 0.0, sleep=lambda seconds: None),
    timeout: float = 1.0,
) -> tuple[JobRunner, InMemoryJobStore, FakeClock]:
    store = InMemoryJobStore()
    clock = FakeClock()
    cache: TimedCache[str, JobRecord] = TimedCache(30, clock)
    runner = JobRunner(
        store=store,
        cache=cache,
        job_factory=job_factory,
        now=lambda: NOW,
        monotonic=clock,
        timeout_seconds=timeout,
    )
    return runner, store, clock


def test_a_first_call_runs_the_job_and_records_it():
    runner, store, _ = make_runner()
    record, from_cache = runner.run("report")
    assert (record.job_key, record.finished, from_cache) == ("report", True, False)
    assert store.records == [record]


def test_a_repeat_call_within_the_time_to_live_is_answered_from_the_cache():
    runner, store, _ = make_runner()
    first, _ = runner.run("report")
    second, from_cache = runner.run("report")
    assert from_cache is True
    assert second == first
    assert len(store.records) == 1

```

- **Lines 16 to 31**: `make_runner` assembles a `JobRunner` from fakes: an in-memory store, a fake clock used for both the cache and the monotonic clock, a 30-second cache lifetime, a fixed "now", and a job factory that creates instant jobs. It returns the runner, the store and the clock so tests can look inside.
- **`test_a_first_call_runs_the_job_and_records_it`** (34 to 38): the result is `("report", True, False)` (key, finished, not from cache) and the store holds that record.
- **`test_a_repeat_call_within_the_time_to_live_is_answered_from_the_cache`** (41 to 47): the second call returns the same record, flagged `from_cache is True`, and the store still has one record.

```python
def test_after_the_time_to_live_the_job_runs_again():
    runner, store, clock = make_runner()
    runner.run("report")
    clock.advance(31)
    _, from_cache = runner.run("report")
    assert from_cache is False
    assert len(store.records) == 2


def test_a_job_that_outlasts_the_timeout_is_recorded_as_unfinished():
    release = threading.Event()

    def block(seconds: float) -> None:
        release.wait()

    runner, _, _ = make_runner(job_factory=lambda: Job(delay=lambda: 1.0, sleep=block), timeout=0.01)
    record, _ = runner.run("slow")
    release.set()
    assert record.finished is False


def test_an_invalid_key_is_refused_before_anything_runs():
    runner, store, _ = make_runner()
    with pytest.raises(InvalidJobKeyError):
        runner.run("not valid!")
    assert store.records == []
```

- **`test_after_the_time_to_live_the_job_runs_again`** (50 to 56): advance 31 seconds (past the 30-second lifetime); the next call is not from the cache and the store now has two records.
- **`test_a_job_that_outlasts_the_timeout_is_recorded_as_unfinished`** (59 to 68): a `threading.Event` called `release` and a `block` function that waits on it make a job that never finishes by itself. With a 0.01-second timeout the record is `finished is False`; `release.set()` then lets the helper thread end so the test leaves nothing running.
- **`test_an_invalid_key_is_refused_before_anything_runs`** (71 to 75): the bad key raises `InvalidJobKeyError` and `store.records == []`.

### `tests/unit/infrastructure/`: logging, retry and settings

```python
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

```

- **Lines 12 to 15**: `format_record` builds a log record by hand (`logging.LogRecord(name, level, path, line, message, args, exc_info)`), attaches the `fields` dictionary and formats it with our formatter.
- **`test_a_record_becomes_one_logfmt_line_with_its_fields`** (18 to 23): the line contains `level=INFO`, `msg="job done"` (quoted because it has a space), `job_key=nightly` and `duration_ms=71`.
- **`test_values_with_spaces_or_quotes_are_quoted`** (26 to 28): `note="two words"` and `note="a=b"`.
- **`test_an_exception_is_attached_on_the_same_line`** (31 to 38): raise and catch a `ValueError`, build a record with `sys.exc_info()` (the current error), format it: the line contains `exc=` and no newline.
- **`test_configure_logging_writes_to_the_given_stream`** (41 to 45): `io.StringIO()` is an in-memory text stream. After `configure_logging("INFO", stream)` a message appears there as `msg=hello a=1`.

```python
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
```

- **`test_retry_returns_the_first_success_without_sleeping`** (48 to 51): `sleep=sleeps.append` records each wait in a list instead of waiting; the list stays empty.
- **`test_retry_backs_off_exponentially_then_succeeds`** (54 to 65): `iter([...])` makes an iterator over two errors and then `"ok"`; `next(attempts)` takes one per call. With a base delay of 1.0 and no jitter (`jitter=lambda: 0.0`), the recorded waits are `[1.0, 2.0]`: doubling.
- **`test_retry_raises_the_last_error_after_the_final_attempt`** (68 to 73), **`test_retry_does_not_catch_other_errors`** (76 to 81), **`test_retry_needs_at_least_one_attempt`** (84 to 86).

```python
import pytest

from small_service.infrastructure.settings import ConfigurationError, Settings

BASE = {"POSTGRES_PASSWORD": "pw"}


def test_defaults_apply_when_only_the_password_is_set():
    settings = Settings.from_env(BASE)
    assert (settings.postgres_host, settings.postgres_port, settings.cache_ttl_seconds) == ("localhost", 5432, 30)


def test_the_password_has_no_default():
    with pytest.raises(ConfigurationError, match="POSTGRES_PASSWORD"):
        Settings.from_env({})


def test_the_connection_uri_escapes_special_characters():
    settings = Settings.from_env({"POSTGRES_PASSWORD": "p@ss/word", "POSTGRES_USER": "me"})
    assert settings.dsn == "postgresql://me:p%40ss%2Fword@localhost:5432/service"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("POSTGRES_PORT", "0"),
        ("POSTGRES_PORT", "70000"),
        ("POSTGRES_PORT", "5432.5"),
        ("POSTGRES_PORT", "abc"),
        ("POSTGRES_HOST", "bad host"),
        ("LOG_LEVEL", "LOUD"),
        ("CACHE_TTL_SECONDS", "-1"),
        ("JOB_TIMEOUT_SECONDS", "0"),
    ],
)
def test_an_unusable_value_names_its_variable(name, value):
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env({**BASE, name: value})


def test_the_log_level_is_case_insensitive():
    assert Settings.from_env({**BASE, "LOG_LEVEL": "debug"}).log_level == "DEBUG"
```

- **`BASE = {"POSTGRES_PASSWORD": "pw"}`**: the one required setting.
- **`test_defaults_apply_when_only_the_password_is_set`** (8 to 10): host `localhost`, port 5432, cache lifetime 30.
- **`test_the_password_has_no_default`** (13 to 15): an empty environment raises `ConfigurationError` that mentions `POSTGRES_PASSWORD`.
- **`test_the_connection_uri_escapes_special_characters`** (18 to 20): a password `p@ss/word` is written as `p%40ss%2Fword` in the connection string.
- **`test_an_unusable_value_names_its_variable`** (23 to 38): eight bad values (port 0, 70000, 5432.5 and `abc`; a host with a space; log level `LOUD`; a negative lifetime; a zero timeout). `{**BASE, name: value}` merges the base dictionary with one bad entry. The error must contain the variable's name.
- **`test_the_log_level_is_case_insensitive`** (41 to 42).

### `tests/unit/interfaces/test_cli.py`: the command line, with the database replaced

```python
from datetime import UTC, datetime

import pytest

from small_service.application.run_job import JobRunner
from small_service.domain.cache import TimedCache
from small_service.domain.jobs import Job, JobRecord
from small_service.interfaces import cli
from tests.unit.fakes import FakeClock, InMemoryJobStore


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> InMemoryJobStore:
    """Replace the PostgreSQL wiring with an in-memory store and an instant job."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    fake = InMemoryJobStore()
    clock = FakeClock()
    cache: TimedCache[str, JobRecord] = TimedCache(30, clock)
    runner = JobRunner(
        fake,
        cache,
        lambda: Job(delay=lambda: 0.0, sleep=lambda seconds: None),
        lambda: datetime(2026, 9, 1, tzinfo=UTC),
        clock,
        1.0,
    )
    monkeypatch.setattr(cli, "_runner", lambda settings: (runner, fake))
    return fake

```

- **Lines 12 to 28**: the fixture `store`. `monkeypatch.setenv("POSTGRES_PASSWORD", "pw")` sets the variable for this test only. It builds a `JobRunner` from fakes and then `monkeypatch.setattr(cli, "_runner", lambda settings: (runner, fake))`, replacing the function that would have connected to PostgreSQL, so the real `main()` runs end to end against the fake store. It returns the fake store so tests can inspect it.

```python
def test_version_prints_the_installed_version_without_needing_a_database(capsys, monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == cli.installed_version()


def test_a_missing_password_exits_with_the_usage_code(capsys, monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    assert cli.main(["health"]) == cli.EXIT_USAGE
    assert "POSTGRES_PASSWORD" in capsys.readouterr().err


def test_run_job_prints_the_record_and_stores_it(store, capsys):
    assert cli.main(["run-job", "nightly"]) == 0
    assert "nightly: finished=True" in capsys.readouterr().out
    assert [record.job_key for record in store.records] == ["nightly"]


def test_an_invalid_key_exits_with_the_usage_code(store, capsys):
    assert cli.main(["run-job", "bad key"]) == cli.EXIT_USAGE
    assert "job key" in capsys.readouterr().err


def test_history_lists_the_newest_runs(store, capsys):
    cli.main(["run-job", "first"])
    cli.main(["run-job", "second"])
    capsys.readouterr()
    assert cli.main(["history", "--limit", "1"]) == 0
    assert capsys.readouterr().out.startswith("second:")


def test_health_exits_zero_when_the_store_answers(store, capsys):
    assert cli.main(["health"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_health_exits_one_when_the_store_is_down(store, capsys):
    store.reachable = False
    assert cli.main(["health"]) == cli.EXIT_FAILED
    assert "unreachable" in capsys.readouterr().out


def test_smoke_runs_twice_and_proves_the_second_came_from_the_cache(store, capsys):
    assert cli.main(["smoke"]) == 0
    assert "first_cached=False second_cached=True stored=1" in capsys.readouterr().out


def test_an_unexpected_error_exits_with_the_failure_code(store, monkeypatch):
    monkeypatch.setattr(store, "save", lambda record: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert cli.main(["run-job", "x"]) == cli.EXIT_FAILED
```

- **`test_version_prints_the_installed_version_without_needing_a_database`** (31 to 34): `monkeypatch.delenv(..., raising=False)` removes the password. `cli.main(["version"]) == 0` and `capsys.readouterr().out.strip()` equals `cli.installed_version()`.
- **`test_a_missing_password_exits_with_the_usage_code`** (37 to 40): exit code `EXIT_USAGE` (2) and the error output mentions `POSTGRES_PASSWORD`.
- **Lines 43 to 46**: `run-job nightly` exits 0, prints `nightly: finished=True`, and stores one record named `nightly`.
- **Lines 49 to 51**: a bad key exits with the usage code; the message mentions "job key".
- **Lines 54 to 59**: after two runs, `history --limit 1` prints the newest first: output starts with `second:`.
- **Lines 62 to 70**: `health` prints `ok` and exits 0 when the store answers; with `store.reachable = False` it exits `EXIT_FAILED` and prints "unreachable".
- **Lines 73 to 75**: `smoke` prints `first_cached=False second_cached=True stored=1`.
- **Lines 78 to 80**: `monkeypatch.setattr(store, "save", lambda record: (_ for _ in ()).throw(RuntimeError("disk full")))` replaces `save` with a function that raises. The odd expression `(_ for _ in ()).throw(...)` is a trick to raise an error inside a `lambda`, which cannot contain a `raise` statement. The command must exit with `EXIT_FAILED` (1).

### `tests/integration/`: against the real database and the built wheel

```python
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
```

- **Lines 16 to 18**: `pytest_collection_modifyitems` is a **hook** that pytest calls after collecting tests (it recognises the special name). It adds the `integration` marker to every test in the folder.
- **Lines 21 to 23**: `settings` has `scope="session"`: built once, from the real environment.
- **Lines 26 to 28**: `store` builds a `PostgresJobStore` from the settings.
- **Lines 31 to 37**: `key_prefix` makes a unique name like `it-3fa91bc2` (`uuid.uuid4().hex[:8]` is the first eight hexadecimal characters of a random identifier), gives it to the test with `yield`, and, after the test, deletes every row whose key starts with it (`LIKE %s` with `"{prefix}%"`). Tests therefore never see each other's rows.
- **Lines 40 to 42**: `running_against_the_artifact` is true when `ARTIFACT_TESTS` is `1`.

```python
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from small_service.domain.jobs import JobRecord
from small_service.infrastructure.postgres_store import PostgresJobStore

WHEN = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_the_database_answers_a_ping(store):
    store.ping()


def test_a_saved_run_is_read_back_unchanged(store, key_prefix):
    record = JobRecord(f"{key_prefix}-a", WHEN, 71, True)
    store.save(record)
    assert record in store.recent(50)


def test_recent_returns_the_newest_first(store, key_prefix):
    older = JobRecord(f"{key_prefix}-old", WHEN, 60, True)
    newer = JobRecord(f"{key_prefix}-new", WHEN + timedelta(minutes=1), 90, False)
    store.save(older)
    store.save(newer)
    mine = [record for record in store.recent(50) if record.job_key.startswith(key_prefix)]
    assert mine == [newer, older]


def test_the_schema_refuses_a_key_the_domain_would_refuse(store):
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save(JobRecord("not valid!", WHEN, 1, True))


def test_the_schema_refuses_a_negative_duration(store, key_prefix):
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save(JobRecord(f"{key_prefix}-neg", WHEN, -1, True))


def test_an_unreachable_database_is_retried_and_then_raises():
    unreachable = PostgresJobStore("postgresql://x:y@127.0.0.1:1/none")
    with pytest.raises(psycopg.OperationalError):
        unreachable.ping()
```

- **Lines 12 to 13**: the database answers a ping. **Lines 16 to 19**: a saved record is read back equal (`record in store.recent(50)`). **Lines 22 to 28**: two records one minute apart come back newest first; `mine = [...]` keeps only this test's rows. **Lines 31 to 38**: the schema's `CHECK` rules fire: `psycopg.errors.CheckViolation` for the key `"not valid!"` and for a duration of -1. **Lines 41 to 44**: a store pointed at `127.0.0.1:1` (nothing listens there) raises `psycopg.OperationalError` after the retries.

```python
"""Run by the pipeline's integration job (ARTIFACT_TESTS=1): the tests exercise the installed wheel, not the sources."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

import small_service
from small_service.interfaces import cli


def test_the_package_under_test_is_the_built_wheel(running_against_the_artifact):
    if not running_against_the_artifact:
        pytest.skip("set ARTIFACT_TESTS=1 (the pipeline does) to require the installed wheel")
    assert "site-packages" in Path(small_service.__file__).parts
    assert "+" in importlib.metadata.version("cicd-green-main"), "a pipeline build carries the commit in its version"


def test_the_smoke_command_runs_a_job_twice_and_reads_it_back(settings, capfd):
    assert cli.main(["smoke"]) == 0
    assert "first_cached=False second_cached=True stored=1" in capfd.readouterr().out


def test_the_installed_command_reports_its_version():
    result = subprocess.run(
        [str(Path(sys.executable).parent / "small-service"), "version"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == cli.installed_version()
```

- Run by the pipeline's integration job with `ARTIFACT_TESTS=1`, against the *installed wheel*.
- **Lines 16 to 20**: if the variable is not set, `pytest.skip(...)` marks the test as skipped with a reason. When set, `"site-packages" in Path(small_service.__file__).parts` proves the code came from an installed package, not the source folder, and `"+" in importlib.metadata.version("cicd-green-main")` proves the version carries a commit.
- **Lines 23 to 25**: `cli.main(["smoke"])` returns 0 and prints the expected summary; `capfd` captures output at the operating-system level.
- **Lines 28 to 32**: runs the installed `small-service` program in a separate process with `subprocess.run` and compares its version with `cli.installed_version()`.

### `tests/e2e/test_gate_demo.py`: the protected-main scenario

```python
"""The protected-main scenario end to end, in temporary git repositories (no network, no database)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.e2e


def test_the_gate_demo_refuses_what_a_protected_main_refuses_and_accepts_the_green_merge():
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"}
    result = subprocess.run(
        [str(ROOT / "scripts" / "gate-demo.sh")], capture_output=True, text=True, env=env, check=False, timeout=300
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("-> refused") == 6
    assert "-> accepted" in result.stdout
    assert "GH006 protected branch: required status checks have not passed" in result.stdout
    assert "the branch is not up to date" in result.stdout
    assert "only CI may post a status" in result.stdout
    assert "all six behaviors confirmed" in result.stdout


def test_changes_script_skips_only_documentation_changes(tmp_path):
    def git(*args: str) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
        }
        return subprocess.run(
            ["git", *args], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
        ).stdout.strip()

    def decide(base: str, head: str) -> str:
        result = subprocess.run(
            [str(ROOT / "pipeline" / "changes.sh"), base, head],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("doc\n")
    (tmp_path / "README.md").write_text("readme\n")
    git("add", ".")
    git("commit", "-qm", "docs only")
    docs_only = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text("x = 2\n")
    git("commit", "-qam", "code")
    assert decide(base, docs_only) == "code=false"
    assert decide(base, "HEAD") == "code=true"
    assert decide("", "HEAD") == "code=true"
    assert decide("0" * 40, "HEAD") == "code=true"
    assert decide("f" * 40, "HEAD") == "code=true"
```

- **Line 12**: `pytestmark = pytest.mark.e2e` labels every test in the file.
- **`test_the_gate_demo_refuses_what_a_protected_main_refuses_and_accepts_the_green_merge`** (15 to 26): puts the Python environment's folder first on `PATH`, runs `scripts/gate-demo.sh` ([bash-and-sh.md](bash-and-sh.md)) with a five-minute timeout and asserts it exits 0, printed `-> refused` exactly six times, printed `-> accepted`, and contains the three kinds of refusal messages and the final `all six behaviors confirmed`.
- **`test_changes_script_skips_only_documentation_changes`** (29 to 69): builds a temporary repository with two helper functions, `git(...)` (runs Git there with a fixed identity) and `decide(base, head)` (runs `pipeline/changes.sh`). Commit 1 adds `app.py`; commit 2 adds only `docs/a.md` and `README.md`; commit 3 changes `app.py`. The asserts: base to commit 2 is `code=false`; base to the final commit is `code=true`; an empty base, a base of forty zeros and a base commit that does not exist (`"f" * 40`) all give `code=true`, the "when unsure run everything" rule.

### `tests/pipeline/`: the pipeline's own logic

```python
import pytest
from pipeline.core import checksum
from pipeline.core.version import VersionError, base_version, build_version, stamp_pyproject

PYPROJECT = '[build-system]\nrequires = ["x"]\n\n[project]\nname = "demo"\nversion = "0.1.0"\n'


def test_the_base_version_is_read_from_pyproject():
    assert base_version(PYPROJECT) == "0.1.0"


def test_a_base_version_that_is_not_major_minor_patch_is_refused():
    with pytest.raises(VersionError):
        base_version(PYPROJECT.replace("0.1.0", "0.1"))


def test_the_version_carries_the_first_seven_characters_of_the_commit():
    assert build_version("0.1.0", "3fa91bcdeadbeef") == "0.1.0+3fa91bc"


def test_the_same_commit_always_gives_the_same_version():
    assert build_version("0.1.0", "3fa91bc") == build_version("0.1.0", "3fa91bc")


def test_uncommitted_changes_mark_the_version_dirty():
    assert build_version("0.1.0", "3fa91bc", dirty=True) == "0.1.0+3fa91bc.dirty"


@pytest.mark.parametrize("sha", ["", "abc", "ZZZZZZZ", "3FA91BC"])
def test_a_bad_commit_is_refused(sha):
    with pytest.raises(VersionError):
        build_version("0.1.0", sha)


def test_stamping_replaces_only_the_project_version():
    stamped = stamp_pyproject(PYPROJECT, "0.1.0+3fa91bc")
    assert 'version = "0.1.0+3fa91bc"' in stamped
    assert 'requires = ["x"]' in stamped


def test_stamping_a_file_with_no_version_is_refused():
    with pytest.raises(VersionError):
        stamp_pyproject("[project]\nname = 'x'\n", "1.0.0")


def test_the_sha256_matches_a_known_value(tmp_path):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    assert checksum.sha256_of(artifact) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_verify_accepts_the_matching_digest_in_any_case(tmp_path):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    assert checksum.verify(artifact, "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD")


def test_verify_refuses_an_artifact_that_changed(tmp_path):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    expected = checksum.sha256_of(artifact)
    artifact.write_bytes(b"abd")
    with pytest.raises(checksum.ChecksumMismatchError, match="expected sha256"):
        checksum.verify(artifact, expected)


def test_sums_lines_round_trip(tmp_path):
    artifact = tmp_path / "a-1.0.whl"
    line = checksum.sums_line(artifact, "ab" * 32)
    assert checksum.parse_sums(line + "\n\n") == {"a-1.0.whl": "ab" * 32}
```

- **Line 5**: `PYPROJECT` is a small sample `pyproject.toml` as text. Tests: the base version is read (8 to 9); `0.1` is refused (12 to 14); the version is `0.1.0+3fa91bc` from a longer commit id (17 to 18); the same commit gives the same version (21 to 22); `dirty=True` adds `.dirty` (25 to 26); bad commits are refused (29 to 32: empty, too short, upper-case letters, a non-hex letter); stamping replaces only the project version and keeps `requires = ["x"]` (35 to 38); a file with no version is refused (41 to 43).
- **Lines 46 to 49**: the SHA-256 of the three bytes `abc` is the well-known value `ba7816bf...15ad`. **Lines 52 to 55**: `verify` accepts the same digest in capitals. **Lines 58 to 64**: change the file after taking its checksum: `ChecksumMismatchError` whose message contains "expected sha256". **Lines 67 to 70**: `sums_line` and `parse_sums` round-trip (a trailing blank line is ignored).

```python
import json

from pipeline.core import flaky, ghruns, runlog
from pipeline.core.runlog import FAILURE, SUCCESS, RunRecord

JUNIT = """<testsuites><testsuite>
<testcase classname="tests.unit.domain.test_jobs_timing" name="test_job_finishes_in_time">
<failure message="assert False&#10; +  where False = &lt;Job&gt;.done">trace</failure></testcase>
<testcase classname="tests.unit.domain.test_cache" name="test_ok"/>
<testcase classname="tests.unit.x" name="test_broken"><error message="ImportError: nope"/></testcase>
</testsuite></testsuites>"""


def record(
    run: int, commit: str, result: str, variant: str = "v", tests: tuple[str, ...] = (), seconds: float = 10
) -> RunRecord:
    return RunRecord(run, commit, seconds, result, variant, tests, "assert False" if tests else "")


def test_a_log_round_trips_through_the_csv_file(tmp_path):
    path = tmp_path / "runs.csv"
    first = record(1, "3fa91bc", FAILURE, tests=("tests/a.py::t1", "tests/a.py::t2"))
    runlog.append(path, first)
    runlog.append(path, record(2, "b84d20e", SUCCESS))
    assert runlog.read(path)[0] == RunRecord(1, "3fa91bc", 10.0, FAILURE, "v", first.failed_tests, "assert False")
    assert path.read_text().splitlines()[0] == "run,commit,seconds,result,variant,failed_tests,message"


def test_a_missing_log_is_empty_and_numbering_starts_at_one(tmp_path):
    records = runlog.read(tmp_path / "none.csv")
    assert records == []
    assert runlog.next_run_number(records) == 1


def test_the_next_run_number_follows_the_highest(tmp_path):
    assert runlog.next_run_number([record(4, "a", SUCCESS), record(2, "b", SUCCESS)]) == 5


def test_a_message_is_kept_on_one_line_and_truncated(tmp_path):
    path = tmp_path / "runs.csv"
    runlog.append(path, RunRecord(1, "a", 1.0, FAILURE, "v", ("t",), "line one\nline two" + "x" * 300))
    message = runlog.read(path)[0].message
    assert "\n" not in message
    assert len(message) == 160


def test_the_summary_uses_the_median_not_the_mean():
    records = [record(index, "c", SUCCESS, seconds=seconds) for index, seconds in enumerate([100, 110, 400], 1)]
    summary = runlog.summarize(records, "v")
    assert summary is not None
    assert (summary.runs, summary.median_seconds, summary.slowest_seconds) == (3, 110, 400)


def test_a_variant_with_no_runs_has_no_summary():
    assert runlog.summarize([record(1, "a", SUCCESS)], "other") is None


def test_durations_read_as_minutes_and_seconds():
    assert runlog.format_duration(65) == "1m 05s"
    assert runlog.format_duration(42.4) == "42s"


def test_the_comparison_says_whether_the_median_is_under_half_the_start():
    before = runlog.summarize([record(1, "a", SUCCESS, "sequential", seconds=100)], "sequential")
    after = runlog.summarize([record(2, "a", SUCCESS, "parallel", seconds=40)], "parallel")
    table = runlog.format_comparison(before, after)
    assert "1. sequential" in table
    assert "3. cached and parallel" in table
    assert table.endswith("median under half of the starting time: yes")
    slow = runlog.summarize([record(3, "a", SUCCESS, "parallel", seconds=60)], "parallel")
    assert runlog.format_comparison(before, slow).endswith("no")

```

- **Lines 6 to 11**: `JUNIT` is a small sample report with one failure whose message has an HTML-style line break (`&#10;`), one passing case and one `error`. **Lines 14 to 17**: `record(...)` builds a `RunRecord` quickly.
- **Lines 20 to 26**: a log written with `append` and read back is equal, and the first line of the file is the header. **Lines 29 to 32**: a missing file is an empty log and numbering starts at 1. **Lines 35 to 36**: the next number is highest plus one (5). **Lines 39 to 44**: a message is kept on one line and cut to exactly 160 characters.
- **Lines 47 to 51**: with times 100, 110 and 400 the median is 110, not the average 203. **Lines 54 to 55**: no runs of a variant gives `None`. **Lines 58 to 60**: `65` seconds is `"1m 05s"` and `42.4` is `"42s"`. **Lines 63 to 71**: the comparison table says "yes" when 40 is under half of 100, and ends with "no" for 60.

```python
def test_flaky_commits_are_those_that_both_passed_and_failed():
    records = [
        record(1, "3fa91bc", FAILURE),
        record(2, "3fa91bc", SUCCESS),
        record(3, "aaaaaaa", SUCCESS),
        record(4, "bbbbbbb", FAILURE),
        record(5, "b84d20e", SUCCESS),
        record(6, "b84d20e", FAILURE),
    ]
    assert flaky.flaky_commits(records) == ["3fa91bc", "b84d20e"]


def test_the_failure_rate_and_messages_of_a_test():
    test = ("tests/unit/domain/test_jobs_timing.py::test_job_finishes_in_time",)
    records = [
        record(index, "c", FAILURE if index % 5 == 0 else SUCCESS, tests=test if index % 5 == 0 else ())
        for index in range(1, 11)
    ]
    (report,) = flaky.flake_reports(records)
    assert (report.failures, report.runs, report.rate) == (2, 10, 0.2)
    assert report.messages == (("assert False", 2),)


def test_the_report_text_names_commits_and_rates():
    test = ("t.py::flaky",)
    text = flaky.format_report([record(1, "3fa91bc", FAILURE, tests=test), record(2, "3fa91bc", SUCCESS)])
    assert "3fa91bc" in text
    assert "failure rate of t.py::flaky: 1 of 2 runs (50%)" in text
    assert "failed 1 times with: assert False" in text


def test_the_report_says_none_when_no_commit_disagrees_with_itself():
    assert "  none" in flaky.format_report([record(1, "a", SUCCESS)])


def test_junit_failures_and_errors_are_listed_with_their_first_message_line():
    failures = flaky.parse_junit_failures(JUNIT)
    assert [failure.test_id for failure in failures] == [
        "tests/unit/domain/test_jobs_timing.py::test_job_finishes_in_time",
        "tests/unit/x.py::test_broken",
    ]
    assert failures[0].message == "assert False"


def test_github_runs_become_log_rows_oldest_first_and_unfinished_runs_are_skipped():
    runs = [
        {
            "databaseId": 2,
            "headSha": "b84d20e" + "0" * 33,
            "conclusion": "failure",
            "createdAt": "2026-09-02T10:00:00Z",
            "updatedAt": "2026-09-02T10:03:30Z",
        },
        {
            "databaseId": 1,
            "headSha": "3fa91bc" + "0" * 33,
            "conclusion": "success",
            "createdAt": "2026-09-01T10:00:00Z",
            "updatedAt": "2026-09-01T10:03:05Z",
        },
        {
            "databaseId": 3,
            "headSha": "c" * 40,
            "conclusion": "",
            "createdAt": "2026-09-03T10:00:00Z",
            "updatedAt": "2026-09-03T10:00:10Z",
        },
    ]
    rows = ghruns.parse_gh_runs(json.dumps(runs))
    assert [(row.run, row.commit, row.seconds, row.result) for row in rows] == [
        (1, "3fa91bc", 185.0, SUCCESS),
        (2, "b84d20e", 210.0, FAILURE),
    ]
```

- **Lines 74 to 83**: commits `3fa91bc` and `b84d20e` have both outcomes; `aaaaaaa` and `bbbbbbb` have one. **Lines 86 to 94**: ten runs where every fifth fails: a test with 2 failures in 10 runs, rate 0.2, one message seen twice. **Lines 97 to 102**: the report text has the commit, `failure rate of t.py::flaky: 1 of 2 runs (50%)` and `failed 1 times with: assert False`. **Lines 105 to 106**: no disagreement prints `none`.
- **Lines 109 to 115**: the JUnit sample yields two failures with test ids `tests/unit/domain/test_jobs_timing.py::test_job_finishes_in_time` and `tests/unit/x.py::test_broken`; the first message is "assert False". **Lines 118 to 146**: GitHub runs given out of order, with one unfinished: only two rows come out, oldest first, with durations 185 and 210 seconds.

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pipeline.adapters import builder, git, local_runner
from pipeline.adapters.process import Command, Job, run_job

from pipeline import cli

PYPROJECT = """[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demo-pkg"
version = "0.1.0"

[tool.setuptools.packages.find]
where = ["src"]
"""


def git_run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src" / "demo_pkg").mkdir(parents=True)
    (tmp_path / "src" / "demo_pkg" / "__init__.py").write_text("VALUE = 1\n")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "README.md").write_text("demo\n")
    (tmp_path / "LICENSE").write_text("MIT\n")
    (tmp_path / ".gitignore").write_text("dist*/\n")
    git_run(tmp_path, "init", "-q", "-b", "main")
    git_run(tmp_path, "add", ".")
    git_run(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_the_wheel_is_versioned_from_the_commit(repo):
    artifact = builder.build_wheel(repo, repo / "dist", sys.executable)
    assert artifact.version == f"0.1.0+{git.head_sha(repo)[:7]}"
    assert artifact.path.name == f"demo_pkg-{artifact.version}-py3-none-any.whl"


def test_building_the_same_commit_twice_gives_the_same_bytes(repo):
    first = builder.build_wheel(repo, repo / "dist", sys.executable)
    second = builder.build_wheel(repo, repo / "dist2", sys.executable)
    assert first.sha256 == second.sha256


def test_the_checksum_file_matches_the_wheel(repo):
    artifact = builder.build_wheel(repo, repo / "dist", sys.executable)
    assert (repo / "dist" / builder.SUMS_FILE).read_text() == f"{artifact.sha256}  {artifact.path.name}\n"


def test_an_uncommitted_change_makes_the_version_dirty(repo):
    (repo / "src" / "demo_pkg" / "__init__.py").write_text("VALUE = 2\n")
    assert builder.build_wheel(repo, repo / "dist", sys.executable).version.endswith(".dirty")

```

- **Lines 12 to 22**: `PYPROJECT` for a tiny demo package. **Lines 25 to 31**: `git_run` runs Git with a fixed identity. **Lines 34 to 45**: the fixture `repo` builds a real temporary repository: a package `demo_pkg`, `pyproject.toml`, `README.md`, `LICENSE`, a `.gitignore` for `dist*/`, then `git init`, `add`, `commit`.
- **Lines 48 to 51**: the wheel's version is `0.1.0+<first 7 of the commit>` and its file name follows the wheel naming scheme. **Lines 54 to 57**: building the same commit twice into different folders gives the same SHA-256: a reproducible build. **Lines 60 to 62**: `dist/SHA256SUMS` contains exactly `<digest>  <file>\n`. **Lines 65 to 67**: after editing a tracked file the version ends in `.dirty`.

```python
def test_a_job_runs_its_steps_in_order_and_logs_them(tmp_path):
    job = Job("demo", (Command(("echo", "one")), Command(("echo", "two"))))
    outcome = run_job(job, tmp_path, tmp_path / "logs")
    assert outcome.ok
    assert outcome.log.read_text().count("$ echo") == 2


def test_a_job_stops_at_its_first_failing_step(tmp_path):
    job = Job("demo", (Command(("false",)), Command(("echo", "never"))))
    outcome = run_job(job, tmp_path, tmp_path / "logs")
    assert not outcome.ok
    assert "never" not in outcome.log.read_text()
    assert "[exit status 1]" in outcome.log.read_text()


def test_a_step_sees_the_environment_it_was_given(tmp_path):
    job = Job("demo", (Command(("sh", "-c", "echo $PIPELINE_DEMO"), {"PIPELINE_DEMO": "hello"}),))
    assert "hello" in run_job(job, tmp_path, tmp_path / "logs").log.read_text()


def test_the_integration_job_is_the_make_target_that_verifies_and_tests_the_wheel(tmp_path):
    job = local_runner.integration_job(tmp_path / "dist" / "a.whl", "abc")
    assert job.steps[0].argv == (
        "make",
        "--no-print-directory",
        "test-artifact",
        f"WHEEL={tmp_path / 'dist' / 'a.whl'}",
        "EXPECTED_SHA256=abc",
    )


def test_the_unit_job_excludes_quarantined_tests_unless_asked():
    assert "UNIT_MARKERS=not flaky_quarantine" in local_runner.unit_job(False).steps[0].argv
    assert "UNIT_MARKERS=" in local_runner.unit_job(True).steps[0].argv


def test_the_digest_is_read_from_the_checksum_file(tmp_path):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / builder.SUMS_FILE).write_text("ab" * 32 + "  a-1.0.whl\n")
    assert local_runner._read_digest(tmp_path) == (tmp_path / "dist" / "a-1.0.whl", "ab" * 32)


def test_the_baseline_starts_from_a_cold_environment_and_installs_without_the_cache(tmp_path):
    steps = [" ".join(step.argv) for step in local_runner.sequential_job(tmp_path).steps]
    assert "venv --clear" in steps[0]
    assert "--no-cache-dir" in steps[1]
    assert steps[-1].endswith("-m pipeline build")


def test_the_parser_accepts_every_command():
    parser = cli.build_parser()
    for argv in (
        ["version"],
        ["build"],
        ["run"],
        ["flaky"],
        ["protection"],
        ["lint-workflows"],
        ["check-contract"],
        ["verify", "a.whl", "--expected", "ab"],
        ["gate", "--sha", "abc", "--token", "t"],
    ):
        parser.parse_args(argv)


def test_verify_exits_one_on_a_mismatch_and_zero_on_a_match(tmp_path, capsys):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    good = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert cli.main(["verify", str(artifact), "--expected", good, "--job", "integration"]) == 0
    assert f"integration: sha256 {good}  verified" in capsys.readouterr().out
    assert cli.main(["verify", str(artifact), "--expected", "00" * 32]) == 1
    assert "MISMATCH" in capsys.readouterr().err


def test_protection_prints_json_and_flaky_reads_the_log(tmp_path, capsys):
    assert cli.main(["protection"]) == 0
    assert '"contexts"' in capsys.readouterr().out
    assert cli.main(["flaky", "--runs-csv", str(tmp_path / "none.csv")]) == 0
    assert "none" in capsys.readouterr().out


def test_importing_github_runs_appends_rows(tmp_path):
    source = tmp_path / "runs.json"
    run = {
        "databaseId": 7,
        "headSha": "abcdef0123",
        "conclusion": "success",
        "createdAt": "2026-09-01T10:00:00Z",
        "updatedAt": "2026-09-01T10:02:00Z",
    }
    source.write_text(json.dumps([run]))
    csv_path = tmp_path / "runs.csv"
    assert cli.main(["import-gh-runs", str(source), "--runs-csv", str(csv_path)]) == 0
    assert csv_path.read_text().splitlines()[1].startswith("7,abcdef0,120.0,success,github")
```

- **Lines 70 to 87**: jobs. Two `echo` steps both appear in the log (`count("$ echo") == 2`); a job whose first step is the program `false` (it always fails) stops there: `never` is not in the log and `[exit status 1]` is; `Command(("sh", "-c", "echo $PIPELINE_DEMO"), {"PIPELINE_DEMO": "hello"})` shows a step sees the environment it was given.
- **Lines 90 to 109**: `integration_job` is exactly the `make test-artifact WHEEL=... EXPECTED_SHA256=...` command; the unit job carries `UNIT_MARKERS=not flaky_quarantine` unless quarantined tests are requested; `_read_digest` parses `dist/SHA256SUMS`. **Lines 112 to 116**: the baseline's first step is `venv --clear`, its second uses `--no-cache-dir`, and the last is `-m pipeline build`.
- **Lines 119 to 132**: the command-line parser accepts each command. **Lines 135 to 142**: `verify` returns 0 for the right digest (printing `integration: sha256 ... verified`) and 1 for a wrong one (printing `MISMATCH` on standard error). **Lines 145 to 149**: `protection` prints JSON with `"contexts"`; `flaky` on a missing log prints `none`. **Lines 152 to 164**: `import-gh-runs` appends a row starting `7,abcdef0,120.0,success,github`.

```python
from pathlib import Path

import pytest
from pipeline.core import contract, protection, workflow

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
GOOD = f"""
name: ci
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{SHA} # v1
      - uses: ./.github/actions/setup
      - run: make lint
  quarantine:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: make quarantine
"""


def findings(text: str, required=("lint",)) -> list[str]:
    return [finding.code for finding in workflow.lint(workflow.load(text), required, ("quarantine",))]


def test_a_good_workflow_has_no_findings():
    assert findings(GOOD) == []


def test_the_on_key_is_read_despite_yaml_treating_it_as_a_boolean():
    assert "push" in workflow.load(GOOD)["on"]


def test_job_names_use_the_name_field_when_present():
    document = workflow.load(GOOD.replace("  lint:\n", "  lint:\n    name: Lint and types\n"))
    assert workflow.job_names(document)["lint"] == "Lint and types"


def test_a_required_check_that_no_job_reports_is_found():
    assert "WF001" in findings(GOOD, required=("lint", "unit"))


def test_a_paths_filter_on_a_trigger_is_found():
    assert "WF003" in findings(GOOD.replace("  push:\n", "  push:\n    paths-ignore: ['docs/**']\n"))


def test_a_workflow_that_does_not_run_on_pull_requests_is_found():
    assert "WF002" in findings(GOOD.replace("  pull_request:\n", ""))


def test_continue_on_error_outside_the_quarantine_job_is_found():
    assert "WF004" in findings(
        GOOD.replace(
            "    steps:\n      - uses: actions", "    continue-on-error: true\n    steps:\n      - uses: actions", 1
        )
    )


```

- **Lines 8 to 27**: `GOOD` is a sample workflow as text that passes every rule. **Lines 30 to 31**: `findings(text, required)` returns the rule codes found. The tests then change one thing at a time with `str.replace` and expect one code: WF001 for a required check no job reports (47 to 48), WF003 for a `paths-ignore` filter (51 to 52), WF002 for no pull-request trigger (55 to 56), WF004 for `continue-on-error` outside the quarantine job (59 to 64), WF005 for three bad pins, parametrized (67 to 69).
- **Lines 38 to 39**: despite YAML reading `on` as `True`, `workflow.load(GOOD)["on"]` works. **Lines 42 to 44**: a job's `name:` is used as its check name.

```python
def test_a_moving_name_in_a_command_or_service_is_found():
    assert "WF006" in findings(GOOD.replace("make lint", "docker run postgres:latest"))
    with_service = GOOD.replace(
        "    steps:\n      - uses: actions",
        "    services:\n      db:\n        image: postgres:latest\n    steps:\n      - uses: actions",
        1,
    )
    assert "WF006" in findings(with_service)


def test_missing_read_only_permissions_are_found():
    assert "WF007" in findings(GOOD.replace("permissions:\n  contents: read\n", ""))


def test_a_workflow_without_required_checks_may_use_other_triggers():
    scheduled = GOOD.replace("on:\n  push:\n  pull_request:\n", "on:\n  schedule:\n    - cron: '0 6 * * 1'\n")
    assert findings(scheduled, required=()) == []


def test_every_workflow_and_composite_action_in_this_repository_passes_the_rules():
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        required = protection.REQUIRED_CHECKS if path.name == "ci.yml" else ()
        problems = workflow.lint(workflow.load(path.read_text()), required, ("quarantine",))
        assert problems == [], f"{path.name}: {problems}"
    for path in sorted((ROOT / ".github" / "actions").glob("*/action.yml")):
        assert workflow.lint_composite(workflow.load(path.read_text())) == [], path


def test_an_unpinned_step_in_a_composite_action_is_found():
    action = workflow.load(
        "runs:\n  using: composite\n  steps:\n    - uses: actions/setup-python@v5\n    - uses: ./x\n"
    )
    assert [finding.code for finding in workflow.lint_composite(action)] == ["WF005"]


def test_the_protection_payload_requires_the_checks_strictly_for_admins_too():
    payload = protection.branch_protection(("lint", "unit"))
    assert payload["required_status_checks"] == {"strict": True, "contexts": ["lint", "unit"]}
    assert payload["enforce_admins"] is True
    assert payload["allow_force_pushes"] is False


def test_protection_needs_at_least_one_check():
    with pytest.raises(ValueError, match="at least one"):
        protection.branch_protection(())


def test_the_required_checks_are_the_names_of_jobs_in_the_ci_workflow():
    names = set(workflow.job_names(workflow.load((ROOT / ".github" / "workflows" / "ci.yml").read_text())).values())
    assert set(protection.REQUIRED_CHECKS) <= names


GOOD_README = """# x

## The pipeline's contract

- Anything on `main` has passed lint, unit and integration tests.
- The required checks finish in under 5 minutes.
- A red `main` stops merging: fix it forward within an hour or revert it.

## Next
"""


def test_a_short_contract_with_the_red_main_rule_passes():
    assert contract.check(GOOD_README) == []


def test_a_contract_over_ten_lines_fails():
    long_readme = GOOD_README.replace("- A red", "\n".join(f"- rule {n}" for n in range(9)) + "\n- A red")
    assert any("limit is 10" in problem for problem in contract.check(long_readme))


def test_a_contract_without_the_red_main_rule_or_a_time_fails():
    problems = contract.check("## The pipeline's contract\n\n- be nice\n")
    assert len(problems) == 2


def test_a_readme_without_the_section_fails():
    assert contract.check("# x\n") != []


def test_this_repository_readme_has_a_valid_contract():
    assert contract.check((ROOT / "README.md").read_text()) == []
```

- **Lines 72 to 79**: WF006 for `postgres:latest` in a command and in a service image. **Lines 82 to 83**: WF007 when permissions are missing. **Lines 86 to 88**: a scheduled workflow with no required checks is fine. **Lines 91 to 97**: every real workflow and composite action in this repository passes the rules. **Lines 100 to 104**: an unpinned step in a composite action is WF005.
- **Lines 107 to 121**: the protection payload requires the checks strictly, for admins, forbids force pushes, needs at least one check, and its required checks are real job names of `ci.yml`.
- **Lines 124 to 155**: `GOOD_README` is a sample README with a contract. A short contract with the red-`main` rule passes; more than ten lines fails with "limit is 10"; a contract with neither the red-`main` rule nor a time gives two problems; a README without the section fails; this repository's README passes.

## Try it yourself

```bash
make test
```
Expect a coverage table and a final line like `NNN passed`, then a coverage report that ends without `FAIL Required test coverage`.

```bash
.venv/bin/python -m pytest tests/unit/domain -q -m "flaky_quarantine"
```
Runs only the flaky test. Run it 10 times (`for i in 1 2 3 4 5 6 7 8 9 10; do ...; done`) and count failures.

```bash
.venv/bin/python -m pytest --collect-only -q tests/unit/domain | tail -5
```
Lists the tests without running them.

```bash
make flaky-hunt HUNT_RUNS=10
```
Runs the domain tests, including the flaky one, 10 times and prints the failure rate from `runs.csv`.

## Mistakes people make

- Tests that call `time.sleep` and guess. This repository has exactly one on purpose, and quarantines it.
- Shared state between tests. The `key_prefix` fixture isolates the database tests.
- A misspelled marker that selects zero tests. `--strict-markers` stops that.
- Chasing 100% coverage with empty tests. The floor measures only the pure layers.
- Rerunning a red build until it turns green. The flake hunt finds the cause instead.

## Check yourself

1. What makes pytest treat a function as a test? *A name starting with `test_` in a file `test_*.py`.*
2. What does `yield` in a fixture do? *Everything before gives the test its value; everything after runs as cleanup.*
3. What does `-m "not flaky_quarantine"` do? *Skips tests marked as quarantined.*
4. What does `--fail-under=95` do? *Exits with an error if coverage is below 95%.*
5. Why does `test-artifact` install the wheel? *To test the thing that will ship, not the source folder.*

## Further reading

- pytest 9 documentation: https://docs.pytest.org/en/stable/
- Fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html
- Markers: https://docs.pytest.org/en/stable/how-to/mark.html
- coverage.py: https://coverage.readthedocs.io/ (7.17.0) and pytest-cov: https://pytest-cov.readthedocs.io/
