# cicd-green-main

## The pipeline's contract

- Anything on `main` has passed lint, unit and integration tests and can be released.
- `main` only receives changes whose required checks (`build`, `lint`, `unit`, `integration`) are green on a branch that is up to date with it; the rules apply to administrators too.
- The artifact is built once, versioned from the commit, and every job that uses it verifies its checksum.
- The required checks finish in under 5 minutes; if the median passes 7 minutes, we look at it.
- A test that fails without a code change is quarantined (`flaky_quarantine`) with an issue that has an owner and a date; nobody reruns a red job until it is green.
- A red `main` stops merging: it is fixed forward within an hour or reverted before new work merges.
