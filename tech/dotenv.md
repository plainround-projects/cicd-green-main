# Environment variables and the `.env` file

## What it is

When you start a program in a terminal, the shell hands it a small set of named pieces of text called **environment variables**. A variable has a name (by convention in capitals, such as `POSTGRES_PORT`) and a value (text, such as `55471`). Every program can read its own environment: in Python, `os.environ["POSTGRES_PORT"]`. A program that is started by another program receives a *copy* of its parent's variables, and it can change only its own copy.

You set a variable for one command like this: `LOG_LEVEL=DEBUG some-command`. Or for everything the shell starts afterwards: `export LOG_LEVEL=DEBUG`.

A **`.env` file** is a plain text file with one `NAME=value` per line. It is only a *convention*: the operating system does not know about it. Some program has to read the file and set the variables. Here the reader is `make` ([make.md](make.md)) and, for its own substitutions, Docker Compose ([docker-compose.md](docker-compose.md)).

## Why this repository uses it

The service follows a rule from "twelve-factor" apps: **configuration comes from the environment, not from values written into the code.** The same package then runs on a laptop, in CI and in a container; only the variables change. The database **password has no default anywhere**: if it is missing, the program refuses to start rather than falling back to something guessable.

## Where it appears

| Path | Role |
|---|---|
| `.env.example` | A committed template with throw-away local values. `make up` copies it to `.env`. |
| `.env` | Your local copy. Ignored by Git (`.gitignore`) and by Docker (`.dockerignore`). |
| `Makefile` lines 8 and 9 | `-include .env` and `export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL CACHE_TTL_SECONDS JOB_TIMEOUT_SECONDS`. |
| `docker-compose.yml` | Fills `${POSTGRES_PORT:-55471}` and the other placeholders. |
| `.github/workflows/ci.yml` | The `integration` job sets the same variables with `env:`. |
| `src/small_service/infrastructure/settings.py` | Reads and validates them. |

## How it works underneath

Every process has an environment; the operating system copies it to each child. All values are text, so a program must convert `"55471"` into the number 55471 itself and decide what to do if the text is not a number. A `.env` file never reaches a program unless a reader loads it and exports its contents. `make` can read a `.env` file directly because a line `POSTGRES_PORT=55471` is also a valid `make` assignment; `export` then passes the named variables to every command that `make` starts.

## Walkthrough of this repository's use

### `.env.example`

The file has eight lines of settings and a header comment:

- `POSTGRES_HOST=localhost`: where the database is, from the point of view of programs on your computer. (Inside Compose, the app reaches it at `db` instead; Compose overrides that.)
- `POSTGRES_PORT=55471`: the port published on your computer. Not the usual 5432, to avoid a clash with a PostgreSQL you may already have.
- `POSTGRES_DB=service`, `POSTGRES_USER=service`: the database's name and the user.
- `POSTGRES_PASSWORD=local-only-password`: a throw-away value for a database that lives in a container for one run. It contains no real secret, which is why the example may be committed.
- `LOG_LEVEL=INFO`: how much to log (one of DEBUG, INFO, WARNING, ERROR).
- `CACHE_TTL_SECONDS=30`: how long a cached job result is kept.
- `JOB_TIMEOUT_SECONDS=5`: how long to wait for a job.

The header comment says the file is copied to `.env` by `make up`. The target is `.env:` with the recipe `cp .env.example .env` ([make.md](make.md)); `make -B .env` forces a fresh copy.

### How `make` hands the values to Python

`-include .env` makes `make` read the file; `export POSTGRES_HOST ...` (eight names) marks them for passing on. Every command in a recipe, including `python -m pipeline run` and `pytest`, now sees them as ordinary environment variables.

### `Settings.from_env` in `settings.py`

```python
    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read and validate. The password has no default: it must come from the environment."""
        env = os.environ if environ is None else environ
        host = _text(env, "POSTGRES_HOST", "localhost")
        if not _HOST.match(host):
            raise ConfigurationError(f"POSTGRES_HOST must be a host name or address, got {host!r}")
        port = _positive_number(env, "POSTGRES_PORT", 5432)
        if port != int(port) or port > 65535:
            raise ConfigurationError(f"POSTGRES_PORT must be a port number, got {port}")
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        return cls(
            postgres_host=host,
            postgres_port=int(port),
            postgres_db=_text(env, "POSTGRES_DB", "service"),
            postgres_user=_text(env, "POSTGRES_USER", "service"),
            postgres_password=_text(env, "POSTGRES_PASSWORD"),
            log_level=level,
            cache_ttl_seconds=_positive_number(env, "CACHE_TTL_SECONDS", 30),
            job_timeout_seconds=_positive_number(env, "JOB_TIMEOUT_SECONDS", 5),
        )

    @property
    def dsn(self) -> str:
        """A libpq connection URI. Never log this: it holds the password."""
        return (
            f"postgresql://{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote(self.postgres_db, safe='')}"
        )
```

- `env = os.environ if environ is None else environ`: use the real environment unless a dictionary is passed in (tests pass one).
- `host = _text(env, "POSTGRES_HOST", "localhost")` reads the variable, strips spaces, and raises `ConfigurationError("POSTGRES_HOST must be set and not empty")` if it is empty; the third argument is the default.
- `_HOST.match(host)` checks the host with a regular expression; `port = _positive_number(env, "POSTGRES_PORT", 5432)` converts to a number and `port != int(port) or port > 65535` rejects `5432.5` and numbers no port can have.
- `level = _text(env, "LOG_LEVEL", "INFO").upper()` accepts `info` or `INFO`; it must be one of `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- `postgres_password=_text(env, "POSTGRES_PASSWORD")` has no default argument, so a missing password stops the program.
- `cache_ttl_seconds` defaults to 30 and `job_timeout_seconds` to 5.
- `dsn` builds `postgresql://user:password@host:port/db`, passing user, password and database through `quote(x, safe='')` so that characters like `@` or `/` inside a password cannot break the URL. Never log it: it holds the password.

How the command handles a failure: `small_service/interfaces/cli.py` calls `Settings.from_env()`; on `ConfigurationError` it prints `configuration error: ...` to standard error and returns exit code 2.

### In CI

```yaml
    env:
      POSTGRES_HOST: localhost
      POSTGRES_PORT: "5432"
      POSTGRES_DB: service
      POSTGRES_USER: service
      POSTGRES_PASSWORD: test-only-password # a throwaway for a container that lives only for this run
      PGPASSWORD: test-only-password
```

The same names are set with `env:` at job level, with the throw-away password `test-only-password` and `PGPASSWORD`, which `psql` reads so it does not prompt for a password ([github-actions.md](github-actions.md)).

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
