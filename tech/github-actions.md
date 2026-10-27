# GitHub Actions

## What it is

**GitHub** is a website that stores Git repositories and lets people work on them together. **GitHub Actions** is the part of GitHub that runs programs for you when something happens in a repository. The thing you write to describe what to run is a **workflow**: a text file in the **YAML** format ([yaml.md](yaml.md)) stored in the folder `.github/workflows/` of the repository.

The words you need:

- An **event** is something that happens: a person pushes commits, someone opens a pull request, a timer fires. A workflow says which events start it (`on:`).
- A **pull request** is a request to merge one branch of commits into another, with a place to discuss and check it first.
- A **job** is a group of steps that runs on one machine. Jobs normally run at the same time, unless one says it needs another.
- A **runner** is the machine a job runs on. GitHub provides fresh virtual machines; `ubuntu-latest` means a current Ubuntu Linux one. Every job gets a clean runner, so nothing is left over from earlier jobs.
- A **step** is one thing a job does. Either a shell command (`run:`) or a ready-made **action** (`uses:`), which is a reusable piece of automation published in another repository, such as "check out the code" or "install Python".
- An **artifact** is a file or folder a job uploads so that later jobs (or you) can download it.
- An **output** is a small piece of text a job publishes for jobs that depend on it.
- A **required check** is a job name that the repository's *branch protection* waits for before it lets a pull request merge.

## Why this repository uses it

The lesson is "keep `main` green": every change must be checked automatically, the checks must be the ones the repository trusts, and a pull request must not merge until they pass. GitHub Actions is where those checks run on GitHub. On a laptop the same jobs run through `make` ([make.md](make.md)).

## Where it appears

| File | Role |
|---|---|
| `.github/workflows/ci.yml` | The pipeline: jobs `changes`, `build`, `lint`, `unit`, `integration`, `quarantine`, `audit`. |
| `.github/workflows/audit.yml` | A weekly vulnerability check on a timer. |
| `.github/actions/setup/action.yml` | A **composite action**: a small reusable list of steps (install Python and keep a cache). |
| `.github/dependabot.yml` | Not a workflow, but read by GitHub ([dependabot.md](dependabot.md)). |
| `pipeline/core/workflow.py` | A linter that reads these files and enforces seven rules. |
| `Makefile` target `act` | Runs one job on your own machine ([act.md](act.md)). |

## How it works underneath

- GitHub reads the workflow file from the **commit being tested**. Changing the pipeline is therefore an ordinary change that is reviewed like any other.
- Jobs run in parallel unless a job lists another in `needs:`. Data moves between jobs only as artifacts and outputs, because each job has its own clean machine.
- A job that is **skipped** by an `if:` condition is reported as *passed* (skipped) to branch protection. A workflow that never **starts** (because of a `paths:` filter, for example) reports *nothing*, and a required check that never reports leaves the pull request waiting for ever. This difference drives a design choice below.
- `${{ ... }}` marks an **expression**: GitHub evaluates it before the step runs. `github.sha` is the commit being built, `github.ref` the branch name, `github.event.pull_request.base.sha` the commit a pull request is based on, `needs.JOB.outputs.NAME` an output of another job, `secrets.NAME` a secret the repository owner stored.
- `GITHUB_OUTPUT` is the name of a file. A step appends `name=value` lines to it, and GitHub turns them into step outputs.
- `permissions:` limits what the automatic **token** (`GITHUB_TOKEN`, a password GitHub hands each run) is allowed to do.
- `concurrency:` makes runs of the same group take turns or cancel each other.

## Walkthrough of this repository's use

Every line of every workflow file is explained here.

### `.github/workflows/ci.yml`

```yaml
# The pipeline of this repository. Every job is one `make` target, so `make run` runs the same jobs on a laptop.
#
# Required checks on main: build, lint, unit, integration (job names, not the workflow name).
# Documentation-only changes skip the jobs with `if:` (a skipped job reports as passed); there is no `paths` filter,
# because a workflow that never starts would leave the required checks pending for ever.
name: ci
```

- **Lines 1 to 5** are comments (`#`) that state the design. Every job is one `make` target. The required checks on `main` are the job names `build`, `lint`, `unit` and `integration`. Documentation-only changes skip jobs with `if:`, never with `paths:`, for the reason given above.
- **Line 6**: `name: ci` is the workflow's display name.

