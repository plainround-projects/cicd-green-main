# mypy

## What it is

mypy is a **static type checker** for Python. "Static" means it reads your code without running it. It uses the type hints you wrote (`def f(x: int) -> str`) to find mistakes such as passing text where a number is expected, or forgetting that a value can be `None`. Pinned: 2.4.0.

## Why this repository uses it

The lesson is about gates that stop broken code before it merges. A type error is a bug caught in seconds, before any test or user finds it. The repository runs mypy in **strict mode**, which turns on every optional check.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.mypy]` | `strict = true`, the files to check. |
| `Makefile` target `lint` | `$(VENV)/bin/mypy` with no arguments (it reads `files` from the config). |
| `src/`, `pipeline/`, `tests/` | All typed. |

## How it works underneath

mypy parses each file, builds a model of every function's input and output types, and checks every call and assignment against it. It knows `Optional` types: `str | None` means "a str, or None". Using such a value as a plain `str` is an error until you check for `None`. mypy also follows `Protocol`s: an object matches if it has the right methods. Libraries without hints need a "stub" package (here `types-PyYAML`).

## Walkthrough of this repository's use

```toml
[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "pipeline", "tests"]
```
`strict = true` bundles many flags, for example: every function must have annotations (`disallow_untyped_defs`), no implicit `Any`, warn when a function returns `Any`, warn about unused `# type: ignore`.

```toml
[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
```
`[[...]]` is a TOML list of tables ([toml.md](toml.md)). For the test modules only, annotations are optional, so tests stay short (`def test_x(store):`).

### What strictness catches here

```python
def get(self, key: K) -> V | None:
```
Anyone who writes `cache.get("a").expires_at` gets an error: the result may be `None`. The code must check first, as `JobRunner.run` does with `if cached is not None:`.

```python
class JobStore(Protocol): ...
```
The `JobRunner` takes a `JobStore`. If `PostgresJobStore` forgot `ping`, mypy would reject `JobRunner(store=PostgresJobStore(...))` in `cli.py`.

```python
cache: TimedCache[str, JobRecord] = TimedCache(settings.cache_ttl_seconds, time.monotonic)
```
Here the annotation tells mypy which type parameters to use. Without it mypy could not infer them from an empty cache.

## Try it yourself

```bash
.venv/bin/mypy --version
.venv/bin/mypy
```
Expect `mypy 2.4.0` and `Success: no issues found in N source files`.

Make a deliberate mistake:
```bash
printf 'from small_service.domain.cache import TimedCache\nc: TimedCache[str, int] = TimedCache(1, lambda: 0.0)\nprint(c.get("a") + 1)\n' > /tmp/typo.py
.venv/bin/mypy /tmp/typo.py
rm /tmp/typo.py
```
Expect an error that `None` does not support `+` (an operator on `int | None`).

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
