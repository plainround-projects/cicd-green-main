# 3. Skip jobs with `if:`, never with a `paths` filter

Status: accepted, 2026-10-26

## Context

A documentation-only change should not spend five minutes of CI. The obvious tool, `paths-ignore` on the trigger, means the workflow does not start, so a required check never reports and the pull request waits for ever.

## Decision

The workflow always starts. A first job, `changes`, runs `pipeline/changes.sh BASE HEAD`, which prints `code=false` only when every changed file is under `docs/` or ends in `.md`. Each required job has `needs: changes` and `if: needs.changes.outputs.code == 'true'`. A job skipped by `if:` is reported as skipped, and GitHub counts a skipped job as passing for a required check. `pipeline lint-workflows` fails the build if a `paths` or `paths-ignore` filter appears on the triggers of the workflow that carries the required checks.

## Alternatives considered

- **`paths-ignore`:** blocks every documentation pull request (the lesson's last "common mistake").
- **A tiny always-run job that reports a green check with the same name:** works, but duplicates every required name; the `if:` form needs one extra job.

## Consequences

- Unknown situations (a new branch, a force push, a missing base commit) run the pipeline: `changes.sh` fails towards running.
- The script is shell so it needs no toolchain, and `tests/e2e/test_gate_demo.py` tests it against a real repository.
