-- The queries the project's README and tests run. Each starts with a one-line comment on what it shows.

-- Newest runs first: what `small-service history` prints.
SELECT job_key, recorded_at, duration_ms, finished FROM job_runs ORDER BY recorded_at DESC, id DESC LIMIT 5;

-- Runs that hit the wait timeout (finished = false): the partial index serves this scan.
SELECT job_key, recorded_at, duration_ms FROM job_runs WHERE NOT finished ORDER BY recorded_at;

-- The job's work is meant to take 50 to 112.5 ms: how the finished runs are distributed.
SELECT job_key, count(*) AS runs, min(duration_ms) AS fastest_ms, max(duration_ms) AS slowest_ms
FROM job_runs WHERE finished GROUP BY job_key ORDER BY job_key;
