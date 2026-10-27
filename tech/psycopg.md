# psycopg 3

## What it is

PostgreSQL is a separate program ([postgresql.md](postgresql.md)). For a Python program to use it, something must open a network connection to the server, send SQL text, wait for the answer and turn the answer into Python values. That "something" is a **driver**, and the driver for PostgreSQL is **psycopg** (this is version 3, a rewrite of the older `psycopg2`). It is a **third-party library**: code written by other people that you install, as opposed to the standard library that ships with Python.

This repository pins `psycopg==3.3.6` and `psycopg-binary==3.3.6` in the lock files. The second package contains the pre-compiled C part of the driver, so no compiler is needed to install it. The project's `pyproject.toml` asks for `psycopg[binary]>=3.2,<4`: the square brackets request the optional "binary" extra, and the range means version 3.2 up to but not including 4.

Ideas used below:

- A **connection** is one open conversation with the server. Opening one takes time, so some programs keep a pool of them; this service is small and simply opens a short-lived connection per call.
- A **cursor** is an object that runs a statement and holds its result.
- **Parameters**: values passed separately from the SQL text. The driver sends the text and the values on different paths, so a value can never be read as SQL ([sql.md](sql.md)).
- A **transaction** ([postgresql.md](postgresql.md)): psycopg opens one automatically with the first statement. Using the connection in a `with` block commits at the end if no error happened, and rolls back if one did.

## Why this repository uses it

It is the service's only runtime dependency. The class `PostgresJobStore` uses it to save and read job runs, and the integration tests use it to clean up after themselves. Only one file in the service imports it (`postgres_store.py`); the layer rules forbid the domain and application layers from importing it ([import-linter.md](import-linter.md)), which keeps the rules of the service independent of the database.

## Where it appears

| Path | Use |
|---|---|
| `src/small_service/infrastructure/postgres_store.py` | `psycopg.connect`, `connection.execute`, `OperationalError`. |
| `tests/integration/conftest.py` | A `key_prefix` fixture that removes the rows it created. |
| `tests/integration/test_postgres_store.py` | Expects `psycopg.errors.CheckViolation` for rows that break a database rule. |
| `pyproject.toml` | `dependencies = ["psycopg[binary]>=3.2,<4"]`. |
| `requirements.lock`, `requirements-dev.lock` | The exact pinned version with its checksums. |

## How it works underneath

`psycopg.connect(dsn)` opens a TCP connection to the host and port in the connection string, logs in with the user and password, and returns a `Connection`. `connection.execute(sql, params)` sends the statement and the parameters separately; the server fills in the placeholders. Python values are converted both ways: a `datetime` with a time zone becomes `timestamptz`, `bool` becomes `boolean`, `int` becomes `integer`, and result columns come back as Python values inside **tuples** (fixed-size groups). Errors are exception classes: a failure to connect raises `psycopg.OperationalError`; a row that breaks a `CHECK` rule raises `psycopg.errors.CheckViolation`.

## Walkthrough of this repository's use

### `src/small_service/infrastructure/postgres_store.py`

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
```
<!-- fmt:on -->

- **Line 1** is the docstring. **Line 3** is the `from __future__` line ([python.md](python.md)). **Line 5**: `Any` from `typing` is the type hint for "anything". **Line 7**: `import psycopg`. **Lines 9 and 10** import our own `JobRecord` and the `retry` helper ([python.md](python.md) explains both).
- **Line 12**: `_CONNECT_TIMEOUT_SECONDS = 5` is the longest to wait for the server to answer a connection attempt.
- **Lines 15 to 20**: the class stores the connection string in `self._dsn`. "DSN" means *data source name*: the text `postgresql://user:password@host:port/db` built by `Settings.dsn` ([dotenv.md](dotenv.md)).
- **Lines 22 to 26**: `_connect` returns a connection. Its type, `psycopg.Connection[tuple[Any, ...]]`, says that result rows come back as tuples of anything. The body is `retry(lambda: psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS), retriable=(psycopg.OperationalError,))`: try to connect; if psycopg reports an `OperationalError` (the server is not reachable yet), wait and try again, up to four times; any other error is raised immediately. `lambda: ...` is a nameless function with no parameters, which is what `retry` expects for "the thing to try". `(psycopg.OperationalError,)` is a one-item tuple; the trailing comma is what makes it a tuple.

<!-- fmt:off -->
```python
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

- **Lines 28 to 34**, `save`: `with self._connect() as connection:` opens the connection and makes sure it is committed and closed when the block ends (rolled back if an error leaves the block). `connection.execute("INSERT ... VALUES (%s, %s, %s, %s)", (record.job_key, record.recorded_at, record.duration_ms, record.finished))` sends one statement and four values. The `datetime` carries a time zone, so PostgreSQL stores an exact moment.
- **Lines 36 to 44**, `recent`: `connection.execute("SELECT ... ORDER BY recorded_at DESC, id DESC LIMIT %s", (limit,)).fetchall()`. `.fetchall()` returns all the result rows as a list of tuples. The `with` block ends before the list is turned into records, because the rows are already in memory. The last line, `[JobRecord(key, recorded_at, duration, finished) for key, recorded_at, duration, finished in rows]`, is a list comprehension that unpacks each tuple into four names and builds a `JobRecord`.
- **Lines 46 to 49**, `ping`: runs `SELECT 1`; any error propagates to the caller ([python.md](python.md): `is_healthy`).

### The integration tests

`tests/integration/conftest.py` opens its own connection with `psycopg.connect(settings.dsn)` in the clean-up part of the `key_prefix` fixture and runs `DELETE FROM job_runs WHERE job_key LIKE %s` with `(f"{prefix}%",)`; the `%` inside the *value* is the SQL wildcard, and it is safe because it is a parameter. `test_postgres_store.py` uses `pytest.raises(psycopg.errors.CheckViolation)` to prove that the database refuses a bad key and a negative duration, which shows the rules hold even without the Python code. Both files are walked through in [pytest.md](pytest.md).

## Try it yourself

```bash
.venv/bin/python -c "import psycopg; print(psycopg.__version__)"
```
Expect `3.3.6`.

```bash
make up
set -a; . ./.env; set +a
.venv/bin/python -c "
import os, psycopg
dsn = f\"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}@localhost:{os.environ['POSTGRES_PORT']}/{os.environ['POSTGRES_DB']}\"
with psycopg.connect(dsn) as c:
    print(c.execute('SELECT count(*) FROM job_runs').fetchone())
"
```
Expect `(6,)`.

```bash
make test-integration
```
Runs the adapter tests against the database.

## Mistakes people make

- Formatting values into the SQL string with f-strings.
- Forgetting the trailing comma in a one-value tuple: `(limit)` is just `limit`.
- Leaving connections open. Here every call uses `with`.
- Retrying on every error. A syntax error will never succeed; only network errors are retried.
- Logging the connection string with the password.

## Check yourself

1. Why does `execute` take the SQL and the values separately? *The server fills placeholders, so values cannot be read as SQL.*
2. What happens at the end of `with conn:`? *Commit if no error, rollback if an error, then close.*
3. Why retry only on `OperationalError`? *Those are connection problems that may pass; other errors are bugs.*
4. What does `psycopg-binary` add? *Precompiled C code, so no compiler is needed.*
5. Why `(limit,)` and not `(limit)`? *Parentheses alone do not make a tuple; the comma does.*

## Further reading

- psycopg 3 documentation: https://www.psycopg.org/psycopg3/docs/ (pinned 3.3.6)
- Passing parameters: https://www.psycopg.org/psycopg3/docs/basic/params.html
- Transactions: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
