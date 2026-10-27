# PostgreSQL 16

## What it is

Programs often need to store information so that it survives when the program stops, and so that many programs can read and change it safely at once. A **database** is a program that does exactly that. **PostgreSQL** (people say "Postgres") is a database of the *relational* kind: it keeps information in **tables**.

A **table** is a grid. Each **column** has a name and a kind of value (text, whole number, true/false, date and time). Each **row** is one record. A table called `job_runs` has one row for each time the job ran, with columns such as `job_key` and `duration_ms`. You talk to the database in a language called SQL ([sql.md](sql.md)).

PostgreSQL is a **server**: a program that keeps running and waits for other programs (called *clients*) to connect to it over the network. Each client says "I am this user, for this database" and then sends commands. The server listens on a **port**, a number from 1 to 65535 that identifies the door; PostgreSQL's usual port is 5432. The address a client uses is a **connection string**: `postgresql://user:password@host:port/database`.

Four more ideas you will see:

- A **transaction** is a group of changes that either all happen or none do. If something fails halfway, PostgreSQL undoes the part already done (a **rollback**). When the group is finished the client says **commit** and the changes become permanent and visible to others.
- A **constraint** is a rule the database itself enforces on a table, such as "this column can never be empty" or "this number cannot be negative". No program, however buggy, can put a violating row in.
- An **index** is a sorted side-structure that makes some searches fast, like the index of a book. A **partial index** covers only the rows that match a condition, so it stays small.
- A **primary key** is a column (or columns) whose value identifies each row uniquely.

## Why this repository uses it

The service records every job run, and `small-service history` shows the newest ones. The integration test checks that the real adapter works against a real database rather than a pretend one. Running PostgreSQL in a container ([docker-compose.md](docker-compose.md)) makes that cheap: nothing to install.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Service `db`: `postgres:16.4-alpine` on `127.0.0.1:55471`. |
| `.github/workflows/ci.yml` | A `services: postgres:` container for the `integration` job. |
| `sql/001_schema.sql` | The table `job_runs`, its constraints and indexes. |
| `sql/002_seed.sql`, `sql/003_queries.sql` | Sample rows and example queries. |
| `src/small_service/infrastructure/postgres_store.py` | The Python adapter ([psycopg.md](psycopg.md)). |
| `tests/integration/` | Tests against the live database. |

## How it works underneath

- One server process listens on the port. For each connected client it starts a worker process.
- The data lives in a **data directory** on disk. To survive a crash, every change is first written to a **write-ahead log**; after a crash the server replays it. In this repository the data directory is in memory (`tmpfs`), so everything disappears when the container is removed, which is exactly what a throw-away test database should do.
- PostgreSQL has many column types. This repository uses `bigint` (a large whole number), `integer`, `text` (any length), `boolean`, and `timestamptz`, a moment in time stored in UTC and shown in whatever time zone the session uses.
- **Isolation**: while a transaction is open, other clients do not see its changes until it commits.
- The official Docker image sets up a database and user on first start from the environment variables `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`. During that set-up it runs a temporary server that listens only on a Unix socket (a local file used like a network connection); only afterwards does the real server start on TCP. A readiness check must therefore use TCP, as the health check does.
- The tools in the image: `psql` is the interactive client (it can also read commands from a file), and `pg_isready` asks a server whether it accepts connections.

## Walkthrough of this repository's use

### The table: `sql/001_schema.sql`

The whole file is explained here statement by statement. This is "DDL", data-definition language: statements that define structure.

```sql
-- DDL: the one table the service writes. Applied by `make db` (and by the CI integration job).
CREATE TABLE IF NOT EXISTS job_runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_key     text        NOT NULL,
    recorded_at timestamptz NOT NULL,
    duration_ms integer     NOT NULL,
    finished    boolean     NOT NULL,
    CONSTRAINT job_runs_key_format CHECK (job_key ~ '^[A-Za-z0-9._-]{1,64}$'),
    CONSTRAINT job_runs_duration_nonnegative CHECK (duration_ms >= 0)
);
```

- **Line 1** (`--` starts a comment that lasts to the end of the line) says: this is the one table the service writes; `make db` applies it, and so does the CI integration job.
- **Line 2**: `CREATE TABLE IF NOT EXISTS job_runs (` creates a table named `job_runs`. `IF NOT EXISTS` makes the statement do nothing, instead of failing, if the table already exists, so running the script twice is safe.
- **Line 3**: `id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY`. A column named `id` of type `bigint`. `GENERATED ALWAYS AS IDENTITY` means the database numbers the rows itself (1, 2, 3, ...); `ALWAYS` forbids a client from supplying its own number by mistake. `PRIMARY KEY` means each value is unique and never empty, and PostgreSQL builds an index for it.
- **Line 4**: `job_key text NOT NULL`. The caller's name for the job. `NOT NULL` forbids a missing value (`NULL` means "unknown or absent").
- **Line 5**: `recorded_at timestamptz NOT NULL`: when the run was recorded, as an exact moment.
- **Line 6**: `duration_ms integer NOT NULL`: how long it took in milliseconds.
- **Line 7**: `finished boolean NOT NULL`: true if the job ended inside the timeout, false if the wait ran out.
- **Line 8**: `CONSTRAINT job_runs_key_format CHECK (job_key ~ '^[A-Za-z0-9._-]{1,64}$')`. A named rule. `~` means "matches this regular expression" ([python.md](python.md) explains regular expressions): the whole key must be 1 to 64 characters, each a letter, digit, dot, underscore or dash. The Python code (`validate_job_key`) enforces the same rule; the database repeats it so that **no program** can store a bad key.
- **Line 9**: `CONSTRAINT job_runs_duration_nonnegative CHECK (duration_ms >= 0)`: a duration can never be negative.
- **Line 10**: `);` ends the table definition. The semicolon ends the statement.

