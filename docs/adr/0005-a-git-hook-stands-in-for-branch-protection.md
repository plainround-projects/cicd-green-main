# 5. A git hook stands in for branch protection when there is no GitHub repository

Status: accepted, 2026-10-26

## Context

Step 2 of the lesson (a failing change cannot merge, a direct push to `main` is refused) is a GitHub setting. This repository is not pushed anywhere yet, and the owner still wants to see the behavior.

## Decision

Two things. `python -m pipeline protection` prints the exact JSON for `PUT /repos/{owner}/{repo}/branches/main/protection` (`make protection APPLY=owner/repo` sends it with `gh`), generated from the same list of required checks that a test compares with the workflow's job names. For the local demonstration, `pipeline/hooks/pre-receive` is installed in a bare repository: `main` only moves forward, only to a commit that has `refs/status/green/<sha>`, and only the holder of the CI token can create such a ref. `scripts/gate-demo.sh` (`make gate-demo`) shows six behaviors against it, and `tests/e2e` runs the script.

## Alternatives considered

- **Only the GitHub JSON:** correct, but nobody can see it work before the repository exists.
- **A local git server or Gitea:** more realistic, far more to run for one lesson step.

## Consequences

- The hook models "required status checks, branch must be up to date, applied to admins" and nothing else; it has no reviews, no merge queue and no teams.
- The first push that creates `main` is allowed (so a repository can be seeded), which GitHub's protection does not need.
