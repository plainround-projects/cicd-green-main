# Git

## What it is

Imagine a project folder in which you keep changing files. **Git** is a program that remembers every version of that folder, so you can see what changed, when, by whom and why, and go back if something broke. This memory is called a **repository** (or "repo"). It lives in a hidden folder named `.git` inside the project folder.

The words you need:

- A **commit** is one saved version: a snapshot of all the files, plus a message ("fix the cache"), an author, a time, and a pointer to the commit that came before it. A repository is a chain of commits.
- A **SHA** (also called a *hash* or *commit id*) is the commit's name: a 40-character code such as `3fa91bc2...`, computed from the commit's contents. Change anything in a commit and its SHA changes, so the SHA is a fingerprint. People usually write only the first 7 characters.
- A **branch** is a movable name for a commit, such as `main`. When you commit on a branch, the name moves forward to the new commit.
- `HEAD` is Git's name for "the commit I am looking at right now".
- A **remote** is another copy of the repository, usually on a server; `origin` is the usual name for the one you cloned from. `git clone` copies a repository; `git push` sends your commits to a remote; `git fetch`/`git pull` bring commits from it.
- A **bare repository** has the history but no working files. It is what a server keeps, because nobody edits files on a server.
- A **working tree** is the actual folder of files you edit. **Staging** (`git add`) chooses which changes go into the next commit.
- A **diff** is the list of differences between two versions.
- A **hook** is a program that Git runs automatically at a given moment, such as before it accepts a push.

## Why this repository uses it

The pipeline's inputs come from Git. "Which files changed in this pull request" decides whether to skip jobs for a docs-only change. "Which commit is this" becomes part of the build's version (`0.1.0+3fa91bc`). "When was that commit made" fixes the clock the wheel build uses, so the same commit always produces the same bytes. And the lesson's second step, "a failing test cannot merge, and a direct push to `main` is refused", is demonstrated locally with a bare repository and a hook.

## Where it appears

| Path | Use |
|---|---|
| `pipeline/adapters/git.py` | Four helpers: `head_sha`, `commit_epoch`, `is_dirty`, `changed_paths`. |
| `pipeline/changes.sh` | `git diff --name-only`, `git cat-file -e`. |
| `pipeline/hooks/pre-receive` | `git merge-base --is-ancestor`, `git rev-parse --verify`. |
| `pipeline/adapters/gate.py` | `git worktree add/remove` and `git push --push-option`. |
| `scripts/gate-demo.sh` | A bare repository, a clone and six pushes. |
| `tests/e2e/test_gate_demo.py` | Runs the demo as a test. |
| `.gitignore` | Names the files Git must never track. |

## How it works underneath

- Git stores its data in `.git/` as **objects**: the contents of files, folders, and commits, each stored under the hash of its content. That is why a SHA changes when anything inside changes.
- A branch is a tiny file that holds one SHA. `HEAD` says which branch you are on.
- `git diff A B` compares two commits. `git diff A...B` (three dots) compares B with the point where it split from A, which is the right question for "what did this branch change".
- A **ref** is any name that points at a commit. Branches live under `refs/heads/`. A repository may also hold refs with invented names. This project uses `refs/status/green/<sha>` to mean "CI says this commit is green". Git does not care what the names mean.
- A **push option** (`git push --push-option text`) is extra text a client sends along with a push. The server may read it. A server only accepts push options if it is configured with `receive.advertisePushOptions true`.
- A **hook** is an executable file in the repository's `hooks/` folder. Hooks are not copied by `git clone`, so they must be installed on the server by hand. A non-zero exit from `pre-receive` rejects the push.

## Walkthrough of this repository's use

### `pipeline/adapters/git.py`

