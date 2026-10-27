# SQL

## What it is

**SQL** (said "S-Q-L" or "sequel") is the language you use to talk to a relational database ([postgresql.md](postgresql.md)). You do not tell the database *how* to do something step by step; you describe *what* you want, and the database works out how.

SQL statements come in three families:

- **Defining structure** (DDL, data-definition language): `CREATE TABLE`, `CREATE INDEX`.
- **Changing data** (DML, data-manipulation language): `INSERT` adds rows, `DELETE` removes rows, `UPDATE` changes them.
- **Reading data**: `SELECT`.

Rules of the language: a statement ends with a semicolon. Keywords are not case-sensitive (this project writes them in capitals). Text values are written in single quotes: `'seed-export'`. `--` starts a comment to the end of the line. `NULL` means "unknown or absent": it is not equal to anything, not even to itself.

This repository uses the PostgreSQL 16 dialect.

## Why this repository uses it

The service must store job runs, and the lesson wants the structure of the database in plain files that anyone can read, apply and apply again. Three files in `sql/` do that.

## Where it appears

| Path | What it does |
|---|---|
| `sql/001_schema.sql` | DDL: the table `job_runs`, two indexes, comments ([postgresql.md](postgresql.md) explains it line by line). |
| `sql/002_seed.sql` | DML: deletes the old sample rows and inserts six new ones. |
| `sql/003_queries.sql` | Three example `SELECT` statements. Not applied by `make db`; run by hand or in tests. |
| `src/small_service/infrastructure/postgres_store.py` | Two statements embedded in Python (an `INSERT` and a `SELECT`) and a tiny `SELECT 1`. |
| `Makefile` target `db` | Applies `sql/001_*` and `sql/002_*` in order. |

## How it works underneath

The database reads the text, checks it, and **plans** it: decides which indexes to use and in what order to do things. `EXPLAIN` in front of a query shows the plan.

A `SELECT` is read in this logical order, whatever order you write the parts in: `FROM` (which table), `WHERE` (keep only rows that satisfy a condition), `GROUP BY` (collapse rows into groups so counts and totals can be made per group), the select list (which columns or calculations to output), `ORDER BY` (sort), `LIMIT` (keep only the first N rows).

A **placeholder** is a hole in a statement for a value that is sent separately. Python's database library writes it as `%s`. Because the value travels separately from the statement text, it can never be mistaken for SQL. Gluing values into SQL text instead is the classic security hole called **SQL injection**.

## Walkthrough of this repository's use

### `sql/002_seed.sql`: sample data that can be loaded again and again

```sql
-- DML: a few rows so `make history` and the queries in 003_queries.sql have something to show.
-- Re-running is safe: the seed rows are keyed 'seed-*' and replaced.
DELETE FROM job_runs WHERE job_key LIKE 'seed-%';

INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES
    ('seed-nightly-report',  '2026-09-01 02:00:00+00',  71, true),
    ('seed-nightly-report',  '2026-09-02 02:00:00+00',  96, true),
    ('seed-cache-warmup',    '2026-09-02 08:15:00+00',  58, true),
    ('seed-nightly-report',  '2026-09-03 02:00:00+00', 112, true),
    ('seed-export',          '2026-09-03 09:30:00+00', 1000, false),
    ('seed-cache-warmup',    '2026-09-04 08:15:00+00',  64, true);
```

- **Lines 1 and 2** are comments: DML, a few rows so `make history` and the queries have something to show; re-running is safe because seed rows are keyed `seed-*` and replaced.
- **Line 3**: `DELETE FROM job_runs WHERE job_key LIKE 'seed-%';` removes every row whose `job_key` begins with `seed-`. `LIKE` compares text to a pattern in which `%` stands for "any characters". Deleting first is what makes the script **idempotent**: running it ten times leaves six rows, not sixty. Rows your own runs created have other keys and are untouched.
- **Lines 5 to 11**: `INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES (...), (...), ...;` adds six rows in one statement. The list in the first parentheses names the columns being filled; each following parentheses is one row, in the same order. The `id` column is not mentioned: the database numbers it. Times such as `'2026-09-01 02:00:00+00'` carry `+00`, the offset from UTC, so each is an exact moment. `true` and `false` are the boolean values. The row `('seed-export', '2026-09-03 09:30:00+00', 1000, false)` is the one that "timed out": 1000 milliseconds and `finished = false`.

### `sql/003_queries.sql`: three questions to ask

