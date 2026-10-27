# cicd-green-main

A small Python service and the CI pipeline that keeps its `main` branch releasable: lint, unit tests and an integration test in parallel, one checksummed artifact built once, a required check on `main`, and a flaky test found in the run log and quarantined instead of rerun.

| | |
| --- | --- |
| **Lesson** | `/prep/cicd/project-green-main`, "A CI pipeline that keeps main green" (`data-structure-explainer/src/content/tracks/cicd/12-project-green-main.md` in the Plainround app) |
| **Planned hours** | 5 |
| **Level** | Beginner |
| **Architecture** | [ARCHITECTURE.md](ARCHITECTURE.md), decisions in [docs/adr](docs/adr) |

## The pipeline's contract

- Anything on `main` has passed lint, unit and integration tests and can be released.
- `main` only receives changes whose required checks (`build`, `lint`, `unit`, `integration`) are green on a branch that is up to date with it; the rules apply to administrators too.
- The artifact is built once, versioned from the commit, and every job that uses it verifies its checksum.
- The required checks finish in under 5 minutes; if the median passes 7 minutes, we look at it.
- A test that fails without a code change is quarantined (`flaky_quarantine`) with an issue that has an owner and a date; nobody reruns a red job until it is green.
- A red `main` is fixed or reverted before new work merges: fix it forward within an hour, or revert it.

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Docker with Compose v2 | 24 or newer (tested with 24.0.6 and Compose v2.23) | the PostgreSQL service the integration test needs |
| Python | 3.12 or 3.13 (tested with 3.13; the workflow uses 3.12) | the service, the pipeline tooling and the tests |
| GNU Make | 3.81 or newer (the one on macOS works) | every job of the pipeline is one make target |
| git | any recent version | versions from the commit, the protected-main demo |
| `act` | optional, 0.2.80 or newer | runs the real workflow locally (see "What act can and cannot do") |
| `gh` | optional | applies branch protection and reads real run history once the repository is on GitHub |
| Python packages | psycopg 3 at run time; pytest, pytest-cov, ruff, mypy, import-linter, pip-audit, build, PyYAML for development. All pinned with hashes in `requirements.lock` and `requirements-dev.lock`; `make` installs them into `.venv/` | everything |

No cloud account, no secrets. The compose database listens on `127.0.0.1:55431` and its throwaway password is in `.env.example`.

## Setup, run, test, stop

```bash
make up              # copies .env, starts PostgreSQL 16, applies sql/001_schema.sql and 002_seed.sql
make run             # the whole pipeline locally: build once, then lint, unit and integration in parallel (+ quarantine); one row in runs.csv
make test            # unit tests of the service and of the pipeline's own logic, with coverage floors (no database needed)
make lint            # ruff, ruff format check, mypy (strict), import-linter, workflow rules, the README contract check
make down            # stops PostgreSQL and deletes its data
```

More targets (`make help` lists them all):

```bash
make run-baseline    # the first version of the pipeline: cold environment, everything in sequence
make bench           # 5 sequential and 5 parallel runs, then the before and after table (about 40 minutes on a busy machine)
make flaky-hunt      # the domain tests WITH the planted flaky test, 40 runs on one commit, then the flaky report
make flaky-report    # find flaky tests in runs.csv: commits with both a pass and a fail, and each test's failure rate
make test-integration   # the PostgreSQL adapter against the running database
make test-e2e        # the protected-main demo and the docs-only change check, in temporary git repositories
make gate-demo       # step 2 without GitHub: a remote that refuses main unless CI posted a green status
make protection APPLY=owner/repo   # prints, or with APPLY applies, the branch-protection JSON (needs gh)
make deploy-local    # builds an image from the verified wheel and runs its smoke test against the database
make act             # runs one job of the real workflow with act (ACT_JOB=changes by default)
make audit           # known-vulnerability check of the locked dependencies
```

What `make run` prints (durations on a busy Mac; the shape is the point):

```text
build        passed      14s  (required)  log: reports/build.log
integration  passed   2m 51s  (required)  log: reports/integration.log     <- the first run builds the clean environment
lint         passed       9s  (required)  log: reports/lint.log
quarantine   passed       8s  (non-blocking)  log: reports/quarantine.log
unit         passed   1m 01s  (required)  log: reports/unit.log
run 1: commit ad1b131 parallel 3m 05s success
```

