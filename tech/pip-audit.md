# pip-audit

## What it is

pip-audit checks the packages you depend on against databases of **known vulnerabilities** (published security problems). It compares each pinned name and version with the Python Packaging Advisory Database. If a pinned version has a published advisory, pip-audit reports it. Pinned: 2.10.1.

## Why this repository uses it

A hash-locked environment ([pip-and-hash-locking.md](pip-and-hash-locking.md)) is repeatable, but a repeatable environment can repeatedly contain a vulnerable package. The `audit` job and a weekly schedule keep an eye on the lock file.

## Where it appears

| Path | Use |
|---|---|
| `Makefile` target `audit` | `pip-audit --no-deps --disable-pip -r requirements-dev.lock` |
| `.github/workflows/ci.yml` job `audit` | Not required, so a new advisory does not block unrelated pull requests. |
| `.github/workflows/audit.yml` | The same check every Monday at 06:17 UTC. |

## How it works underneath

pip-audit reads a requirements file, asks the advisory service (PyPI's JSON API by default) about each `name==version`, and prints a table of findings. It needs network access. Exit status 0 means nothing found; 1 means vulnerabilities were found.

## Walkthrough of this repository's use

```make
audit: $(STAMP)
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock
```
- `-r requirements-dev.lock` audits exactly what the project installs.
- `--no-deps` says "do not resolve dependencies". The lock already lists all of them, so there is nothing to resolve. This is also required with hashed requirement files.
- `--disable-pip` stops pip-audit from creating a temporary virtual environment through pip; with a fully pinned file it simply reads the names and versions.

In `ci.yml` the job has no `needs:` and runs on every event. It is **not** in the list of required checks (`pipeline/core/protection.py`), so a vulnerability published tomorrow does not break every open pull request.

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
