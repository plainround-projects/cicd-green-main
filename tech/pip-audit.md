# pip-audit

## What it is

Software libraries have bugs, and some bugs are security holes. When a hole is found in a published version of a library, it is reported with an identifier (an **advisory**, for example `PYSEC-2024-1234` or a CVE number) and a note of which versions are affected and which version fixes it. These reports are collected in databases.

**pip-audit** compares the packages you depend on with such a database. Give it a list of exact versions (a lock file) and it says which of them have a known advisory. This repository pins pip-audit 2.10.1. It asks the Python Packaging Advisory Database (through PyPI), so it needs network access.

## Why this repository uses it

A hash-locked environment ([pip-and-hash-locking.md](pip-and-hash-locking.md)) is repeatable, but a repeatable environment can repeatedly contain a vulnerable package. Pins make updates a conscious act, so the project needs something that tells it when an update is overdue. That is this check.

## Where it appears

| Path | Use |
|---|---|
| `Makefile` target `audit` (lines 111 and 112) | `pip-audit --no-deps --disable-pip -r requirements-dev.lock` |
| `.github/workflows/ci.yml` job `audit` (lines 140 to 148) | Runs `make audit` on every push and pull request. |
| `.github/workflows/audit.yml` | Runs `make audit` every Monday at 06:17 UTC. |

## How it works underneath

pip-audit reads a requirements file, takes each `name==version`, asks the advisory service whether that exact version is affected, and prints a table of findings: package, installed version, advisory id and the version that fixes it. Exit status 0 means nothing found; 1 means at least one finding. By default it also builds a temporary environment to resolve dependencies; the flags below turn that off because the lock already contains every dependency.

## Walkthrough of this repository's use

```make
audit: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock
```

- **Line 111**: the target `audit` needs the environment (`$(STAMP)`) so the tool is installed. The `##` text is its description for `make help`.
- **Line 112**: `$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock`:
  - `-r requirements-dev.lock` audits the packages in that file, which is exactly what the project installs, development tools included.
  - `--no-deps` means "do not work out dependencies yourself". The lock already lists every package, so nothing needs resolving.
  - `--disable-pip` means "do not call pip to build a temporary environment"; with a fully pinned file the tool can simply read the names and versions.

### In the workflow

The job `audit` in `ci.yml` has no `needs` and no `if`, so it runs on every event, in parallel with the others. It is **not** in the list of required checks ([github-actions.md](github-actions.md)): a newly published advisory should not block unrelated pull requests. `audit.yml` runs the same check on a weekly timer so that a new advisory is found even when nobody pushes.

### What to do with a finding

Update the package: change the range in `pyproject.toml` if needed, regenerate the lock ([uv.md](uv.md)), run the tests. If an advisory does not apply to how the package is used, record the reason and a date to look again.

## Try it yourself

```bash
make audit
```
Expect `No known vulnerabilities found` (requires network access). If an advisory exists for a pinned version, a table lists the package, the version, the advisory id and the fixed version.

```bash
.venv/bin/pip-audit --version
```
Expect `pip-audit 2.10.1`.

## Mistakes people make

- Making the audit a required check, so an advisory published today blocks all work.
- Auditing only occasionally. A schedule finds new advisories without a push.
- Ignoring a finding without a reason or a date to revisit.
- Auditing a loose `requirements.txt` instead of the lock.

## Check yourself

1. What does pip-audit compare? *Pinned package versions against known advisories.*
2. Why is `audit` not a required check? *A new advisory should not block unrelated pull requests.*
3. Why does a schedule exist as well? *To find new advisories without waiting for a push.*
4. What does `--no-deps` mean here? *Do not resolve dependencies; the lock already lists them.*
5. Does it need network access? *Yes, to fetch advisories.*

## Further reading

- pip-audit: https://pypi.org/project/pip-audit/ and https://github.com/pypa/pip-audit (pinned 2.10.1)
- Python Packaging Advisory Database: https://github.com/pypa/advisory-database