`reports/build.log` holds the artifact line the lesson shows, and `reports/integration.log` the check of it:

```text
build: sha256 0ef922c8d556fb2859a16b26a1d2d42ef4f546073092791107e942dcc081d1ea  dist/cicd_green_main-0.1.0+ad1b131-py3-none-any.whl
integration: sha256 0ef922c8d556fb2859a16b26a1d2d42ef4f546073092791107e942dcc081d1ea  verified
```

## Done when: the lesson's checklist and the proof for each line

| # | Done when (from the lesson) | Command | What proves it |
| --- | --- | --- | --- |
| 1 | The pipeline runs on every push, and you have its duration for five runs. | Read [`.github/workflows/ci.yml`](.github/workflows/ci.yml): `on: push, pull_request, merge_group`. Run `make bench` (or `make run` five times). | The workflow triggers on every push and pull request. `runs.csv` has one row per run with its duration: the five sequential runs of the first version were 415.9, 345.9, 376.8, 401.3 and 485.3 seconds ([docs/measurements/bench.csv](docs/measurements/bench.csv)). |
| 2 | A pull request with a failing test can't be merged, and a direct push to `main` is refused. | `make gate-demo` (runs [scripts/gate-demo.sh](scripts/gate-demo.sh)); `make protection` prints the GitHub setting. | Six behaviors against a protected bare repository: a direct push is refused (`GH006 protected branch: required status checks have not passed`); a change that breaks a test never gets a green status, so its merge is refused; the fixed change gets one and is accepted; a stale branch, a forged status without the CI token, a force push and deleting `main` are all refused. For GitHub itself, `make protection APPLY=owner/repo` sends the payload from [`pipeline/core/protection.py`](pipeline/core/protection.py): `strict: true`, `enforce_admins: true`, a pull request required, the checks `build`, `lint`, `unit`, `integration` (the job names, which a test compares with `ci.yml`). Applying it needs the repository to exist; it was not applied here. |
| 3 | The median run is under five minutes, or under half the starting time, and the log shows both. | `make bench` | Medians over five runs each, measured on this Mac while a dozen other sessions kept it busy: **sequential 6m 41s** (slowest 8m 05s) and **cached and parallel 1m 55s** (slowest 2m 25s), so the median is under half of the starting time and under five minutes. The table is the output of `pipeline bench`; the rows are in [docs/measurements/bench.csv](docs/measurements/bench.csv). One of the five parallel runs failed (run 8, the integration job, 34 seconds in, with the machine's load average above 100); the default wait for the smoke job was one second and is now five (see "Troubleshooting"). It is in the log as a failure, not removed. |
| 4 | The artifact's checksum is the same in every job that uses it, checked in the pipeline itself. | `make run`, then `cat reports/build.log reports/integration.log`; `make test-artifact` with a different `EXPECTED_SHA256` exits 1. | `build: sha256 0ef922c8...81d1ea` in the build job and `integration: sha256 0ef922c8...81d1ea  verified` in the integration job (full values above). `pipeline verify` exits 1 with `sha256 MISMATCH` otherwise. The wheel's version is `0.1.0+<commit>`, the same commit always gives the same bytes (a test builds twice and compares), and a test fails the integration job unless the package under test is in `site-packages`, so it is the wheel that is tested. |
| 5 | `main` stays green, the quarantined test still runs and reports, and the issue names the cause after you find it. | `make flaky-hunt`; `make quarantine`; read [docs/issues/0001-flaky-job-timing-test.md](docs/issues/0001-flaky-job-timing-test.md). | `make flaky-hunt` ran the domain tests with the planted test 40 times on commit `8275c82`: 3 failed, every time with `assert False`, and `make flaky-report` printed that commit as one that both passed and failed (the `gh run list` query of the lesson, on the local log). The required `unit` job runs `-m "not flaky_quarantine"` and stays green; the `quarantine` job (`continue-on-error: true`, on that job only) still runs the test and reports it. The issue names the cause (a 100 ms sleep against a 50 to 112.5 ms job: 20% by arithmetic, 8% measured here), the owner, the date, and the fix, which is `Job.wait` and its 25-iteration test. |
| 6 | The section fits in ten lines and includes the rule that a red `main` is fixed or reverted before new work merges. | `make contract` (also part of `make lint`) | The section "The pipeline's contract" above is 6 lines and ends with the rule. `pipeline check-contract` fails the build if it grows past ten lines, loses the rule or the time in minutes. |

The same behaviors run as automated tests: [tests/pipeline](tests/pipeline) (versions, checksums, run-log statistics, flaky detection, workflow rules, the contract, the builder, the runner), [tests/e2e](tests/e2e) (the protected-main demo, the docs-only skip), [tests/integration](tests/integration) (the PostgreSQL adapter and the artifact) and [tests/unit](tests/unit) (the service).

## What act can and cannot do

`act` runs a workflow's jobs in containers on your machine. What was run here, against the real [`ci.yml`](.github/workflows/ci.yml) with `act pull_request` and the runner image `plainround-act-runner:ubuntu-24.04` (a plain Ubuntu 24.04 with `make`, `git`, `node` and `curl`):

```text
[ci/changes] Success - Main actions/checkout@11bd7190... [34s]
[ci/changes] | code=true
[ci/changes] Success - Main pipeline/changes.sh "$BASE" "38637e9b..." | tee -a "$GITHUB_OUTPUT"
[ci/changes] Job succeeded
```

- **Works:** the `changes` job (checkout of a pinned action, the shell script, the job output). `make act` runs it, and any job whose runner image has what the job needs. It is the quickest check of the workflow's syntax, the `needs` graph (`act -l` lists it) and the pinned references, because act fetches each pinned action by its commit.
- **Does not work with that image:** the `lint`, `unit` and `quarantine` jobs stop at `actions/setup-python` (`Unable to locate executable file: lsb_release`): the image has no Python and no `lsb_release`. The usual fix is the community runner image `catthehacker/ubuntu:act-22.04` (`make act ACT_JOB=lint ACT_IMAGE=catthehacker/ubuntu:act-22.04`); it is about 1.5 GB and was not pulled here, so those jobs were **not** run through act. They run through the same make targets with `make run`.
- **Cannot work in act:** the `integration` job (a PostgreSQL service container and artifacts that pass between jobs need the Docker socket and `--artifact-server-path`, and `--container-daemon-socket -` turns the socket off for the others), `merge_group` (there is no queue), the pull-request protection (a repository setting) and anything that needs a GitHub-hosted cache. On a Mac, act also needs `--container-architecture linux/arm64` and the socket flag, which `make act` passes.

## Stretch goals

| Stretch (from the lesson) | Built? |
| --- | --- |
| Add a merge queue so changes are tested against the latest `main` before merging. | Partly. `merge_group` is a trigger of `ci.yml`, so enabling the queue in the repository settings needs no workflow change. The queue itself is a repository setting and was not enabled. |
| Report test durations and fail the build when the suite grows past a time budget. | No. `reports/unit.xml` has every test's time; the JUnit reader in `pipeline/core/flaky.py` is where a budget check would start. |
| Add a dependency update bot and auto-merge its patch updates when the pipeline is green. | Partly. `.github/dependabot.yml` opens weekly updates for pip and for the actions. Auto-merge is not built: it needs the repository setting and a workflow that cannot be exercised before the repository exists. |

## What is simplified for teaching

Only what the lesson scopes out, plus where this build differs from the lesson's text:

- **The service is tiny on purpose** (a time-limited cache and a background job whose runs go to PostgreSQL) but it is layered, typed and tested like a real one.
- **The local runner is not a CI system.** `make run` runs the workflow's jobs as processes of the same make targets; there is no isolation between jobs, and the durations are those of one busy laptop. The numbers prove the shape (cached and parallel against cold and sequential), not the seconds of a hosted runner.
- **Step 2 is shown against a git hook, not GitHub.** The hook models required status checks, an up-to-date branch and administrators being bound, nothing else. The real settings are generated and tested but not applied.
- **The run log has more columns than the lesson's four** (`variant`, `failed_tests`, `message`) so a failed row says where it failed.
- **The lesson's `gh run list` query** is covered by `pipeline flaky` over the local log and by `pipeline import-gh-runs`, which converts `gh run list --json databaseId,headSha,conclusion,createdAt,updatedAt` output into the same rows (tested with a fixture; no GitHub run was involved here).
- **`paths-ignore` is not used.** The lesson suggests it and then warns about it; the workflow skips documentation-only changes with a job-level `if:` instead ([ADR 0003](docs/adr/0003-skip-with-if-never-with-paths-filters.md)).
- **The artifact is a wheel**, not the lesson's `tar.gz` built with `python -m build`; the version, the checksum and the reuse are the same idea.

## Project structure

```text
src/small_service/
  domain/            the time-limited cache, the background job and its record, job-key validation, named errors.
                     Depends on nothing outside the standard library.
  application/       the run-job use case (cache, run, record), queries, and the JobStore port.
                     Depends on domain only.
  infrastructure/    the PostgreSQL adapter, settings (environment, validated), logfmt logging, retry with backoff.
                     Depends on application and domain.
  interfaces/        the small-service command: run-job, history, health, smoke, version. Nothing depends on it.
pipeline/            the pipeline's own code, a second package that never imports the service
  core/              pure logic: versions from commits, checksums, the run log, flaky-test detection, workflow rules,
                     branch protection, the README contract. No subprocess, no network.
  adapters/          git, subprocesses, the wheel builder, the local runner, the git gate, the gh CLI. Depends on core.
  hooks/pre-receive  the protected-main hook used by the demo.
  changes.sh         decides code or docs-only for the workflow's `changes` job.
  cli.py             python -m pipeline: version, build, verify, run, bench, hunt, flaky, protection, lint-workflows, ...
tests/
  unit/              the service's domain, application, infrastructure helpers and command. No database.
  pipeline/          the pipeline's own logic, the builder (real wheels in temporary repositories), the runner.
  integration/       the PostgreSQL adapter, and the tests that run against the installed wheel in the integration job.
  e2e/               the protected-main demo and the docs-only skip.
sql/                 001_schema.sql (DDL), 002_seed.sql (DML), 003_queries.sql (the queries the README names).
scripts/             gate-demo.sh, the protected-main demo.
docs/                adr/ (five decision records), issues/ (the quarantine issue), measurements/ (the measured runs).
.github/             workflows/ci.yml (the pipeline), workflows/audit.yml (weekly), actions/setup (Python and the pip cache), dependabot.yml.
docker-compose.yml   PostgreSQL 16 (and the packaged service, profile "app").    Dockerfile  the wheel as an image.
pyproject.toml       metadata and every tool's configuration.     requirements*.lock  hash-pinned dependencies.
Makefile             the only commands a reader needs (make help).
```

The dependency rule (domain depends on nothing; application on domain; infrastructure and interfaces on both; nothing on interfaces) and the rules of the pipeline package (`cli` over `adapters` over `core`; `core` pure; `pipeline` never imports the service) are enforced by `make lint` through import-linter.

## SQL

`make up` applies `sql/001_schema.sql` (the `job_runs` table: keys, checks, comments, two indexes) and `sql/002_seed.sql` (six sample rows); `sql/003_queries.sql` holds the three queries the project uses, each with a one-line comment. `make db` repeats the first two safely; in CI the same scripts are applied with `psql` against the service container.

## Troubleshooting

- **Port 55431 is in use:** change `POSTGRES_PORT` in `.env`.
- **The integration job is slow the first time:** it builds a clean environment for the wheel (`.cache/artifact-venv-<hash of the lock file>`); later runs reuse it. This is the "cache by lock-file hash" of step 3 on a laptop.
- **A parallel run failed once in the first benchmark (the integration job, 34 seconds in):** the machine's load average was above 100. The cause was not captured (the log of that run was overwritten by the next one). The likeliest cause is the smoke command waiting one second for a job that sleeps up to 112 ms while the CPU was starved, so the wait is now five seconds (`JOB_TIMEOUT_SECONDS`). Twelve repeated runs of the integration job passed afterwards, including with the old one-second wait, so that explanation is a hypothesis, not a finding. The run log now records the failing test of the integration job as well, so the next such row says where it failed.
- **`make bench` takes a long time:** the sequential variant builds a fresh environment from the network every time, on purpose.

## Author and license

Written by Sumit Srivastava. Released under the MIT License, see [LICENSE](LICENSE). Changes are in [CHANGELOG.md](CHANGELOG.md).
