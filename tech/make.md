# Make and the Makefile

## What it is

A **terminal** is a window where you type commands. A **command** is the name of a program followed by some words (its **arguments**). A **shell** is the program that reads what you type and starts the program you named. Typing `ls` in a shell starts a small program that lists the files in the current folder.

`make` is one such program. It is a tool for **running recipes in the right order**. You describe your recipes in a text file named `Makefile`. When you type `make lint`, `make` reads the file, finds the recipe named `lint`, and runs the commands written under it.

A Makefile is a list of **rules**. Each rule has three parts:

```make
target: prerequisite another-prerequisite
	command that makes the target
```

- The **target** is the name of the thing the rule makes. It can be a file (such as `.venv/.installed`) or just a name for an action (such as `lint`).
- The **prerequisites** are other targets that must be ready first. `make` builds them before it runs this rule's commands.
- The **recipe** is the indented lines. Each line is a shell command. The indent **must be a tab character**, not spaces. (If you use spaces, `make` stops with `*** missing separator`.)

One more idea: `make` compares file **modification times**. If the target is a file and it is newer than all its prerequisites, there is nothing to do and the rule is skipped. This makes `make` good at "do the slow step only when its inputs changed".

macOS ships GNU Make **3.81**, which is very old; Linux machines and GitHub's runners have 4.x. This Makefile uses only features that both versions have.

## Why this repository uses it

The lesson's rule is: *every job of the CI pipeline is one `make` target, so `make run` on a laptop runs the same jobs as GitHub does.* The workflow file never contains a command like `ruff check .`. It says `run: make lint`. That has three benefits: a learner finds what each job does in one place; a laptop and CI cannot drift apart; and changing how lint works means editing the Makefile, not every place that calls it.

## Where it appears

| Path | Role |
|---|---|
| `Makefile` | 28 documented targets. `make help` prints them. |
| `.github/workflows/ci.yml` | Calls `make build`, `make lint`, `make test`, `make test-artifact`, `make quarantine`, `make audit` and `make db`. |
| `.github/workflows/audit.yml` | Calls `make audit`. |
| `pipeline/adapters/local_runner.py` | Starts `make --no-print-directory <target>` for every local job. |
| `.editorconfig` | Says Makefiles are indented with tabs. |

## How it works underneath

- `make test` finds the rule whose target is `test`, makes each prerequisite first (following their own prerequisites, recursively), and then runs the recipe.
- Each recipe line is run by **its own new shell**. So a `cd` on one line does not carry over to the next line. To make several commands share a shell, the line is continued with a backslash `\` at the end.
- A line starting with `@` is run but not printed first. A line starting with `-` is run and its failure is ignored.
- A **variable** is a named piece of text. `NAME := value` sets it. `$(NAME)` uses it. `$$` is how you write a single dollar sign that the shell (not `make`) should see, so `$$script` is the shell variable `script`.
- `NAME ?= value` sets the variable only if nobody has set it already. That lets a caller override it: `make test PYTHON=python3.12`.
- A **phony** target is a name for an action, not a file. It is listed after `.PHONY:` so that `make` does not get confused when a file with the same name exists.
- `make` passes its variables to commands it starts only if they are **exported**.

## Walkthrough of this repository's use

The whole Makefile is covered here, top to bottom.

### Variables and set-up (lines 1 to 12)

```make
# make up | run | test | lint | down      (make help lists everything)
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
COMPOSE := docker compose

-include .env
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL CACHE_TTL_SECONDS JOB_TIMEOUT_SECONDS

.PHONY: help install up db down run run-baseline bench flaky-hunt flaky-report test test-domain quarantine test-integration test-artifact \
        test-e2e lint format audit check build verify deploy-local gate-demo workflows act protection contract history clean
