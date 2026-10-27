# Shell scripts (`sh` and Bash)

## What it is

A **shell** is a program that reads commands, starts other programs and connects them. When you type `ls` in a terminal, a shell is reading it. A **shell script** is a text file of such commands. `sh` is the small, portable shell language every Unix machine has. **Bash** is a bigger shell with extra features. This repository's three scripts start with `#!/bin/sh`, so they use only the portable part. They also run on the bare Linux containers in CI.

The first line `#!/bin/sh` is the **shebang**. It tells the operating system which program should run the file. `chmod +x file` marks the file as runnable.

## Why this repository uses it

A pipeline has to glue programs together: ask git which files changed, run a hook when someone pushes, stage a fake remote and push to it. Shell is the shortest way to say that. The lesson also needs a script that runs **on the server side of git**, where only the shell is guaranteed.

## Where it appears

| File | Role |
|---|---|
| `pipeline/changes.sh` | Prints `code=true` or `code=false`: does this change touch more than documentation? CI uses the answer to skip jobs. |
| `pipeline/hooks/pre-receive` | A git **hook**: the stand-in for GitHub branch protection. Refuses pushes to `main` that have no green status. |
| `scripts/gate-demo.sh` | Builds a fake remote and tries pushes to it: five kinds must be refused and one must be accepted. |
| `Makefile` recipes | Every recipe line is a shell command (see [make.md](make.md)). |
| `.github/workflows/ci.yml` `run:` lines | Each is a shell snippet run on the CI machine. |

## How it works underneath

