# Python 3.12

## What it is

A **computer program** is a list of instructions that a computer follows. **Python** is a language you write those instructions in. You write them in a plain text file whose name ends in `.py`. Such a file is called a **source file**.

A computer cannot follow Python text directly. A program called the **interpreter** reads your file and does what it says, one instruction at a time. When you type `python something.py` in a **terminal** (a window where you type commands and read answers), you are starting the interpreter and giving it your file.

A few words you will meet again and again:

- A **module** is one `.py` file. Other files can use what it defines by *importing* it.
- A **package** is a folder of modules. Python knows a folder is a package when it contains a file called `__init__.py` (it may be almost empty).
- A **function** is a named set of instructions you can run whenever you want. A **class** is a recipe for making *objects*: values that bundle data together with the functions that work on it.
- A **library** is code that somebody else wrote and you use. The **standard library** is the large set of libraries that comes with Python itself, so nothing needs to be installed to use it.
- A **type hint** is a note such as `x: int` that says "this should be a whole number". Python does not enforce it when the program runs. Other tools read it and warn you about mistakes ([mypy.md](mypy.md)).

This repository needs Python 3.12 or newer (`requires-python = ">=3.12"` in `pyproject.toml`). The container image uses 3.12.8. The version matters because some lines below use features that older Pythons do not have.

## Why this repository uses it

The whole project is Python, in two halves that never mix:

1. **The service** (`src/small_service/`) is the small program that gets shipped. It keeps a cache of recent results in memory, runs a pretend background job, and records each run in a PostgreSQL database.
2. **The pipeline** (`pipeline/`) is the code that checks and ships the service: it versions a build from its commit, writes a checksum, reads test reports to find a flaky test, lints the GitHub workflow files, and guards a Git branch.

Using one language for both means one set of tools (formatter, type checker, test runner) checks everything, and a learner has only one language to learn.

## Where it appears

The folder layout is itself part of the design. Each folder is a **layer**, and a layer may only use the layers below it:

| Path | Layer | What lives there |
|---|---|---|
| `src/small_service/domain/` | innermost | The rules: `TimedCache`, `Job`, `JobRecord`, the error classes. It uses nothing but the standard library. |
| `src/small_service/application/` | uses the domain | The use cases (`JobRunner`, `recent_runs`, `is_healthy`) and `ports.py`, which lists what the outside world must offer. |
| `src/small_service/infrastructure/` | uses the layers above it | The parts that touch the world: settings from the environment, logging, retrying, and the PostgreSQL store. |
| `src/small_service/interfaces/cli.py` | outermost | The `small-service` command that a person types. |
| `pipeline/core/` | pure rules | Version numbers, checksums, flaky-test maths, workflow rules. No files, no network, no programs started. |
| `pipeline/adapters/` | touches the world | Running programs, Git, the build, GitHub. |
| `pipeline/cli.py`, `pipeline/__main__.py` | outermost | The command `python -m pipeline`. |
| `tests/` | | The tests ([pytest.md](pytest.md)). |

The rule "a layer may only use the layers below it" is checked by a tool ([import-linter.md](import-linter.md)).

## How it works underneath

**What happens when you run a Python file.** The interpreter reads the text, checks that it is valid Python, and turns it into **bytecode**: a compact list of small steps. It keeps a copy of that bytecode in a folder named `__pycache__` so the next run starts faster. Then it carries out the steps one by one.

**What `import` does.** The line `import x` makes the interpreter look for a module called `x`. It searches a list of folders (`sys.path`): the folder of your script, the standard library, and the folders where installed libraries live. When it finds `x` it runs the file *once*, remembers the result, and gives you the name `x`. The second time any file imports `x`, the interpreter reuses the remembered result.

**Where installed libraries live.** A **virtual environment** (the `.venv` folder) is a private copy of Python with its own empty place for libraries. Each project gets its own, so two projects can use different versions of the same library without clashing ([pip-and-hash-locking.md](pip-and-hash-locking.md)).

**Names and values.** In `count = 3`, `count` is a *name* and `3` is a *value*. Writing `count = 3` attaches the name to the value. Values have types: whole numbers (`int`), numbers with a fraction (`float`), text (`str`), true/false (`bool`), lists, dictionaries and many more. A **dictionary** (`dict`) maps keys to values, like `{"a": 1}`.

**A thread** is a second line of execution inside the same running program. Two threads can run at the same time and can see the same data. That is useful and dangerous: if two threads change the same dictionary at once, the result can be garbage. A **lock** lets only one thread into a protected piece of code at a time. You will see both in `cache.py` and `jobs.py`.

## Walkthrough of this repository's use

Every Python file of the service and of the pipeline is covered below, in the order a newcomer should read them. Tests are in [pytest.md](pytest.md).

### The service: `src/small_service/`

#### `src/small_service/__init__.py` and the other `__init__.py` files

<!-- fmt:off -->
```python
"""A small service: a time-limited cache and a background job, recorded in PostgreSQL."""
```
<!-- fmt:on -->

This file has one line and that line is a **docstring**: a piece of text in triple quotes (`"""..."""`) placed first in a file (or first in a function or class). Python keeps it as documentation. It is not an instruction. Its presence is what makes the folder `small_service` a *package*, so other files can write `import small_service`.

The other `__init__.py` files are the same idea for their folders. The five in the service are:

<!-- fmt:off -->
```python
"""Rules of the service. Depends on nothing outside the standard library."""
```
<!-- fmt:on -->

(`domain/`), and one-line docstrings for `application/`, `infrastructure/` and `interfaces/`. In `pipeline/` there are `pipeline/__init__.py`, `pipeline/core/__init__.py` and `pipeline/adapters/__init__.py`, and `tests/` has its own as well. Each only declares "this folder is a package". Nothing else is in them.

#### `src/small_service/domain/errors.py`: names for the things that can go wrong

<!-- fmt:off -->
```python
"""Named errors of the domain."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error the domain raises on purpose."""


class InvalidTtlError(DomainError, ValueError):
    """A cache time-to-live must be a positive number of seconds."""


class InvalidJobKeyError(DomainError, ValueError):
    """A job key must be 1 to 64 characters from letters, digits, dot, dash and underscore."""


class JobNotStartedError(DomainError, RuntimeError):
    """`Job.wait` was called before `Job.start`."""
```
<!-- fmt:on -->

- **Line 1** is the docstring of the file.
- **Line 3**, `from __future__ import annotations`, appears at the top of almost every module here. A type hint such as `-> Job` names a class. Without this line Python would try to look the name up the moment it reads the hint, which fails if the class is defined further down the file. With the line, Python just keeps the hint as text and looks nothing up. You can ignore it while reading; it only removes one class of surprise.
- **Lines 6 to 7** define a **class** called `DomainError`. `class DomainError(Exception):` means "a new kind of thing named `DomainError` that is a special case of `Exception`". `Exception` is Python's built-in name for "something went wrong". A class that extends another **inherits** everything the other has. The text below the class line, indented by four spaces, is its **body**. Python uses *indentation* (the spaces at the start of a line) to show what belongs together; this is why every file here is carefully indented by four spaces per level. The body is only a docstring, so `DomainError` behaves exactly like `Exception`; the point is its *name*.
- When code wants to report a problem it writes `raise SomeError("message")`. That stops what it was doing and travels up through the callers until some code catches it (with `try`/`except`, which you will see in `queries.py`) or the program ends with an error message.
- **Lines 10 to 11**: `InvalidTtlError` is a `DomainError` *and* a `ValueError`. A class can extend two parents; here it means a handler that catches `DomainError` and a handler that catches Python's own `ValueError` (a value of the right type but unusable) will both catch it. "TTL" means *time to live*: how long a cached value is kept.
- **Lines 14 to 15**: `InvalidJobKeyError`, for a job name that breaks the naming rule.
- **Lines 18 to 19**: `JobNotStartedError` is a `DomainError` and a `RuntimeError` (a mistake in the order of calls). The text with backticks in the docstring is only formatting.

Why bother? Later, the command-line program catches `DomainError` to print a calm message for mistakes the *caller* made, and treats every other error as a bug worth a full report.

#### `src/small_service/domain/cache.py`: a cache whose clock is passed in

A **cache** keeps the answer to an earlier question so you can give it again without redoing the work. This one forgets an answer after a set time.

<!-- fmt:off -->
```python
"""A small time-limited cache. The clock is injected, so expiry is tested without sleeping."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from small_service.domain.errors import InvalidTtlError

```
<!-- fmt:on -->

- **Line 3** is the `from __future__` line explained above.
- **Line 5**, `import threading`, makes the standard library's threading tools available under the name `threading`.
- **Line 6**, `from collections.abc import Callable`, imports one name from inside a module. `Callable` is how a type hint says "this is something you can call like a function".
- **Line 7** imports `dataclass`, a *decorator* (explained next).
- **Line 9** imports our own `InvalidTtlError` from the file just described. The long dotted name is the path: package `small_service`, sub-package `domain`, module `errors`.

<!-- fmt:off -->
```python
@dataclass(frozen=True, slots=True)
class _Entry[V]:
    value: V
    expires_at: float

```
<!-- fmt:on -->

- **Line 12** is a **decorator**: a line that starts with `@` and changes the class or function written right below it. `@dataclass` tells Python: look at the fields I list in the body and write the boring methods for me (the one that sets the fields when an object is made, one that prints the object, one that compares two objects). The words in brackets change how: `frozen=True` forbids changing a field after the object is made (trying raises an error), so an entry cannot be altered by accident or by another thread. `slots=True` stores the fields in a fixed, compact layout and makes a mistyped field name an error.
- **Line 13**, `class _Entry[V]:`. The leading underscore is a convention meaning "private to this file; do not use from outside". The `[V]` is new in Python 3.12: it declares a **type parameter**, a placeholder for "some type, to be decided by whoever uses it". An entry holds a value of *some* type `V`.
- **Lines 14 and 15** are the fields. `value: V` says a field named `value` of type `V`. `expires_at: float` says the moment (a number of seconds on a clock) when this entry stops being valid.

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 18**, `class TimedCache[K, V]:`, makes a class with two placeholders: `K` for the type of keys and `V` for the type of values. A user writes `TimedCache[str, JobRecord]` to say "text keys, job-record values". The hint changes nothing at run time; it lets the type checker catch a mistake such as storing a number where a record belongs.
- **Line 21**: `def __init__(...)` defines a function inside a class. Such a function is a **method**. The name `__init__` is special: Python runs it automatically when someone creates an object with `TimedCache(...)`. The first parameter, `self`, is the object being made; Python passes it automatically so the method can store things on the object.
- The other parameters are `ttl_seconds: float` (how long entries live) and `clock: Callable[[], float]`. That last type reads "something callable that takes nothing (the empty `[]`) and returns a float". The cache does **not** read the system time itself. The caller hands in a function that says what time it is. The real program hands in `time.monotonic` (a clock that only moves forward). A test hands in a fake clock that it moves by hand, so a test about "expires after ten seconds" does not have to wait ten seconds.
- **Line 22** is the docstring of the method. **Lines 23 to 24**: `if ttl_seconds <= 0:` is a **condition**. When it is true, the indented lines run. `raise InvalidTtlError(f"...")` stops with our error. The text starting `f"` is an **f-string**: inside the quotes, anything in `{curly braces}` is replaced by its value, so `{ttl_seconds}` shows the bad number in the message.
- **Lines 25 and 26**: `self._ttl_seconds = ttl_seconds` stores the number on the object under the name `_ttl_seconds` (underscore again: private). Now the other methods can read `self._ttl_seconds`. The clock is stored the same way.
- **Line 27**: `self._entries: dict[K, _Entry[V]] = {}`. `{}` is an empty dictionary. The part after the colon is a type hint: a dictionary from `K` to `_Entry[V]`. This dictionary holds the cache's contents.
- **Line 28**: `threading.Lock()` makes a lock. Many threads may call this cache at once, because the server handles requests on several threads, so every method that touches `_entries` takes the lock first.

<!-- fmt:off -->
```python
    def put(self, key: K, value: V) -> None:
        """Store `value`, replacing any earlier value and restarting its time to live."""
        with self._lock:
            self._entries[key] = _Entry(value, self._clock() + self._ttl_seconds)
```
<!-- fmt:on -->

