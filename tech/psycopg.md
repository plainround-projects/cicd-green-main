# psycopg 3

## What it is

psycopg is the Python library ("driver") that talks to PostgreSQL. You give it a connection string, it opens a network connection, sends SQL and turns the answers into Python values. Version 3 is a rewrite of the older `psycopg2`. This repository pins `psycopg==3.3.6` and `psycopg-binary==3.3.6` (the second contains the compiled C parts, so no compiler is needed).

## Why this repository uses it

It is the only runtime dependency of the service (`dependencies = ["psycopg[binary]>=3.2,<4"]` in `pyproject.toml`). The `PostgresJobStore` adapter and the integration tests use it.

## Where it appears

| Path | Use |
|---|---|
| `src/small_service/infrastructure/postgres_store.py` | `psycopg.connect`, `connection.execute`, `OperationalError`. |
| `tests/integration/conftest.py` | A `key_prefix` fixture that deletes its rows afterwards. |
| `tests/integration/test_postgres_store.py` | Expects `psycopg.errors.CheckViolation` for bad rows. |
| `requirements.lock` | The pinned, hashed version. |

## How it works underneath

- `psycopg.connect(dsn)` opens a TCP connection to the server, logs in, and returns a **Connection** object.
- `connection.execute(sql, params)` sends the statement and the parameters **separately**. The server fills the placeholders, so a value can never become SQL.
- Python types are converted both ways: `datetime` with a time zone becomes `timestamptz`, `bool` becomes `boolean`, `int` becomes `integer`.
- A connection used as `with conn:` wraps one **transaction**: it commits at the end of the block, or rolls back if an exception left the block, and then **closes** the connection (psycopg 3 behavior).
- Errors are exception classes. A connection that cannot be made raises `psycopg.OperationalError`. A broken `CHECK` constraint raises `psycopg.errors.CheckViolation`.

## Walkthrough of this repository's use

```python
def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
    return retry(
        lambda: psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS),
        retriable=(psycopg.OperationalError,),
    )
```
Each call opens a **short-lived** connection (no pool; the service is small). `connect_timeout=5` stops a dead server from hanging for minutes. The `retry` helper ([python.md](python.md): generics) tries up to four times with exponential waiting, but only for `OperationalError` (network trouble), never for a bad SQL statement. The type `Connection[tuple[Any, ...]]` says rows come back as tuples.

```python
with self._connect() as connection:
    connection.execute("INSERT INTO job_runs (...) VALUES (%s, %s, %s, %s)", (...))
```
Open, execute, commit, close.

```python
rows = connection.execute(
    "SELECT job_key, recorded_at, duration_ms, finished FROM job_runs "
    "ORDER BY recorded_at DESC, id DESC LIMIT %s",
    (limit,),
).fetchall()
return [JobRecord(key, recorded_at, duration, finished) for key, recorded_at, duration, finished in rows]
```
`.fetchall()` returns a list of tuples. The list comprehension unpacks each tuple into a `JobRecord`. Note `(limit,)`: a one-item tuple needs the trailing comma.

The DSN comes from `Settings.dsn`: `postgresql://user:password@host:port/db`, with each part passed through `urllib.parse.quote` so characters like `@` or `/` in a password cannot break the URL. It carries a password, so it is never logged.

In the tests, `pytest.raises(psycopg.errors.CheckViolation)` proves the **database** (not just the Python code) refuses a bad key.

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
