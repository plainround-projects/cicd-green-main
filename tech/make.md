# Make and the Makefile

## What it is

`make` is a command-line tool from the 1970s that runs recipes written in a file called `Makefile`. A Makefile is a list of **targets**. Each target has **prerequisites** (things that must be ready first) and a **recipe** (shell commands that produce the target). Make compares file times: if a target file is newer than all its prerequisites, it skips the recipe.

macOS ships GNU Make 3.81 (very old). Linux CI runners ship 4.x. The Makefile here uses only features common to both.

## Why this repository uses it

The lesson's rule is "every CI job is one `make` target, so `make run` runs the same jobs on a laptop." The workflow file does not contain commands like `ruff check .`. It says `run: make lint`. That keeps the laptop and CI identical and gives the learner one place to read what each job does.

## Where it appears

| Path | Role |
|---|---|
| `Makefile` | 28 documented targets. `make help` lists them. |
| `.github/workflows/ci.yml` | Calls `make build`, `make lint`, `make test`, `make test-artifact`, `make quarantine`, `make audit`, `make db`. |
| `pipeline/adapters/local_runner.py` | Runs `make --no-print-directory <target>` for each job of the local pipeline. |
| `.editorconfig` | Says Makefiles must be indented with tabs. |

## How it works underneath

- Running `make test` finds the target `test`, builds its prerequisites first (in order, recursively), then runs its recipe.
- Each recipe line runs in its **own** shell. A `cd` on one line does not carry to the next. Lines end with `\` to join them into one shell command.
- A recipe line starting with `@` is not printed before running. A line starting with `-` ignores errors.
- `$(NAME)` is a **Make** variable. `$$NAME` is a **shell** variable (Make turns `$$` into `$`).
- A **phony** target (listed after `.PHONY:`) is a name for an action, not a file, so it always runs.
- A **file target** like `.venv/.installed` is a real file. Make runs its recipe only when a prerequisite is newer.

## Walkthrough of this repository's use

```make
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
COMPOSE := docker compose
```
`?=` sets a variable only if the caller did not already set it (`make PYTHON=python3.12 install` overrides). `$(shell ...)` runs a command at read time and uses its output. `:=` expands the right side once, now. `STAMP` is the stamp file explained below.

```make
-include .env
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL CACHE_TTL_SECONDS JOB_TIMEOUT_SECONDS
```
`-include` reads another file as Makefile text; the leading `-` means "no error if it does not exist". `.env` contains lines like `POSTGRES_PORT=55471`, which are valid Make assignments. `export` passes those variables to every command Make starts, so the Python programs find their settings. See [dotenv.md](dotenv.md).

```make
$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@
```
This is the **stamp file** pattern. The target `.venv/.installed` depends on the lock file and `pyproject.toml`. If either changes, Make rebuilds the environment. `touch $@` creates the stamp at the end (`$@` is "the target's name"). Nearly every other target lists `$(STAMP)` as a prerequisite, so the first `make test` creates `.venv` and later runs skip it. `--require-hashes` makes pip refuse any file whose hash is not in the lock ([pip-and-hash-locking.md](pip-and-hash-locking.md)). `-e .` installs this project in editable mode so tests import the working copy.

```make
.env:
	cp .env.example .env
```
A file target with no prerequisites: if `.env` does not exist, copy the example.

```make
help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort
```
A self-documenting trick: every target has a `## description` after it. `help` greps those lines (`$(MAKEFILE_LIST)` is the list of Makefiles read) and prints `target<TAB>description`.

```make
up: $(STAMP) .env ## start PostgreSQL and apply sql/001_schema.sql and 002_seed.sql
	$(COMPOSE) up -d --wait db
	$(MAKE) --no-print-directory db
```
`up` needs the environment and `.env`, starts the `db` service ([docker-compose.md](docker-compose.md)) and waits until it is healthy (`--wait`), then calls Make again for the `db` target. `$(MAKE)` (not plain `make`) is how a Makefile calls itself.

```make
PSQL ?= $(COMPOSE) exec -T -e PGOPTIONS=--client-min-messages=warning db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db: ## apply the numbered scripts in sql/ (safe to repeat)
	@for script in sql/00[12]_*.sql; do \
	  echo "applying $$script"; \
	  $(PSQL) < $$script || exit 1; \
	done
```
`PSQL` is the command that runs SQL. CI overrides it (`make db PSQL="psql -h localhost ..."`) because there it talks to a service container, not compose. The `for` loop is one shell command spread over lines with `\`. `$$script` is a shell variable. `< $$script` feeds the file to psql's input. `|| exit 1` stops on the first failure. `-T` turns off the terminal so psql can read a pipe. See [postgresql.md](postgresql.md).

```make
test: $(STAMP) ## unit tests ...
	@mkdir -p reports
	$(PY) -m pytest tests/unit tests/pipeline -m "$(UNIT_MARKERS)" -p no:cacheprovider --junitxml=reports/unit.xml \
	  --cov --cov-report=term --cov-report=xml:reports/coverage.xml
	$(PY) -m coverage report --include='src/small_service/domain/*,src/small_service/application/*,pipeline/core/*' --fail-under=95
```
`UNIT_MARKERS ?= not flaky_quarantine` is a variable the flake hunt overrides. The last line fails the target if coverage of the pure layers is below 95%. See [pytest.md](pytest.md).

```make
ARTIFACT_VENV := .cache/artifact-venv-$(shell shasum -a 256 requirements-dev.lock | cut -c1-12)
```
A second virtual environment whose folder name contains the first 12 characters of the lock file's hash. Change the lock and you automatically get a fresh environment.

```make
test-artifact: $(STAMP)
	@test -n "$(WHEEL)" -a -n "$(EXPECTED_SHA256)" || { echo "usage: ..."; exit 2; }
```
Checks that the caller passed both variables and prints usage with exit status 2 otherwise.

`flaky-hunt` runs `$(PY) -m pipeline hunt --runs $(HUNT_RUNS)` and then `$(MAKE) --no-print-directory flaky-report`. `clean: down` removes build folders; because it depends on `down`, it stops the database first.

`.PHONY` lists all action targets so a file named `test` in the folder can never stop `make test` from running.

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