```

- **Line 1** is a comment (lines starting with `#` are ignored by `make`). It lists the commands a newcomer will use most.
- **Line 2**: `PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)`. `$(shell ...)` runs a shell command and uses its output as text. `command -v NAME` prints the path of a program if it exists. The `||` means "if the left side failed, try the right side". So `PYTHON` becomes the first of Python 3.13, 3.12 or plain `python3` that is installed. `?=` lets you override it from outside.
- **Line 3**: `VENV := .venv`. The virtual environment lives in a folder named `.venv` ([python.md](python.md)). `:=` means "work out the right side now, once".
- **Line 4**: `PY := $(VENV)/bin/python` is the Python *inside* that environment. Every target uses `$(PY)` so it always runs with the project's installed tools.
- **Line 5**: `STAMP := $(VENV)/.installed`. This is the **stamp file** explained below.
- **Line 6**: `COMPOSE := docker compose` names the command that runs the database container ([docker-compose.md](docker-compose.md)).
- **Line 8**: `-include .env`. `include` reads another file as if its lines were written here. The `-` in front means "no error if the file does not exist". `.env` holds lines like `POSTGRES_PORT=55471`, which are valid `make` assignments ([dotenv.md](dotenv.md)).
- **Line 9**: `export POSTGRES_HOST POSTGRES_PORT ...` marks eight variables as exported, so every command `make` starts can read them. This is how the Python programs learn the database address and password without any of it being written in code.
- **Lines 11 and 12**: `.PHONY:` lists every target that is an action rather than a file. The trailing backslash continues the list onto the next line.

### `help`

```make
help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort
```

`make help` prints a table of targets. The recipe is a `grep` that searches the Makefile (`$(MAKEFILE_LIST)` is the list of files `make` read) for lines of the form `name: ... ## description`, then `sed` replaces the `: ... ##` part with a tab, and `sort` orders the lines. So each target's `## description` after its colon is the documentation. `grep -E` means "extended regular expression", a pattern language ([python.md](python.md) explains regular expressions). `@` hides the command line itself.

### `install` and the stamp file (lines 17 to 23)

```make
$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file
```

This rule is the foundation of every other target.

- **Line 17**: the target is the *file* `.venv/.installed`. Its prerequisites are `requirements-dev.lock` and `pyproject.toml`. If either is newer than the stamp (or the stamp is missing), the recipe runs.
- **Line 18**: `$(PYTHON) -m venv $(VENV)` creates the virtual environment. `-m venv` runs Python's built-in module that makes one.
- **Line 19**: `pip install -q --require-hashes -r requirements-dev.lock` installs the exact tools listed in the lock file. `pip` is Python's installer; `-q` is quiet; `-r FILE` reads the list of packages from a file; `--require-hashes` makes pip refuse any download whose fingerprint (hash) is not written in the file ([pip-and-hash-locking.md](pip-and-hash-locking.md)).
- **Line 20**: `pip install -q --no-deps -e .` installs *this project* into the environment. `.` means "the project in this folder", `-e` means *editable* (the environment points at your source files, so edits take effect at once), and `--no-deps` means "do not install anything else; the lock already did".
- **Line 21**: `touch $@`. `$@` is an automatic variable meaning "this rule's target". `touch` creates the file or updates its time. After this, the stamp is newer than both inputs, so the next `make` run skips the whole rule.
- **Line 23**: `install: $(STAMP) ## ...` is a rule with no recipe of its own: asking for `install` just asks for the stamp.

Nearly every other target lists `$(STAMP)` as a prerequisite, so whatever you run first creates the environment.

### `.env`

```make
.env:
	cp .env.example .env
```

A rule with no prerequisites whose target is the file `.env`. If the file does not exist, copy `.env.example` to it. That is why `make up` works on a fresh clone with no manual set-up. (`.env` is ignored by Git, so the copy is yours alone.) To overwrite an existing one, run `make -B .env`; `-B` means "treat everything as out of date".

### `up`, `db` and the database (lines 28 to 40)

```make
# The local target: PostgreSQL in a container, with the schema and the seed rows from sql/ applied.
up: $(STAMP) .env ## start PostgreSQL and apply sql/001_schema.sql and 002_seed.sql
	$(COMPOSE) up -d --wait db
	$(MAKE) --no-print-directory db

# CI has a service container instead of compose: make db PSQL="psql -h localhost -p 5432 -U service -d service"
PSQL ?= $(COMPOSE) exec -T -e PGOPTIONS=--client-min-messages=warning db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db: ## apply the numbered scripts in sql/ (safe to repeat)
	@for script in sql/00[12]_*.sql; do \
	  echo "applying $$script"; \
	  $(PSQL) < $$script || exit 1; \
	done
```

