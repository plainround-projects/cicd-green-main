# 0001: `test_job_finishes_in_time` fails about one run in five

Status: quarantined (non-blocking `quarantine` job), fix landed as a separate test
Owner: team platform (a team, not a person)
Fix by: 2026-11-30, then delete the marker and this test

## What the log says

Measured with `make flaky-hunt` (the unit job with the quarantined test included, 40 runs on one commit, `runs.csv`):

FAILURE_RATE_PLACEHOLDER

Every failure has the same message, `assert False` on `job.done`, and never anything else. A flake that always fails the same assertion points at timing, not at a bug in the logic.

## Cause

`Job.start()` runs for a random 50 to 112.5 ms. The test sleeps a fixed 100 ms and asserts `job.done`. The job is still running when the draw is above 100 ms: (112.5 - 100) / (112.5 - 50) = 12.5 / 62.5 = 20% of the time. The assumption "the job is usually finished by now" is the bug.

## Fix

Wait for the thing you need, not for a guessed time: `Job.wait(timeout_seconds)` blocks on a `threading.Event` that the job sets when it ends, so it takes exactly as long as the work. `test_the_fix_for_the_flaky_test_waits_for_the_job_instead_of_sleeping_a_guess` runs it 25 times in the required `unit` job. A longer sleep (say 200 ms) would only move the failure rate, not remove it, and would make every run slower.

## What not to do

Rerun the job until it is green. The rerun hides the failure rate, the next flaky test arrives unnoticed, and a red run stops meaning anything.
