# 1. One make target per pipeline job

Status: accepted, 2026-10-26

## Context

The lesson asks for a pipeline on "any CI system", and a reader without a GitHub repository still has to see it run. If the workflow file holds the commands, the laptop copy drifts from it.

## Decision

Every job in `.github/workflows/ci.yml` is one `make` target (`lint`, `test`, `quarantine`, `build`, `test-artifact`). The workflow only decides where and when a job runs, which artifacts pass between jobs and which checks are required. The local runner (`python -m pipeline run`, `make run`) runs the same targets as processes, in the same order and in parallel where the workflow does.

## Alternatives considered

- **Commands written in the workflow, copied into a script for the laptop:** two definitions of each job; the first edit to one of them breaks the other silently.
- **A task runner such as `act` for everything:** it needs Docker images of the size of a CI runner and does not run every action (see the README, "What act can and cannot do"). It stays as a check on the workflow file itself, not as the way to run the pipeline.

## Consequences

- A job that passes on a laptop and fails in CI points at the environment (Python version, service container), not at different commands.
- The workflow is short enough to read in one screen, and `pipeline lint-workflows` can check it against the lesson's mistakes.
