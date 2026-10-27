# TOML and `pyproject.toml`

## What it is

A **configuration file** holds settings for a program, separate from the program's code. **TOML** ("Tom's Obvious, Minimal Language") is a text format for such files that is easy for people to read and write. Its building blocks:

- A line `key = value` sets a setting. Values can be **text** (in double quotes: `"py312"`), **whole numbers** (`120`), **true/false** (`true`, `false`), **lists** (square brackets: `["a", "b"]`) or **inline tables** (curly braces: `{ text = "MIT" }`).
- A line in square brackets, `[tool.ruff]`, starts a **table**: a named group of settings. Dots express nesting, so `[tool.ruff.lint]` is a table `lint` inside `ruff` inside `tool`. The settings that follow belong to that table until the next table heading.
- A line in double square brackets, `[[tool.mypy.overrides]]`, starts a new entry in a **list of tables**: you may write the same heading several times, and each time adds one more item to the list.
- A `#` starts a comment.

`pyproject.toml` is the one file in a Python project where tools look for their settings: the build tool, the formatter, the type checker, the test runner. Python 3.11 and newer can also read TOML itself with the standard library module `tomllib`.

## Why this repository uses it

One file holds the project's name and version, its dependencies, and the settings of every tool: ruff, mypy, pytest, coverage and import-linter. A learner who wants to know "how is this checked?" looks in one place. The pipeline also *reads* this file: it takes the project's version from it ([python-packaging.md](python-packaging.md)).

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | All of it, 112 lines, covered below. |
| `pipeline/core/version.py` | Reads `project.version` with `tomllib` and rewrites the version line in a copy. |
| `.editorconfig` | Gives TOML files a two-space indent ([editorconfig.md](editorconfig.md)). |

## How it works underneath

`tomllib.loads(text)` turns the text into ordinary Python dictionaries. `[tool.ruff]` becomes `{"tool": {"ruff": {...}}}`; each `[[tool.importlinter.contracts]]` appends one dictionary to the list at `["tool"]["importlinter"]["contracts"]`. A tool reads only its own table (ruff reads `tool.ruff`, mypy reads `tool.mypy`), and it ignores the rest.

## Walkthrough of this repository's use

Every line of `pyproject.toml`, in order.

### `[build-system]`: how the package is built

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"
```

When someone builds the package, the build tool reads this table first. `requires` lists what must be installed to run the build: `setuptools` (at least version 75, the library that knows how to assemble a Python package) and `wheel` (the helper that writes the `.whl` file format). `build-backend` names the Python object that does the build: `setuptools.build_meta`. See [python-packaging.md](python-packaging.md).

### `[project]`: the package's identity

```toml
[project]
name = "cicd-green-main"
version = "0.1.0"
description = "A small service and the CI pipeline that keeps its main branch releasable: parallel jobs, one checksummed artifact, a quarantined flaky test."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "Sumit Srivastava" }]
dependencies = ["psycopg[binary]>=3.2,<4"]
```

- `name`: the package's name. `version = "0.1.0"`: the base version; the pipeline stamps the commit onto it for every build. `description`: one sentence. `readme = "README.md"`: the file shown as the package's long description. `requires-python = ">=3.12"`: refuse to install on older Python. `license = { text = "MIT" }`: an inline table naming the licence. `authors = [{ name = "Sumit Srivastava" }]`: a list containing one inline table.
- `dependencies = ["psycopg[binary]>=3.2,<4"]`: what the service needs to run. `psycopg[binary]` is the library with its optional "binary" extra; `>=3.2,<4` is a version range: 3.2 or newer, but below 4. See [psycopg.md](psycopg.md).

### `[project.optional-dependencies]`: the tools for development

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8,<10",
    "pytest-cov>=5",
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.0",
    "pip-audit>=2.7",
    "build>=1.2",
    "setuptools>=75",
    "wheel>=0.45",
    "pyyaml>=6",
    "types-PyYAML>=6",
]
```

A named group `dev` of packages that are *not* needed to run the service but are needed to check and build it: `pytest` and `pytest-cov` (tests and coverage), `ruff` (lint and format), `mypy` (types), `import-linter` (layer rules), `pip-audit` (vulnerability check), `build`, `setuptools` and `wheel` (packaging), `pyyaml` (the workflow linter reads YAML) and `types-PyYAML` (type information for it). The lock files are generated from these ranges ([uv.md](uv.md)).

### `[project.scripts]`: a command that the installer creates

```toml
[project.scripts]
small-service = "small_service.interfaces.cli:main"
```

`small-service = "small_service.interfaces.cli:main"` means: when this package is installed, create a command named `small-service` that imports the module `small_service.interfaces.cli` and calls its function `main`. That is how `small-service history` works after `pip install`.

### `[tool.setuptools.packages.find]`

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

`where = ["src"]`: look for packages inside the `src` folder. (A `src` layout keeps tests from accidentally importing the source folder instead of the installed package.)

