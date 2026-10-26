# make up | run | test | lint | down      (make help lists everything)
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
COMPOSE := docker compose

-include .env
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL CACHE_TTL_SECONDS JOB_TIMEOUT_SECONDS

.PHONY: help install up db down run run-baseline bench flaky-hunt flaky-report test quarantine test-integration test-artifact \
        test-e2e lint format audit check build verify deploy-local gate-demo workflows act protection contract history clean

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort

$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file

.env:
	cp .env.example .env

# The local target: PostgreSQL in a container, with the schema and the seed rows from sql/ applied.
up: $(STAMP) .env ## start PostgreSQL and apply sql/001_schema.sql and 002_seed.sql
	$(COMPOSE) up -d --wait db
	$(MAKE) --no-print-directory db

# CI has a service container instead of compose: make db PSQL="psql -h localhost -p 5432 -U service -d service"
PSQL ?= $(COMPOSE) exec -T db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db: ## apply the numbered scripts in sql/ (safe to repeat)
	@for script in sql/00[12]_*.sql; do \
	  echo "applying $$script"; \
	  $(PSQL) < $$script || exit 1; \
	done

# The whole pipeline, locally: build once, then lint, unit tests and the integration test in parallel (the integration
# test runs against the built, checksum-verified wheel), and the quarantine job beside them. One row goes to runs.csv.
run: up ## the whole pipeline locally (parallel jobs, one artifact); appends a row to runs.csv
	$(PY) -m pipeline run

run-baseline: up ## the first version of the pipeline: cold environment, everything in sequence
	$(PY) -m pipeline run --variant sequential

bench: up ## 5 sequential and 5 parallel runs, then the before and after table (takes about 10 minutes)
	$(PY) -m pipeline bench --runs 5

# Step 5: run the unit job WITH the quarantined test 40 times on one commit, then read the log.
HUNT_RUNS ?= 40
flaky-hunt: $(STAMP) ## run the unit job with the planted flaky test HUNT_RUNS times (default 40)
	@for run in $$(seq 1 $(HUNT_RUNS)); do \
	  $(PY) -m pipeline run --variant parallel --only unit --include-quarantined >/dev/null || true; \
	done
	$(MAKE) --no-print-directory flaky-report

flaky-report: $(STAMP) ## find flaky tests in runs.csv: commits with both a pass and a fail, and each test's failure rate
	$(PY) -m pipeline flaky

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

# Unit tests need no database. The quarantined test is excluded here (UNIT_MARKERS) and run by `make quarantine`,
# which the CI quarantine job calls, and by `make flaky-hunt`.
UNIT_MARKERS ?= not flaky_quarantine
test: $(STAMP) ## unit tests of the service and the pipeline, with coverage and a JUnit report (no database needed)
	@mkdir -p reports
	$(PY) -m pytest tests/unit tests/pipeline -m "$(UNIT_MARKERS)" -p no:cacheprovider --junitxml=reports/unit.xml \
	  --cov --cov-report=term --cov-report=xml:reports/coverage.xml
	$(PY) -m coverage report --include='src/small_service/domain/*,src/small_service/application/*,pipeline/core/*' --fail-under=95

quarantine: $(STAMP) ## the quarantined tests: they still run and report, and never block (exit status is ignored by CI)
	@mkdir -p reports
	$(PY) -m pytest tests/unit -m flaky_quarantine -p no:cacheprovider --junitxml=reports/quarantine.xml

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

test-e2e: $(STAMP) ## the git gate end to end, in a temporary repository
	$(PY) -m pytest tests/e2e -m e2e

audit: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock

check: lint test ## everything that needs no database

build: $(STAMP) ## build the wheel once: dist/*.whl and dist/SHA256SUMS
	$(PY) -m pipeline build

verify: ## verify dist/*.whl against dist/SHA256SUMS
	cd dist && shasum -a 256 -c SHA256SUMS

# The artifact, installed into an image and run against the database: the local "deploy" of this lesson.
deploy-local: up build verify ## build an image from the verified wheel and run its smoke test against the database
	$(COMPOSE) --profile app build app
	$(COMPOSE) --profile app run --rm app

gate-demo: $(STAMP) ## step 2 without GitHub: a remote that refuses main unless CI posted a green status
	PATH="$(CURDIR)/$(VENV)/bin:$$PATH" scripts/gate-demo.sh

workflows: $(STAMP) ## lint the workflows (required checks exist, nothing unpinned, no paths filter)
	$(PY) -m pipeline lint-workflows

# Run the real workflow with act (needs Docker; see the README for what act cannot do).
act: ## run the CI workflow's lint and unit jobs with act
	act pull_request -j lint --container-architecture linux/arm64 -P ubuntu-latest=catthehacker/ubuntu:act-22.04
	act pull_request -j unit --container-architecture linux/arm64 -P ubuntu-latest=catthehacker/ubuntu:act-22.04

protection: $(STAMP) ## print the branch-protection JSON (make protection APPLY=owner/repo applies it with gh)
	$(PY) -m pipeline protection $(if $(APPLY),--apply $(APPLY),)

contract: $(STAMP) ## check the README's pipeline contract (ten lines, the red-main rule)
	$(PY) -m pipeline check-contract

history: $(STAMP) ## print the newest job runs recorded in the database
	$(VENV)/bin/small-service history

down: ## stop PostgreSQL and delete its data
	$(COMPOSE) --profile app down -v

clean: down
	rm -rf $(VENV) .cache dist build reports logs .pytest_cache .mypy_cache .ruff_cache .import_linter_cache .coverage coverage.xml runs.csv
