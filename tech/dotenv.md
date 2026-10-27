# Environment variables and the `.env` file

## What it is

An **environment variable** is a named piece of text that a process receives from the program that started it. `POSTGRES_HOST=localhost` is one. Every program can read them (`os.environ` in Python). A **`.env` file** is a plain text file of `NAME=value` lines used to set many at once during development. It is a convention, not an operating-system feature: some tool has to read it.

## Why this repository uses it

The service follows the "twelve-factor" rule: configuration comes from the environment, not from values written in code. The same wheel runs on a laptop, in CI and in a container, and only the variables change. The database password has **no default** anywhere; it must be supplied.

## Where it appears

| Path | Role |
|---|---|
| `.env.example` | A committed template with throwaway local values. |
| `.env` | Your local copy, created by `make up`; ignored by git (`.gitignore`) and by Docker (`.dockerignore`). |
| `Makefile` | `-include .env` and `export ...` hand the values to every command. |
| `docker-compose.yml` | Substitutes `${POSTGRES_PORT:-55471}` etc. from `.env`. |
| `.github/workflows/ci.yml` | The `integration` job sets the same variables with `env:`. |
| `src/small_service/infrastructure/settings.py` | Reads and validates them. |

## How it works underneath

- When a program starts another, it passes a copy of its environment. A child cannot change its parent's variables.
- `export NAME` (in a shell) marks a variable to be passed on to children.
- Docker Compose reads `.env` from the project folder to fill `${...}` in its YAML. That is separate from the container's own environment, which is set by the `environment:` key.
- Everything in the environment is text. The program converts and checks it.

## Walkthrough of this repository's use

### `.env.example`

```
POSTGRES_HOST=localhost
POSTGRES_PORT=55471
POSTGRES_DB=service
POSTGRES_USER=service
POSTGRES_PASSWORD=local-only-password
LOG_LEVEL=INFO
CACHE_TTL_SECONDS=30
JOB_TIMEOUT_SECONDS=5
```
The header comment says these are throwaway values for a database that lives in a container for one run. The file has no real secrets, so it is safe to commit.

### The Makefile

```make
.env:
	cp .env.example .env
-include .env
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL CACHE_TTL_SECONDS JOB_TIMEOUT_SECONDS
```
If `.env` is missing, `make up` copies the example. The file is read as Make variable assignments, and `export` passes eight of them to every command.

### `Settings.from_env`

```python
host = _text(env, "POSTGRES_HOST", "localhost")
port = _positive_number(env, "POSTGRES_PORT", 5432)
...
postgres_password=_text(env, "POSTGRES_PASSWORD"),
```
Each helper reads the variable, strips spaces and raises `ConfigurationError` with the variable's name when it is empty or invalid. Host names are checked with a regular expression, the port must be a whole number up to 65535, and `LOG_LEVEL` must be one of DEBUG, INFO, WARNING, ERROR. The password helper is called without a default, so a missing password fails at startup, not at the first query. `main()` prints `configuration error: ...` and exits with status 2.

The settings object is passed **in** (`Settings.from_env(environ)` accepts a dict), so tests never touch the real environment.

### In CI

The workflow sets `POSTGRES_PASSWORD: test-only-password # a throwaway for a container that lives only for this run`. Real secrets would use GitHub's secret store, not the file.

## Try it yourself

```bash
make -B .env && cat .env
```
`-B` forces the copy rule to run (it overwrites `.env` with the example).

```bash
POSTGRES_PASSWORD= .venv/bin/small-service version
POSTGRES_PASSWORD= LOG_LEVEL=INFO .venv/bin/small-service health; echo "exit: $?"
```
The first prints the version (it never reads settings). The second prints `configuration error: POSTGRES_PASSWORD must be set and not empty` and `exit: 2`.

```bash
LOG_LEVEL=LOUD POSTGRES_PASSWORD=x .venv/bin/small-service health; echo "exit: $?"
```
Expect `configuration error: LOG_LEVEL must be one of ['DEBUG', 'ERROR', 'INFO', 'WARNING'], got 'LOUD'` and `exit: 2`.

```bash
env | grep ^POSTGRES
```
Shows what your shell currently exports.

## Mistakes people make

- Committing `.env` with real secrets. It is in `.gitignore` and `.dockerignore`.
- Giving the password a default "to make it work". Here a missing password stops the program.
- Reading the environment all over the code. Here one `Settings` object does it once.
- Putting spaces around `=` in a `.env` file.
- Logging the connection URL, which contains the password.

## Check yourself

1. What is an environment variable? *Named text that a process receives from the program that started it.*
2. Why is there no default password? *A missing secret should fail loudly at startup.*
3. Who reads `.env` in this repository? *Make (and Docker Compose for its substitutions), not Python.*
4. Why is `Settings.from_env` given a dict in tests? *To avoid touching the real environment.*
5. What exit status means a configuration error? *2.*

## Further reading

- The Twelve-Factor App, config: https://12factor.net/config
- Docker Compose environment files: https://docs.docker.com/compose/how-tos/environment-variables/
- `os.environ`: https://docs.python.org/3.12/library/os.html#os.environ