- Every command starts a **process**. When it ends it returns an **exit status**: a number 0 to 255. `0` means success. Anything else means failure.
- `$?` holds the last exit status. `if cmd; then` runs the `then` part when `cmd` exits 0.
- Standard **streams**: 0 is input (stdin), 1 is output (stdout), 2 is errors (stderr). `>file` sends stdout to a file. `2>&1` sends errors to the same place as output. `>&2` sends output to the error stream. `2>/dev/null` throws errors away.
- A **pipe** `a | b` connects a's stdout to b's stdin. Both run at once.
- A **variable** is text. `name=value` sets it (no spaces around `=`). `$name` reads it. Always write `"$name"` with quotes, or the shell splits the text at spaces.
- The shell **expands** things before running a command: variables, `$(command)` (replaced by the command's output), and `*` patterns.

## Walkthrough of this repository's use

### `pipeline/changes.sh`

```sh
base=$1
head=${2:-HEAD}
zero=0000000000000000000000000000000000000000
```
`$1` and `$2` are the first and second arguments. `${2:-HEAD}` means "the second argument, or `HEAD` if it is missing or empty". `zero` is git's way of writing "no commit" (forty zeros).

```sh
if [ -z "$base" ] || [ "$base" = "$zero" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  echo "code=true"
  exit 0
fi
```
`[ ... ]` is the `test` command. `-z "$base"` is true when the text is empty. `||` means "or, if the left side failed". `!` flips success and failure. `git cat-file -e "$base^{commit}"` succeeds only if that commit exists in this clone. If we cannot compare (new branch, missing commit), the safe answer is `code=true`: run everything. `exit 0` ends the script successfully.

```sh
changed=$(git diff --name-only "$base" "$head" 2>/dev/null) || { echo "code=true"; exit 0; }
[ -n "$changed" ] || { echo "code=true"; exit 0; }
```
`$(...)` captures the list of changed file names. `|| { ...; }` runs the braces only if `git diff` failed. `-n` is true when the text is not empty.

```sh
if printf '%s\n' "$changed" | grep -qvE '^(docs/|.*\.md$)'; then
  echo "code=true"
else
  echo "code=false"
fi
```
`printf '%s\n'` prints the list safely (unlike `echo`, it never treats text as options). `grep -v` keeps lines that do **not** match, `-E` allows the pattern `docs/` or "ends in `.md`", `-q` prints nothing and only sets the exit status. So: if any changed file is not documentation, the answer is `true`.

In `ci.yml` the line `pipeline/changes.sh "$BASE" "${{ github.sha }}" | tee -a "$GITHUB_OUTPUT"` appends `code=...` to a file that GitHub reads to build job outputs. See [github-actions.md](github-actions.md).

### `pipeline/hooks/pre-receive`

Git runs this program on the **server** when someone pushes. It reads one line per updated branch from stdin: `old-sha new-sha ref-name`. If it exits non-zero, git rejects the whole push.

```sh
ci_token_given() {
  expected=$(cat "$GIT_DIR/ci-token" 2>/dev/null)
  [ -n "$expected" ] || return 1
  i=0
  while [ "$i" -lt "${GIT_PUSH_OPTION_COUNT:-0}" ]; do
    eval "option=\$GIT_PUSH_OPTION_$i"
    [ "$option" = "ci-token=$expected" ] && return 0
    i=$((i + 1))
  done
  return 1
}
```
A **function** groups commands. `return 1` leaves the function with "failure". Git passes **push options** (extra text sent with `git push --push-option`) as variables `GIT_PUSH_OPTION_0`, `GIT_PUSH_OPTION_1`, ... and their count in `GIT_PUSH_OPTION_COUNT`. `eval` builds the variable name and reads it; this is the portable way to do "variable of a variable" in `sh`. `$((i + 1))` is integer arithmetic. The function succeeds only if some push option equals `ci-token=<the secret in the server's file>`.

```sh
status=0
while read -r old new ref; do
  case "$ref" in
    refs/status/*)
      ...
    refs/heads/main)
      ...
  esac
done
exit "$status"
```
`while read -r old new ref` reads each input line and splits it into three variables (`-r` keeps backslashes as they are). `case ... esac` matches text against patterns. The script records a failure in `status` but keeps looping so it can print every problem, then exits with that status.

For `main` it checks three things, in this order:
1. `[ "$new" = "$zero" ]`: the push would delete `main`. Refused.
2. `! git merge-base --is-ancestor "$old" "$new"`: the old tip must be inside the new history. If not, someone is rewriting history (a force push) or the branch is behind. Refused.
3. `! git rev-parse --verify -q "refs/status/green/$new"`: there must be a ref named after the new commit that only CI can create. No ref, no merge.

`${new%"${new#???????}"}` shortens a SHA to seven characters using only `sh` features: `${new#???????}` is "new without its first seven characters", and `%` then removes that tail from `new`.

### `scripts/gate-demo.sh`

```sh
set -eu
```
`set -e` stops the script at the first command that fails. `set -u` makes an unset variable an error instead of silently empty text. (`-o pipefail`, which makes a pipeline fail when any part fails, is not available in every `sh`, so the script avoids long pipelines.)

```sh
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
```
`$0` is the script's own path. `dirname` strips the file name. `cd ... && pwd` gives an absolute path of the repository root. `mktemp -d` makes a fresh temporary folder. `trap '...' EXIT` runs the cleanup when the script ends, however it ends.

```sh
export GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.test GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.test
token=$(python -c 'import secrets; print(secrets.token_hex(16))')
```
`export` makes variables visible to the programs the script starts, so `git commit` works on a machine with no git identity. The token is a random 32-character secret.

```sh
say() { printf '\n== %s\n' "$*"; }
must_be_refused() {
  if "$@" >"$work/out" 2>&1; then
    cat "$work/out"
    echo "UNEXPECTED: the push was accepted"
    exit 1
  fi
  grep -E 'remote:|rejected' "$work/out" | head -3
  echo "-> refused"
}
```
`"$@"` means "all the arguments, each kept whole". `must_be_refused git push origin main` runs that git command. If it succeeds, that is a bug in the demo, so the script stops. If it fails (as it should), the script shows the first three lines of the server's explanation.

The six scenarios use `git init --bare`, `git config receive.advertisePushOptions true` (so the server accepts push options), `cp` of the hook plus `chmod +x`, and `git push origin $sha:refs/status/green/$sha` to post a status. See [git.md](git.md).

## Try it yourself

```bash
pipeline/changes.sh HEAD~1 HEAD
```
Prints `code=true` or `code=false` depending on what the last commit changed.

```bash
git diff --name-only HEAD~3 HEAD | grep -qvE '^(docs/|.*\.md$)'; echo "exit status: $?"
```
`0` means at least one non-documentation file changed. `1` means only docs changed.

```bash
make gate-demo
```
Expect six sections, each ending in `-> refused` or `-> accepted`, and `all six behaviors confirmed` at the end.

```bash
sh -n scripts/gate-demo.sh && echo "syntax ok"
```
`-n` checks the syntax without running anything.

## Mistakes people make

- Forgetting quotes: `rm -rf $dir` with an empty `dir` is a disaster. Here every expansion is quoted.
- Writing Bash-only features (`[[ ]]`, arrays, `pipefail`) in a file that starts with `#!/bin/sh`. The pre-receive hook must run on a plain `sh`.
- Parsing `ls` output. Here `git diff --name-only` gives clean lines.
- Forgetting that a pipeline's exit status is the **last** command's. `set -e` alone will not catch `failing_cmd | cat`.
- Not cleaning up temporary files. `trap ... EXIT` handles it.

## Check yourself

1. What does exit status 0 mean? *Success; any other number is a failure.*
2. What is the difference between `$*`/`$@` quoted as `"$@"` and an unquoted `$@`? *Quoted keeps every argument whole, even with spaces; unquoted splits them.*
3. Why does `changes.sh` print `code=true` when it cannot find the base commit? *When unsure, run the full pipeline; a wrong `false` would skip needed checks.*
4. What does `set -eu` do? *Stops at the first failing command and treats unset variables as errors.*
5. Why does the hook need the file `$GIT_DIR/ci-token`? *Only the server owner and CI know it, so nobody else can post a green status.*

## Further reading

- POSIX shell language (what `sh` must support): https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html
- Bash manual (for the features `sh` lacks): https://www.gnu.org/software/bash/manual/bash.html
- `githooks`, the `pre-receive` section: https://git-scm.com/docs/githooks#pre-receive