```yaml
on:
  push:
  pull_request:
  merge_group:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

- **Lines 8 to 11**: `on:` lists the triggering events: `push` (any branch gets new commits), `pull_request`, and `merge_group`, the event GitHub's *merge queue* sends when it tests a candidate merge before landing it. Empty values (nothing after the colon) mean "all of these events, with no extra filters".
- **Lines 13 and 14**: `permissions: contents: read` gives the run's token permission to read the repository and nothing else. A step that was tricked into doing something nasty could not push code or change settings. This is **least privilege**.
- **Lines 16 to 18**: `concurrency:` with `group: ci-${{ github.workflow }}-${{ github.ref }}` says "at most one run per workflow and branch at a time". `cancel-in-progress: true` cancels an older run when a newer commit arrives on the same branch, saving minutes.

```yaml
jobs:
  changes:
    name: changes
    runs-on: ubuntu-latest
    outputs:
      code: ${{ steps.decide.outputs.code }}
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
      - id: decide
        env:
          BASE: ${{ github.event.pull_request.base.sha || github.event.before }}
        run: pipeline/changes.sh "$BASE" "${{ github.sha }}" | tee -a "$GITHUB_OUTPUT"
```

- **Line 20**: `jobs:` starts the list. **Line 21**: `changes:` is the job's id. **Line 22**: `name: changes` is the name GitHub shows (and the name a required check refers to). **Line 23**: `runs-on: ubuntu-latest` picks the runner.
- **Lines 24 and 25**: `outputs: code: ${{ steps.decide.outputs.code }}` publishes a value called `code` that comes from the step whose `id` is `decide` (line 30).
- **Lines 26 to 29**: the first step uses an action: `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2` downloads the repository into the runner. The long hexadecimal text is a **full commit id**: the action is pinned to exactly one version of its code. (A tag such as `v4` can be moved to different code later; a commit id cannot.) The comment records the human version. `with: fetch-depth: 0` fetches the whole history, not just the latest commit, so `git diff` can compare two commits.
- **Lines 30 to 33**: a step with `id: decide` and an environment variable `BASE: ${{ github.event.pull_request.base.sha || github.event.before }}`. `||` means "or": for a pull request use its base commit; for a plain push use the commit before the push. `run:` runs `pipeline/changes.sh "$BASE" "${{ github.sha }}" | tee -a "$GITHUB_OUTPUT"` ([bash-and-sh.md](bash-and-sh.md)), appending `code=true` or `code=false` to the output file.

```yaml
  build:
    name: build
    needs: changes
    if: needs.changes.outputs.code == 'true'
    runs-on: ubuntu-latest
    outputs:
      sha256: ${{ steps.digest.outputs.sha256 }}
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - run: make build
      - id: digest
        run: echo "sha256=$(cut -d' ' -f1 dist/SHA256SUMS)" | tee -a "$GITHUB_OUTPUT"
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        with:
          name: wheel
          path: dist/
          if-no-files-found: error
```

- **Line 37**: `needs: changes` makes this job wait for `changes`. **Line 38**: `if: needs.changes.outputs.code == 'true'` runs the job only when code changed; otherwise it is skipped, which counts as passed.
- **Lines 40 and 41**: `build` publishes an output `sha256` taken from its step `digest`.
- **Lines 43 to 45**: check out the repository, run our composite action `./.github/actions/setup` (a path beginning `./` means "an action stored in this repository"), then `make build`.
- **Lines 46 and 47**: `echo "sha256=$(cut -d' ' -f1 dist/SHA256SUMS)" | tee -a "$GITHUB_OUTPUT"` takes the first space-separated word of the checksum file, which is the SHA-256 digest of the wheel, and publishes it.
- **Lines 48 to 52**: `actions/upload-artifact@ea165f8...` (pinned, v4.6.2) uploads the `dist/` folder under the name `wheel`. `if-no-files-found: error` fails the step if nothing is there. Later jobs download exactly this file, so the code that was built is the code that is tested.

```yaml
  lint:
    name: lint
    needs: changes
    if: needs.changes.outputs.code == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - run: make lint

  unit:
    name: unit
    needs: changes
    if: needs.changes.outputs.code == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - run: make test
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        if: always()
        with:
          name: unit-reports
          path: reports/
          if-no-files-found: warn
