# Git

## What it is

Git is a version-control tool. It stores the history of a project as a chain of **commits**. A commit is a snapshot of all the files plus a message, an author, a time and a pointer to its parent commit. Each commit gets an id called a **SHA** (a 40-character hexadecimal fingerprint of its contents). A **branch** is a name that points at one commit (for example `main`). A **remote** is another copy of the repository, usually on a server (`origin`). A **bare** repository has the history but no working files; servers use these.

## Why this repository uses it

The pipeline's inputs come from git: "which files changed" (to skip documentation-only runs), "which commit is this" (to version the build as `0.1.0+3fa91bc`), "when was that commit made" (a fixed clock for a reproducible build). The lesson's second step, "a failing test cannot merge", is shown locally by a git **hook** that guards a fake remote.

## Where it appears

| Path | Use |
|---|---|
| `pipeline/adapters/git.py` | `head_sha`, `commit_epoch`, `is_dirty`, `changed_paths`. |
| `pipeline/changes.sh` | `git diff --name-only`, `git cat-file -e`. |
| `pipeline/hooks/pre-receive` | `git merge-base --is-ancestor`, `git rev-parse --verify`. |
| `pipeline/adapters/gate.py` | `git worktree add` to check out a commit in a throwaway folder; `git push --push-option` to post a green status. |
| `scripts/gate-demo.sh` | A bare remote, a clone, six pushes. |
| `tests/e2e/test_gate_demo.py` | Runs the demo as a test. |
| `.gitignore` | Files git must never track (`.venv/`, `.env`, `dist/`, `runs.csv`, ...). |

## How it works underneath

- Git stores content in a database under `.git/`: **blobs** (file contents), **trees** (folders), **commits**. Everything is named by the hash of its content, so a SHA changes if anything in it changes.
- A branch is just a small file holding one SHA. `HEAD` says which branch (or commit) you are on.
- `git diff A B` compares two commits. `A...B` (three dots) compares B with the point where it split from A.
- A **hook** is an executable file in `.git/hooks/` (or `hooks/` in a bare repo) that git runs at a set moment. `pre-receive` runs on the server before it accepts a push. A non-zero exit rejects the push.
- A **ref** is any name that points at a commit. Branches live under `refs/heads/`. This repository invents `refs/status/green/<sha>`: a ref that means "CI says this commit is green". Git does not mind; refs are just names.
- A **push option** (`git push --push-option text`) is extra text the client sends with the push. The server may read it.

## Walkthrough of this repository's use

### `pipeline/adapters/git.py`

```python
def head_sha(repo: Path) -> str:
    return run_output(["git", "rev-parse", "HEAD"], repo).strip()
```
`git rev-parse HEAD` prints the full SHA of the current commit. `.strip()` removes the trailing newline.

```python
def commit_epoch(repo: Path, sha: str) -> int:
    return int(run_output(["git", "show", "-s", "--format=%ct", sha], repo).strip())
```
`-s` hides the diff. `--format=%ct` prints only the commit time as seconds since 1970-01-01 (the "epoch"). That number becomes `SOURCE_DATE_EPOCH`, the clock the wheel build uses ([python-packaging.md](python-packaging.md)). Same commit, same clock, same bytes.

```python
def is_dirty(repo: Path) -> bool:
    return bool(run_output(["git", "status", "--porcelain"], repo).strip())
```
`--porcelain` is the stable, machine-readable format. Any output at all means changed or untracked files. A dirty tree gets `.dirty` added to its version so nobody ships uncommitted work by mistake.

```python
f"{base}...{head}"   # in changed_paths
```
Three dots: "what changed on `head` since it branched off `base`".

### The branch guard (`pre-receive`)

See the line-by-line shell walkthrough in [bash-and-sh.md](bash-and-sh.md). The three rules: `main` is never deleted, `main` only moves forward (`git merge-base --is-ancestor old new`), and `main` only moves to a commit that has `refs/status/green/<sha>` (`git rev-parse --verify -q`). Posting such a ref requires the CI token as a push option.

### `pipeline/adapters/gate.py`

```python
run_output(["git", "worktree", "add", "--detach", str(tree), sha], repo)
```
A **worktree** is a second working folder for the same repository. `--detach` checks out the commit without making a branch. The gate runs the checks in that temporary folder, so your own working files are never touched. The `finally:` block removes the worktree with `git worktree remove --force`.

```python
run_output(["git", "push", "--push-option", f"ci-token={token}", remote, f"{sha}:refs/status/green/{sha}"], repo)
```
`A:B` in a push means "send my A to the remote's ref B". Here it creates `refs/status/green/<sha>` on the remote pointing at that same commit.

### `scripts/gate-demo.sh`

`git init -q --bare "$work/origin.git"` makes the fake server. `git config receive.advertisePushOptions true` tells it to accept push options (off by default). The hook is copied to `hooks/pre-receive` and made executable. The demo then pushes a direct change (refused: no green ref), a broken change (the gate fails, no ref, refused), a fix (gate passes, ref posted, accepted), a stale branch (green but not a descendant of main, refused), a forged status (no token, refused), and a force-push and a delete (refused).

### `.gitignore`

One pattern per line. `.venv/` ignores a folder. `*.pyc` ignores by extension. `.env` keeps local settings out of history. `runs.csv` is the local run log, not a source file.

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
