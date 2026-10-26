# 4. Quarantine a flaky test with a marker and a non-blocking job

Status: accepted, 2026-10-26

## Context

The planted test (`test_job_finishes_in_time`) fails about one run in five. The two bad answers are to rerun until green, which teaches the team to ignore red, and to delete the test, which loses the signal.

## Decision

The test carries `@pytest.mark.flaky_quarantine`. The required `unit` job runs `-m "not flaky_quarantine"`. A separate `quarantine` job runs `-m flaky_quarantine` with `continue-on-error: true` on that job only, uploads its JUnit report and never blocks. `pipeline lint-workflows` rejects `continue-on-error` on any other job. The failure rate is measured from the run log (`make flaky-hunt`, `make flaky-report`), the issue in `docs/issues/` carries the rate, the cause and an owner and a date, and the fix (waiting on the job with `Job.wait`) is a separate, deterministic test.

## Alternatives considered

- **A retry plugin (rerun failures automatically):** hides the flake in the pass rate; the failure is still there and nobody sees it.
- **`continue-on-error` on the whole workflow:** real failures would pass as well.

## Consequences

- `main` stays green and the quarantined test keeps running and reporting; the quarantine has an owner and a date in its issue, so it cannot become a graveyard.
- Deleting the quarantine marker is the whole "un-quarantine" change once the test no longer sleeps a guessed time.
