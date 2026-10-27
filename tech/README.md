# tech: the technologies in this repository, from zero

One file per technology. Each file says what the technology is, why this repository uses it, where it appears, how it works underneath, walks through this repository's own lines, gives commands to try, lists common mistakes, asks five questions and links the official documentation. Read them with the repository open next to you.

## If you have ten minutes

1. [python.md](python.md): the language, and the few features this code leans on.
2. [make.md](make.md): every pipeline job is one `make` target, so this is the map.
3. [github-actions.md](github-actions.md): the pipeline itself, job by job.

## Reading order

**The language and the build tools**

| File | Role |
|---|---|
| [python.md](python.md) | Python 3.12: the service and the pipeline are written in it. |
| [bash-and-sh.md](bash-and-sh.md) | The three shell scripts: the change detector, the git hook and the demo. |
| [make.md](make.md) | The `Makefile`: one target per job. |
| [pip-and-hash-locking.md](pip-and-hash-locking.md) | Virtual environments, `pip`, hash-checked lock files. |
| [uv.md](uv.md) | The tool that writes the lock files. |
| [python-packaging.md](python-packaging.md) | `setuptools`, `build`, wheels, checksums and reproducible builds. |

**The pipeline**

| File | Role |
|---|---|
| [git.md](git.md) | Commits, diffs, worktrees and the `pre-receive` hook that guards `main`. |
| [github-actions.md](github-actions.md) | `ci.yml`, `audit.yml` and the composite action. |
| [act.md](act.md) | Running a workflow job on your own machine. |
| [dependabot.md](dependabot.md) | Weekly update pull requests. |
| [gh-cli.md](gh-cli.md) | The GitHub CLI: branch protection and run history. |

**The runtime pieces**

| File | Role |
|---|---|
| [docker.md](docker.md) | The `Dockerfile`: the verified wheel as an image. |
| [docker-compose.md](docker-compose.md) | `docker-compose.yml`: the database and the packaged app. |
| [postgresql.md](postgresql.md) | The database server. |
| [sql.md](sql.md) | The files under `sql/` and the statements in the adapter. |
| [psycopg.md](psycopg.md) | The Python driver for PostgreSQL. |
| [dotenv.md](dotenv.md) | Environment variables and `.env`. |

**The checks and the tests**

| File | Role |
|---|---|
| [pytest.md](pytest.md) | The test runner and coverage. |
| [ruff.md](ruff.md) | Lint and format. |
| [mypy.md](mypy.md) | Static type checks. |
| [import-linter.md](import-linter.md) | Architecture rules over imports. |
| [pip-audit.md](pip-audit.md) | Known-vulnerability check of the lock. |
| [junit-xml.md](junit-xml.md) | The test report format the flaky hunt reads. |

**File formats**

| File | Role |
|---|---|
| [yaml.md](yaml.md) | Workflows, compose file, Dependabot config. |
| [toml.md](toml.md) | `pyproject.toml`. |
| [json.md](json.md) | GitHub API bodies and run history. |
| [csv.md](csv.md) | The run log `runs.csv`. |
| [markdown.md](markdown.md) | The documentation, and the README contract check. |
| [editorconfig.md](editorconfig.md) | Shared editor settings. |

## What was not verified

The notes were written against the pinned versions in `requirements-dev.lock` and the files in this repository. Commands that need Docker or network access (`make up`, `make audit`, `make deploy-local`), `act` jobs other than `changes`, and everything that talks to GitHub (`gh`, Dependabot, branch protection) are explained from the code and the official documentation, and were not all run again when these notes were written. Each file says so where it matters.
