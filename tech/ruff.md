# ruff

## What it is

ruff is a very fast tool, written in Rust, that does two jobs for Python: a **linter** (finds likely bugs and style problems) and a **formatter** (rewrites code to one consistent layout). Pinned: 0.17.2. A **lint rule** has a code like `E501` (line too long) or `S603` (a subprocess call that deserves a look). You turn groups of rules on by their letter prefix.

## Why this repository uses it

A pipeline's `lint` job should be cheap and strict, and it should fail on the same things everywhere. `make lint` runs `ruff check` and `ruff format --check` first. Rules with a `S` prefix come from the "bandit" security checks and catch things like shell injection.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.ruff]`, `[tool.ruff.lint]` | Line length 120, target version, selected rule groups. |
| `Makefile` | `lint` runs `ruff check .` and `ruff format --check .`; `format` runs `ruff check --fix .` and `ruff format .`. |
| Source files | A few lines end with `# noqa: S603 - reason` to allow one finding with a written reason. |

## How it works underneath

ruff reads every `.py` file, builds a syntax tree, and applies rules to the tree. It does not run your code. The formatter prints the tree back out in a fixed style. `--check` only reports if a file would change (exit status 1) and leaves it alone.

## Walkthrough of this repository's use

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "pipeline", "tests"]
extend-exclude = ["build"]
```
Lines may be 120 characters. `target-version` lets ruff suggest modern syntax (3.12). `src` tells the import sorter which folders are "our" code, so it groups imports correctly. `build` is skipped.

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "S", "D100", "D101", "D103", "D104"]
```

| Prefix | Meaning |
|---|---|
| `E` | pycodestyle errors (line length, whitespace) |
| `F` | Pyflakes: unused imports and variables, undefined names |
| `I` | isort: import order |
| `B` | bugbear: likely bugs such as mutable default arguments |
| `UP` | pyupgrade: use newer syntax |
| `SIM` | simplifications |
| `N` | naming conventions |
| `C4` | comprehension tidy-ups |
| `RUF` | ruff's own rules |
| `PT` | pytest style |
| `S` | security (bandit) |
| `D100`, `D101`, `D103`, `D104` | missing docstring in a module, class, function, package |

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S"]
```
Tests do not need docstrings, and `assert` (flagged by `S101`) is the whole point of a test.

### Reasoned exceptions

```python
return random.uniform(MIN_JOB_SECONDS, MAX_JOB_SECONDS)  # noqa: S311 - simulated work time, not a secret
```
`S311` warns that `random` is not safe for secrets. Here it picks a delay, so the line says so. `# noqa: CODE - reason` silences only that code on that line, and the reason is part of the review. `process.py` uses `# noqa: S603 - argv is built by this program, never through a shell`.

### Format check in CI

`ruff format --check .` exits 1 if any file is not formatted. That keeps style arguments out of review.

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