- **Line 30**: `put` takes a key and a value and returns `None` (the `-> None`), which means "nothing useful".
- **Line 32**: `with self._lock:` is a **context manager**. `with` runs some set-up when the block starts (here: wait until the lock is free and take it) and some clean-up when the block ends *in every case*, even if an error happened inside (here: release the lock). That guarantee is why `with` is used instead of taking and releasing by hand.
- **Line 33**: the entry is stored under `key`. It expires at "now plus the time to live": `self._clock()` calls the clock function, and `+ self._ttl_seconds` adds the lifetime. Storing again under an existing key *replaces* the old entry, which restarts the lifetime.

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 35**: the return type `V | None` means "a value of type V, or the special value `None`". `None` is Python's way to say "no value".
- **Line 38**: `self._entries.get(key)` looks the key up and returns `None` instead of failing when the key is missing.
- **Lines 39 and 40**: if there is nothing, return `None`.
- **Line 41**: `entry.expires_at <= self._clock()` asks: has the entry's deadline passed? If so, **line 42** deletes it (`del dictionary[key]`) and **line 43** reports "nothing". The cache therefore cleans an old entry the moment someone asks for it. **Line 44** returns the stored value.
- Because all of this happens inside `with self._lock`, no other thread can change the dictionary in the middle.

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 50** is a **list comprehension**: a compact way to build a list. Read it as "make a list of `key` for each `key, entry` pair in `self._entries.items()`, but only if the entry has expired". `.items()` gives the dictionary's pairs. Collecting the expired keys *first* and deleting them afterwards (lines 51 and 52, a `for` loop that repeats its body once per item) avoids changing a dictionary while looping over it, which Python forbids.
- **Line 53** returns how many were removed: `len(expired)` is the length of the list.
- **Lines 55 to 58**: `__len__` is another special name. Python calls it when someone writes `len(cache)`. It returns the number of stored entries, including expired ones nobody has read yet (the docstring says so).

#### `src/small_service/domain/jobs.py`: the pretend background job

<!-- fmt:off -->
```python
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

```
<!-- fmt:on -->

- **Lines 5 to 11**: more imports. `random` gives random numbers, `time` gives the clock and `sleep`, `datetime` is a date-and-time type, and `Final` marks a name that must never be reassigned.
- **Lines 15 and 16** are **constants**: names written in capitals by convention, giving the job's shortest and longest duration in seconds (50 ms and 112.5 ms). A millisecond is a thousandth of a second.
- **Line 17**: `frozenset("abc...")` turns a string into an immutable *set* of its characters. A set holds each item at most once and answers "is this item in it?" very quickly. This set is every character a job key may contain.
- **Lines 20 to 24**: `validate_job_key`. `not 1 <= len(key) <= 64` is a chained comparison: "the length is at least 1 and at most 64". `set(key) <= _KEY_CHARACTERS` asks whether the set of the key's characters is a *subset* of the allowed characters. If either rule is broken the function raises `InvalidJobKeyError`; otherwise it hands the key back unchanged, so a caller can write `key = validate_job_key(text)`. `{key!r}` inside an f-string prints the key with quotes, which shows invisible mistakes such as a trailing space.
- **Lines 27 to 29**: `lesson_delay` returns a random number between the two limits. The comment after `# noqa: S311` tells the linter to stay quiet about a warning ("random is unsafe for secrets"), with the reason: this is pretend work time, not a secret ([ruff.md](ruff.md)). A `#` starts a **comment**: text for humans that Python ignores.

<!-- fmt:off -->
```python
@dataclass(frozen=True, slots=True)
class JobRecord:
    """What one job run left behind: how long it took and whether it finished inside the wait."""

    job_key: str
    recorded_at: datetime
    duration_ms: int
    finished: bool

```
<!-- fmt:on -->

`JobRecord` is a frozen data holder like `_Entry`, with four fields: the job's key, when it was recorded (`datetime`), how long it took in milliseconds, and whether it finished before the wait ran out.

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Lines 45 to 54**: `__init__` takes two optional functions. `delay: Callable[[], float] = lesson_delay` means "a function returning a float, and if you pass nothing, use `lesson_delay`". The `= value` after a parameter is a **default**. `sleep` defaults to the real `time.sleep`. Tests pass fakes for both, so a test of the job does not wait and does not depend on luck.
- **Line 53**: `threading.Event()` is a small flag shared between threads. One thread can *set* it ("I am done") and another can wait until it is set. **Line 54** starts `_thread` as `None`; it will hold the worker thread once started. The type `threading.Thread | None` says so.
- **Lines 56 to 59**: `@property` is a decorator that turns a method into something you read without parentheses: `job.done` instead of `job.done()`. It reports whether the flag is set.
- **Lines 61 to 69**: `start`. **Lines 64 to 66** define a function *inside* a function (`work`). It sleeps for the chosen delay and then sets the flag. **Line 68** makes a `threading.Thread` that will run `work`; `daemon=True` means this thread must not keep the whole program alive if the program wants to exit. **Line 69**, `.start()`, launches it. From now on `work` runs beside the code that called `start`.
- **Lines 71 to 76**: `wait` blocks the caller until the work ends or until `timeout_seconds` pass. If `start` was never called it raises `JobNotStartedError` (the `is None` test). `self._finished.wait(timeout_seconds)` returns `True` if the flag got set in time and `False` if the time ran out. The docstring records the lesson: waiting for the flag takes exactly as long as the work, whereas a test that sleeps a fixed guess is a *flaky test* (sometimes passes, sometimes fails).

#### `src/small_service/application/ports.py`: what the outside world must offer

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 5**: `Protocol` comes from `typing`, the module of type-hint tools.
- **Lines 10 to 20**: `class JobStore(Protocol)` is an **interface**: a list of methods an object must have to be used as a job store. Each method has a signature and a docstring but no real body (the docstring *is* the body). `save(record)` stores one run; `recent(limit)` returns the newest runs; `ping()` raises an error if the store cannot be reached. The class is named a *port* because it is the plug-shaped hole in the application layer that an adapter (the PostgreSQL store, or a fake in a test) plugs into. A class does not have to say "I implement JobStore". If it has methods with these names and shapes, the type checker accepts it. That is what `Protocol` means.