```sql
-- The queries the project's README and tests run. Each starts with a one-line comment on what it shows.

-- Newest runs first: what `small-service history` prints.
SELECT job_key, recorded_at, duration_ms, finished FROM job_runs ORDER BY recorded_at DESC, id DESC LIMIT 5;

-- Runs that hit the wait timeout (finished = false): the partial index serves this scan.
SELECT job_key, recorded_at, duration_ms FROM job_runs WHERE NOT finished ORDER BY recorded_at;

-- The job's work is meant to take 50 to 112.5 ms: how the finished runs are distributed.
SELECT job_key, count(*) AS runs, min(duration_ms) AS fastest_ms, max(duration_ms) AS slowest_ms
FROM job_runs WHERE finished GROUP BY job_key ORDER BY job_key;
```

- **Line 1** is a comment. **Lines 3 and 4**: `SELECT job_key, recorded_at, duration_ms, finished FROM job_runs ORDER BY recorded_at DESC, id DESC LIMIT 5;` The five newest runs. `ORDER BY recorded_at DESC` sorts from newest to oldest (`DESC` is descending); `id DESC` breaks ties; `LIMIT 5` keeps five rows. This is what `small-service history` prints, and the first index serves it.
- **Lines 6 and 7**: `SELECT job_key, recorded_at, duration_ms FROM job_runs WHERE NOT finished ORDER BY recorded_at;` The runs that hit the timeout, oldest first. `WHERE NOT finished` keeps rows where `finished` is false; the partial index serves it.
- **Lines 9 to 11**: `SELECT job_key, count(*) AS runs, min(duration_ms) AS fastest_ms, max(duration_ms) AS slowest_ms FROM job_runs WHERE finished GROUP BY job_key ORDER BY job_key;` One output row per job key: `GROUP BY job_key` collapses the finished rows into one group per key; `count(*)` counts the rows in a group, `min` and `max` give the smallest and largest value of a column; `AS runs` names the output column. The comment says the job's work takes 50 to 112.5 ms, so a group's fastest and slowest times should fall in that range.

### SQL written inside Python: `postgres_store.py`

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

- **Lines 31 to 34**: `INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES (%s, %s, %s, %s)` followed by a tuple of four values. The four `%s` are the placeholders; psycopg sends the statement and the values separately ([psycopg.md](psycopg.md)).
- **Lines 39 to 43**: the `SELECT` is the first query above with a placeholder for the limit: `... ORDER BY recorded_at DESC, id DESC LIMIT %s` and `(limit,)` as the values. The two string pieces on adjacent lines are joined by Python into one statement. `(limit,)` has a comma because that is what makes a one-item tuple in Python.
- **Lines 46 to 49**: `connection.execute("SELECT 1")` is the smallest possible query. If the database answers, it is up.

## Try it yourself

```bash
make up
docker compose exec -T db psql -U service -d service < sql/003_queries.sql
```
Three result tables. The first lists the newest runs; the second shows `seed-export`; the third shows counts per key.

```bash
docker compose exec db psql -U service -d service -c "SELECT count(*) FROM job_runs WHERE job_key LIKE 'seed-%';"
make db && docker compose exec db psql -U service -d service -c "SELECT count(*) FROM job_runs WHERE job_key LIKE 'seed-%';"
```
Both print `6`: re-applying the seed does not add rows.

```bash
docker compose exec db psql -U service -d service -c "EXPLAIN SELECT * FROM job_runs WHERE NOT finished ORDER BY recorded_at;"
```
Read the plan.

## Mistakes people make

- Building SQL with string concatenation: `"... WHERE job_key = '" + key + "'"`. This opens SQL injection. Use placeholders.
- Forgetting `WHERE` on `DELETE` or `UPDATE`.
- Scripts that fail the second time. Here `IF NOT EXISTS` and delete-then-insert make them repeatable.
- Comparing to `NULL` with `=`.
- Relying on row order without `ORDER BY`.

## Check yourself

1. What does `LIKE 'seed-%'` match? *Any text that starts with `seed-`.*
2. Why does `002_seed.sql` start with a `DELETE`? *So it can be run again without piling up duplicate rows.*
3. What does `GROUP BY job_key` do? *Makes one result row per distinct key so `count` and `max` work per key.*
4. Why use `%s` placeholders? *Data stays separate from the SQL text, which blocks injection.*
5. What does `LIMIT 5` do? *Returns at most five rows.*

## Further reading

- PostgreSQL 16 SQL commands: https://www.postgresql.org/docs/16/sql-commands.html
- `SELECT`: https://www.postgresql.org/docs/16/sql-select.html
- Tutorial: https://www.postgresql.org/docs/16/tutorial.html