- **Line 29**: `up` needs the environment and `.env`. Its recipe (lines 30 and 31) runs `docker compose up -d --wait db`, which starts the `db` service in the background (`-d` is *detached*) and **waits** until its health check passes. Then it calls `make` again for the `db` target. `$(MAKE)` is the right way to call `make` recursively; `--no-print-directory` silences the "Entering directory" line.
- **Line 34**: `PSQL ?= ...` is the command that runs SQL. By default it is `docker compose exec -T -e PGOPTIONS=--client-min-messages=warning db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB)`. Read it as: run a command inside the already-running `db` container (`exec`); `-T` means no terminal, so input can be piped in; `-e PGOPTIONS=...` sets an environment variable that quiets notices; `psql` is PostgreSQL's command-line client; `-v ON_ERROR_STOP=1` makes psql stop at the first error and exit non-zero; `-q` is quiet; `-U` and `-d` pick the database user and the database. CI overrides `PSQL` with a plain `psql -h localhost ...` because there the database runs as a service container.
- **Lines 36 to 40**: `db` applies the numbered SQL files. `for script in sql/00[12]_*.sql; do ... done` is a shell loop. The pattern `00[12]_*.sql` matches files starting `001_` or `002_` (the square brackets mean "one of these characters"), so the schema and the seed are applied, in order, and the example queries in `003_queries.sql` are not. `echo "applying $$script"` prints the name. `$(PSQL) < $$script` feeds the file into the client's input. `|| exit 1` means "if that failed, stop the loop with an error". The whole `for` is one logical line (the backslashes continue it) so the loop variable survives between its lines. Because the schema uses `IF NOT EXISTS` and the seed deletes before inserting, the target is safe to repeat ([sql.md](sql.md)).

### `run`, `run-baseline`, `bench` (lines 42 to 51)

```make
# The whole pipeline, locally: build once, then lint, unit tests and the integration test in parallel (the integration
# test runs against the built, checksum-verified wheel), and the quarantine job beside them. One row goes to runs.csv.
run: up ## the whole pipeline locally (parallel jobs, one artifact); appends a row to runs.csv
	$(PY) -m pipeline run

run-baseline: up ## the first version of the pipeline: cold environment, everything in sequence
	$(PY) -m pipeline run --variant sequential

bench: up ## 5 sequential and 5 parallel runs, then the before and after table (takes about 10 minutes)
	$(PY) -m pipeline bench --runs 5
```

- `run` needs `up` and then calls `python -m pipeline run`: the pipeline in parallel. It builds the wheel once, runs lint, unit tests and the integration test at the same time, and appends a row to `runs.csv`.
- `run-baseline` is the first version of the pipeline, `--variant sequential`: a fresh environment and every step in a row.
- `bench` runs five of each and prints the before-and-after table (it takes about ten minutes).

### `flaky-hunt` and `flaky-report` (lines 53 to 60)

```make
# Step 5: run the unit job WITH the quarantined test 40 times on one commit, then read the log.
HUNT_RUNS ?= 40
flaky-hunt: $(STAMP) ## run the domain tests WITH the planted flaky test HUNT_RUNS times (default 40) and log each run
	$(PY) -m pipeline hunt --runs $(HUNT_RUNS)
	$(MAKE) --no-print-directory flaky-report

flaky-report: $(STAMP) ## find flaky tests in runs.csv: commits with both a pass and a fail, and each test's failure rate
	$(PY) -m pipeline flaky --variant flake-hunt
```

- **Line 54**: `HUNT_RUNS ?= 40`. A variable with a default you can override: `make flaky-hunt HUNT_RUNS=10`.
- **Lines 55 to 57**: `flaky-hunt` runs the domain tests, with the planted flaky test included, `HUNT_RUNS` times on one commit and then calls `flaky-report`. The log it writes is the evidence: failures on a commit that otherwise passes.
- **Lines 59 and 60**: `flaky-report` reads `runs.csv` and prints which commits had both a pass and a fail and each test's failure rate.

### `lint` and `format` (lines 62 to 72)

```make
lint: $(STAMP) ## ruff check, ruff format check, mypy, import-linter, workflow and contract checks
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/mypy
	$(VENV)/bin/lint-imports
	$(PY) -m pipeline lint-workflows
	$(PY) -m pipeline check-contract

format: $(STAMP) ## apply ruff's formatting and safe fixes
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .
```

`lint` is the job `lint` in CI. Its six commands, run in order and stopping at the first failure:

1. `ruff check .` finds likely bugs and style problems ([ruff.md](ruff.md)). The dot means "the whole project".
2. `ruff format --check .` fails if any file is not formatted the project's way.
3. `mypy` checks the type hints ([mypy.md](mypy.md)).
4. `lint-imports` checks the layer rules ([import-linter.md](import-linter.md)).
5. `python -m pipeline lint-workflows` applies the workflow rules ([github-actions.md](github-actions.md)).
6. `python -m pipeline check-contract` checks the ten-line contract in the README.