```sql
COMMENT ON TABLE  job_runs             IS 'One row per background job run the service executed (cache hits are not stored).';
COMMENT ON COLUMN job_runs.job_key     IS 'Caller-chosen key: the same key within the cache TTL is answered from memory, not run again.';
COMMENT ON COLUMN job_runs.duration_ms IS 'Wall-clock milliseconds from start to finish, or to the timeout when the job did not finish.';
COMMENT ON COLUMN job_runs.finished    IS 'False when the wait timed out before the job ended.';
```

- `COMMENT ON TABLE ... IS '...'` and `COMMENT ON COLUMN table.column IS '...'` store documentation inside the database. `psql` shows it with `\d+ job_runs`. The texts say what a row means (one per executed run; cache hits are not stored), what `job_key` means (the same key within the cache lifetime is answered from memory), what `duration_ms` measures and what `finished = false` means. The doubled-up spacing is only alignment.

```sql
-- "newest first" is the only read path (small-service history).
CREATE INDEX IF NOT EXISTS job_runs_recorded_at_idx ON job_runs (recorded_at DESC, id DESC);
-- the slow-run query below filters on unfinished runs; the partial index stays tiny.
CREATE INDEX IF NOT EXISTS job_runs_unfinished_idx ON job_runs (recorded_at) WHERE NOT finished;
```

- **Line 17** (comment): "newest first" is the only way the service reads. **Line 18**: `CREATE INDEX IF NOT EXISTS job_runs_recorded_at_idx ON job_runs (recorded_at DESC, id DESC);` builds an index named `job_runs_recorded_at_idx` on the table, sorted by `recorded_at` from newest to oldest and, to break ties, by `id` the same way. `small-service history` asks for exactly that order, so PostgreSQL can read the first rows straight from the index.
- **Line 19** (comment) and **line 20**: `CREATE INDEX IF NOT EXISTS job_runs_unfinished_idx ON job_runs (recorded_at) WHERE NOT finished;` is a **partial index**: it contains only the rows where `finished` is false. Timeouts should be rare, so this index stays tiny, and it serves the query "show me the runs that timed out" ([sql.md](sql.md)).

### The seed and the queries

`sql/002_seed.sql` and `sql/003_queries.sql` are explained statement by statement in [sql.md](sql.md).

### The container: `docker-compose.yml` and the workflow

The database is configured by environment variables, published on `127.0.0.1` only, and health-checked over TCP; the data directory is on `tmpfs`. Every key is explained in [docker-compose.md](docker-compose.md). In CI, `services: postgres:` starts the same image with the same variables and the same health check; every key is explained in [github-actions.md](github-actions.md).

### The tools the Makefile uses

`make db` runs `psql` once per SQL file: `docker compose exec -T -e PGOPTIONS=--client-min-messages=warning db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB) < sql/001_schema.sql`. `-U` is the database user, `-d` the database, `-v ON_ERROR_STOP=1` makes psql stop and exit non-zero at the first error (by default it carries on), `-q` quiet, and `PGOPTIONS=--client-min-messages=warning` hides routine notices such as "table already exists, skipping" ([make.md](make.md)).

## Try it yourself

```bash
make up
docker compose exec db psql -U service -d service -c '\d job_runs'
```
Shows the columns, the primary key, the two indexes and the check constraints.

```bash
docker compose exec db psql -U service -d service -c "INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES ('bad key!', now(), 1, true);"
```
Expect `ERROR: new row for relation "job_runs" violates check constraint "job_runs_key_format"`.

```bash
make history
```
Lists up to five rows, newest first (the seed rows, until you run jobs).

```bash
docker compose exec db psql -U service -d service -c "EXPLAIN SELECT * FROM job_runs WHERE NOT finished ORDER BY recorded_at;"
```
On a table this small PostgreSQL may prefer a plain scan. The index matters when the table grows.

## Mistakes people make

- Storing times without a zone (`timestamp`). Here `timestamptz`.
- Building SQL by pasting strings (SQL injection). Here parameters are passed separately ([psycopg.md](psycopg.md)).
- Trusting only application code to validate. Here the database checks too.
- Exposing port 5432 to the network. Here it listens on `127.0.0.1` only.
- Using the superuser for the app; here the user is a throwaway for a throwaway container.

## Check yourself

1. What is a transaction? *A group of changes that all happen or none do.*
2. What does a partial index do? *Indexes only rows that match a condition, so it stays small.*
3. Why store `timestamptz`? *It keeps an exact moment, independent of the server's zone.*
4. What does `CHECK` do? *Rejects rows that break a rule, no matter which program wrote them.*
5. Why does the health check use TCP? *The setup server listens only on the socket.*

## Further reading

- PostgreSQL 16 documentation: https://www.postgresql.org/docs/16/
- Constraints: https://www.postgresql.org/docs/16/ddl-constraints.html
- Partial indexes: https://www.postgresql.org/docs/16/indexes-partial.html
- Identity columns: https://www.postgresql.org/docs/16/ddl-identity-columns.html