```

- **`lint`** (lines 54 to 62): the same set-up, then `make lint`.
- **`unit`** (lines 64 to 78): the same set-up, then `make test`. The last step uploads `reports/` as an artifact named `unit-reports`; `if: always()` makes it run even if the tests failed, so the reports exist exactly when you want them; `if-no-files-found: warn` only warns if the folder is empty.

```yaml
  integration:
    name: integration
    needs: [changes, build]
    if: needs.changes.outputs.code == 'true'
    runs-on: ubuntu-latest
    env:
      POSTGRES_HOST: localhost
      POSTGRES_PORT: "5432"
      POSTGRES_DB: service
      POSTGRES_USER: service
      POSTGRES_PASSWORD: test-only-password # a throwaway for a container that lives only for this run
      PGPASSWORD: test-only-password
    services:
      postgres:
        image: postgres:16.4-alpine
        env:
          POSTGRES_DB: service
          POSTGRES_USER: service
          POSTGRES_PASSWORD: test-only-password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U service -d service"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4.3.0
        with:
          name: wheel
          path: dist/
      - run: make db PSQL="psql -v ON_ERROR_STOP=1 -q -h localhost -p 5432 -U service -d service"
      - run: make test-artifact WHEEL="$(ls dist/*.whl)" EXPECTED_SHA256="${{ needs.build.outputs.sha256 }}"
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        if: always()
        with:
          name: integration-reports
          path: reports/
          if-no-files-found: warn

```

- **Lines 82 and 83**: `needs: [changes, build]` waits for both.
- **Lines 85 to 91**: job-level `env:` sets environment variables for every step: the database's host, port, name, user and password, and `PGPASSWORD`, which `psql` reads. The comment on line 90 says the password is a throw-away for a container that lives only for this run.
- **Lines 92 to 105**: `services:` starts extra containers beside the job. `postgres:` is a database server from the image `postgres:16.4-alpine`; its own `env:` creates the database and user; `ports: - 5432:5432` makes the container's port 5432 reachable on the runner's port 5432. `options: >-` passes flags to Docker that define a health check: `--health-cmd "pg_isready -h 127.0.0.1 -U service -d service"` is the command (it asks the server whether it accepts connections, over TCP because a Unix-socket check can say "ready" too early), and `--health-interval`, `--health-timeout`, `--health-retries` say how often, how long and how many times. `>-` is YAML for "fold the following lines into one line of text with no final newline" ([yaml.md](yaml.md)). GitHub waits until the service is healthy before running the steps.
- **Lines 107 and 108**: check out and set up.
- **Lines 109 to 112**: `actions/download-artifact@d3f86a1...` (pinned, v4.3.0) downloads the artifact `wheel` into `dist/`.
- **Line 113**: `make db PSQL="psql ..."` applies the SQL files, overriding the Makefile's `PSQL` variable so it talks to the service container ([make.md](make.md)).
- **Line 114**: `make test-artifact WHEEL="$(ls dist/*.whl)" EXPECTED_SHA256="${{ needs.build.outputs.sha256 }}"` installs and tests the downloaded wheel after checking that its checksum equals the one the build job reported.
- **Lines 115 to 120**: upload `reports/` as `integration-reports`, even on failure.

```yaml
  # Not required, and never blocking: the quarantined test still runs and reports its result on every push.
  quarantine:
    name: quarantine
    needs: changes
    if: needs.changes.outputs.code == 'true'
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - run: make quarantine
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        if: always()
        with:
          name: quarantine-reports
          path: reports/
          if-no-files-found: warn
```

- **Line 122** is a comment: this job is not required and never blocks.
- **`quarantine`** (lines 123 to 138): `continue-on-error: true` means a failure of this job does not fail the workflow. It runs `make quarantine`, which runs the planted flaky test ([pytest.md](pytest.md)), and uploads `quarantine-reports`. Only this job may have `continue-on-error` (rule WF004 below).

```yaml
  # Known-vulnerability check of the locked dependencies. Not a required check: a new advisory should not block
  # unrelated pull requests, so it also runs on a weekly schedule (audit.yml).
  audit:
    name: audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - run: make audit
```

- **`audit`** (lines 142 to 148): has no `needs` and no `if`, so it runs on every event. It runs `make audit` ([pip-audit.md](pip-audit.md)). It is deliberately not a required check: a new vulnerability report should not block unrelated pull requests, so it also runs weekly in `audit.yml`.

### `.github/workflows/audit.yml`

```yaml
# Weekly known-vulnerability check of the locked dependencies, so a new advisory is found without waiting for a push.
name: audit

