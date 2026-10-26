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

COMMENT ON TABLE  job_runs             IS 'One row per background job run the service executed (cache hits are not stored).';
COMMENT ON COLUMN job_runs.job_key     IS 'Caller-chosen key: the same key within the cache TTL is answered from memory, not run again.';
COMMENT ON COLUMN job_runs.duration_ms IS 'Wall-clock milliseconds from start to finish, or to the timeout when the job did not finish.';
COMMENT ON COLUMN job_runs.finished    IS 'False when the wait timed out before the job ended.';

-- "newest first" is the only read path (small-service history).
CREATE INDEX IF NOT EXISTS job_runs_recorded_at_idx ON job_runs (recorded_at DESC, id DESC);
-- the slow-run query below filters on unfinished runs; the partial index stays tiny.
CREATE INDEX IF NOT EXISTS job_runs_unfinished_idx ON job_runs (recorded_at) WHERE NOT finished;
