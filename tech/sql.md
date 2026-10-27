# SQL

## What it is

SQL (Structured Query Language) is the language you use to talk to a relational database. It has statements that **define** structure (DDL: `CREATE TABLE`, `CREATE INDEX`), **change** data (DML: `INSERT`, `UPDATE`, `DELETE`) and **read** data (`SELECT`). You say *what* you want, and the database decides *how* to get it. This repository uses the PostgreSQL dialect ([postgresql.md](postgresql.md)).

## Why this repository uses it

The service must store job runs, and the lesson wants the schema kept in plain files that anyone can read, apply and re-apply. The three files under `sql/` are applied by `make db` locally and by the CI integration job.

## Where it appears

| Path | What it does |
|---|---|
| `sql/001_schema.sql` | DDL: the table `job_runs`, two indexes, comments. |
| `sql/002_seed.sql` | DML: deletes and re-inserts six sample rows (keys start with `seed-`). |
| `sql/003_queries.sql` | Three example `SELECT` queries. Not applied; for reading and for `psql`. |
| `src/small_service/infrastructure/postgres_store.py` | Two statements embedded in Python (`INSERT`, `SELECT`) plus `SELECT 1`. |
| `Makefile` target `db` | Applies `sql/00[12]_*.sql` in order. |

## How it works underneath

- A statement ends with `;`. `--` starts a comment that lasts to the end of the line.
- The database parses the text, plans how to run it (which index to use) and runs it. `EXPLAIN` shows the plan.
- `NULL` means "unknown". `NULL = NULL` is not true. That is why columns here are `NOT NULL`.
- A `WHERE` clause filters rows, `ORDER BY` sorts, `LIMIT` cuts, `GROUP BY` collapses rows into groups for functions like `count` and `max`.
- A **placeholder** (`%s` in psycopg) keeps data separate from the statement, so data can never be read as SQL.

## Walkthrough of this repository's use

### `002_seed.sql`: safe to repeat

```sql
DELETE FROM job_runs WHERE job_key LIKE 'seed-%';

INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES
    ('seed-nightly-report',  '2026-09-01 02:00:00+00',  71, true),
    ...
    ('seed-export',          '2026-09-03 09:30:00+00', 1000, false),
```
`LIKE 'seed-%'` matches any text starting with `seed-` (`%` means "anything"). Deleting first makes the script **idempotent**: running it ten times leaves six rows, not sixty. The `+00` in each time is the UTC offset. The `seed-export` row has `finished = false` and 1000 ms, so the "timed out" query has something to show. The `id` column is not listed: the database numbers the rows.

### `003_queries.sql`

```sql
SELECT job_key, recorded_at, duration_ms, finished FROM job_runs ORDER BY recorded_at DESC, id DESC LIMIT 5;
```
The five newest runs. `DESC` is descending. `id DESC` breaks ties when two runs have the same time.

```sql
SELECT job_key, recorded_at, duration_ms FROM job_runs WHERE NOT finished ORDER BY recorded_at;
```
Runs that hit the timeout. The partial index `job_runs_unfinished_idx` covers exactly `WHERE NOT finished`.

```sql
SELECT job_key, count(*) AS runs, min(duration_ms) AS fastest_ms, max(duration_ms) AS slowest_ms
FROM job_runs WHERE finished GROUP BY job_key ORDER BY job_key;
```
One output row per job key: how many finished runs, the fastest and the slowest. `AS` names the output columns.

### SQL inside Python

```python
connection.execute(
    "INSERT INTO job_runs (job_key, recorded_at, duration_ms, finished) VALUES (%s, %s, %s, %s)",
    (record.job_key, record.recorded_at, record.duration_ms, record.finished),
)
```
Four placeholders, and a tuple of four values. The driver sends them separately ([psycopg.md](psycopg.md)). The same pattern with `LIMIT %s` is used in `recent`.

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