### `[tool.ruff]` and `[tool.ruff.lint]`

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "pipeline", "tests"]
extend-exclude = ["build"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "S", "D100", "D101", "D103", "D104"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S"]
```

Explained key by key in [ruff.md](ruff.md).

### `[tool.mypy]` and its override

```toml
[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "pipeline", "tests"]

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
```

Explained in [mypy.md](mypy.md). Notice the `[[ ... ]]` heading on line 53: it adds one item to the list of overrides, an entry that applies only to modules matching `tests.*`.

### `[tool.pytest.ini_options]`

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

- `testpaths = ["tests"]`: where pytest looks. `pythonpath = ["."]`: add the repository root to Python's import search list, so `from tests.unit.fakes import ...` works. `addopts = "-ra --strict-markers"`: options added to every run (`-ra` prints a short summary of everything that did not pass cleanly; `--strict-markers` makes an unknown marker an error). `markers = [...]` declares the three labels used on tests: `integration`, `e2e` and `flaky_quarantine`, each with a description. See [pytest.md](pytest.md).

### `[tool.coverage.run]` and `[tool.coverage.report]`

```toml
[tool.coverage.run]
source = ["small_service", "pipeline"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = false
```

- `source = ["small_service", "pipeline"]`: measure these packages. `branch = true`: also check, for each `if`, whether both outcomes were exercised. In the report table: `show_missing = true` lists the line numbers that no test ran; `skip_covered = false` keeps fully covered files in the table.

### `[tool.importlinter]` and its contracts

```toml
[tool.importlinter]
root_packages = ["small_service", "pipeline"]
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Service layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = [
    "small_service.interfaces",
    "small_service.infrastructure",
    "small_service.application",
    "small_service.domain",
]

[[tool.importlinter.contracts]]
name = "Service domain and application know nothing about PostgreSQL"
type = "forbidden"
source_modules = ["small_service.domain", "small_service.application"]
forbidden_modules = ["psycopg"]

[[tool.importlinter.contracts]]
name = "Pipeline layers: cli -> adapters -> core, never upward"
type = "layers"
layers = ["pipeline.cli", "pipeline.adapters", "pipeline.core"]

[[tool.importlinter.contracts]]
name = "Pipeline core is pure: no subprocess, no network"
type = "forbidden"
source_modules = ["pipeline.core"]
forbidden_modules = ["subprocess", "socket", "urllib", "http"]

[[tool.importlinter.contracts]]
name = "The pipeline tooling never imports the service it builds"
type = "forbidden"
source_modules = ["pipeline"]
forbidden_modules = ["small_service"]
```

Explained contract by contract in [import-linter.md](import-linter.md).

### How the pipeline reads this file

```python
def base_version(pyproject_text: str) -> str:
    """The `project.version` of a pyproject.toml, which must be MAJOR.MINOR.PATCH."""
    version = tomllib.loads(pyproject_text)["project"]["version"]
    if not _SEMVER.match(version):
        raise VersionError(f"project.version must be MAJOR.MINOR.PATCH, got {version!r}")
    return str(version)
```

`tomllib.loads(pyproject_text)["project"]["version"]` reaches into the `project` table and takes `version`. Opening the file for `tomllib.load` instead of `loads` requires binary mode (`"rb"`), because the module decodes the UTF-8 itself. The function then checks that the value looks like `MAJOR.MINOR.PATCH`.

```python
def stamp_pyproject(pyproject_text: str, version: str) -> str:
    """Replace the first `version = "..."` line (the one in `[project]`) with `version`."""
    stamped, count = _VERSION_LINE.subn(lambda match: f'{match.group(1)}"{version}"', pyproject_text, count=1)
    if count != 1:
        raise VersionError("pyproject.toml has no version line to stamp")
    return stamped
```

`stamp_pyproject` rewrites only the first `version = "..."` line, with a regular expression, in a *copy* of the file, so that a comment or the order of keys is never disturbed.

## Try it yourself

```bash
.venv/bin/python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); print(d['project']['version'], d['tool']['ruff']['line-length'])"
```
Expect `0.1.0 120`. (`tomllib` needs the file opened in binary mode.)

```bash
.venv/bin/python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); print(len(d['tool']['importlinter']['contracts']))"
```
Expect `5`.

```bash
.venv/bin/python -m pipeline version
```
The base `0.1.0` plus the commit.

## Mistakes people make

- Single quotes vs double quotes confusion (both exist; here double quotes are used).
- Forgetting the double brackets for a list of tables.
- Repeating a table heading twice (an error).
- Editing the version by hand in a build step instead of stamping a copy.

## Check yourself

1. What does `[[tool.importlinter.contracts]]` do? *Adds one entry to a list of tables.*
2. Why open the file in binary mode for `tomllib.load`? *The module expects bytes so it can decode UTF-8 itself.*
3. What does `>=3.2,<4` mean? *Version 3.2 or newer, but below 4.*
4. Where do tool settings live? *Under `[tool.<name>]`.*
5. Why does the stamp function check `count`? *To fail if no version line was replaced.*

## Further reading

- TOML specification: https://toml.io/en/v1.0.0
- `tomllib`: https://docs.python.org/3.12/library/tomllib.html
- `pyproject.toml` guide: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