on:
  schedule:
    - cron: "17 6 * * 1"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  audit:
    name: audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/setup
      - run: make audit
```

- **Line 1** is a comment. **Line 2**: the name.
- **Lines 4 to 7**: `schedule: - cron: "17 6 * * 1"`. A **cron expression** has five fields: minute (17), hour (6), day of month (`*`, any), month (`*`, any), day of week (1, Monday). So: every Monday at 06:17 UTC. `workflow_dispatch:` adds a "Run workflow" button so a person can start it by hand.
- **Lines 9 and 10**: read-only token. **Lines 12 to 19**: one job `audit` on `ubuntu-latest`: check out, set up Python, `make audit`.

### `.github/actions/setup/action.yml`

```yaml
name: setup
description: Python 3.12 with the pip cache keyed by the lock file's hash, so the cache changes only when dependencies do.
runs:
  using: composite
  steps:
    - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
      with:
        python-version: "3.12"
        cache: pip
        cache-dependency-path: requirements-dev.lock
```

- A **composite action** is an action made of other steps. **Lines 1 and 2**: its name and description. **Lines 3 and 4**: `runs: using: composite` says the action is a list of steps. **Lines 5 to 10**: the one step uses `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` (pinned, v5.6.0). `python-version: "3.12"` is quoted so YAML keeps it as text (unquoted, `3.10` would turn into `3.1`). `cache: pip` saves pip's downloads between runs. `cache-dependency-path: requirements-dev.lock` names the **key**: the cache is reused as long as that file is unchanged, and is replaced when dependencies change.

### The rules enforced by `pipeline/core/workflow.py`

`make lint` runs a small program that reads these files and checks seven rules ([python.md](python.md) explains how it works):

| Code | Rule |
|---|---|
| WF001 | Every required check (`build`, `lint`, `unit`, `integration`) is the name of a real job. |
| WF002 | The workflow runs on `push` and on `pull_request`. |
| WF003 | Neither trigger has a `paths` or `paths-ignore` filter. |
| WF004 | Only the quarantine job has `continue-on-error`. |
| WF005 | Every `uses:` is a local path or pinned to a full 40-character commit id (this applies to the composite action too). |
| WF006 | No moving names (`latest`, `@main`, `@master`) in `uses:`, `run:` or a service image. |
| WF007 | The top-level `permissions` is exactly `contents: read`. |

## Try it yourself

```bash
make workflows
```
Prints that the workflows pass the rules (or the findings).

```bash
.venv/bin/python -c "import yaml; print(list(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']))"
```
Expect `['changes', 'build', 'lint', 'unit', 'integration', 'quarantine', 'audit']`.

```bash
sed -i.bak 's/@11bd71901bbe5b1630ceea73d27597364c9af683/@v4/' .github/workflows/ci.yml && make workflows; mv .github/workflows/ci.yml.bak .github/workflows/ci.yml
```
The linter reports WF005 (not pinned). The last command restores the file.

```bash
make protection
```
Prints the branch-protection JSON that makes `build`, `lint`, `unit` and `integration` required.

## Mistakes people make

- Using `paths:` on a workflow with required checks: a docs-only pull request waits forever.
- Naming the required check after the workflow, not the job.
- Pinning an action to a tag (`@v4`). Tags can be moved; a SHA cannot.
- Giving the token write access by default.
- Putting secrets in `env:` of a pull request from a fork.
- Rebuilding the package in every job, so the thing tested is not the thing shipped.

## Check yourself

1. Why does a skipped job not block a merge but a filtered-out workflow does? *A skipped job reports as passed; a workflow that never starts reports nothing, so the required check stays pending.*
2. What does `needs:` do? *Makes a job wait for another and lets it read that job's outputs.*
3. Why pin actions to a SHA? *A tag can be re-pointed to different code; a SHA cannot.*
4. What does `continue-on-error: true` change? *A failure of that job does not fail the workflow.*
5. How does the integration job know it is testing the right wheel? *It compares the downloaded file's SHA-256 with the digest the build job published.*

## Further reading

- Workflow syntax: https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions
- Events that trigger workflows: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows
- Composite actions: https://docs.github.com/en/actions/creating-actions/creating-a-composite-action
- Security hardening (pinning, permissions): https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions
- Pinned here: checkout v4.2.2, setup-python v5.6.0, upload-artifact v4.6.2, download-artifact v4.3.0
