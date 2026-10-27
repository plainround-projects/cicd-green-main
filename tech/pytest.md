# pytest and coverage

## What it is

pytest is a Python test runner. You write functions whose names start with `test_`; pytest finds them, runs each one, and reports which passed. A test **passes** if it finishes and **fails** if an `assert` is false or an exception escapes. `pytest-cov` adds **coverage**: a measurement of which lines of your code ran during the tests (done by the `coverage` library). Pinned: pytest 9.1.1, pytest-cov 7.1.0, coverage 7.17.0.

## Why this repository uses it

The pipeline's job is to run checks and decide if `main` is releasable. The checks are these tests, in four groups: unit (no database), pipeline (the pipeline's own rules), integration (against PostgreSQL) and e2e (the git gate). Coverage gives a floor: the pure layers must stay at 95% or higher.

## Where it appears

| Path | Use |
|---|---|
| `tests/unit/` | Service tests with fakes (`FakeClock`, `InMemoryJobStore`). |
| `tests/pipeline/` | Tests of `pipeline/core` and the builder, runner, and rules. |
| `tests/integration/` | The PostgreSQL adapter; the built wheel. |
| `tests/e2e/test_gate_demo.py` | Runs `scripts/gate-demo.sh`. |
| `pyproject.toml` `[tool.pytest.ini_options]` and `[tool.coverage.*]` | Settings and markers. |
| `Makefile` | `test`, `test-domain`, `quarantine`, `test-integration`, `test-artifact`, `test-e2e`. |

## How it works underneath

- pytest **collects**: it walks the folders you name, imports files called `test_*.py`, and picks functions called `test_*`.
- When a test uses an `assert`, pytest rewrites it at import time so a failure shows the values on both sides.
- A **fixture** is a function marked `@pytest.fixture`. A test asks for one by naming it as a parameter. pytest runs the fixture first and passes in its result. A fixture with `yield` runs its cleanup after the test.
- A **marker** (`@pytest.mark.name`) labels tests. `-m "not flaky_quarantine"` selects by marker.
- **Coverage** traces the program as it runs and records which lines (and with `branch = true`, which `if` outcomes) executed.
- **JUnit XML** (`--junitxml`) is a standard report format other tools read ([junit-xml.md](junit-xml.md)).

## Walkthrough of this repository's use

### Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs the PostgreSQL service from docker-compose.yml (make up)",
    "e2e: runs the pipeline's own scenarios (git gate, local runner) end to end",
    "flaky_quarantine: a test with a known timing flake; excluded from the required job, run by the non-blocking quarantine job",
]
```
`pythonpath = ["."]` puts the repository root on the import path so `from tests.unit.fakes import FakeClock` works. `-ra` prints a summary line for every test that did not simply pass. `--strict-markers` turns a misspelled marker into an error instead of silently selecting nothing.

### Tests without sleeping

```python
def test_a_value_expires_exactly_at_its_time_to_live():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(10)
    assert cache.get("a") is None
```
`FakeClock` is an object you call like a function; `advance(10)` moves time by hand. The test proves expiry at exactly the TTL and takes microseconds.

### Fixtures that clean up (`tests/integration/conftest.py`)

```python
@pytest.fixture
def key_prefix(settings: Settings) -> Iterator[str]:
    prefix = f"it-{uuid.uuid4().hex[:8]}"
    yield prefix
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("DELETE FROM job_runs WHERE job_key LIKE %s", (f"{prefix}%",))
```
Each test gets a random prefix, saves rows under it, and the code after `yield` deletes them. Tests never see each other's data. `scope="session"` on the `settings` fixture means it is built once.

```python
def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.integration)
```
A **hook function** (pytest calls it by name) that marks every test in the folder as `integration`.

### The quarantined flaky test

```python
@pytest.mark.flaky_quarantine
def test_job_finishes_in_time():
    job = Job()
    job.start()
    time.sleep(0.1)  # a timing assumption: the job is usually, not always, finished by now
    assert job.done
```
The job takes a random 50 to 112.5 ms; the test guesses 100 ms. It fails about one run in five. The marker keeps it out of the required `unit` job (`-m "not flaky_quarantine"`) and the non-blocking `quarantine` job still runs it. The fixed version, in `test_jobs.py`, calls `job.wait(...)`, which takes exactly as long as the work.

### Makefile flags

```make
$(PY) -m pytest tests/unit tests/pipeline -m "$(UNIT_MARKERS)" -p no:cacheprovider --junitxml=reports/unit.xml \
  --cov --cov-report=term --cov-report=xml:reports/coverage.xml
$(PY) -m coverage report --include='src/small_service/domain/*,src/small_service/application/*,pipeline/core/*' --fail-under=95
```
`-p no:cacheprovider` disables pytest's `.pytest_cache` folder. `--cov` turns on coverage using `[tool.coverage.run]` (`source`, `branch = true`). `--cov-report=term` prints a table; `xml:` writes a file CI can read. The second command fails the build if the three pure areas (the logic that needs no database) are under 95%.

### Testing the artifact

`make test-artifact` installs the **built wheel** into a separate environment and sets `ARTIFACT_TESTS=1`, so `tests/integration/test_artifact.py` checks the installed package, not the source tree.

## Try it yourself

```bash
make test
```
Expect a coverage table and a final line like `NNN passed`, then a coverage report that ends without `FAIL Required test coverage`.

```bash
.venv/bin/python -m pytest tests/unit/domain -q -m "flaky_quarantine"
```
Runs only the flaky test. Run it 10 times (`for i in 1 2 3 4 5 6 7 8 9 10; do ...; done`) and count failures.

```bash
.venv/bin/python -m pytest --collect-only -q tests/unit/domain | tail -5
```
Lists the tests without running them.

```bash
make flaky-hunt HUNT_RUNS=10
```
Runs the domain tests, including the flaky one, 10 times and prints the failure rate from `runs.csv`.

## Mistakes people make

- Tests that call `time.sleep` and guess. This repository has exactly one on purpose, and quarantines it.
- Shared state between tests. The `key_prefix` fixture isolates the database tests.
- A misspelled marker that selects zero tests. `--strict-markers` stops that.
- Chasing 100% coverage with empty tests. The floor measures only the pure layers.
- Rerunning a red build until it turns green. The flake hunt finds the cause instead.

## Check yourself

1. What makes pytest treat a function as a test? *A name starting with `test_` in a file `test_*.py`.*
2. What does `yield` in a fixture do? *Everything before gives the test its value; everything after runs as cleanup.*
3. What does `-m "not flaky_quarantine"` do? *Skips tests marked as quarantined.*
4. What does `--fail-under=95` do? *Exits with an error if coverage is below 95%.*
5. Why does `test-artifact` install the wheel? *To test the thing that will ship, not the source folder.*

## Further reading

- pytest 9 documentation: https://docs.pytest.org/en/stable/
- Fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html
- Markers: https://docs.pytest.org/en/stable/how-to/mark.html
- coverage.py: https://coverage.readthedocs.io/ (7.17.0) and pytest-cov: https://pytest-cov.readthedocs.io/