`format` is the fixing counterpart: `ruff check --fix .` applies safe fixes and `ruff format .` reformats.

### `test`, `test-domain`, `quarantine` (lines 74 to 90)

```make
# Unit tests need no database. The quarantined test is excluded here (UNIT_MARKERS) and run by `make quarantine`,
# which the CI quarantine job calls, and by `make flaky-hunt`.
UNIT_MARKERS ?= not flaky_quarantine
test: $(STAMP) ## unit tests of the service and the pipeline, with coverage and a JUnit report (no database needed)
	@mkdir -p reports
	$(PY) -m pytest tests/unit tests/pipeline -m "$(UNIT_MARKERS)" -p no:cacheprovider --junitxml=reports/unit.xml \
	  --cov --cov-report=term --cov-report=xml:reports/coverage.xml
	$(PY) -m coverage report --include='src/small_service/domain/*,src/small_service/application/*,pipeline/core/*' --fail-under=95

# The domain tests alone, quick enough to run dozens of times: what `make flaky-hunt` repeats.
test-domain: $(STAMP) ## unit tests of the domain package only (no coverage); UNIT_MARKERS= includes the quarantined test
	@mkdir -p reports
	$(PY) -m pytest tests/unit/domain -m "$(UNIT_MARKERS)" -p no:cacheprovider --junitxml=reports/unit.xml -q

quarantine: $(STAMP) ## the quarantined tests: they still run and report, and never block (exit status is ignored by CI)
	@mkdir -p reports
	$(PY) -m pytest tests/unit -m flaky_quarantine -p no:cacheprovider --junitxml=reports/quarantine.xml
```

- **Line 76**: `UNIT_MARKERS ?= not flaky_quarantine`. A *marker* labels tests; this expression selects every test **except** those labelled `flaky_quarantine` ([pytest.md](pytest.md)).
- **Lines 77 to 81**, `test`: `@mkdir -p reports` creates the `reports` folder if missing. Then `pytest` runs the unit and pipeline tests: `-m "$(UNIT_MARKERS)"` applies the marker expression; `-p no:cacheprovider` turns off pytest's cache folder; `--junitxml=reports/unit.xml` writes a machine-readable report; `--cov --cov-report=term --cov-report=xml:reports/coverage.xml` measure and print **coverage** (the share of code lines the tests ran) and also write it as a file. The last line, `coverage report ... --fail-under=95`, fails the target if the three pure folders are less than 95 percent covered.
- **Lines 84 to 86**, `test-domain`: only `tests/unit/domain`, quick enough to repeat dozens of times, without coverage. `UNIT_MARKERS=` (empty) includes the quarantined test. `make flaky-hunt` repeats this target. `-q` is quiet.
- **Lines 88 to 90**, `quarantine`: runs *only* the quarantined tests (`-m flaky_quarantine`). CI runs it as a non-blocking job: the test still runs and reports, but its failure does not fail the pipeline.

### `test-integration` and `test-artifact` (lines 92 to 106)

```make
test-integration: $(STAMP) ## the PostgreSQL adapter against the running database (make up first)
	@mkdir -p reports
	$(PY) -m pytest tests/integration -p no:cacheprovider --junitxml=reports/integration.xml

# The integration job of the pipeline: the same tests, run against the BUILT wheel in a clean environment.
ARTIFACT_VENV := .cache/artifact-venv-$(shell shasum -a 256 requirements-dev.lock | cut -c1-12)
test-artifact: $(STAMP) ## make test-artifact WHEEL=dist/x.whl EXPECTED_SHA256=...: verify, install the wheel, run the integration tests
	@test -n "$(WHEEL)" -a -n "$(EXPECTED_SHA256)" || { echo "usage: make test-artifact WHEEL=dist/x.whl EXPECTED_SHA256=<digest>"; exit 2; }
	@mkdir -p reports
	$(PY) -m pipeline verify $(WHEEL) --expected $(EXPECTED_SHA256) --job integration
	@test -x $(ARTIFACT_VENV)/bin/python || { $(PYTHON) -m venv $(ARTIFACT_VENV) && \
	  $(ARTIFACT_VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock; }
	$(ARTIFACT_VENV)/bin/pip install -q --no-deps --force-reinstall $(WHEEL)
	ARTIFACT_TESTS=1 $(ARTIFACT_VENV)/bin/python -m pytest tests/integration -p no:cacheprovider \
	  --junitxml=reports/integration.xml
```