#### `src/small_service/application/queries.py`: two read-only use cases

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Lines 9 to 13**: `recent_runs` checks that `limit` is at least 1 (raising Python's built-in `ValueError` otherwise) and asks the store for the newest runs. The return type `list[JobRecord]` is a list of records.
- **Lines 16 to 22**: `is_healthy`. `try:` starts a block of code that might fail. If it fails, Python jumps to the matching `except` block. Here `store.ping()` is tried; if *anything* goes wrong (`except Exception`) the function returns `False`. If nothing went wrong it continues to `return True`. The comment explains the choice: for a health check every failure means "not healthy"; the caller is responsible for logging the reason.

#### `src/small_service/application/run_job.py`: the main use case

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Lines 5 to 10**: imports. Notice that the application layer imports the *domain* (`TimedCache`, `Job`, `JobRecord`, `validate_job_key`) and its own `JobStore` port, and nothing from the database.
- **Lines 13 to 14**: the class and its docstring.
- **Lines 16 to 31**: `__init__` receives every collaborator as an argument: the store, the cache, a `job_factory` (a function that makes a new job, so tests can make fake ones), `now` (returns the current date and time), `monotonic` (a clock for measuring durations) and the timeout. Each is stored on `self`. The docstring says what this buys: nothing in this class reads the real clock or the environment. That idea, giving an object its collaborators instead of letting it grab them, is called **dependency injection**. It is what makes the class testable.
- **Lines 33 to 51**: `run`. It returns `tuple[JobRecord, bool]`: a **tuple** is a fixed group of values, here the record and a flag saying whether it came from the cache.
  - **Line 35**: validate the key (raises on a bad one).
  - **Lines 36 to 38**: ask the cache. `is not None` tests that something was found. If so, return the cached record and `True`; the job is not run again and nothing is stored again.
  - **Lines 39 to 42**: make a job, note the start time, start it, and wait for it up to the timeout. `finished` is `True` or `False`.
  - **Lines 43 to 48**: build the `JobRecord`. `round((end - start) * 1000)` converts seconds to whole milliseconds. Writing `job_key=key` is a **keyword argument**: the parameter's name is written out, which is clearer than relying on order.
  - **Lines 49 to 51**: save it in the store, put it in the cache so the next call within the lifetime is answered from memory, and return it with `False` ("not from the cache").

#### `src/small_service/infrastructure/settings.py`: reading configuration from the environment

An **environment variable** is a named piece of text that the program that started yours hands over. In a terminal, `LOG_LEVEL=DEBUG some-command` starts `some-command` with a variable `LOG_LEVEL` whose value is `DEBUG`. Programs read them to learn their settings without those settings being written into the code ([dotenv.md](dotenv.md)).

<!-- fmt:off -->
```python
"""Configuration from the environment, validated once at startup (twelve-factor)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_HOST = re.compile(r"^[\w.\-]+$")


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty")
    return value


def _positive_number(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive, got {raw!r}")
    return value

```
<!-- fmt:on -->

- **Line 5**: `import os` gives access to `os.environ`, the dictionary of all environment variables. `import re` gives regular expressions. A **regular expression** is a pattern that describes text. **Line 12**, `re.compile(r"^[\w.\-]+$")`, builds the pattern: `^` is the start; `[\w.\-]` is one character from "a letter, digit or underscore (`\w`), a dot, or a dash"; `+` means "one or more of those"; `$` is the end. So it accepts a host name like `db.example-1` and refuses anything with a space or a slash. The `r` before the quotes makes it a *raw* string, in which a backslash is just a backslash.
- **Lines 15 to 16**: `ConfigurationError(ValueError)` is the error raised for a bad setting.
- **Lines 19 to 23**: `_text` reads one variable. `environ.get(name, default if default is not None else "")` takes the variable's value or, if it is missing, a default (or empty text). `.strip()` removes spaces at both ends. If the result is empty it raises an error naming the variable. The type `Mapping[str, str]` means "anything that behaves like a read-only dictionary of text to text", which is why tests can pass an ordinary dictionary instead of the real environment.
- **Lines 26 to 34**: `_positive_number` reads a variable, converts it with `float(raw)`, and turns a failure into a `ConfigurationError`. `raise ... from None` hides the confusing original `ValueError` so the user sees only our message. It refuses zero and negative numbers.

<!-- fmt:off -->
```python
@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    log_level: str
    cache_ttl_seconds: float
    job_timeout_seconds: float

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read and validate. The password has no default: it must come from the environment."""
        env = os.environ if environ is None else environ
        host = _text(env, "POSTGRES_HOST", "localhost")
        if not _HOST.match(host):
            raise ConfigurationError(f"POSTGRES_HOST must be a host name or address, got {host!r}")
        port = _positive_number(env, "POSTGRES_PORT", 5432)
        if port != int(port) or port > 65535:
            raise ConfigurationError(f"POSTGRES_PORT must be a port number, got {port}")
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        return cls(
            postgres_host=host,
            postgres_port=int(port),
            postgres_db=_text(env, "POSTGRES_DB", "service"),
            postgres_user=_text(env, "POSTGRES_USER", "service"),
            postgres_password=_text(env, "POSTGRES_PASSWORD"),
            log_level=level,
            cache_ttl_seconds=_positive_number(env, "CACHE_TTL_SECONDS", 30),
            job_timeout_seconds=_positive_number(env, "JOB_TIMEOUT_SECONDS", 5),
        )

    @property
    def dsn(self) -> str:
        """A libpq connection URI. Never log this: it holds the password."""
        return (
            f"postgresql://{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote(self.postgres_db, safe='')}"
        )
```
<!-- fmt:on -->

- **Lines 37 to 48**: `Settings` is a frozen dataclass: all the settings in one object, validated once at start-up. Its eight fields are the database's host, port, name, user and password, the log level, the cache lifetime and the job timeout.
- **Lines 50 to 52**: `@classmethod` makes `from_env` a method that belongs to the *class*, not to one object: it is called as `Settings.from_env()` and its first parameter, `cls`, is the class itself. It builds and returns a `Settings`. The parameter `environ=None` means "use the real environment unless a dictionary is passed". Line 53 picks one or the other: `os.environ if environ is None else environ`.
- **Lines 54 to 56**: the host (default `localhost`), checked with the pattern.
- **Lines 57 to 59**: the port. `port != int(port)` catches `5432.5`; `port > 65535` catches numbers no network port can have (a port is a number from 1 to 65535 that selects one program on a machine).
- **Lines 60 to 62**: the log level, forced to upper case and checked against the allowed set.
- **Lines 63 to 72**: `cls(...)` builds the object. The password has **no default**: `_text(env, "POSTGRES_PASSWORD")` fails if it is missing, so the program refuses to start without it.
- **Lines 74 to 80**: `dsn` is a property returning a **connection string**, the single line of text that tells the database library where and as whom to connect: `postgresql://user:password@host:port/database`. `quote(x, safe='')` percent-encodes characters such as `@` or `/` so a strange password cannot break the URL. The docstring warns: never log this, it contains the password.

#### `src/small_service/infrastructure/logging.py`: one readable line per event

A **log** is a record of what a program did, written as it runs. This module formats each event as one line of `key=value` words (the style is called *logfmt*), which people and tools can both read.

<!-- fmt:off -->
```python
"""Structured logging: one logfmt line per event (`ts=... level=... logger=... msg=... key=value`)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO


def _quote(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char in text for char in ' ="\n') else text


class LogfmtFormatter(logging.Formatter):
    """Format a log record as one logfmt line, with the record's extra fields as key=value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        """Render `record`; the exception, when there is one, goes on the same line."""
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        parts = [
            f"ts={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"msg={_quote(record.getMessage())}",
        ]
        parts.extend(f"{key}={_quote(value)}" for key, value in getattr(record, "fields", {}).items())
        if record.exc_info:
            parts.append(f"exc={_quote(self.formatException(record.exc_info))}")
        return " ".join(parts)

```
<!-- fmt:on -->

- **Lines 12 to 14**: `_quote` turns any value into text, and wraps it in quotes (using `json.dumps`, which also escapes special characters) if the text is empty or contains a space, an equals sign, a quote or a newline. `any(char in text for char in ' ="\n')` is `True` if at least one of those characters is present. The expression `A if condition else B` is Python's one-line choice.
- **Lines 17 to 32**: `LogfmtFormatter` extends the standard `logging.Formatter`, the part that turns an event (a `LogRecord`) into text. Overriding `format` replaces its behaviour. `record.created` is when the event happened, in seconds since 1970; `datetime.fromtimestamp(..., tz=UTC).isoformat(timespec="milliseconds")` turns it into text like `2026-10-27T10:00:00.123+00:00`. UTC is the world reference time zone, so logs from different machines line up.
- **Lines 23 to 28** build a list of `key=value` pieces: `ts`, `level`, `logger` (the name of the part of the program that spoke) and `msg`. **Line 29** adds extra fields: `getattr(record, "fields", {})` reads an attribute that may not exist, falling back to an empty dictionary. `parts.extend(generator)` appends many items. **Lines 30 and 31** add the exception text, if an error is being reported. **Line 32** joins the pieces with spaces.

<!-- fmt:off -->
```python
def fields(**values: Any) -> dict[str, Any]:
    """Use as `logger.info("message", extra=fields(job_key=...))` to attach key=value pairs."""
    return {"fields": values}


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Send every log record to `stream` (stderr by default) as logfmt. Safe to call twice."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(LogfmtFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
```
<!-- fmt:on -->

- **Lines 35 to 37**: `fields(**values)`. The two stars collect all the keyword arguments into a dictionary. A caller writes `logger.info("message", extra=fields(job_key="a"))`, and the formatter later finds `fields` on the record.
- **Lines 40 to 46**: `configure_logging` makes a *handler* (where log lines go: `sys.stderr`, the stream for diagnostics, unless a stream is given), gives it the formatter, and installs it on the **root logger**, the one every other logger passes its events up to. `root.handlers[:] = [handler]` *replaces* any existing handlers, so calling the function twice does not print every line twice. `root.setLevel(level)` sets the minimum importance that is shown.

#### `src/small_service/infrastructure/retry.py`: trying again after a failure

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- A network call can fail for a moment and then work. **Retrying with backoff** means: try, wait a little, try again, wait longer each time. **Jitter** is a small random extra wait so that many callers do not all retry at the same instant.
- **Line 15**: `def retry[T](...) -> T` declares a generic function. Whatever type `operation` returns, `retry` returns the same type.
- **Lines 16 to 22**: parameters. `operation` is the thing to try, `retriable` is a tuple of error classes worth retrying (`tuple[type[Exception], ...]`), `attempts` defaults to 4, `base_delay_seconds` to 0.2. `sleep` and `jitter` are injected for tests.
- **Lines 27 and 28**: refuse nonsense (`attempts` below 1).
- **Lines 29 to 39**: `for attempt in range(attempts):` repeats with `attempt` taking the values 0, 1, 2, 3. `try: return operation()` returns on success. `except retriable as error:` catches only the listed kinds of error. If this was the last attempt, `raise` with nothing after it re-raises the same error. Otherwise the wait is computed: `base_delay_seconds * 2**attempt * (1 + jitter() / 2)` is 0.2, 0.4, 0.8 seconds, each stretched by up to 50 percent (`2**attempt` is two to the power of `attempt`). A warning is logged, then `sleep(delay)`.
- **Line 40**: the function can never reach here; `raise AssertionError("unreachable")` documents that and keeps the type checker content. `# pragma: no cover` tells the coverage tool not to count it as untested.

#### `src/small_service/infrastructure/postgres_store.py`: the PostgreSQL store

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 7**: `import psycopg` is the library that talks to PostgreSQL ([psycopg.md](psycopg.md)). Only this file in the service imports it. A rule enforced by [import-linter.md](import-linter.md) keeps the domain and application layers free of it.
- **Lines 15 to 20**: the class stores the connection string. **Lines 22 to 26**: `_connect` opens a connection, using `retry` so a brief outage is survived, retrying only when psycopg raises `OperationalError` (the error for "could not connect"). `lambda: ...` makes a tiny nameless function, here one that connects with a five-second timeout.
- **Lines 28 to 34**: `save` runs an `INSERT` statement ([sql.md](sql.md)). `with self._connect() as connection:` opens a connection, and when the block ends successfully the change is committed (made permanent); if an error leaves the block it is rolled back (undone). The four `%s` are **placeholders** and the tuple after the statement holds the four values: they are sent separately, so a value can never be mistaken for SQL.
- **Lines 36 to 44**: `recent` selects the newest rows. `.fetchall()` returns all result rows as a list of tuples. The list comprehension on line 44 turns each tuple back into a `JobRecord`: `for key, recorded_at, duration, finished in rows` unpacks each tuple into four names.
- **Lines 46 to 49**: `ping` runs `SELECT 1`, the smallest possible question, to prove the database answers.

#### `src/small_service/interfaces/cli.py`: the `small-service` command

A **command-line interface (CLI)** lets a person run the program by typing its name and some words (**arguments**).

<!-- fmt:off -->
```python
"""`small-service`: run a job, read the history, check health, smoke-test an installed build."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib import metadata

from small_service.application.queries import is_healthy, recent_runs
from small_service.application.run_job import JobRunner
from small_service.domain.cache import TimedCache
from small_service.domain.errors import DomainError
from small_service.domain.jobs import Job, JobRecord
from small_service.infrastructure.logging import configure_logging, fields
from small_service.infrastructure.postgres_store import PostgresJobStore
from small_service.infrastructure.settings import ConfigurationError, Settings

_log = logging.getLogger("small_service")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """The argument parser; exposed so tests can drive it."""
    parser = argparse.ArgumentParser(prog="small-service", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-job", help="run one job and record it")
    run.add_argument("key", help="job key: 1-64 characters of letters, digits, '.', '-', '_'")
    history = commands.add_parser("history", help="print the newest recorded runs")
    history.add_argument("--limit", type=int, default=5)
    commands.add_parser("health", help="exit 0 when the database answers")
    commands.add_parser("smoke", help="run a job twice (the second from the cache), read it back, print the version")
    commands.add_parser("version", help="print the installed version")
    return parser


def installed_version() -> str:
    """The version of the installed distribution: `0.1.0+g<commit>` for a pipeline build."""
    return metadata.version("cicd-green-main")

```
<!-- fmt:on -->

- **Line 5**: `argparse` is the standard library's argument reader. **Line 22**: `logging.getLogger("small_service")` gets the named logger this module writes to. **Lines 24 to 26**: three constants for **exit codes**. When a program ends it hands a number back to whoever started it: 0 means success, anything else means failure. Here 1 means "the command failed", 2 means "you used it wrongly".
- **Lines 29 to 40**: `build_parser` describes the command. `add_subparsers` creates sub-commands: `run-job KEY`, `history [--limit N]`, `health`, `smoke`, `version`. `add_argument("key", help=...)` adds a required word; `add_argument("--limit", type=int, default=5)` adds an optional named setting converted to a whole number. `required=True` on the sub-commands means omitting one is an error. The function is separate so tests can use it.
- **Lines 43 to 45**: `installed_version` asks the installed package for its version number (`importlib.metadata`).

<!-- fmt:off -->
```python
def _runner(settings: Settings) -> tuple[JobRunner, PostgresJobStore]:
    store = PostgresJobStore(settings.dsn)
    cache: TimedCache[str, JobRecord] = TimedCache(settings.cache_ttl_seconds, time.monotonic)
    runner = JobRunner(
        store=store,
        cache=cache,
        job_factory=Job,
        now=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        timeout_seconds=settings.job_timeout_seconds,
    )
    return runner, store


def _print_record(record: JobRecord, from_cache: bool) -> None:
    source = "cache" if from_cache else "run"
    print(f"{record.job_key}: finished={record.finished} duration_ms={record.duration_ms} source={source}")
```
<!-- fmt:on -->

- **Lines 48 to 59**: `_runner` builds the real objects: the PostgreSQL store, a cache that uses `time.monotonic` as its clock, and the `JobRunner` with `Job` as the job factory, `datetime.now(UTC)` for the time and the settings' timeout. This is where everything is wired together; it is the only place that knows both the real clock and the real database.
- **Lines 62 to 64**: `_print_record` writes one line: `print(f"...")` writes text to the screen (standard output).

<!-- fmt:off -->
```python
def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the exit code instead of exiting, so tests can call it."""
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(installed_version())
        return EXIT_OK
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return EXIT_USAGE
    configure_logging(settings.log_level)
    runner, store = _runner(settings)
    try:
        return _dispatch(args, runner, store)
    except DomainError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except Exception:
        _log.exception("command failed", extra=fields(command=args.command))
        return EXIT_FAILED


def _dispatch(args: argparse.Namespace, runner: JobRunner, store: PostgresJobStore) -> int:
    if args.command == "health":
        healthy = is_healthy(store)
        print("ok" if healthy else "database unreachable")
        return EXIT_OK if healthy else EXIT_FAILED
    if args.command == "run-job":
        _print_record(*runner.run(args.key))
        return EXIT_OK
    if args.command == "history":
        for record in recent_runs(store, args.limit):
            stamp = f"{record.recorded_at:%Y-%m-%d %H:%M:%S}"
            print(f"{record.job_key}: finished={record.finished} duration_ms={record.duration_ms} at={stamp}")
        return EXIT_OK
    return _smoke(runner, store)


def _smoke(runner: JobRunner, store: PostgresJobStore) -> int:
    key = f"smoke-{int(time.time())}"
    first, first_cached = runner.run(key)
    _, second_cached = runner.run(key)
    stored = [record.job_key for record in recent_runs(store, 20)]
    ok = first.finished and not first_cached and second_cached and stored.count(key) == 1
    summary = f"first_cached={first_cached} second_cached={second_cached} stored={stored.count(key)}"
    print(f"version={installed_version()} {summary}")
    return EXIT_OK if ok else EXIT_FAILED
```
<!-- fmt:on -->

- **Lines 67 to 87**: `main` is the entry point. It returns an exit code instead of ending the program itself, so a test can call it and check the number. `argv: Sequence[str] | None = None` lets a test pass the words; `None` makes `parse_args` use the real command line. The `version` command is answered before settings are loaded, so it works without a database password. `Settings.from_env()` failing prints `configuration error: ...` to `sys.stderr` and returns 2. Then logging is set up, `_dispatch` runs, and the two `except` blocks sort failures: a `DomainError` is the caller's mistake (print a calm message, return 2); anything else is logged with its full trace by `_log.exception` and returns 1.
- **Lines 90 to 103**: `_dispatch` chooses what to do for each sub-command. `health` prints `ok` or `database unreachable` and returns 0 or 1. `run-job` prints the record; the leading `*` in `_print_record(*runner.run(args.key))` spreads the returned tuple into two arguments. `history` prints each record with its time formatted by `f"{record.recorded_at:%Y-%m-%d %H:%M:%S}"` (the part after the colon is a date format).
- **Lines 106 to 114**: `_smoke` is a self-test of an installed build. It runs a job twice with the same key, reads the history back, and prints `version=... first_cached=False second_cached=True stored=1`. It succeeds only if the first run finished and was not cached, the second was cached, and exactly one row was stored. `int(time.time())` makes the key unique per second.
- In `pyproject.toml`, `small-service = "small_service.interfaces.cli:main"` tells the installer to create a command named `small-service` that calls this `main` ([toml.md](toml.md)).

### The pipeline: `pipeline/`

#### `pipeline/__init__.py` and `pipeline/__main__.py`

<!-- fmt:off -->
```python
"""The pipeline's own code: versioning, checksums, the run log, flaky-test detection, workflow lint, the local runner.

The same commands run in GitHub Actions (see .github/workflows/ci.yml) and on a laptop (`make run`).
"""
```
<!-- fmt:on -->

The package's docstring (four lines). It says the same commands run in GitHub Actions and on a laptop (`make run`).

<!-- fmt:off -->
```python
"""`python -m pipeline`."""

import sys

from pipeline.cli import main

sys.exit(main())
```
<!-- fmt:on -->

- A package that contains a file named `__main__.py` can be *run*: typing `python -m pipeline` (the `-m` means "run this module") runs this file.
- **Line 3** imports `sys`, the module for talking to the interpreter itself. **Line 5** imports the function `main` from `pipeline/cli.py`.
- **Line 7**: `main()` runs the command-line program and returns an exit code (a number; 0 means success). `sys.exit(number)` ends the whole program and hands that number to whoever started it, so scripts and `make` can tell whether the command worked.

#### `pipeline/cli.py`: the command `python -m pipeline`

<!-- fmt:off -->
```python
"""`python -m pipeline <command>`: the pipeline's steps, the same on a laptop and in GitHub Actions."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from pipeline.adapters import builder, gate, git, github, local_runner
from pipeline.adapters.process import Outcome
from pipeline.core import checksum, contract, flaky, ghruns, protection, runlog, workflow
from pipeline.core.version import base_version, build_version

_log = logging.getLogger("pipeline")
ROOT = Path(__file__).resolve().parent.parent
QUARANTINE_JOBS = ("quarantine",)
```
<!-- fmt:on -->

- **Lines 5 to 11** are imports from the standard library: `argparse` (reads the command line), `json`, `logging`, `shlex` (splits a string into words the way a shell does), `sys`, `Sequence` (a type hint meaning "a list-like thing") and `Path`. `pathlib.Path` represents a file or folder location as an object: `Path("a") / "b"` joins parts with the right slash, `.read_text()` reads a file, `.glob("*.yml")` finds files by pattern.
- **Lines 13 to 16** import the pipeline's own parts. `from pipeline.adapters import builder, gate, git, github, local_runner` imports five modules at once. The list shows the layering: the CLI (outermost) uses both adapters and core.
- **Line 18** gets a logger named `pipeline`. **Line 19**: `Path(__file__)` is the location of this very file (`__file__` is a name Python provides); `.resolve()` makes it absolute; `.parent.parent` goes up two folders, from `pipeline/cli.py` to the repository root. **Line 20**: the names of jobs allowed to fail without failing the pipeline: only `quarantine`.

<!-- fmt:off -->
```python
def build_parser() -> argparse.ArgumentParser:
    """The argument parser; exposed so tests can drive it."""
    parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="print the version this commit would be built as")
    commands.add_parser("build", help="build the wheel once and write dist/SHA256SUMS")
    verify = commands.add_parser("verify", help="check an artifact's SHA-256 (exit 1 on a mismatch)")
    verify.add_argument("artifact", type=Path)
    verify.add_argument("--expected", required=True, help="the digest the build job reported")
    verify.add_argument("--job", default="job", help="the job name to print")
    run = commands.add_parser("run", help="run the whole pipeline locally and append a row to runs.csv")
    run.add_argument("--variant", choices=("parallel", "sequential"), default="parallel")
    run.add_argument("--only", help="comma-separated jobs to run (build, lint, unit, integration, quarantine)")
    run.add_argument("--include-quarantined", action="store_true", help="run quarantined tests inside the unit job")
    run.add_argument("--label", default="", help="the name this run gets in runs.csv (default: the variant)")
    run.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    hunt = commands.add_parser("hunt", help="run the domain tests with the quarantined test N times on one commit")
    hunt.add_argument("--runs", type=int, default=40)
    hunt.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    bench = commands.add_parser("bench", help="run both variants N times and print the before and after table")
    bench.add_argument("--runs", type=int, default=5)
    bench.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    report = commands.add_parser("flaky", help="find flaky tests in the run log")
    report.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    report.add_argument("--variant", help="only rows of this variant")
    importer = commands.add_parser("import-gh-runs", help="convert `gh run list --json ...` output into run-log rows")
    importer.add_argument("json_file", type=Path)
    importer.add_argument("--runs-csv", type=Path, default=ROOT / "runs.csv")
    protect = commands.add_parser("protection", help="print (or apply) the branch-protection settings for main")
    protect.add_argument("--apply", metavar="OWNER/REPO", help="apply them with the gh CLI")
    commands.add_parser("lint-workflows", help="check every workflow against the rules in pipeline/core/workflow.py")
    commands.add_parser("check-contract", help="check the README's pipeline contract")
    status = commands.add_parser("gate", help="run the checks on a commit and, if they pass, post its green status")
    status.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="the repository holding the commit (default: here)"
    )
    status.add_argument("--remote", default="origin")
    status.add_argument("--sha", required=True)
    status.add_argument("--token", required=True, help="the remote's CI token")
    status.add_argument("--checks", default="make check", help="the checks to run on the commit, as one string")
    return parser
```
<!-- fmt:on -->

- `argparse.ArgumentParser(prog=..., description=__doc__)` creates the parser; `__doc__` is the file's docstring. `parser.add_subparsers(dest="command", required=True)` makes sub-commands, and `dest="command"` says the chosen sub-command's name is stored in `args.command`.
- Each `commands.add_parser("name", help="...")` registers one sub-command and its help text (shown by `--help`). Most take options:
  - `add_argument("artifact", type=Path)` is a required positional word, converted to a `Path`.
  - `add_argument("--expected", required=True)` is a required named option.
  - `add_argument("--variant", choices=("parallel", "sequential"), default="parallel")` accepts only those two words, defaulting to `parallel`.
  - `action="store_true"` makes a flag with no value (`--include-quarantined`) that is `False` unless present.
  - `type=int` converts the text to a whole number.
  - `default=ROOT / "runs.csv"` sets the default location of the run log.
  - `metavar="OWNER/REPO"` only changes how the placeholder is shown in help.
- The sub-commands are: `version`, `build`, `verify` (check a file's checksum), `run` (the whole pipeline locally), `hunt` (repeat the domain tests many times), `bench` (time both pipeline variants), `flaky` (read the log for flaky tests), `import-gh-runs` (turn `gh run list` output into log rows), `protection` (print or apply branch protection), `lint-workflows`, `check-contract` and `gate` (run checks on a commit and, if they pass, post a green status).

<!-- fmt:off -->
```python
def _print_outcomes(outcomes: Sequence[Outcome], record: runlog.RunRecord) -> None:
    for outcome in sorted(outcomes, key=lambda item: item.name):
        required = outcome.name in local_runner.REQUIRED or outcome.name == "sequential"
        verdict = "passed" if outcome.ok else "FAILED"
        note = "(required)" if required else "(non-blocking)"
        print(
            f"{outcome.name:<12} {verdict:<7} {runlog.format_duration(outcome.seconds):>7}  {note}  log: {outcome.log}"
        )
    duration = runlog.format_duration(record.seconds)
    print(f"run {record.run}: commit {record.commit} {record.variant} {duration} {record.result}")


def _run(args: argparse.Namespace) -> int:
    only = frozenset(args.only.split(",")) if args.only else None
    options = local_runner.RunOptions(args.variant, only, args.include_quarantined, args.label)
    outcomes, record = local_runner.run_pipeline(ROOT, options, args.runs_csv)
    _print_outcomes(outcomes, record)
    return 0 if record.result == runlog.SUCCESS else 1
```
<!-- fmt:on -->

- `_print_outcomes` prints one line per finished job. `sorted(outcomes, key=lambda item: item.name)` sorts by name: `lambda item: item.name` is a tiny function that says how to sort. The line `f"{outcome.name:<12} {verdict:<7} ..."` uses format codes after the colon: `:<12` pads on the right to 12 characters (left-aligned), `:>7` pads on the left (right-aligned). `required` is true for the four required jobs (and the `sequential` variant, a single job).
- `_run` splits `--only` at commas into a `frozenset` (an unchangeable set), builds the options, runs the pipeline and prints. It returns 0 if the run succeeded and 1 otherwise: `0 if condition else 1`.

<!-- fmt:off -->
```python
def _bench(args: argparse.Namespace) -> int:
    for variant in ("sequential", "parallel"):
        for _ in range(args.runs):
            outcomes, record = local_runner.run_pipeline(ROOT, local_runner.RunOptions(variant), args.runs_csv)
            _print_outcomes(outcomes, record)
    records = runlog.read(args.runs_csv)
    print(runlog.format_comparison(runlog.summarize(records, "sequential"), runlog.summarize(records, "parallel")))
    return 0


def _lint_workflows() -> int:
    problems = 0
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        document = workflow.load(path.read_text())
        required = protection.REQUIRED_CHECKS if path.name == "ci.yml" else ()
        for finding in workflow.lint(document, required, QUARANTINE_JOBS):
            print(f"{path.name}: {finding.code} {finding.message}")
            problems += 1
    for path in sorted((ROOT / ".github" / "actions").glob("*/action.yml")):
        for finding in workflow.lint_composite(workflow.load(path.read_text())):
            print(f"{path.parent.name}/action.yml: {finding.code} {finding.message}")
            problems += 1
    print("workflows ok" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0
```
<!-- fmt:on -->

- `_bench`: two nested `for` loops run each variant `args.runs` times. The loop variable `_` (an underscore) is the convention for "I don't use this value". Afterwards it reads the log and prints the before-and-after table.
- `_lint_workflows`: `(ROOT / ".github" / "workflows").glob("*.yml")` finds every workflow file. `workflow.load` parses a file ([yaml.md](yaml.md)). Only `ci.yml` has required checks. For each finding it prints `file: CODE message` and counts a problem. A second loop checks the composite actions, which are small reusable step lists. The function returns 1 if there was any problem.

<!-- fmt:off -->
```python
def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    match args.command:
        case "version":
            print(
                build_version(
                    base_version((ROOT / "pyproject.toml").read_text()), git.head_sha(ROOT), git.is_dirty(ROOT)
                )
            )
        case "build":
            artifact = builder.build_wheel(ROOT, ROOT / "dist")
            print(f"build: sha256 {artifact.sha256}  dist/{artifact.path.name}")
        case "verify":
            try:
                digest = checksum.verify(args.artifact, args.expected)
            except checksum.ChecksumMismatchError as error:
                print(f"{args.job}: sha256 MISMATCH: {error}", file=sys.stderr)
                return 1
            print(f"{args.job}: sha256 {digest}  verified")
        case "run":
            return _run(args)
        case "bench":
            return _bench(args)
        case "hunt":
            records = local_runner.hunt(ROOT, args.runs, args.runs_csv)
            failed = sum(1 for record in records if record.result == runlog.FAILURE)
            print(f"{len(records)} runs on commit {records[0].commit if records else '-'}: {failed} failed")
        case "flaky":
            records = runlog.read(args.runs_csv)
            print(
                flaky.format_report(
                    [record for record in records if not args.variant or record.variant == args.variant]
                )
            )
        case "import-gh-runs":
            for record in ghruns.parse_gh_runs(args.json_file.read_text()):
                runlog.append(args.runs_csv, record)
        case "protection":
            payload = protection.branch_protection()
            if args.apply:
                github.apply_branch_protection(args.apply, payload)
            else:
                print(json.dumps(payload, indent=2))
        case "lint-workflows":
            return _lint_workflows()
        case "check-contract":
            problems = contract.check((ROOT / "README.md").read_text())
            print("\n".join(problems) if problems else "contract ok")
            return 1 if problems else 0
        case "gate":
            if not gate.run_checks_on_commit(args.repo, args.sha, shlex.split(args.checks)):
                print(f"gate: checks failed for {args.sha[:7]}; no status posted", file=sys.stderr)
                return 1
            gate.post_green_status(args.repo, args.remote, args.sha, args.token)
            print(f"gate: checks passed; posted green status for {args.sha[:7]}")
    return 0
```
<!-- fmt:on -->

- `main` parses the arguments, sets up simple logging, and then uses `match args.command:`. A **`match` statement** (Python 3.10 and newer) compares a value with several `case` patterns and runs the first that fits, like a tidy chain of `if`/`elif`.
- `case "version"`: prints the version this commit would get. It reads `pyproject.toml`, asks Git for the current commit and whether the tree has uncommitted changes, and combines them ([python-packaging.md](python-packaging.md)).
- `case "build"`: builds the wheel and prints its checksum. `case "verify"`: calls `checksum.verify`; a mismatch is caught (`except checksum.ChecksumMismatchError as error`), printed to `sys.stderr` with `file=sys.stderr`, and the command returns 1.
- `case "hunt"`: runs the domain tests repeatedly; `sum(1 for record in records if record.result == runlog.FAILURE)` counts failures by adding 1 for each failed record (a *generator expression*). The conditional inside the f-string prints `-` when there are no records.
- `case "flaky"`: reads the log, filters by variant, prints the report. `case "import-gh-runs"`: appends one log row per GitHub run. `case "protection"`: prints the JSON with `json.dumps(payload, indent=2)` (indent for readability) or applies it with `gh`. `case "check-contract"`: prints either `contract ok` or the list of problems, joined by newlines. `case "gate"`: runs the checks; `shlex.split(args.checks)` turns the one-string command into a list of words. If the checks pass it posts a green status. Any case that does not return falls through to `return 0` on the last line.

#### `pipeline/core/version.py`: one commit, one version

<!-- fmt:off -->
```python
"""Version a build from its commit, so one commit always gives one version (`0.1.0+3fa91bc`)."""

from __future__ import annotations

import re
import tomllib

_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_VERSION_LINE = re.compile(r'^(version\s*=\s*)"[^"]*"', re.MULTILINE)


class VersionError(ValueError):
    """A version or commit could not be used."""


def base_version(pyproject_text: str) -> str:
    """The `project.version` of a pyproject.toml, which must be MAJOR.MINOR.PATCH."""
    version = tomllib.loads(pyproject_text)["project"]["version"]
    if not _SEMVER.match(version):
        raise VersionError(f"project.version must be MAJOR.MINOR.PATCH, got {version!r}")
    return str(version)


def build_version(base: str, commit_sha: str, dirty: bool = False) -> str:
    """`base+<first 7 characters of the commit>`, with `.dirty` when the working tree has uncommitted changes."""
    if not _SEMVER.match(base):
        raise VersionError(f"base version must be MAJOR.MINOR.PATCH, got {base!r}")
    if not _SHA.match(commit_sha):
        raise VersionError(f"commit must be 7 to 40 lowercase hex characters, got {commit_sha!r}")
    return f"{base}+{commit_sha[:7]}{'.dirty' if dirty else ''}"


def stamp_pyproject(pyproject_text: str, version: str) -> str:
    """Replace the first `version = "..."` line (the one in `[project]`) with `version`."""
    stamped, count = _VERSION_LINE.subn(lambda match: f'{match.group(1)}"{version}"', pyproject_text, count=1)
    if count != 1:
        raise VersionError("pyproject.toml has no version line to stamp")
    return stamped
```
<!-- fmt:on -->

- **Line 6**: `tomllib` is the standard library's reader for TOML files ([toml.md](toml.md)).
- **Lines 8 to 10**: three compiled patterns. `_SHA`: 7 to 40 characters from `0-9a-f` (a commit id). `_SEMVER`: three numbers joined by dots (`\d+` means one or more digits). `_VERSION_LINE`: a line that starts with `version =` and a quoted value; `re.MULTILINE` lets `^` match at the start of every line, not only of the whole text. The parentheses make a **group**, a part of the match we can reuse.
- **Lines 17 to 22**: `base_version` parses the TOML text (`tomllib.loads`), digs out `["project"]["version"]` (a dictionary inside a dictionary), checks it looks like `0.1.0`, and returns it.
- **Lines 25 to 31**: `build_version` checks both inputs and builds `0.1.0+3fa91bc`. `commit_sha[:7]` is a **slice**: characters from the start up to (not including) position 7. `'.dirty' if dirty else ''` appends `.dirty` when the working tree has uncommitted changes. The part after `+` is a *local version label* that Python packaging allows.
- **Lines 34 to 39**: `stamp_pyproject` replaces the first `version = "..."` line. `subn(replacement, text, count=1)` returns the new text and how many replacements it made. `lambda match: ...` builds the replacement from the matched group so everything else on the line stays. If `count != 1` it raises: the file had no version line.

#### `pipeline/core/checksum.py`: a fingerprint of a file

A **checksum** (here SHA-256) is a long number computed from a file's bytes. Any change to the file, even one bit, gives a completely different number, so two files with the same checksum are the same file.

<!-- fmt:off -->
```python
"""SHA-256 of a build artifact, and the check every job that uses it must pass."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


class ChecksumMismatchError(Exception):
    """The artifact on disk is not the artifact the build job produced."""


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sums_line(path: Path, digest: str) -> str:
    """One `sha256sum`-compatible line: `<digest>  <file name>`."""
    return f"{digest}  {path.name}"


def parse_sums(text: str) -> dict[str, str]:
    """Parse the output of `sha256sum` into `{file name: digest}`."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            sums[name.strip()] = digest.strip()
    return sums


def verify(path: Path, expected: str) -> str:
    """Return the digest when `path` matches `expected`; raise `ChecksumMismatchError` otherwise."""
    actual = sha256_of(path)
    if actual != expected.strip().lower():
        raise ChecksumMismatchError(f"{path.name}: expected sha256 {expected}, found {actual}")
    return actual
```
<!-- fmt:on -->

- **Line 5**: `hashlib` computes checksums. **Line 8**: `_CHUNK = 1024 * 1024` is one mebibyte.
- **Lines 11 to 12**: `ChecksumMismatchError(Exception)` is the error raised when a file is not what was expected.
- **Lines 15 to 21**: `sha256_of` opens the file in **binary** mode (`"rb"`: read bytes, not text). `while chunk := handle.read(_CHUNK):` uses the **walrus operator** `:=`, which assigns and tests in one step: read a piece, and keep going while the piece is not empty. Each piece is fed to the running hash (`digest.update(chunk)`), so even a huge file never sits whole in memory. `hexdigest()` returns the result as 64 hexadecimal characters.
- **Lines 24 to 26**: `sums_line` formats the line `<digest>  <file name>` (two spaces) that the `shasum -c` command understands.
- **Lines 29 to 36**: `parse_sums` reads such lines back into a dictionary `{file name: digest}`. `line.partition("  ")` splits at the first double space into three parts; `digest, _, name` keeps the first and last.
- **Lines 39 to 44**: `verify` computes the file's checksum and compares it with the expected one (`.strip().lower()` ignores spaces and case). A difference raises `ChecksumMismatchError` with both values; otherwise it returns the digest.

#### `pipeline/core/runlog.py`: the run log

<!-- fmt:off -->
```python
"""The run log (`runs.csv`): one row per pipeline run, and the numbers the lesson asks for."""

from __future__ import annotations

import csv
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

HEADER = ("run", "commit", "seconds", "result", "variant", "failed_tests", "message")
SUCCESS = "success"
FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class RunRecord:
    """One pipeline run. `failed_tests` are test ids joined by `;`; `message` is the first failure's first line."""

    run: int
    commit: str
    seconds: float
    result: str
    variant: str
    failed_tests: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class Summary:
    """Count, median and slowest duration of a set of runs."""

    variant: str
    runs: int
    median_seconds: float
    slowest_seconds: float


def read(path: Path) -> list[RunRecord]:
    """Read a run log; a missing file is an empty log."""
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return [
            RunRecord(
                run=int(row["run"]),
                commit=row["commit"],
                seconds=float(row["seconds"]),
                result=row["result"],
                variant=row.get("variant", ""),
                failed_tests=tuple(filter(None, row.get("failed_tests", "").split(";"))),
                message=row.get("message", ""),
            )
            for row in csv.DictReader(handle)
        ]


def append(path: Path, record: RunRecord) -> None:
    """Append one row, writing the header first when the file is new."""
    is_new = not path.exists() or path.stat().st_size == 0
```
<!-- fmt:on -->

- **Lines 5 to 10**: `csv` reads and writes comma-separated tables ([csv.md](csv.md)); `statistics` has the median. **Line 12**: `HEADER` is a tuple of the seven column names. **Lines 13 to 14**: the two possible results, `success` and `failure`.
- **Lines 17 to 26**: `RunRecord` is a frozen dataclass: one pipeline run (number, commit, seconds, result, variant, the failed test ids and the first message line). Fields with `= ()` or `= ""` have defaults and can be left out.
- **Lines 29 to 36**: `Summary`, the count, median and slowest time of a set of runs.
- **Lines 39 to 54**: `read`. `if not path.exists(): return []` treats a missing file as an empty log. `csv.DictReader(handle)` gives each row as a dictionary keyed by the header. The list comprehension builds a `RunRecord` per row: `int(row["run"])` and `float(row["seconds"])` convert text to numbers; `row.get("variant", "")` tolerates a missing column; `tuple(filter(None, row.get(...).split(";")))` splits the failed-test cell at semicolons and throws away empty pieces.

<!-- fmt:off -->
```python

def append(path: Path, record: RunRecord) -> None:
    """Append one row, writing the header first when the file is new."""
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(HEADER)
        writer.writerow(
            [
                record.run,
                record.commit,
                f"{record.seconds:.1f}",
                record.result,
                record.variant,
                ";".join(record.failed_tests),
                record.message.replace("\n", " ")[:160],
            ]
        )


def next_run_number(records: Sequence[RunRecord]) -> int:
    """The number for the next row: one more than the highest so far."""
    return max((record.run for record in records), default=0) + 1


def summarize(records: Iterable[RunRecord], variant: str) -> Summary | None:
    """Median and slowest duration of the runs of one variant; None when there are none."""
    seconds = [record.seconds for record in records if record.variant == variant]
    if not seconds:
        return None
    return Summary(variant, len(seconds), statistics.median(seconds), max(seconds))


def format_duration(seconds: float) -> str:
    """`1m 05s` for 65 seconds, `42s` under a minute."""
    whole = round(seconds)
    minutes, rest = divmod(whole, 60)
    return f"{minutes}m {rest:02d}s" if minutes else f"{rest}s"


def format_comparison(before: Summary | None, after: Summary | None) -> str:
    """The before-and-after table of step 3, and whether the median is under half the starting time."""
    lines = [f"{'version':<24}{'runs':<7}{'median':<10}slowest"]
    for label, summary in (("1. sequential", before), ("3. cached and parallel", after)):
        if summary is not None:
            lines.append(
                f"{label:<24}{summary.runs:<7}{format_duration(summary.median_seconds):<10}"
                f"{format_duration(summary.slowest_seconds)}"
            )
    if before is not None and after is not None:
        verdict = "yes" if after.median_seconds < before.median_seconds / 2 else "no"
        lines.append(f"median under half of the starting time: {verdict}")
    return "\n".join(lines)
```
<!-- fmt:on -->

- **Lines 57 to 74**: `append` writes one row. `is_new` is true if the file is missing or empty, in which case the header is written first. `open("a", newline="")` opens for **appending** (adding at the end); `newline=""` stops Python changing line endings that the csv module handles. `f"{record.seconds:.1f}"` rounds to one decimal. The message has newlines replaced by spaces and is cut to 160 characters with a slice.
- **Lines 77 to 79**: `next_run_number` is the highest run number plus one; `max(..., default=0)` handles an empty log.
- **Lines 82 to 87**: `summarize` takes the durations of one variant and returns the count, `statistics.median` (the middle value) and the slowest, or `None` if there are none.
- **Lines 90 to 93**: `format_duration`. `divmod(whole, 60)` returns the quotient and remainder at once: minutes and seconds. `f"{rest:02d}"` pads to two digits. The result looks like `1m 05s` or `42s`.
- **Lines 96 to 110**: `format_comparison` builds the before-and-after table. `f"{'version':<24}{'runs':<7}..."` aligns columns. It ends with `median under half of the starting time: yes/no`, comparing `after.median_seconds < before.median_seconds / 2`.

#### `pipeline/core/flaky.py`: finding a flaky test in the log

A **flaky test** sometimes passes and sometimes fails on the same code. Rerunning until it is green hides it; counting how often it fails shows it.

<!-- fmt:off -->
```python
"""Find a flaky test in the run log instead of rerunning until green."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pipeline.core.runlog import FAILURE, SUCCESS, RunRecord


@dataclass(frozen=True, slots=True)
class FailedTest:
    """A failed test case from a JUnit report."""

    test_id: str
    message: str


@dataclass(frozen=True, slots=True)
class FlakeReport:
    """What the log says about one failing test."""

    test_id: str
    failures: int
    runs: int
    messages: tuple[tuple[str, int], ...]

    @property
    def rate(self) -> float:
        """Failures divided by runs."""
        return self.failures / self.runs if self.runs else 0.0


def flaky_commits(records: Iterable[RunRecord]) -> list[str]:
    """Commits that have at least one passing and one failing run: the same code gave both answers."""
    outcomes: dict[str, set[str]] = defaultdict(set)
    for record in records:
        outcomes[record.commit].add(record.result)
    return sorted(commit for commit, seen in outcomes.items() if {SUCCESS, FAILURE} <= seen)


def flake_reports(records: Sequence[RunRecord]) -> list[FlakeReport]:
    """For every test that failed in some run, its failure rate and the messages it failed with."""
    failing_ids = {test for record in records for test in record.failed_tests}
    reports = []
    for test_id in sorted(failing_ids):
        failed = [record for record in records if test_id in record.failed_tests]
        messages = Counter(record.message for record in failed if record.message)
        reports.append(FlakeReport(test_id, len(failed), len(records), tuple(messages.most_common())))
    return reports


def parse_junit_failures(xml_text: str) -> list[FailedTest]:
    """Failed or errored test cases of a JUnit XML report (pytest's `--junitxml`)."""
    root = ET.fromstring(xml_text)  # noqa: S314 - our own pytest report, not untrusted input
    failures = []
    for case in root.iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        if problem is not None:
            test_id = f"{case.get('classname', '').replace('.', '/')}.py::{case.get('name', '')}"
            first_line = (problem.get("message") or "").splitlines()[0] if problem.get("message") else ""
            failures.append(FailedTest(test_id, first_line))
    return failures


def format_report(records: Sequence[RunRecord]) -> str:
    """The text `make flaky-report` prints: the commits that disagree with themselves, then each test's failure rate."""
    commits = flaky_commits(records)
    lines = ["commits with both a pass and a fail:", *(f"  {commit}" for commit in commits or ["none"])]
    for report in flake_reports(records):
        lines.append(f"failure rate of {report.test_id}: {report.failures} of {report.runs} runs ({report.rate:.0%})")
        lines.extend(f"  failed {count} times with: {message}" for message, count in report.messages)
    return "\n".join(lines)
```
<!-- fmt:on -->

- **Line 5**: `xml.etree.ElementTree` reads XML files ([junit-xml.md](junit-xml.md)). **Line 6**: `Counter` counts items; `defaultdict` is a dictionary that creates a default value (here an empty set) the first time a key is used.
- **Lines 13 to 18**: `FailedTest`, a test id and the first line of its message. **Lines 21 to 33**: `FlakeReport` with a computed property `rate`: failures divided by runs, `0.0` if there are no runs.
- **Lines 36 to 41**: `flaky_commits` builds `commit -> set of results seen`. A commit is flaky when its set contains both `success` and `failure`: `{SUCCESS, FAILURE} <= seen` asks "is this two-item set a subset of `seen`?". The same code gave two answers, which is the definition of flaky. `sorted(...)` returns a list in order.
- **Lines 44 to 52**: `flake_reports` collects every test id that failed anywhere, counts for each how many runs it failed in, and tallies its messages with `Counter(...).most_common()` (most frequent first).
- **Lines 55 to 65**: `parse_junit_failures` parses a test report. `ET.fromstring(xml_text)` builds a tree; `root.iter("testcase")` walks all test cases; `case.find("failure")` looks for a child tag and returns `None` when there is none. A test id is rebuilt as `path/to/file.py::test_name`: `classname.replace(".", "/")` converts dots to slashes. Only the first line of the message is kept (`splitlines()[0]`). The `# noqa: S314` comment says why parsing XML is fine here: it is our own test report, not text from a stranger.
- **Lines 68 to 75**: `format_report` produces the text of `make flaky-report`. `*(f"  {commit}" for commit in commits or ["none"])` unpacks a generator into the list; `commits or ["none"]` is the commits, or `["none"]` if the list is empty. `{report.rate:.0%}` formats a fraction as a percentage.

#### `pipeline/core/ghruns.py`: GitHub's run history as log rows

<!-- fmt:off -->
```python
"""Turn `gh run list --json databaseId,headSha,conclusion,createdAt,updatedAt` into run-log rows."""

from __future__ import annotations

import json
from datetime import datetime

from pipeline.core.runlog import FAILURE, SUCCESS, RunRecord


def parse_gh_runs(json_text: str, variant: str = "github") -> list[RunRecord]:
    """Completed runs only, oldest first. A conclusion of `success` is a pass; every other conclusion is a failure."""
    rows = json.loads(json_text)
    records = []
    for row in sorted(rows, key=lambda item: item["createdAt"]):
        if not row.get("conclusion"):
            continue  # still running
        started = datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(row["updatedAt"].replace("Z", "+00:00"))
        records.append(
            RunRecord(
                run=int(row["databaseId"]),
                commit=str(row["headSha"])[:7],
                seconds=(ended - started).total_seconds(),
                result=SUCCESS if row["conclusion"] == "success" else FAILURE,
                variant=variant,
            )
        )
    return records
```
<!-- fmt:on -->

- **Lines 11 to 29**: `parse_gh_runs` takes the JSON that `gh run list --json ...` prints ([json.md](json.md)). `json.loads` turns text into Python lists and dictionaries. Runs are sorted by `createdAt` (ISO 8601 date text sorts correctly as plain text). A run with no `conclusion` is still going and is skipped (`continue` jumps to the next loop item). `datetime.fromisoformat(... .replace("Z", "+00:00"))` parses the times (`Z` means UTC). The duration is `(ended - started).total_seconds()`: subtracting two datetimes gives a `timedelta`. The commit is cut to 7 characters; anything other than `success` counts as a failure.

#### `pipeline/core/protection.py`: the branch-protection payload

<!-- fmt:off -->
```python
"""The branch-protection settings that make the pipeline a required check on `main`."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

REQUIRED_CHECKS = ("build", "lint", "unit", "integration")


def branch_protection(checks: Sequence[str] = REQUIRED_CHECKS) -> dict[str, Any]:
    """The JSON body for `PUT /repos/{owner}/{repo}/branches/main/protection`.

    `strict` is "branch must be up to date", `enforce_admins` applies the rules to the owner too, and the pull request
    rule refuses direct pushes. The check names are job names, not the workflow name.
    """
    if not checks:
        raise ValueError("at least one required check is needed")
    return {
        "required_status_checks": {"strict": True, "contexts": list(checks)},
        "enforce_admins": True,
        "required_pull_request_reviews": {"required_approving_review_count": 0},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }
```
<!-- fmt:on -->

- **Line 8**: `REQUIRED_CHECKS = ("build", "lint", "unit", "integration")` is the list of job names GitHub must require.
- **Lines 11 to 26**: `branch_protection` returns a dictionary shaped like the body of GitHub's API call that sets protection on a branch. `"strict": True` means the branch must be up to date before merging; `"enforce_admins": True` applies the rules to the repository owner too; `required_approving_review_count: 0` requires a pull request without requiring a person to approve it; `"restrictions": None` (JSON `null`) adds no list of who may push; force pushes and deletion are off. `list(checks)` copies the tuple into a list because JSON has lists, not tuples. An empty list of checks raises `ValueError`.

#### `pipeline/core/contract.py`: checking the README's ten lines

<!-- fmt:off -->
```python
"""Check the README's pipeline contract: short, concrete, and it says what to do when `main` is red."""

from __future__ import annotations

import re

_HEADING = re.compile(r"^## ")
CONTRACT_HEADING = "## The pipeline's contract"
MAX_LINES = 10


def contract_lines(readme: str) -> list[str]:
    """The non-empty lines under the contract heading, up to the next `## ` heading."""
    lines = readme.splitlines()
    try:
        start = lines.index(CONTRACT_HEADING) + 1
    except ValueError:
        return []
    body = []
    for line in lines[start:]:
        if _HEADING.match(line):
            break
        if line.strip():
            body.append(line)
    return body


def check(readme: str) -> list[str]:
    """Problems with the contract; an empty list means it fits ten lines and states the red-main rule."""
    body = contract_lines(readme)
    text = " ".join(body).lower()
    problems = []
    if not body:
        problems.append(f"no section titled {CONTRACT_HEADING!r}")
    if len(body) > MAX_LINES:
        problems.append(f"the contract has {len(body)} lines, the limit is {MAX_LINES}")
    if "red `main`" not in text or "fix" not in text or "revert" not in text:
        problems.append("it must say that a red `main` is fixed or reverted before new work merges")
    if not re.search(r"\d+ minutes", text):
        problems.append("it must give the time the required checks should take, in minutes")
    return problems
```
<!-- fmt:on -->

- **Line 8**: `_HEADING` matches a line that starts with `## ` (a Markdown level-2 heading). **Lines 9 and 10** name the heading to find and the limit of ten lines.
- **Lines 13 to 26**: `contract_lines` splits the README into lines, finds the heading with `lines.index(...)` (which raises `ValueError` when absent, caught to return `[]`), then collects the non-empty lines until the next `## ` heading. `line.strip()` is empty text (false) for a blank line.
- **Lines 29 to 41**: `check` returns a list of problems: no section, more than ten lines, missing the words "red `main`", "fix" and "revert", or no `N minutes` figure (`re.search(r"\d+ minutes", text)`). An empty list means the contract is fine. `" ".join(body).lower()` makes one lower-case string to search.

#### `pipeline/core/workflow.py`: the workflow linter

<!-- fmt:off -->
```python
"""Lint a GitHub Actions workflow for the mistakes the lesson lists, so they fail a test and not a merge."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

_PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_LATEST = re.compile(r"(:latest\b|@(main|master|latest)\b)")


@dataclass(frozen=True, slots=True)
class Finding:
    """One problem: a stable code and what to change."""

    code: str
    message: str


def load(text: str) -> Mapping[str, Any]:
    """Parse a workflow. PyYAML reads the key `on` as the boolean True; put it back under "on"."""
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("a workflow must be a mapping")
    if True in document:
        document["on"] = document.pop(True)
    return document


def job_names(document: Mapping[str, Any]) -> dict[str, str]:
    """Map job id to the check name GitHub reports: the job's `name`, or its id when it has none."""
    return {job_id: str(job.get("name", job_id)) for job_id, job in document.get("jobs", {}).items()}

```
<!-- fmt:on -->

- **Line 10**: `import yaml` is PyYAML ([yaml.md](yaml.md)). **Line 12**: `_PINNED` matches `owner/name@` followed by exactly 40 hexadecimal characters (a full commit id). **Line 13**: `_LATEST` finds moving names: `:latest`, `@main`, `@master`, `@latest` (`\b` is a word boundary).
- **Lines 16 to 21**: `Finding(code, message)`. **Lines 24 to 31**: `load` parses a workflow with `yaml.safe_load`, which builds only plain data and never runs code. `if True in document` repairs a YAML quirk: the key `on:` is read as the boolean `True`, so it is moved back under the string `"on"`. `isinstance(document, dict)` checks the type.
- **Lines 34 to 36**: `job_names` maps each job id to the name GitHub shows for it, the job's `name:` or else its id: the name branch protection checks.

<!-- fmt:off -->
```python
def lint(document: Mapping[str, Any], required_checks: Sequence[str], quarantine_jobs: Sequence[str]) -> list[Finding]:
    """Check one workflow. An empty list means it passes every rule.

    The trigger rules (WF002, WF003) apply only to a workflow that carries required checks: pass `required_checks=()`
    for any other workflow, such as a scheduled audit.
    """
    findings: list[Finding] = []
    names = set(job_names(document).values())
    for check in required_checks:
        if check not in names:
            findings.append(
                Finding("WF001", f"required check {check!r} is not the name of any job: it would never report")
            )
    triggers = document.get("on", {})
    for event in ("push", "pull_request") if required_checks else ():
        if event not in (triggers if isinstance(triggers, dict | list) else []):
            findings.append(Finding("WF002", f"the workflow does not run on {event}"))
        trigger = triggers.get(event) if isinstance(triggers, dict) else None
        if isinstance(trigger, dict) and ({"paths", "paths-ignore"} & trigger.keys()):
            findings.append(
                Finding("WF003", f"{event} has a paths filter: a skipped workflow never reports its required checks")
            )
    for job_id, job in document.get("jobs", {}).items():
        if job.get("continue-on-error") and job_id not in quarantine_jobs:
            findings.append(Finding("WF004", f"job {job_id!r} has continue-on-error: only the quarantine job may"))
        for step in job.get("steps", []):
            used = step.get("uses")
            if used and not used.startswith("./") and not _PINNED.match(used):
                findings.append(Finding("WF005", f"{used!r} is not pinned to a full commit SHA"))
            if _LATEST.search(str(step.get("uses", "")) + str(step.get("run", ""))):
                findings.append(Finding("WF006", f"job {job_id!r} uses a moving name (latest, main or master)"))
        if _LATEST.search(str(job.get("services", ""))):
            findings.append(Finding("WF006", f"job {job_id!r} uses a service image with a moving tag"))
    permissions = document.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        findings.append(Finding("WF007", "the workflow must set top-level permissions with contents: read"))
    return findings


def lint_composite(document: Mapping[str, Any]) -> list[Finding]:
    """A composite action's steps get the same pinning rules as workflow steps."""
    findings: list[Finding] = []
    for step in document.get("runs", {}).get("steps", []):
        used = step.get("uses")
        if used and not used.startswith("./") and not _PINNED.match(used):
            findings.append(Finding("WF005", f"{used!r} is not pinned to a full commit SHA"))
    return findings
```
<!-- fmt:on -->

`lint` returns a list of `Finding`s; an empty list means the workflow passes. The rules:

- **WF001** (lines 47 to 51): every required check must be the name of a real job, otherwise it would never report and block merging for ever.
- **WF002 and WF003** (lines 52 to 60): for a workflow with required checks, `push` and `pull_request` must be triggers, and neither may have a `paths` or `paths-ignore` filter. A filtered-out workflow never starts and reports nothing, so a required check would hang.
- **WF004** (lines 61 to 63): `continue-on-error` is allowed only on the quarantine job. `job.get("continue-on-error")` is falsy if missing.
- **WF005 and WF006** (lines 64 to 71): for each step, `uses:` must be a local path (`./...`) or pinned to a full commit id; neither `uses` nor `run` may contain a moving name; a service image in a job may not use a moving tag.
- **WF007** (lines 72 to 74): the top-level `permissions` must be a dictionary with `contents: read`.
- `lint_composite` (lines 78 to 85) applies the pinning rule to steps of a composite action.

#### `pipeline/adapters/process.py`: running programs as jobs

A **process** is a running program. A program can start other programs; `subprocess` is the standard library module that does so.

<!-- fmt:off -->
```python
"""Run commands as pipeline jobs: sequential steps, a log file per job, jobs in parallel."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Command:
    """One step: the program and its arguments, plus environment variables added to the current environment."""

    argv: tuple[str, ...]
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Job:
    """A named list of steps that run one after another and stop at the first failure."""

    name: str
    steps: tuple[Command, ...]


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a job ended and how long it took."""

    name: str
    ok: bool
    seconds: float
    log: Path

```
<!-- fmt:on -->

- **Lines 14 to 19**: `Command` is a program and its arguments (`argv`, a tuple of text), plus extra environment variables (`env`) added to the current ones. `field(default_factory=dict)` gives each object its own empty dictionary as default (a plain `= {}` would be shared by all, a classic Python trap).
- **Lines 22 to 27**: `Job`, a named tuple of steps that run one after another. **Lines 30 to 37**: `Outcome`, how a job ended (`ok`), how long it took and where its log is.

<!-- fmt:off -->
```python
def run_job(job: Job, cwd: Path, log_dir: Path) -> Outcome:
    """Run the steps, writing each command and its output to `<log_dir>/<job>.log`."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{job.name}.log"
    started = time.monotonic()
    ok = True
    with log.open("w") as handle:
        for step in job.steps:
            handle.write(f"$ {' '.join(step.argv)}\n")
            handle.flush()
            result = subprocess.run(  # noqa: S603 - argv is built by this program, never through a shell
                step.argv,
                cwd=cwd,
                env={**os.environ, **step.env},
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                handle.write(f"\n[exit status {result.returncode}]\n")
                ok = False
                break
    return Outcome(job.name, ok, time.monotonic() - started, log)


def submit(pool: ThreadPoolExecutor, job: Job, cwd: Path, log_dir: Path) -> Future[Outcome]:
    """Start a job on the pool."""
    return pool.submit(run_job, job, cwd, log_dir)


def run_output(argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None) -> str:
    """Run one command and return its standard output; a non-zero exit raises `CalledProcessError`."""
    result = subprocess.run(  # noqa: S603
        list(argv), cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=True
    )
    return result.stdout
```
<!-- fmt:on -->

- **Lines 40 to 62**: `run_job` creates the log folder (`mkdir(parents=True, exist_ok=True)`: create missing parents, no error if it exists), notes the start with `time.monotonic()`, and opens the log file for writing. For each step it writes `$ command`, flushes, and runs `subprocess.run(step.argv, cwd=cwd, env={**os.environ, **step.env}, stdout=handle, stderr=subprocess.STDOUT, check=False)`. Reading it piece by piece: `cwd` is the folder to run in; `{**a, **b}` merges two dictionaries (later wins), giving the current environment plus the step's extras; `stdout=handle` sends the program's normal output to the log file; `stderr=subprocess.STDOUT` sends its error output to the same place; `check=False` means do not raise on failure, because the code reads `returncode` itself. The comment `# noqa: S603 - argv is built by this program, never through a shell` explains why the security warning is fine: no text is ever interpreted by a shell. A non-zero `returncode` is written to the log, the job is marked failed, and `break` leaves the loop: later steps do not run.
- **Lines 65 to 67**: `submit` hands `run_job` to a **thread pool** (`ThreadPoolExecutor`): a set of worker threads that run submitted functions. The result is a `Future`, a promise of an `Outcome` that will exist later; `future.result()` waits for it.
- **Lines 70 to 75**: `run_output` runs one command and returns its standard output. `capture_output=True` collects output instead of printing it, `text=True` decodes bytes to text, and `check=True` makes a failure raise `CalledProcessError`.

#### `pipeline/adapters/git.py`: the few Git facts the pipeline needs

<!-- fmt:off -->
```python
"""The few git facts the pipeline needs."""

from __future__ import annotations

from pathlib import Path

from pipeline.adapters.process import run_output


def head_sha(repo: Path) -> str:
    """Full SHA of HEAD."""
    return run_output(["git", "rev-parse", "HEAD"], repo).strip()


def commit_epoch(repo: Path, sha: str) -> int:
    """Commit time of `sha` in seconds since the epoch: the fixed clock for a reproducible build."""
    return int(run_output(["git", "show", "-s", "--format=%ct", sha], repo).strip())


def is_dirty(repo: Path) -> bool:
    """True when tracked files changed or untracked files exist that git does not ignore."""
    return bool(run_output(["git", "status", "--porcelain"], repo).strip())


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    """Files changed between two commits (three-dot: since `head` branched from `base`)."""
    return run_output(["git", "diff", "--name-only", f"{base}...{head}"], repo).split()
```
<!-- fmt:on -->

Four small functions, each running one Git command through `run_output` ([git.md](git.md)): `head_sha` (`git rev-parse HEAD`: the current commit's id), `commit_epoch` (`git show -s --format=%ct SHA`: the commit time in seconds since 1 January 1970, converted with `int(...)`), `is_dirty` (`git status --porcelain` prints one line per changed or untracked file; any output means "dirty"; `bool(text)` is false only for an empty string) and `changed_paths` (`git diff --name-only base...head` splits the output into names with `.split()`).

#### `pipeline/adapters/builder.py`: building the wheel once

<!-- fmt:off -->
```python
"""Build the wheel once, versioned from the commit, with a checksum file next to it."""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pipeline.adapters import git
from pipeline.adapters.process import run_output
from pipeline.core.checksum import sha256_of, sums_line
from pipeline.core.version import base_version, build_version, stamp_pyproject

SUMS_FILE = "SHA256SUMS"


@dataclass(frozen=True, slots=True)
class BuiltArtifact:
    """The wheel that was built, its version and its SHA-256."""

    path: Path
    version: str
    sha256: str


def build_wheel(root: Path, dist: Path, python: str = sys.executable) -> BuiltArtifact:
    """Stamp the version into a copy of the sources, build the wheel in a temporary folder and write `dist/SHA256SUMS`.

    The commit time is the build's clock (`SOURCE_DATE_EPOCH`), so the same commit gives the same bytes.
    """
    sha = git.head_sha(root)
    version = build_version(base_version((root / "pyproject.toml").read_text()), sha, git.is_dirty(root))
    with tempfile.TemporaryDirectory(prefix="wheel-build-") as workdir:
```
<!-- fmt:on -->

- **Lines 5 to 9** import `shutil` (copying files and folders) and `tempfile` (temporary folders). **Line 16**: `SUMS_FILE = "SHA256SUMS"`. **Lines 19 to 25**: `BuiltArtifact` holds the wheel's path, version and checksum.
- **Lines 28 to 34**: `build_wheel(root, dist, python=sys.executable)`. `sys.executable` is the path of the Python running now, so the build uses the same interpreter. It asks Git for the commit, builds the version and, if the tree is dirty, marks it.

<!-- fmt:off -->
```python
    with tempfile.TemporaryDirectory(prefix="wheel-build-") as workdir:
        staging = Path(workdir) / "source"
        shutil.copytree(root / "src", staging / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for name in ("README.md", "LICENSE"):
            shutil.copy2(root / name, staging / name)
        (staging / "pyproject.toml").write_text(stamp_pyproject((root / "pyproject.toml").read_text(), version))
        out = Path(workdir) / "out"
        run_output(
            [python, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out), str(staging)],
            root,
            env={"SOURCE_DATE_EPOCH": str(git.commit_epoch(root, sha))},
        )
        built = next(out.glob("*.whl"))
        dist.mkdir(parents=True, exist_ok=True)
        for old in dist.glob("*.whl"):
            old.unlink()
        target = dist / built.name
        shutil.copy2(built, target)
    digest = sha256_of(target)
    (dist / SUMS_FILE).write_text(sums_line(target, digest) + "\n")
    return BuiltArtifact(target, version, digest)
```
<!-- fmt:on -->

- **Line 35**: `with tempfile.TemporaryDirectory(prefix="wheel-build-") as workdir:` creates a temporary folder that is deleted automatically when the block ends.
- **Lines 36 to 40**: the sources are *copied* into it (`copytree`, ignoring `__pycache__` and `*.egg-info`), together with `README.md` and `LICENSE`, and a copy of `pyproject.toml` with the new version stamped in. The repository itself is never modified.
- **Lines 42 to 46**: `run_output([python, "-m", "build", "--wheel", "--no-isolation", "--outdir", out, staging], root, env={"SOURCE_DATE_EPOCH": ...})`. `build` is the standard tool that builds packages. `--wheel` makes only the wheel. `--no-isolation` makes it use the already-installed build tools instead of downloading its own. `SOURCE_DATE_EPOCH` is an environment variable that build tools honour as "the time to write into the files": setting it to the commit's time makes the output depend only on the commit ([python-packaging.md](python-packaging.md)).
- **Lines 47 to 55**: `next(out.glob("*.whl"))` takes the one built file; older wheels in `dist/` are deleted; the new one is copied there with `shutil.copy2` (which keeps the file's times); the checksum is written to `dist/SHA256SUMS`; the result is returned.

#### `pipeline/adapters/gate.py`: a green status that only CI can post

<!-- fmt:off -->
```python
"""A local stand-in for "required status checks": CI posts a green status for a commit, and the remote refuses `main`
without it. See pipeline/hooks/pre-receive and scripts/gate-demo.sh."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pipeline.adapters.process import run_output


def run_checks_on_commit(repo: Path, sha: str, command: Sequence[str]) -> bool:
    """Check out `sha` in a throwaway worktree and run `command` there. True when it exits 0."""
    with tempfile.TemporaryDirectory(prefix="gate-") as workdir:
        tree = Path(workdir) / "tree"
        run_output(["git", "worktree", "add", "--detach", str(tree), sha], repo)
        try:
            return subprocess.run(list(command), cwd=tree, check=False).returncode == 0  # noqa: S603
        finally:
            run_output(["git", "worktree", "remove", "--force", str(tree)], repo)


def post_green_status(repo: Path, remote: str, sha: str, token: str) -> None:
    """Push `refs/status/green/<sha>` to `remote`. The remote accepts it only with the CI token as a push option."""
    run_output(["git", "push", "--push-option", f"ci-token={token}", remote, f"{sha}:refs/status/green/{sha}"], repo)
```
<!-- fmt:on -->

- **Lines 14 to 22**: `run_checks_on_commit` checks the commit out into a temporary **worktree** (a second working folder for the same repository: `git worktree add --detach TREE SHA`), runs the given command there with `subprocess.run(..., cwd=tree)` and returns whether it exited with 0. The `try`/`finally` makes sure `git worktree remove --force` runs even if the command fails or raises.
- **Lines 25 to 27**: `post_green_status` pushes `SHA:refs/status/green/SHA` to the remote, adding `--push-option ci-token=TOKEN`. A *ref* is any name that points at a commit; `refs/status/green/<sha>` is an invented one that the server's hook ([bash-and-sh.md](bash-and-sh.md)) treats as "CI says this commit is green", accepted only with the right token.

#### `pipeline/adapters/github.py`: talking to GitHub with `gh`

<!-- fmt:off -->
```python
"""Talk to GitHub through the `gh` CLI (needs `gh auth login`; nothing here runs in the tests)."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def apply_branch_protection(repo: str, payload: dict[str, Any]) -> None:
    """`PUT /repos/{repo}/branches/main/protection` with `payload`."""
    subprocess.run(  # noqa: S603
        ["gh", "api", "-X", "PUT", f"repos/{repo}/branches/main/protection", "--input", "-"],  # noqa: S607
        input=json.dumps(payload),
        text=True,
        check=True,
    )


def list_runs(repo: str, limit: int) -> str:
    """The JSON that `import-gh-runs` reads: the last `limit` workflow runs."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--limit",
            str(limit),
            "--json",
            "databaseId,headSha,conclusion,createdAt,updatedAt",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
```
<!-- fmt:on -->

- **Lines 10 to 17**: `apply_branch_protection` runs `gh api -X PUT repos/<repo>/branches/main/protection --input -` and feeds it the JSON on standard input (`input=json.dumps(payload)`). `check=True` raises if `gh` fails. The `# noqa: S607` comments silence a warning about calling `gh` by a partial path.
- **Lines 20 to 38**: `list_runs` runs `gh run list --repo REPO --limit N --json databaseId,headSha,conclusion,createdAt,updatedAt` and returns its output text ([gh-cli.md](gh-cli.md)).

#### `pipeline/adapters/local_runner.py`: the pipeline on a laptop

This is the longest file. It runs the same jobs as `ci.yml`, each one a `make` target ([make.md](make.md)).


<!-- fmt:off -->
```python
"""The whole pipeline on a laptop: the same jobs as .github/workflows/ci.yml, each one a `make` target.

Two variants give the lesson's before and after:

- `sequential`: a fresh virtual environment with no cache, then lint, unit tests, the integration test and the build,
  one after another.
- `parallel`: the cached environment (`.venv`, keyed by the lock file's hash), the build once, then lint, unit tests and
  the integration test at the same time. The integration test runs against the built wheel, after its checksum is
  verified. The quarantine job runs beside them and never counts.
"""

from __future__ import annotations

import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pipeline.adapters import git
from pipeline.adapters.builder import SUMS_FILE
from pipeline.adapters.process import Command, Job, Outcome, run_job, submit
from pipeline.core import runlog
from pipeline.core.checksum import parse_sums
from pipeline.core.flaky import FailedTest, parse_junit_failures

REQUIRED = ("build", "lint", "unit", "integration")
UNIT_PATHS = ("tests/unit", "tests/pipeline")
LOCK_FILE = "requirements-dev.lock"
```
<!-- fmt:on -->

- **Lines 1 to 10** are the docstring. It describes the two ways to run the pipeline. The `sequential` way starts from a fresh environment and does everything in a row. The `parallel` way reuses the cached environment, builds once, then runs lint, unit tests and the integration test at the same time, with the quarantine job running beside them.
- **Lines 14 to 26** are imports. `ThreadPoolExecutor` runs functions on several threads at once.
- **Lines 28 to 30** are constants: the four required job names, the two test folders of the unit job, and the lock file's name.

<!-- fmt:off -->
```python
@dataclass(frozen=True, slots=True)
class RunOptions:
    """What to run: the variant, the jobs to keep (None means all), whether quarantined tests join the unit job, and
    the label written to the run log in place of the variant (to keep a flake hunt apart from ordinary runs)."""

    variant: str
    only: frozenset[str] | None = None
    include_quarantined: bool = False
    label: str = ""


def make_job(name: str, *arguments: str) -> Job:
    """A job that is one `make` target: the pipeline file and the laptop share one definition of each job."""
    return Job(name, (Command(("make", "--no-print-directory", *arguments)),))


def unit_job(include_quarantined: bool) -> Job:
    """`make test`, with the quarantine marker filter removed when quarantined tests are wanted."""
    return make_job("unit", "test", "UNIT_MARKERS=" if include_quarantined else "UNIT_MARKERS=not flaky_quarantine")


def integration_job(wheel: Path, digest: str) -> Job:
    """`make test-artifact`: verify the wheel's checksum, install it (not the sources) and test it."""
    return make_job("integration", "test-artifact", f"WHEEL={wheel}", f"EXPECTED_SHA256={digest}")


def _read_digest(root: Path) -> tuple[Path, str]:
    sums = parse_sums((root / "dist" / SUMS_FILE).read_text())
    name, digest = next(iter(sums.items()))
    return root / "dist" / name, digest
```
<!-- fmt:on -->

- **Lines 33 to 41**: `RunOptions` bundles the choices for one run: the `variant`, which jobs to keep (`only`, `None` meaning all), whether the quarantined test joins the unit job, and a `label` that replaces the variant's name in the log. Fields after the first have defaults.
- **Lines 44 to 46**: `make_job(name, *arguments)` builds a job whose single step is `make --no-print-directory <arguments>`. The `*arguments` in the parameter list collects any number of extra positional words into a tuple; `*arguments` in the call spreads them back out. The flag keeps `make` from printing "Entering directory" lines.
- **Lines 49 to 51**: the unit job is `make test` with the variable `UNIT_MARKERS` set. By default it is `not flaky_quarantine` (skip the quarantined test); it is empty when quarantined tests are wanted (for the flake hunt). `A if condition else B` chooses the text.
- **Lines 54 to 56**: the integration job is `make test-artifact` with two variables: the wheel's path and its expected checksum.
- **Lines 59 to 62**: `_read_digest` reads `dist/SHA256SUMS` and returns the wheel's path and checksum. `next(iter(sums.items()))` takes the first (here the only) pair of the dictionary; `name, digest = ...` unpacks it.

<!-- fmt:off -->
```python
def run_parallel(root: Path, options: RunOptions) -> list[Outcome]:
    """Build, then lint, unit and integration at the same time; the quarantine job runs beside them."""
    log_dir = root / "reports"
    wanted = options.only or frozenset({*REQUIRED, "quarantine"})
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        if "lint" in wanted:
            futures["lint"] = submit(pool, make_job("lint", "lint"), root, log_dir)
        if "unit" in wanted:
            futures["unit"] = submit(pool, unit_job(options.include_quarantined), root, log_dir)
        if "quarantine" in wanted:
            futures["quarantine"] = submit(pool, make_job("quarantine", "quarantine"), root, log_dir)
        if wanted & {"build", "integration"}:
            futures["build"] = submit(pool, make_job("build", "build"), root, log_dir)
        if "integration" in wanted:

            def integrate() -> Outcome:
                built = futures["build"].result()
                if not built.ok:
                    return Outcome("integration", False, 0.0, built.log)
                wheel, digest = _read_digest(root)
                return run_job(integration_job(wheel, digest), root, log_dir)

            futures["integration"] = pool.submit(integrate)
        outcomes = [future.result() for future in futures.values()]
    return outcomes
```
<!-- fmt:on -->

`run_parallel` is the heart of the "after" version of the pipeline.

- **Line 68**: `wanted = options.only or frozenset({*REQUIRED, "quarantine"})`. If `--only` was given use it; otherwise all five jobs. `{*REQUIRED, "quarantine"}` builds a set from the four names plus one.
- **Line 69**: `with ThreadPoolExecutor(max_workers=5) as pool:` creates up to five worker threads and guarantees they are cleaned up. `futures = {}` will map a job name to its `Future`.
- **Lines 71 to 76** submit lint, unit and quarantine at once with `submit(pool, job, root, log_dir)`; they start running immediately in other threads.
- **Lines 77 and 78**: the build job is submitted if either `build` or `integration` is wanted (`wanted & {...}` is the set intersection, true when not empty), because integration needs the wheel.
- **Lines 79 to 88**: the integration job is a *function inside the function* so it can wait for the build. `futures["build"].result()` blocks until the build job has finished and returns its `Outcome`. If the build failed, integration is reported as failed without running (`Outcome("integration", False, 0.0, built.log)`). Otherwise it reads the checksum and runs the integration job. `pool.submit(integrate)` runs that function on a pool thread. The result: lint, unit tests and quarantine run during the build, and integration starts the moment the build ends.
- **Line 89**: `[future.result() for future in futures.values()]` waits for every job and collects the outcomes.

<!-- fmt:off -->
```python
def sequential_job(root: Path) -> Job:
    """Everything in one job, from a cold environment, as the first version of the pipeline did."""
    venv = root / ".cache" / "baseline-venv"
    python = str(venv / "bin" / "python")

    def tool(name: str) -> str:
        return str(venv / "bin" / name)

    pytest = (python, "-m", "pytest", "-p", "no:cacheprovider", "-q")
    return Job(
        "sequential",
        (
            Command((sys.executable, "-m", "venv", "--clear", str(venv))),
            Command(
                (tool("pip"), "install", "-q", "--no-cache-dir", "--require-hashes", "-r", "requirements-dev.lock")
            ),
            Command((tool("pip"), "install", "-q", "--no-deps", "-e", ".")),
            Command((tool("ruff"), "check", ".")),
            Command((tool("ruff"), "format", "--check", ".")),
            Command((tool("mypy"),)),
            Command((tool("lint-imports"),)),
            Command((*pytest, *UNIT_PATHS, "-m", "not flaky_quarantine", "--junitxml=reports/unit.xml")),
            Command((*pytest, "tests/integration")),
            Command((python, "-m", "pipeline", "build")),
        ),
    )
```
<!-- fmt:on -->

`sequential_job` is the "before" version: one job of ten steps, run in order.

- **Lines 95 to 99**: `venv` is `.cache/baseline-venv`; `tool(name)` returns the path of a program inside it. A nested function is used again.
- **Line 101**: `pytest` is a tuple of the words that start pytest quietly; later `*pytest` spreads them into another tuple.
- **Lines 105 to 117**: the steps. (1) `python -m venv --clear DIR` makes a fresh virtual environment, deleting any old one: no cache, on purpose. (2) `pip install -q --no-cache-dir --require-hashes -r requirements-dev.lock` installs the locked tools and refuses any file whose hash is not in the lock ([pip-and-hash-locking.md](pip-and-hash-locking.md)). (3) `pip install --no-deps -e .` installs this project in editable mode. (4 to 7) ruff check, ruff format check, mypy and import-linter. (8) the unit tests with the quarantined test excluded and a JUnit report written. (9) the integration tests. (10) the build.
- `Command((tool("mypy"),))` has a trailing comma because `(x)` is only `x` in parentheses, whereas `(x,)` is a one-item tuple.

<!-- fmt:off -->
```python
def run_pipeline(root: Path, options: RunOptions, runs_csv: Path) -> tuple[list[Outcome], runlog.RunRecord]:
    """Run one variant, append its row to the run log and return the job outcomes with that row."""
    shutil.rmtree(root / "reports", ignore_errors=True)
    started = time.monotonic()
    if options.variant == "sequential":
        outcomes = [run_job(sequential_job(root), root, root / "reports")]
    else:
        outcomes = run_parallel(root, options)
    seconds = time.monotonic() - started
    required_ok = all(outcome.ok for outcome in outcomes if outcome.name in REQUIRED or outcome.name == "sequential")
    failures = _failures(root)
    record = runlog.RunRecord(
        run=runlog.next_run_number(runlog.read(runs_csv)),
        commit=git.head_sha(root)[:7],
        seconds=seconds,
        result=runlog.SUCCESS if required_ok else runlog.FAILURE,
        variant=options.label or options.variant,
        failed_tests=tuple(failure.test_id for failure in failures),
        message=failures[0].message if failures else "",
    )
    runlog.append(runs_csv, record)
    return outcomes, record
```
<!-- fmt:on -->

`run_pipeline` runs one variant and records it.

- **Line 123**: delete the old `reports/` folder (`ignore_errors=True` means no complaint if it is missing). **Lines 124 and 129**: measure the total time with a clock that only moves forward.
- **Lines 125 to 128**: pick the variant. **Line 130**: `all(...)` is true only if every required job (or the sequential job) succeeded; the quarantine job is deliberately not counted.
- **Lines 131 to 140**: read the failures out of the test reports, and build one `RunRecord`: the next run number, the first 7 characters of the commit (`[:7]`), the elapsed seconds, success or failure, the variant, the ids of failed tests and the first failure's message. **Line 141** appends it to the log.

<!-- fmt:off -->
```python
def hunt(root: Path, runs: int, runs_csv: Path) -> list[runlog.RunRecord]:
    """Run the domain tests, quarantined test included, `runs` times on the same commit, logging every run.

    Each row is one pass or fail of the same code: the data a flaky test shows up in, instead of a rerun until green."""
    records = []
    commit = git.head_sha(root)[:7]
    for _ in range(runs):
        shutil.rmtree(root / "reports", ignore_errors=True)
        started = time.monotonic()
        outcome = run_job(make_job("hunt", "test-domain", "UNIT_MARKERS="), root, root / "reports")
        failures = _failures(root)
        record = runlog.RunRecord(
            run=runlog.next_run_number(runlog.read(runs_csv)),
            commit=commit,
            seconds=time.monotonic() - started,
            result=runlog.SUCCESS if outcome.ok else runlog.FAILURE,
            variant="flake-hunt",
            failed_tests=tuple(failure.test_id for failure in failures),
            message=failures[0].message if failures else "",
        )
        runlog.append(runs_csv, record)
        records.append(record)
    return records


def _failures(root: Path) -> list[FailedTest]:
    """Failed tests of the unit and integration reports, so a failed run says where it failed."""
    reports = [root / "reports" / "unit.xml", root / "reports" / "integration.xml"]
    return [failure for report in reports if report.exists() for failure in parse_junit_failures(report.read_text())]
```
<!-- fmt:on -->

- `hunt` repeats `make test-domain UNIT_MARKERS=` (the domain tests with the flaky test included) `runs` times on the same commit and logs each as a `flake-hunt` row. The pass/fail pattern of those rows is the evidence that the test is flaky.
- `_failures` (lines 170 to 173) reads the unit and integration reports if they exist. A comprehension with two `for` parts and an `if`: for each existing report file, for each failure in it, keep the failure. This makes the log say *which test* failed.

## Try it yourself

```bash
make install
.venv/bin/python --version
```
Expect `Python 3.12.x` or newer (this machine shows 3.13).

```bash
.venv/bin/python -c "from small_service.domain.cache import TimedCache; c = TimedCache(10, lambda: 0.0); c.put('a', 1); print(c.get('a'), len(c))"
```
Expect `1 1`. The clock is a lambda that always says 0, so nothing expires.

```bash
.venv/bin/python -c "from small_service.domain.cache import TimedCache; TimedCache(0, lambda: 0.0)"
```
Expect a traceback ending in `InvalidTtlError: ttl_seconds must be positive, got 0`.

```bash
.venv/bin/python -m pipeline version
```
Prints the version this commit would get, for example `0.1.0+3fa91bc`.

## Mistakes people make

- Installing libraries into the system Python instead of a virtual environment. Here `make install` always makes `.venv`.
- Calling `time.sleep()` in tests. Here the clock and the sleeping function are injected.
- Mutable default arguments (`def f(x=[])`). Here defaults are numbers, `None` or `field(default_factory=dict)`.
- Catching `Exception` everywhere. Here only `cli.py` does, once, and it logs the traceback.
- Sharing a dict between threads without a lock. `TimedCache` locks every method.

## Check yourself

1. What does `frozen=True` on a dataclass prevent? *Changing a field after the object is created.*
2. Why does `TimedCache` take a `clock` argument and not call `time.monotonic()` itself? *So tests can control time and never sleep.*
3. What does `with self._lock:` guarantee? *Only one thread runs the block at a time, and the lock is released even if an error occurs.*
4. What is a `Protocol`? *A list of methods an object must have, checked by mypy, with no inheritance needed.*
5. Why does `main()` return an int and not call `sys.exit()`? *Tests can call it and check the number.*

## Further reading

- Python 3.12 tutorial and reference: https://docs.python.org/3.12/
- Dataclasses: https://docs.python.org/3.12/library/dataclasses.html
- Generic syntax (PEP 695): https://docs.python.org/3.12/reference/compound_stmts.html#generic-classes
- `threading`: https://docs.python.org/3.12/library/threading.html
