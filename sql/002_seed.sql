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