```python
"""The few git facts the pipeline needs."""

from __future__ import annotations

from pathlib import Path

from pipeline.adapters.process import run_output


def head_sha(repo: Path) -> str:
    """Full SHA of HEAD."""
    return run_output(["git", "rev-parse", "HEAD"], repo).strip()


def commit_epoch(repo: Path, sha: str) -> int:
    """Commit time of `sha` in seconds since the epoch: the fixed clock for a reproducible build."""
    return int(run_output(["git", "show", "-s", "--format=%ct", sha], repo).strip())


def is_dirty(repo: Path) -> bool:
    """True when tracked files changed or untracked files exist that git does not ignore."""
    return bool(run_output(["git", "status", "--porcelain"], repo).strip())


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    """Files changed between two commits (three-dot: since `head` branched from `base`)."""
    return run_output(["git", "diff", "--name-only", f"{base}...{head}"], repo).split()
```

- **Line 3** (`from __future__ import annotations`), **line 5** (`Path`) and **line 7** (`run_output`, which runs a command and returns what it printed) are explained in [python.md](python.md).
- **Lines 10 to 12**, `head_sha`: `git rev-parse HEAD` prints the full SHA of the current commit. `rev-parse` turns a name into a SHA. `.strip()` removes the newline at the end.
- **Lines 15 to 17**, `commit_epoch`: `git show -s --format=%ct SHA`. `show` normally prints a commit's message and changes; `-s` suppresses the changes; `--format=%ct` prints only the commit time as a count of seconds since 1 January 1970 (the "epoch"; `%ct` is the committer time). `int(...)` converts that text to a number. This is the fixed clock for the reproducible build ([python-packaging.md](python-packaging.md)).
- **Lines 20 to 22**, `is_dirty`: `git status --porcelain` lists changed and untracked files in a stable, machine-readable format, one per line. If the output is empty the tree is clean. `bool(text)` is true if the text is not empty. A dirty tree gets `.dirty` in its version so nobody ships uncommitted work by mistake.
- **Lines 25 to 27**, `changed_paths`: `git diff --name-only BASE...HEAD` with three dots (see above) and `.split()` to turn the lines into a list of names.

### The branch guard: `pipeline/hooks/pre-receive`

