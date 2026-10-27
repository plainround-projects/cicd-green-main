# PostgreSQL 16

## What it is

PostgreSQL ("Postgres") is a **relational database server**. It keeps data in **tables** (rows and columns) on disk, and it is a program that listens on a network port. Clients connect, send **SQL** commands ([sql.md](sql.md)) and get results back. It guarantees that a **transaction** (a group of changes) either happens completely or not at all.

## Why this repository uses it

The service records every job run so `small-service history` can show it. The integration test checks that the real adapter works against a real database and not a fake. Running it in a container ([docker-compose.md](docker-compose.md)) makes that cheap.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | The `db` service: `postgres:16.4-alpine`. |
| `.github/workflows/ci.yml` | A `services: postgres:` container in the `integration` job. |
| `sql/001_schema.sql` | The table `job_runs` and its indexes. |
| `sql/002_seed.sql`, `003_queries.sql` | Example rows and queries. |
| `src/small_service/infrastructure/postgres_store.py` | The Python adapter ([psycopg.md](psycopg.md)). |
| `tests/integration/` | Tests against the live database. |

## How it works underneath

- One server process (the **postmaster**) accepts connections and starts a worker process for each. The default port is 5432.
- Data is stored in a **data directory**. Changes are first written to a **write-ahead log** so a crash cannot corrupt committed data.
- A **connection string** (DSN) names the server: `postgresql://user:password@host:port/database`.
- A **transaction** begins with the first command and ends with `COMMIT` (keep) or `ROLLBACK` (undo). Other connections do not see your changes until you commit.
- An **index** is a sorted side structure that makes some lookups fast. A **partial index** covers only rows matching a condition.
- A **constraint** is a rule the database enforces (not null, a check, a primary key).

## Walkthrough of this repository's use

### The schema (`sql/001_schema.sql`)

```sql
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
- `IF NOT EXISTS` makes running the script twice safe.
- `bigint GENERATED ALWAYS AS IDENTITY` is a number the database counts up by itself. `ALWAYS` means you cannot insert your own value by accident. `PRIMARY KEY` means unique and not null, and it creates an index.
- `text` is a string of any length. `timestamptz` is a point in time stored in UTC and shown in the session's time zone. `integer` is a 32-bit whole number.
- `NOT NULL` forbids missing values.
- `CHECK (job_key ~ '...')` uses a **regular expression** (`~` means "matches"). The database itself enforces the same key rule as the Python code. A second guard: even a buggy writer cannot store a bad key.

```sql
COMMENT ON TABLE job_runs IS '...';
COMMENT ON COLUMN job_runs.finished IS 'False when the wait timed out before the job ended.';
```
Documentation stored inside the database; `\d+ job_runs` in `psql` shows it.

```sql
CREATE INDEX IF NOT EXISTS job_runs_recorded_at_idx ON job_runs (recorded_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS job_runs_unfinished_idx ON job_runs (recorded_at) WHERE NOT finished;
```
The first serves "newest first", the only read path. The second is a **partial index**: it contains only rows where `finished` is false, so it stays tiny and serves the "runs that timed out" query.

### The container, in `docker-compose.yml`

The environment variables `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` make the image create that database and user on first start. The data directory is on `tmpfs`.

### The tools in the image

`psql` is the interactive client. The Makefile feeds it files: `$(PSQL) < sql/001_schema.sql` with `-v ON_ERROR_STOP=1` (stop at the first error) and `-q` (quiet). `pg_isready` is the readiness probe used in the health check.

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