- **Lines 92 to 94**, `test-integration`: runs `tests/integration` against the running database (`make up` first).
- **Line 97**: `ARTIFACT_VENV := .cache/artifact-venv-$(shell shasum -a 256 requirements-dev.lock | cut -c1-12)`. The name of a second environment includes the first 12 characters of the lock file's checksum, so if the lock changes you automatically get a fresh environment. `shasum -a 256` prints a file's SHA-256; `cut -c1-12` keeps characters 1 to 12.
- **Lines 98 to 106**, `test-artifact`: the CI integration job. It is called as `make test-artifact WHEEL=dist/x.whl EXPECTED_SHA256=<digest>`.
  - **Line 99** checks both variables were given: `test -n "$(WHEEL)" -a -n "$(EXPECTED_SHA256)"` is true if both are non-empty (`-n` non-empty, `-a` and). If not, `||` prints a usage message and `exit 2` ends with status 2.
  - **Line 101** verifies the wheel's checksum with `python -m pipeline verify`.
  - **Lines 102 and 103**: if the artifact environment's Python does not exist (`test -x` checks that a file is executable), create it and install the locked tools. The braces `{ ...; }` group commands.
  - **Line 104** installs the **built wheel** into that clean environment (`--force-reinstall`, `--no-deps`).
  - **Lines 105 and 106** run the integration tests with `ARTIFACT_TESTS=1` set for that one command; the tests then check that the code imported comes from the installed wheel and not from the source folder. The point of the lesson: test the thing you will ship.

### `test-e2e`, `audit`, `check` (lines 108 to 114)

```make
test-e2e: $(STAMP) ## the git gate end to end, in a temporary repository
	$(PY) -m pytest tests/e2e -m e2e

audit: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock

check: lint test ## everything that needs no database
```

- `test-e2e` runs the end-to-end test that builds a throw-away Git repository and exercises the push gate.
- `audit` runs `pip-audit` on the lock file to look for known vulnerabilities ([pip-audit.md](pip-audit.md)). The flags: `--no-deps` (the lock already lists everything), `--disable-pip` (do not make a temporary environment), `-r` (read this file).
- `check: lint test` has no recipe; it is a name for "both of those".

### `build`, `verify`, `deploy-local` (lines 116 to 125)

```make
build: $(STAMP) ## build the wheel once: dist/*.whl and dist/SHA256SUMS
	$(PY) -m pipeline build

verify: ## verify dist/*.whl against dist/SHA256SUMS
	cd dist && shasum -a 256 -c SHA256SUMS

# The artifact, installed into an image and run against the database: the local "deploy" of this lesson.
deploy-local: up build verify ## build an image from the verified wheel and run its smoke test against the database
	$(COMPOSE) --profile app build app
	$(COMPOSE) --profile app run --rm app
```

- `build` runs `python -m pipeline build`, which builds the wheel once from a copy of the sources and writes `dist/SHA256SUMS` ([python-packaging.md](python-packaging.md)).
- `verify` runs `cd dist && shasum -a 256 -c SHA256SUMS`: change into `dist` and check each file against the recorded checksum; `-c` means "check". The `&&` joins the two commands on one line so the `cd` applies.
- `deploy-local` needs `up build verify` (in that order), then builds a container image that installs the wheel (`docker compose --profile app build app`) and runs it once (`run --rm app` removes the container afterwards). This is the local "deploy": the artifact, not the source, is installed and run against the database.

### `gate-demo` and `workflows` (lines 127 to 131)

```make
gate-demo: $(STAMP) ## step 2 without GitHub: a remote that refuses main unless CI posted a green status
	PATH="$(CURDIR)/$(VENV)/bin:$$PATH" scripts/gate-demo.sh

workflows: $(STAMP) ## lint the workflows (required checks exist, nothing unpinned, no paths filter)
	$(PY) -m pipeline lint-workflows
```

- `gate-demo` runs `scripts/gate-demo.sh` with the project's `bin` folder first on `PATH` (the list of folders the shell searches for programs), so the script finds `python` and `pytest` ([bash-and-sh.md](bash-and-sh.md)). `$(CURDIR)` is the folder `make` runs in.
- `workflows` runs the workflow linter on its own.

### `act` (lines 133 to 138)

