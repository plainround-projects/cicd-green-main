# ruff

## What it is

Code can be correct and still be hard to read, inconsistent, or full of small mistakes: an unused variable, a name that is used before it exists, a risky call. A **linter** is a program that reads your source files *without running them* and points these out. A **formatter** is a program that rewrites your files into one fixed layout (spaces, line breaks, quote style) so people never argue about it.

**ruff** is both, for Python. It is written in Rust, which makes it very fast. This repository pins ruff 0.17.2. A **lint rule** has a code like `E501` ("line too long") or `S603` ("a program is started from variable input"). Rules are grouped by the letters at the start of their codes, and you switch groups on by those letters.

## Why this repository uses it

A pipeline's `lint` job should be cheap and strict. `make lint` runs ruff first. The security group (the letter `S`, from a tool named "bandit") is included because the pipeline starts programs and opens files, which is where such mistakes happen.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.ruff]` and `[tool.ruff.lint]` | The settings. |
| `Makefile` | `lint` runs `ruff check .` and `ruff format --check .`; `format` runs `ruff check --fix .` and `ruff format .`. |
| Several source files | Lines that end in `# noqa: CODE - reason`. |

## How it works underneath

ruff reads every `.py` file and turns it into a *syntax tree* (a structured picture of the program: functions, statements, calls). It applies each enabled rule to the tree and reports matches with file, line and code. It does not run your program. The formatter prints the same tree back in a fixed style. `ruff check --fix` applies the fixes it is sure about. `ruff format --check` reports unformatted files and exits with 1, changing nothing.

## Walkthrough of this repository's use

### The settings in `pyproject.toml`

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "pipeline", "tests"]
extend-exclude = ["build"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "S", "D100", "D101", "D103", "D104"]
```

- **Line 36**: `[tool.ruff]` starts the table of general settings ([toml.md](toml.md)).
- **Line 37**: `line-length = 120`: the formatter wraps at 120 characters, and rule `E501` complains above that.
- **Line 38**: `target-version = "py312"`: the oldest Python the code must run on, so ruff may suggest newer syntax (rule group `UP`).
- **Line 39**: `src = ["src", "pipeline", "tests"]`: the folders that hold the project's own code, so the import sorter can tell *our* modules from third-party ones.
- **Line 40**: `extend-exclude = ["build"]`: skip the `build` folder.
- **Line 42**: `[tool.ruff.lint]` is the table for lint rules. **Line 43**: `select = [...]` lists which groups are on:

| Prefix | What it checks |
|---|---|
| `E` | style errors from pycodestyle (line length, whitespace) |
| `F` | Pyflakes: unused imports and variables, undefined names |
| `I` | isort: the order of `import` lines |
| `B` | bugbear: constructs that are probably bugs (for example a mutable default argument) |
| `UP` | pyupgrade: old syntax that has a newer form |
| `SIM` | simplifications of needlessly complicated code |
| `N` | naming conventions (classes in `CamelCase`, functions in `snake_case`) |
| `C4` | clearer ways to write list, dictionary and set comprehensions |
| `RUF` | ruff's own rules |
| `PT` | style of pytest tests |
| `S` | security (from "bandit") |
| `D100`, `D101`, `D103`, `D104` | a docstring is missing from a module, a class, a function, a package |

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S"]
```

- **Lines 45 and 46**: `[tool.ruff.lint.per-file-ignores]` with `"tests/**" = ["D", "S"]`: in the tests folder, docstring rules (`D`) and security rules (`S`) are off. Tests use `assert`, which the security group flags, and need no docstrings.

### The `Makefile` commands

- `ruff check .` (the dot means the whole project) prints each finding and exits non-zero if there is any. `ruff format --check .` fails if any file would be reformatted. `make format` runs `ruff check --fix .` then `ruff format .` ([make.md](make.md)).

### Reasoned exceptions in the code

When a rule fires on code that is fine, the line ends with `# noqa: CODE - reason`: `noqa` means "no quality assurance" for this line, only for that code, and the text after the dash is the reason, so a reviewer can judge it. The ones in this repository:

- `src/small_service/domain/jobs.py` line 29: `random.uniform(...)  # noqa: S311 - simulated work time, not a secret`. Rule `S311` warns that Python's `random` module is not safe for passwords or tokens. Here it only picks a pretend duration.
- `pipeline/adapters/process.py` lines 50 and 72, `gate.py` line 20 and `github.py` lines 12, 22 and 23: `# noqa: S603` (and `S607` for a partial program path such as `gh`): rules about starting programs from variable input. The command is always a *list built by this program* and is never passed through a shell, so nothing a stranger types can become a command.
- `pipeline/core/flaky.py` line 57: `# noqa: S314 - our own pytest report, not untrusted input`. `S314` warns that reading XML from an unknown source can be abused; this file was written by our own test run.

## Try it yourself

```bash
.venv/bin/ruff --version
.venv/bin/ruff check .
```
Expect `ruff 0.17.2` and `All checks passed!`.

```bash
.venv/bin/ruff check . --select E501 --statistics
```
Counts a single rule.

```bash
.venv/bin/ruff rule S603
```
Prints the rule's explanation.

```bash
.venv/bin/ruff format --diff src/small_service/domain/cache.py
```
Shows what the formatter would change (nothing, if it is already formatted).

## Mistakes people make

- Silencing a rule with a bare `# noqa`. Always name the code and give a reason.
- Fighting the formatter by hand. Run `make format`.
- Turning on every rule at once and drowning in noise. Select groups you can keep clean.
- Treating `--fix` as safe for every rule. Review the diff.

## Check yourself

1. What is the difference between `ruff check` and `ruff format`? *`check` finds problems; `format` rewrites layout.*
2. What does `--check` do on `format`? *Reports unformatted files with exit 1 and changes nothing.*
3. What does the `S` prefix cover? *Security rules from bandit.*
4. Why ignore `S` in `tests/**`? *Tests use `assert` and similar patterns that the rules would flag.*
5. What belongs after `# noqa: S311`? *A reason.*

## Further reading

- ruff documentation: https://docs.astral.sh/ruff/ (pinned 0.17.2)
- Rules list: https://docs.astral.sh/ruff/rules/
- Configuration: https://docs.astral.sh/ruff/configuration/
