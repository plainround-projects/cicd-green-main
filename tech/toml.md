# TOML and `pyproject.toml`

## What it is

TOML is a text format for configuration. It has `key = value` lines, `[table]` headings that group keys, and `[[array-of-tables]]` headings that start a new entry in a list. Strings are in double quotes, lists in `[...]`. Python 3.11 and newer can read TOML with the standard library module `tomllib`. `pyproject.toml` is the one file Python tools look at for project settings.

## Why this repository uses it

One file holds the project's name and version, its dependencies, and the settings of every tool: ruff, mypy, pytest, coverage and import-linter. A learner finds all settings in one place, and the pipeline itself reads the version from it.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | All the settings. |
| `pipeline/core/version.py` | `tomllib.loads(...)["project"]["version"]` and a regular expression that rewrites the `version = "..."` line. |
| `.editorconfig` | Says TOML files use a 2-space indent. |

## How it works underneath

A `[tool.ruff]` heading creates a table named `ruff` inside a table named `tool`. In Python that becomes `{"tool": {"ruff": {...}}}`. `[[tool.importlinter.contracts]]` appears several times, and each occurrence adds one dict to the `contracts` list. TOML has real types: strings, integers, floats, booleans, dates, lists, tables. Comments start with `#`.

## Walkthrough of this repository's use

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"
```
Which tool builds the package ([python-packaging.md](python-packaging.md)).

```toml
[project]
name = "cicd-green-main"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["psycopg[binary]>=3.2,<4"]
```
The package's identity. `psycopg[binary]` means "psycopg with its optional `binary` extra". `>=3.2,<4` is a version range.

```toml
[project.optional-dependencies]
dev = [ "pytest>=8,<10", "ruff>=0.6", "mypy>=1.11", ... ]
```
A named group. `pip install -e ".[dev]"` would install it; `uv pip compile --extra dev` reads it ([pip-and-hash-locking.md](pip-and-hash-locking.md)).

```toml
[project.scripts]
small-service = "small_service.interfaces.cli:main"
```
Command name = `module:function`.

```toml
[tool.ruff] ...        # see ruff.md
[tool.mypy] ...        # see mypy.md
[tool.pytest.ini_options] ...   # see pytest.md
[tool.coverage.run]
source = ["small_service", "pipeline"]
branch = true
[tool.coverage.report]
show_missing = true
skip_covered = false
[tool.importlinter] ...  # see import-linter.md
```
Each tool reads only its own table.

### Reading and stamping the version

```python
version = tomllib.loads(pyproject_text)["project"]["version"]
```
`tomllib.loads` parses text into a dict. The pipeline then checks the value looks like `MAJOR.MINOR.PATCH`.

```python
_VERSION_LINE = re.compile(r'^(version\s*=\s*)"[^"]*"', re.MULTILINE)
stamped, count = _VERSION_LINE.subn(lambda match: f'{match.group(1)}"{version}"', pyproject_text, count=1)
```
Replaces only the first `version = "..."` line in a copy, keeping everything else byte for byte. `count != 1` raises an error, so a file with no version line cannot be silently built wrong.

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