```make
# Run a job of the real workflow with act (needs Docker; see the README for what act can and cannot do).
# --container-daemon-socket - because the default socket path of Docker Desktop on a Mac cannot be mounted into the job.
ACT_JOB ?= changes
ACT_IMAGE ?= catthehacker/ubuntu:act-22.04
act: ## run one job of ci.yml with act (make act ACT_JOB=lint ACT_IMAGE=<an image with python, make, lsb-release>)
	act pull_request -j $(ACT_JOB) --container-architecture linux/arm64 --container-daemon-socket - -P ubuntu-latest=$(ACT_IMAGE)
```

- **Lines 135 and 136** set two overridable variables: the job to run and the Docker image that stands in for GitHub's runner.
- **Line 138**: `act pull_request -j $(ACT_JOB) --container-architecture linux/arm64 --container-daemon-socket - -P ubuntu-latest=$(ACT_IMAGE)`. `act` runs a workflow job on your own machine in a container ([act.md](act.md)). `pull_request` is the event to pretend. `-j` picks the job. `--container-architecture linux/arm64` matches an Apple-silicon Mac so nothing is emulated. `--container-daemon-socket -` stops `act` from mounting Docker's control socket into the job (the Docker Desktop path cannot be mounted). `-P ubuntu-latest=IMAGE` says which image to use for the label `ubuntu-latest`.

### `protection`, `contract`, `history` (lines 140 to 147)

```make
protection: $(STAMP) ## print the branch-protection JSON (make protection APPLY=owner/repo applies it with gh)
	$(PY) -m pipeline protection $(if $(APPLY),--apply $(APPLY),)

contract: $(STAMP) ## check the README's pipeline contract (ten lines, the red-main rule)
	$(PY) -m pipeline check-contract

history: $(STAMP) ## print the newest job runs recorded in the database
	$(VENV)/bin/small-service history
```

- `protection` prints the GitHub branch-protection JSON; `make protection APPLY=owner/repo` applies it with `gh`. `$(if $(APPLY),--apply $(APPLY),)` is `make`'s own `if`: if `APPLY` is non-empty add `--apply` and its value, otherwise add nothing.
- `contract` checks the README's ten-line contract. `history` runs `small-service history`: the newest job runs recorded in the database.

### `down` and `clean` (lines 149 to 153)

```make
down: ## stop PostgreSQL and delete its data
	$(COMPOSE) --profile app down -v

clean: down
	rm -rf $(VENV) .cache dist build reports logs .pytest_cache .mypy_cache .ruff_cache .import_linter_cache .coverage coverage.xml runs.csv
```

- `down` stops the database and deletes its data: `docker compose --profile app down -v` (`-v` also removes volumes).
- `clean` first does `down` (a prerequisite with no recipe of its own) and then `rm -rf` removes the environment, caches, build output, reports, logs and the run log. `rm -rf` deletes files and folders without asking.

## Try it yourself

```bash
make help
```
A sorted table of every target and its description.

```bash
make -n test
```
`-n` prints the commands without running them. You see the `mkdir`, the `pytest` line, the `coverage report` line.

```bash
make install && ls -la .venv/.installed && make install
```
The second `make install` prints nothing: the stamp file is newer than its prerequisites.

```bash
touch requirements-dev.lock && make -n install | head -3
```
Now Make would rebuild the environment, because a prerequisite is newer.

## Mistakes people make

- Using spaces instead of a tab to indent a recipe: `*** missing separator`. `.editorconfig` pins tabs for this file.
- Expecting `cd` to carry over between recipe lines. Use one joined line.
- Forgetting `$$` for shell variables inside a recipe.
- Forgetting `.PHONY` so that a stray folder named `test` silently disables `make test`.
- Writing Make 4-only features and breaking on macOS's Make 3.81.

## Check yourself

1. What does the stamp file `.venv/.installed` do? *It records that the environment was built; Make rebuilds only when the lock file or `pyproject.toml` is newer.*
2. What is the difference between `$(VENV)` and `$$script`? *The first is a Make variable; the second is a shell variable.*
3. Why does the workflow call `make lint` and not `ruff check .` directly? *So CI and a laptop run exactly the same job.*
4. What does `?=` do? *Sets a variable only if it is not already set, so callers can override.*
5. What does `make -n target` do? *Prints the commands without running them.*

## Further reading

- GNU Make manual: https://www.gnu.org/software/make/manual/make.html (this machine has 3.81; CI has 4.3 or newer)
- Phony targets: https://www.gnu.org/software/make/manual/make.html#Phony-Targets
