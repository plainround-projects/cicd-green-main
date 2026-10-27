# Python 3.12

## What it is

Python is a programming language. You write text files that end in `.py`. A program called the **interpreter** reads a file and does what it says, line by line. A **module** is one `.py` file. A **package** is a folder of modules that has an `__init__.py` file in it. This repository needs Python 3.12 or newer (`requires-python = ">=3.12"` in `pyproject.toml`) and the container image uses 3.12.8.

## Why this repository uses it

The lesson is about a pipeline that keeps `main` releasable. The thing being shipped is a small service, and the pipeline's own logic (version numbers, checksums, flaky-test detection, workflow rules) is also code. Both are Python, so one language and one set of tools check everything.

## Where it appears

| Path | What it does with Python |
|---|---|
| `src/small_service/domain/` | Pure logic: `TimedCache`, `Job`, `JobRecord`, error classes. No network, no files. |
| `src/small_service/application/` | Use cases (`JobRunner`) and the `JobStore` port (an interface). |
| `src/small_service/infrastructure/` | Settings, logging, retry, and the PostgreSQL store. |
| `src/small_service/interfaces/cli.py` | The `small-service` command. |
| `pipeline/core/` | Pipeline rules as pure functions: `version.py`, `checksum.py`, `flaky.py`, `runlog.py`, `workflow.py`, `protection.py`, `contract.py`, `ghruns.py`. |
| `pipeline/adapters/` | The parts that touch the outside world: `git`, `subprocess`, files. |
| `pipeline/cli.py` | `python -m pipeline ...` (the pipeline's command line). |
| `tests/` | The tests, also Python. |

## How it works underneath

- You run `python file.py`. The interpreter turns the source into **bytecode** (a compact list of instructions, cached in `__pycache__`) and runs it on a small virtual machine.
- `import x` finds a module named `x` by looking through the folders in `sys.path`, runs it once, and keeps the result in memory. The second `import x` is free.
- A **virtual environment** (`.venv`) is a private folder with its own `python` and its own installed libraries. Each project gets its own, so versions never clash. See [pip-and-hash-locking.md](pip-and-hash-locking.md).
- A **type hint** (`x: int`) is a note for tools and people. Python itself ignores it when running. [mypy](mypy.md) reads the hints and checks them.
- A **thread** is a second line of execution inside one process. Python threads share memory. That is why the cache in this repository uses a lock.

## Walkthrough of this repository's use

### Modules, packages and the `src` layout

The code lives under `src/small_service`. `pyproject.toml` says:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

This tells the build tool to look for packages inside `src/`. The `src` layout stops a common mistake: running tests against the folder you are standing in instead of the installed package. See [python-packaging.md](python-packaging.md).

### `from __future__ import annotations`

Every module starts with this line. It tells Python 3.12 to keep type hints as text and not to evaluate them when the file loads. That lets a hint mention a class that is defined later in the file.

### Dataclasses with `frozen` and `slots`

```python
@dataclass(frozen=True, slots=True)
class JobRecord:
    job_key: str
    recorded_at: datetime
    duration_ms: int
    finished: bool
```

- `@dataclass` is a **decorator**: a function that takes a class and returns an improved class. It writes `__init__`, `__repr__` and `__eq__` for you from the field list.
- `frozen=True` makes instances read-only. Setting `record.finished = True` raises an error. A frozen record can be shared between threads and kept in a cache without anyone changing it.
- `slots=True` stores fields in fixed slots instead of a per-object dictionary. It uses less memory and rejects typos like `record.finishd = 1`.

### Generics with the new syntax (Python 3.12)

```python
class TimedCache[K, V]:
    def get(self, key: K) -> V | None: ...
```

`[K, V]` after the class name declares two **type parameters**. `TimedCache[str, JobRecord]` is a cache from text to records. `V | None` means "a V or None". Before 3.12 you had to write `TypeVar("K")` by hand. `def retry[T](operation: Callable[[], T], ...) -> T` in `retry.py` uses the same syntax for functions: whatever type the operation returns is what `retry` returns.

### Dependency injection with plain callables

```python
def __init__(self, ttl_seconds: float, clock: Callable[[], float]) -> None:
```

`Callable[[], float]` means "a function that takes nothing and returns a float". The cache never calls `time.monotonic()` itself. The caller passes it in (`TimedCache(settings.cache_ttl_seconds, time.monotonic)` in `cli.py`). Tests pass a `FakeClock` and move time by hand, so no test ever sleeps. `JobRunner` does the same for `now`, `monotonic` and `job_factory`.

### Locks and events

```python
self._lock = threading.Lock()
...
with self._lock:
    self._entries[key] = _Entry(value, self._clock() + self._ttl_seconds)
```

A **lock** lets one thread at a time into a block. `with` enters the lock and always releases it, even if an error is raised inside. `Job` uses `threading.Event`: a flag that one thread sets (`self._finished.set()`) and another waits on (`self._finished.wait(timeout_seconds)`). `wait` returns `True` if the flag was set in time, `False` if the timeout passed first.

### Protocols (interfaces without inheritance)

```python
class JobStore(Protocol):
    def save(self, record: JobRecord) -> None: ...
```

A `Protocol` lists the methods an object must have. `PostgresJobStore` never says it inherits from `JobStore`. It simply has `save`, `recent` and `ping`, and mypy accepts it. The application layer depends on the protocol, not on PostgreSQL.

### Exceptions

```python
class InvalidTtlError(DomainError, ValueError): ...
```

An **exception** is an object raised to stop normal flow. The domain raises its own named errors, all children of `DomainError`, so `cli.py` can catch `DomainError` and print a clean message and let anything else become a logged traceback. `raise ConfigurationError(...) from None` in `settings.py` hides the confusing original `ValueError` from the user.

### Context managers and `with`

`with self._connect() as connection:` in `postgres_store.py` opens a database connection, commits if the block ends normally, rolls back if it raises, and closes it. `with log.open("w") as handle:` in `process.py` closes the file at the end.

### Command line with `argparse`

`build_parser()` in `cli.py` makes sub-commands: `run-job`, `history`, `health`, `smoke`, `version`. `main(argv)` returns an exit code (0 ok, 1 failed, 2 usage error) instead of calling `sys.exit`. The entry point in `pyproject.toml` (`small-service = "small_service.interfaces.cli:main"`) lets the installer create the `small-service` command.

### Standard library pieces worth knowing

| Piece | Where | Why |
|---|---|---|
| `tomllib` | `pipeline/core/version.py` | Reads `pyproject.toml` without a third-party library (new in 3.11). |
| `hashlib.sha256` | `pipeline/core/checksum.py` | The checksum of the wheel, read 1 MiB at a time. |
| `subprocess.run` | `pipeline/adapters/process.py` | Starts `make`, `git`. A list of arguments, never a shell string, so quoting bugs cannot happen. |
| `ThreadPoolExecutor` | `process.py`, `local_runner.py` | Runs the lint, unit and integration jobs at the same time. |
| `xml.etree.ElementTree` | `pipeline/core/flaky.py` | Reads pytest's JUnit XML to find which test failed. See [junit-xml.md](junit-xml.md). |
| `logging` | `infrastructure/logging.py` | One `key=value` line per event. |
| `random.uniform` | `domain/jobs.py` | The job's work lasts 50 to 112.5 ms. |
| `walrus :=` | `checksum.py`: `while chunk := handle.read(_CHUNK):` | Assigns and tests in one line. |

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