The full line-by-line walkthrough is in [bash-and-sh.md](bash-and-sh.md). The three rules it enforces: `main` is never deleted; `main` only moves forward (`git merge-base --is-ancestor OLD NEW`, which exits 0 when OLD is part of NEW's history); and `main` only moves to a commit that has a ref `refs/status/green/<sha>` (`git rev-parse --verify -q NAME` exits 0 when the name exists). Posting such a ref requires the secret token as a push option.

### `pipeline/adapters/gate.py`: running the checks on one commit

```python
"""A local stand-in for "required status checks": CI posts a green status for a commit, and the remote refuses `main`
without it. See pipeline/hooks/pre-receive and scripts/gate-demo.sh."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pipeline.adapters.process import run_output


def run_checks_on_commit(repo: Path, sha: str, command: Sequence[str]) -> bool:
    """Check out `sha` in a throwaway worktree and run `command` there. True when it exits 0."""
    with tempfile.TemporaryDirectory(prefix="gate-") as workdir:
        tree = Path(workdir) / "tree"
        run_output(["git", "worktree", "add", "--detach", str(tree), sha], repo)
        try:
            return subprocess.run(list(command), cwd=tree, check=False).returncode == 0  # noqa: S603
        finally:
            run_output(["git", "worktree", "remove", "--force", str(tree)], repo)


def post_green_status(repo: Path, remote: str, sha: str, token: str) -> None:
    """Push `refs/status/green/<sha>` to `remote`. The remote accepts it only with the CI token as a push option."""
    run_output(["git", "push", "--push-option", f"ci-token={token}", remote, f"{sha}:refs/status/green/{sha}"], repo)
```

- **Line 18**: `git worktree add --detach TREE SHA` makes a **worktree**: a second working folder, connected to the same repository, with the files of one commit checked out. `--detach` means "check out the commit itself without making a branch". The checks run there, so the developer's own working files are never touched.
- **Lines 19 to 22**: `try: return subprocess.run(...)` runs the checks inside the worktree and returns whether they exited with 0. `finally:` runs whether or not an error happened: `git worktree remove --force TREE` deletes the temporary worktree. (The temporary folder from `tempfile` disappears at the end of the `with` block.)
- **Lines 25 to 27**: `git push --push-option ci-token=TOKEN REMOTE SHA:refs/status/green/SHA`. `A:B` in a push means "send my A to the name B on the remote". Here the commit is pushed to a ref that names itself, so `refs/status/green/<sha>` exists on the server, pointing at that commit.

### `scripts/gate-demo.sh`

The script creates `git init -q --bare` (the fake server), runs `git config receive.advertisePushOptions true`, installs the hook (`cp` and `chmod +x`), clones with `git clone`, creates `main` with `git checkout -q -b main`, stages and commits (`git add .`, `git commit -q -m`), and pushes six times (`git push origin main`, `git push origin "$fixed:main"`, `git push --force ...`, `git push origin :main`). Every line is explained in [bash-and-sh.md](bash-and-sh.md). The six behaviours it proves: a direct push is refused; a push that breaks a test has no green status and is refused; the fixed change gets a green status and is accepted; a branch cut from old history is refused; a forged status is refused; a force push and a delete are refused.

### `pipeline/changes.sh`

`git cat-file -e "$base^{commit}"` (does this commit exist in my copy?) and `git diff --name-only` (which files differ?). See [bash-and-sh.md](bash-and-sh.md).

### `.gitignore`

```
.venv/
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.import_linter_cache/
.coverage
coverage.xml
.env
.DS_Store
logs/
reports/
.cache/
runs.csv
.omc/
```

One pattern per line; a file matching a pattern is invisible to `git add`.

- `.venv/` is the Python environment, `__pycache__/` and `*.pyc` are compiled Python files, `*.egg-info/` is packaging output, `build/` and `dist/` are build output, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.import_linter_cache/` are tool caches, `.coverage` and `coverage.xml` are coverage output.
- `.env` holds local settings (it may contain a password), `.DS_Store` is a macOS folder-view file, `logs/`, `reports/` and `.cache/` are generated output, `runs.csv` is the local run log ([csv.md](csv.md)) and `.omc/` is a tool's working folder.
- A trailing `/` means "a folder"; `*` is a wildcard for any characters.

## Try it yourself

```bash
git log --oneline | head -5
git rev-parse HEAD
git show -s --format=%ct HEAD
```
The last number is the commit time in seconds since 1970.

```bash
.venv/bin/python -m pipeline version
```
Prints `0.1.0+<first 7 characters of HEAD>`, plus `.dirty` if you have uncommitted changes.

```bash
git diff --name-only HEAD~1 HEAD
```
The same list `changes.sh` reads.

```bash
make gate-demo
```
Watch each refusal message start with `remote:`. Those lines are printed by the hook running on the "server".

## Mistakes people make

- Force-pushing over shared history. The hook refuses it (`GH006 protected branch`).
- Committing `.env` or `.venv`. `.gitignore` lists both.
- Comparing branches with two dots when you mean three, and getting changes that are not yours.
- Trusting a status that anyone can post. Here only a holder of the token can.
- Forgetting that hooks are not copied by `git clone`. The demo copies the hook by hand into the bare repo.

## Check yourself

1. What is a SHA? *A fingerprint of a commit's content; it identifies the commit.*
2. What does a non-zero exit from `pre-receive` do? *The whole push is rejected.*
3. What is a bare repository? *One with history but no working files, used on servers.*
4. Why does the build use the commit time as its clock? *So the same commit always gives the same wheel bytes.*
5. What is a worktree used for in `gate.py`? *Checking out the commit under test in a temporary folder without touching your files.*

## Further reading

- Git documentation: https://git-scm.com/docs (this machine runs Git 2.50.1)
- `git-diff` ranges: https://git-scm.com/docs/git-diff
- `git-worktree`: https://git-scm.com/docs/git-worktree
- `githooks`: https://git-scm.com/docs/githooks
