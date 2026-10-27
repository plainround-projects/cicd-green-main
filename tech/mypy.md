# mypy

## What it is

Python lets you pass anything to anything and finds out at run time, when something fails. A **type hint** is a note on a name, a parameter or a result saying what kind of value belongs there: `limit: int`, `-> list[JobRecord]`. A **type checker** is a program that reads those notes *without running the program* and reports places where they contradict each other: you passed text where a number is expected; you used a value that might be `None` as if it were never `None`; you called a method that the object does not have.

**mypy** is the most widely used type checker for Python. This repository pins mypy 2.4.0. Python itself ignores type hints when the program runs; they are for mypy, for editors and for the reader.

Useful words: `X | None` means "an X, or the special value `None`" (a value that means "nothing"). A **Protocol** is a list of methods that an object must have; mypy accepts any object that has them, without inheritance. **Strict mode** switches on all of mypy's optional checks.

## Why this repository uses it

The lesson is about gates that stop bad changes before they merge. A type error is a mistake found in seconds, before any test or user meets it. Here the checker also guards the design: the `JobStore` port is a `Protocol`, and mypy verifies that the PostgreSQL adapter really offers every method the application layer calls.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 48 to 57 | The settings. |
| `Makefile` `lint` | Runs `mypy` with no arguments (the files come from the settings). |
| `src/`, `pipeline/`, `tests/` | All three are checked. |

## How it works underneath

mypy parses every file, builds a model of each function's input and output types, and then checks every call and assignment against it. It follows `if x is not None:` checks to know that inside the `if` the value is not `None`. For a `Protocol` it compares method names and signatures. Libraries without hints need a *stub package* of hints: `types-PyYAML` is the stub package for `pyyaml`.

## Walkthrough of this repository's use

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

- **Line 48**: `[tool.mypy]` starts the table. **Line 49**: `python_version = "3.12"` checks as if running Python 3.12.
- **Line 50**: `strict = true` turns on every optional strictness check. Among them: every function must have type hints on all parameters and its result (`disallow_untyped_defs`); calling an untyped function from typed code is an error; returning a value of type `Any` from a typed function is a warning; an unused `# type: ignore` comment is an error; implicit `Optional` is not allowed.
- **Line 51**: `files = ["src", "pipeline", "tests"]` are the folders to check, so `mypy` with no arguments checks the project.
- **Lines 53 to 57**: `[[tool.mypy.overrides]]` adds an override for `module = ["tests.*"]` (all test modules): `disallow_untyped_defs`, `disallow_incomplete_defs` and `disallow_untyped_calls` are set to `false`. Test functions then need no hints (`def test_x(store):`), which keeps them short; the code under test stays strictly checked.

### What strictness catches in this code

- `TimedCache.get(self, key: K) -> V | None` (`domain/cache.py`): the result may be `None`, so every caller must check before using it. `JobRunner.run` does: `cached = self._cache.get(key)` then `if cached is not None:`.
- `JobStore` (`application/ports.py`) is a `Protocol` with `save`, `recent` and `ping`. `JobRunner` is declared to take a `JobStore`; in `interfaces/cli.py` it is given a `PostgresJobStore`. If `PostgresJobStore` lost a method or changed a signature, `mypy` would reject that line. In the tests, `InMemoryJobStore` (tests/unit/fakes.py) is accepted the same way.
- `Settings.from_env(cls, environ: Mapping[str, str] | None = None) -> Settings`: `Mapping` means a read-only dictionary-like object, so the function promises not to change what it is given; the `| None` default is checked: the body does `os.environ if environ is None else environ`.
- `class TimedCache[K, V]` and `def retry[T](...) -> T` use Python 3.12 generics: mypy tracks which type goes in and which comes out, so `retry(lambda: psycopg.connect(...))` is known to return a connection.
- `Callable[[], float]` for `clock` means "a function taking no arguments and returning a float"; passing `time.monotonic` is accepted, passing a function that needs an argument is rejected.

## Try it yourself

```bash
.venv/bin/mypy --version
.venv/bin/mypy
```
Expect `mypy 2.4.0` and `Success: no issues found in N source files`.

Make a deliberate mistake (the file must live inside `src/` so mypy resolves the project's modules):
```bash
printf 'from small_service.domain.cache import TimedCache\nc: TimedCache[str, int] = TimedCache(1, lambda: 0.0)\nprint(c.get("a") + 1)\n' > src/typo_demo.py
.venv/bin/mypy src/typo_demo.py
rm src/typo_demo.py
```
Expect `Unsupported operand types for + ("None" and "int")` with the note `Left operand is of type "int | None"`.

```bash
.venv/bin/mypy --strict --no-incremental src/small_service/domain/cache.py
```
Checks one file.

## Mistakes people make

- Sprinkling `# type: ignore` everywhere. Strict mode flags unused ignores, so they cannot rot.
- Using `Any` to make errors disappear.
- Believing hints change how Python runs. They do not; only mypy and other tools read them.
- Forgetting stub packages for untyped libraries.

## Check yourself

1. Does mypy run your program? *No; it only reads the code.*
2. What does `V | None` force you to do? *Check for `None` before using the value.*
3. What does `strict = true` do? *Turns on all optional strictness checks.*
4. Why relax the rules for `tests.*`? *Test functions stay short without annotations.*
5. What is a `Protocol` check? *mypy verifies that an object has the methods listed, without inheritance.*

## Further reading

- mypy documentation: https://mypy.readthedocs.io/en/stable/ (pinned 2.4.0)
- Strict mode flags: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
- Protocols: https://mypy.readthedocs.io/en/stable/protocols.html
