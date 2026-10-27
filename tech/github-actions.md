# GitHub Actions

## What it is

GitHub Actions is GitHub's built-in automation service. You describe **workflows** in YAML files under `.github/workflows/`. GitHub starts a workflow when an **event** happens (a push, a pull request, a timer). A workflow is a set of **jobs**. Each job runs on a fresh virtual machine called a **runner** and is a list of **steps**. A step is either a shell command (`run:`) or a ready-made **action** (`uses:`), which is a reusable piece of automation published in another repository.

## Why this repository uses it

The lesson is "keep `main` green". That needs a check that runs on every change and that GitHub treats as **required**: a pull request cannot merge until the named jobs pass. Here GitHub Actions is the real pipeline. The same jobs also run on a laptop through [make](make.md).

## Where it appears

| File | Role |
|---|---|
| `.github/workflows/ci.yml` | The pipeline: `changes`, `build`, `lint`, `unit`, `integration`, `quarantine`, `audit`. |
| `.github/workflows/audit.yml` | A weekly vulnerability check on a timer. |
| `.github/actions/setup/action.yml` | A **composite action**: our own reusable steps (Python plus a cache). |
| `pipeline/core/workflow.py` | A linter that reads these YAML files and enforces seven rules (WF001 to WF007). |
| `Makefile` target `act` | Runs one job locally with [act](act.md). |

## How it works underneath

- GitHub reads the workflow file from the commit being tested. Changing the pipeline is a code change like any other.
- Jobs run **in parallel** unless one lists another in `needs:`. Each job gets a clean machine, so files do not carry over; **artifacts** (uploaded folders) and **outputs** (small strings) pass data between jobs.
- The **name of a job** is what branch protection checks. A **required check** with no job of that name never reports, and the pull request waits forever.
- A job skipped by an `if:` condition reports as **passed** (skipped). A workflow filtered out by `paths:` never starts and reports **nothing**. That difference drives the design below.
- `${{ ... }}` is an **expression**. GitHub fills it in before the step runs.
- `GITHUB_OUTPUT` is a file. A step appends `name=value` lines to it and the job exposes them as step outputs.
- The `permissions:` key limits what the automatic `GITHUB_TOKEN` can do.

## Walkthrough of this repository's use

### Triggers, permissions and concurrency

```yaml
on:
  push:
  pull_request:
  merge_group:
```
Run on every push, on every pull request, and on the **merge queue** event `merge_group` (GitHub's merge queue tests a candidate merge before landing it).

```yaml
permissions:
  contents: read
```
The token may read the repository and do nothing else. This is the least privilege rule: a compromised step cannot push code or edit releases.

```yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
At most one run per workflow and branch. A new push cancels the older run, which saves minutes.

### The `changes` job: skip with `if:`, never with `paths:`

```yaml
  changes:
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
`uses: actions/checkout@<40-character SHA>` downloads the repository. The comment `# v4.2.2` is for humans. Pinning to a full SHA, and not a tag, means nobody can change what that action does later. `fetch-depth: 0` fetches the whole history so `git diff` can compare. `BASE` is the pull request's base commit, or for a plain push the commit before it. `tee -a` prints and appends to `$GITHUB_OUTPUT`. See [bash-and-sh.md](bash-and-sh.md) for the script.

```yaml
  build:
    needs: changes
    if: needs.changes.outputs.code == 'true'
```
Every other job waits for `changes` and runs only if code changed. A documentation-only change makes them **skipped**, and a skipped job satisfies a required check.

### `build`: one artifact for everyone

```yaml
    outputs:
      sha256: ${{ steps.digest.outputs.sha256 }}
    steps:
      - run: make build
      - id: digest
        run: echo "sha256=$(cut -d' ' -f1 dist/SHA256SUMS)" | tee -a "$GITHUB_OUTPUT"
      - uses: actions/upload-artifact@ea165f8d... # v4.6.2
        with:
          name: wheel
          path: dist/
          if-no-files-found: error
```
`make build` creates `dist/*.whl` and `dist/SHA256SUMS` ([python-packaging.md](python-packaging.md)). `cut -d' ' -f1` takes the first space-separated word: the checksum. It becomes the job output `sha256`. The wheel is uploaded once. `if-no-files-found: error` fails the job if nothing was built.

### `lint` and `unit`

Each job is three steps: checkout, our `./.github/actions/setup`, then one `make` target. `unit` also uploads `reports/` with `if: always()`, so the reports exist even when tests fail.

### `integration`: a service container and the built wheel

```yaml
    needs: [changes, build]
    services:
      postgres:
        image: postgres:16.4-alpine
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U service -d service"
```
`services:` starts a PostgreSQL container next to the job. `ports` maps it to the runner's port 5432. `options` passes health-check flags to Docker, so the job waits until the database answers. `>-` is YAML for a folded multi-line string ([yaml.md](yaml.md)).

```yaml
      - uses: actions/download-artifact@d3f86a10... # v4.3.0
        with: { name: wheel, path: dist/ }
      - run: make db PSQL="psql -v ON_ERROR_STOP=1 -q -h localhost -p 5432 -U service -d service"
      - run: make test-artifact WHEEL="$(ls dist/*.whl)" EXPECTED_SHA256="${{ needs.build.outputs.sha256 }}"
```
The job downloads the **same** wheel the build job made, checks its SHA-256 against the build job's output, installs the wheel (not the source), and runs the integration tests against it. That is the lesson's rule: test the artifact you will ship. The `env:` block holds a throwaway password for a container that exists only for this run.

### `quarantine`

```yaml
    continue-on-error: true
```
The job runs the known-flaky test and reports it, but a failure never fails the workflow. Only this job may have the key; rule WF004 in `workflow.py` enforces that.

### `audit` and `audit.yml`

`audit.yml` uses `on: schedule: - cron: "17 6 * * 1"`: every Monday at 06:17 UTC. Five fields: minute, hour, day of month, month, day of week. `workflow_dispatch:` adds a manual "Run workflow" button.

### The composite action

```yaml
runs:
  using: composite
  steps:
    - uses: actions/setup-python@a26af69b... # v5.6.0
      with:
        python-version: "3.12"
        cache: pip
        cache-dependency-path: requirements-dev.lock
```
`using: composite` means "a list of steps I can reuse". `cache: pip` saves pip's download folder between runs, keyed on the **hash of the lock file**. The cache changes only when the dependencies do.

### Rules enforced by `pipeline/core/workflow.py`

| Code | Rule |
|---|---|
| WF001 | Every required check is the name of a real job. |
| WF002 | The workflow runs on `push` and `pull_request`. |
| WF003 | No `paths` / `paths-ignore` filter. |
| WF004 | Only the quarantine job has `continue-on-error`. |
| WF005 | Every `uses:` is pinned to a full 40-character SHA. |
| WF006 | No moving names (`latest`, `@main`, `@master`). |
| WF007 | Top-level `permissions: contents: read`. |

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
