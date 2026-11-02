# Shell scripts (`sh` and Bash)

## What it is

A **terminal** is a window in which you type text commands. The program that reads what you type and starts other programs for you is called a **shell**. `sh` is the oldest and most portable shell language: every Unix-like computer (Linux, macOS, the little Linux inside a container) understands it. **Bash** is a larger shell that adds features; this repository's scripts avoid those features on purpose, so they begin with `#!/bin/sh`.

A **shell script** is a text file of shell commands that the shell runs from top to bottom. Its first line, `#!/bin/sh`, is called the **shebang**: it tells the operating system "run this file with the program `/bin/sh`". For the file to be runnable you also set its *execute permission* (`chmod +x file`). A line starting with `#` anywhere else is a **comment**: the shell ignores it and it is there for people.

You will meet these ideas in every script below, so here they are in one place:

- **Process.** Every command you run becomes a *process*: one running copy of a program. When it ends it hands back an **exit status**, a number from 0 to 255. By convention `0` means "it worked" and any other number means "it failed". The shell remembers the last status in `$?`.
- **Streams.** A process has three channels: **standard input** (number 0, what it reads), **standard output** (number 1, what it prints normally) and **standard error** (number 2, where it prints complaints). `command > file` sends standard output to a file; `command 2> file` sends the errors; `2>&1` means "send errors to wherever output goes"; `>&2` on a command means "send its output to the error channel"; `/dev/null` is a place where anything written is thrown away. `<` feeds a file to a command's input.
- **Pipe.** `a | b` connects the output of `a` to the input of `b`; both run at the same time.
- **Variable.** A named piece of text. `name=value` sets it (no spaces around `=`). `$name` or `${name}` reads it. Always put quotes around a read, as in `"$name"`: without quotes the shell splits the text at spaces and expands wildcard characters, which causes bugs when a name contains a space.
- **Command substitution.** `$(command)` runs the command and is replaced by what it printed.
- **Arguments.** `$1`, `$2`, ... are the words given to the script. `"$@"` means "all of them, each kept as one word". `$0` is the script's own path.
- **Defaults and checks.** `${name:-default}` means "the variable, or `default` if it is unset or empty". `${name:?message}` means "the variable, or stop with `message` if it is unset".
- **Tests.** `[ ... ]` is a command (it is called `test`) that exits 0 if the condition inside is true. `[ -z "$x" ]` is true if `x` is empty; `[ -n "$x" ]` if it is not empty; `[ a = b ]` if the two texts are equal; `[ "$i" -lt 5 ]` if the number `i` is less than 5. `!` in front reverses it. `if cmd; then ...; elif ...; else ...; fi` runs a command and branches on its exit status.
- **Lists.** `a && b` runs `b` only if `a` succeeded. `a || b` runs `b` only if `a` failed. `a; b` runs both. `{ a; b; }` groups commands.
- **Loops.** `while cmd; do ...; done` repeats while the command succeeds; `for x in a b c; do ...; done` repeats once for each item.
- **Functions.** `name() { ...; }` defines a reusable block of commands; `return N` leaves it with status N.
- **`set -eu`.** `set -e` makes the script stop at the first command that fails; `set -u` makes using an unset variable an error.
- **`trap`.** `trap 'commands' EXIT` runs the commands when the script ends, however it ends: a clean-up that cannot be forgotten.

## Why this repository uses it

A pipeline has to glue programs together: ask Git which files changed, react when someone pushes, stage a fake remote and push to it. Shell is the shortest way to say that. One of the scripts also runs **on the server side of Git**, where only a plain shell can be counted on. The lesson's step "a failing test cannot merge" is shown locally by that script.

## Where it appears

| File | Role |
|---|---|
| `pipeline/changes.sh` | Prints `code=true` or `code=false`: does a change touch more than documentation? CI uses the answer to skip jobs. |
| `pipeline/hooks/pre-receive` | A Git *hook*: the local stand-in for GitHub's branch protection. Refuses pushes to `main` that have no green status. |
| `scripts/gate-demo.sh` | Builds a fake remote and makes six push attempts; five must be refused and one accepted. |
| `Makefile` recipes | Every recipe line is a shell command ([make.md](make.md)). |
| `.github/workflows/ci.yml` `run:` lines | Each is a shell snippet run on the CI machine ([github-actions.md](github-actions.md)). |

## How it works underneath

When you type a command, the shell: (1) reads the line, (2) performs **expansions** (replaces `$variables`, `$(...)`, and wildcards such as `*.sql`), (3) finds the program (looking through the folders listed in the `PATH` variable), (4) starts it as a new process with the arguments, (5) waits for it to end and records its exit status. A script is that, repeated line by line, with `if`/`while` deciding which lines run.

`mktemp -d` creates a new empty folder with an unpredictable name in the system's temporary area. `eval` runs a string as shell code after expanding it. `read -r a b c` reads a line from standard input and splits it into three variables (`-r` stops backslashes being treated specially). `case value in pattern) ... ;; esac` compares a value with patterns, like a tidier `if`. `printf 'format' args` prints text exactly (unlike `echo`, it never treats the text as options). `grep` searches text for a pattern; `sed` edits text as it flows past; `head -3` keeps the first three lines; `cut`, `sort`, `tee -a file` (copy output to a file and to the screen, appending) are small tools for reshaping text.

## Walkthrough of this repository's use

All three scripts are covered line by line. After that, the shell lines in other files.

### `pipeline/changes.sh`: does this change touch code?

CI runs this first. A change that only touches documentation can skip the expensive jobs, so the pipeline asks this script. It must never say "docs only" by mistake, so whenever it is unsure it says "code".

```sh
#!/bin/sh
# Decide whether a change can affect the code: prints `code=true` or `code=false`.
# usage: changes.sh BASE HEAD     (BASE may be empty or all zeros, for a new branch)
# `false` only when every changed file is documentation (docs/ or *.md). Anything unknown runs the pipeline.
# The pipeline's jobs are skipped with `if:`, not with a `paths` filter: a skipped job reports as passed to a required
# check, while a workflow that never starts reports nothing and blocks the merge for ever.
```

- **Line 1** is the shebang. **Lines 2 to 6** are comments that state the contract: the arguments are `BASE HEAD`, the output is `code=true` or `code=false`, and `false` happens only when every changed file is documentation (under `docs/` or ending in `.md`). They also say *why* the jobs are skipped with an `if:` and not with a `paths` filter: a skipped job counts as passed for a required check, while a workflow that never starts leaves the check missing, and a missing check blocks the merge for ever.

```sh
base=$1
head=${2:-HEAD}
zero=0000000000000000000000000000000000000000
```

- **Line 7**: `base=$1` stores the first argument (the commit before the change) in a variable named `base`. There are no spaces around `=`.
- **Line 8**: `head=${2:-HEAD}` stores the second argument, or the word `HEAD` (Git's name for "the commit I am on") if there is none.
- **Line 9**: `zero=000...000` is forty zeros. GitHub reports the "commit before" of a brand-new branch as forty zeros: it means "nothing".

```sh
if [ -z "$base" ] || [ "$base" = "$zero" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  echo "code=true"
  exit 0
fi
```

- **Line 11**: three conditions joined by `||` (or): the base is empty (`[ -z "$base" ]`), or it is the forty zeros, or `git cat-file -e "$base^{commit}"` fails. `git cat-file -e` checks whether an object exists in this copy of the repository (`-e` for *exists*); `^{commit}` asks for it to be a commit; `2>/dev/null` hides its complaint; the `!` in front reverses the result, so the test is true when the commit is **missing**. This happens if the checkout is too shallow to know the base.
- **Lines 12 and 13**: in any of those cases print `code=true` (run everything) and `exit 0` (end the script with success). `echo` prints a line.
- **Line 14**: `fi` ends the `if`.

```sh
changed=$(git diff --name-only "$base" "$head" 2>/dev/null) || { echo "code=true"; exit 0; }
[ -n "$changed" ] || { echo "code=true"; exit 0; }
```

- **Line 16**: `changed=$(git diff --name-only "$base" "$head" 2>/dev/null)` runs `git diff --name-only`, which lists the names of files that differ between the two commits, one per line, and stores the list in `changed`. The `|| { echo "code=true"; exit 0; }` after it means: if the git command itself failed, print `code=true` and stop. The braces group the two commands.
- **Line 17**: `[ -n "$changed" ] || { ... }`: if the list is empty, again say `code=true`. An empty diff is unusual, so the safe answer is to run everything.

```sh
if printf '%s\n' "$changed" | grep -qvE '^(docs/|.*\.md$)'; then
  echo "code=true"
else
  echo "code=false"
fi
```

- **Line 19**: `printf '%s\n' "$changed"` prints the list, one name per line; `| grep -qvE '^(docs/|.*\.md$)'` passes it to `grep`. The flags: `-E` allows the pattern syntax with parentheses and `|`; `-v` selects lines that do **not** match; `-q` prints nothing and only sets the exit status (success if at least one line was selected). The pattern `^(docs/|.*\.md$)` means: a line that starts with `docs/`, or that ends in `.md` (`.*` is any text, `\.` a real dot, `$` the end). So the `if` is true when *at least one changed file is neither under `docs/` nor a Markdown file*.
- **Lines 20 to 23**: print `code=true` in that case, otherwise `code=false`.

In `ci.yml` the line is `pipeline/changes.sh "$BASE" "${{ github.sha }}" | tee -a "$GITHUB_OUTPUT"`. `tee -a` prints the line and also appends it to the file named by `GITHUB_OUTPUT`, which is how a step passes a value to later jobs ([github-actions.md](github-actions.md)).

### `pipeline/hooks/pre-receive`: the rules of `main`, on the server

A Git **hook** is a program that Git runs automatically at a certain moment. `pre-receive` runs **on the server**, after a `git push` has arrived and before Git accepts it. Git sends it one line per branch or tag being updated, on its standard input, in the form `old-sha new-sha ref-name`. If the hook exits with anything but 0, Git rejects the whole push. GitHub does not allow hooks, so this is the local stand-in for GitHub's *branch protection* ([git.md](git.md)).

```
#!/bin/sh
# Server-side protection for `main`, the local counterpart of GitHub branch protection:
#   - main only moves forward (the branch must be up to date; no force push, no deletion);
#   - main only moves to a commit that has a green status, posted by CI as refs/status/green/<sha>;
#   - only CI can post a status: a push to refs/status/* needs the token in $GIT_DIR/ci-token as a push option.
# The first push that creates main is allowed, so a repository can be seeded.
zero=0000000000000000000000000000000000000000
```

- **Lines 2 to 6** state the three rules. (1) `main` only moves forward: no force push, no deletion. (2) `main` only moves to a commit with a green status, which CI posts as a reference named `refs/status/green/<sha>`. (3) Only CI can post a status: pushing to `refs/status/*` needs a secret token, kept in the file `$GIT_DIR/ci-token` on the server and sent by the pusher as a **push option** (extra text a client can send along with a push). The first push that creates `main` is allowed so the repository can be seeded.
- **Line 7**: `zero` is the forty-zeros "no commit" value again.

```
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

This defines a function `ci_token_given` that answers "did the pusher present the right token?" by exiting 0 or 1.

- **Line 10**: `expected=$(cat "$GIT_DIR/ci-token" 2>/dev/null)` reads the secret. `GIT_DIR` is a variable Git sets for hooks to the repository's folder. Errors are hidden, so a missing file gives empty text.
- **Line 11**: `[ -n "$expected" ] || return 1`: with no secret configured nobody can post a status, so leave with failure (1).
- **Line 12**: `i=0` is a counter. **Line 13**: `while [ "$i" -lt "${GIT_PUSH_OPTION_COUNT:-0}" ]; do` loops while the counter is less than the number of push options (Git puts that number in `GIT_PUSH_OPTION_COUNT`; `:-0` supplies 0 if it is unset).
- **Line 14**: `eval "option=\$GIT_PUSH_OPTION_$i"`. Git passes the options as variables named `GIT_PUSH_OPTION_0`, `GIT_PUSH_OPTION_1`, `GIT_PUSH_OPTION_2`, one more for each option, up to the count in `GIT_PUSH_OPTION_COUNT`. To read "the variable whose name ends with the counter" the script builds the text `option=$GIT_PUSH_OPTION_0` and hands it to `eval`, which expands and runs it. (`\$` keeps the first dollar sign literal for `eval` to expand.)
- **Line 15**: if the option equals `ci-token=` plus the secret, `return 0` (success). **Line 16**: `i=$((i + 1))`: `$(( ))` is whole-number arithmetic. **Lines 17 and 18**: after the loop, `return 1`.

```
status=0
while read -r old new ref; do
  case "$ref" in
    refs/status/*)
      if ! ci_token_given; then
        echo "protected: only CI may post a status ($ref)" >&2
        status=1
      fi
      ;;
    refs/heads/main)
      if [ "$new" = "$zero" ]; then
        echo "GH006 protected branch: main cannot be deleted" >&2
        status=1
      elif [ "$old" != "$zero" ] && ! git merge-base --is-ancestor "$old" "$new"; then
        echo "GH006 protected branch: the branch is not up to date with main (no force push)" >&2
        status=1
      elif [ "$old" != "$zero" ] && ! git rev-parse --verify -q "refs/status/green/$new" >/dev/null; then
        echo "GH006 protected branch: required status checks have not passed for ${new%"${new#???????}"}" >&2
        status=1
      fi
      ;;
  esac
done
exit "$status"
```

- **Line 21**: `status=0` will become 1 if any rule is broken. The loop does not exit on the first problem, so all problems are printed.
- **Line 22**: `while read -r old new ref; do` reads one line from standard input per round and splits it into the three variables. The loop ends when there are no more lines (line 43, `done`).
- **Line 23**: `case "$ref" in` compares the ref's name with patterns.
  - **Lines 24 to 29**, pattern `refs/status/*`: someone is posting a status. `if ! ci_token_given; then` (the `!` reverses the function's answer) prints `protected: only CI may post a status (ref)` to standard error (`>&2`) and sets `status=1`. `;;` ends this case.
  - **Lines 30 to 41**, pattern `refs/heads/main`: three checks, each an `if`/`elif`.
    - `[ "$new" = "$zero" ]`: the new value is "nothing", i.e. the push deletes `main`. Refuse with Git's own wording `GH006 protected branch`.
    - `[ "$old" != "$zero" ] && ! git merge-base --is-ancestor "$old" "$new"`: unless this is the first push, the old tip must be contained in the new history; `git merge-base --is-ancestor A B` exits 0 if A is an ancestor of B. If not, someone rewrote history (a force push) or the branch is behind. Refuse.
    - `[ "$old" != "$zero" ] && ! git rev-parse --verify -q "refs/status/green/$new" >/dev/null`: the commit must have a green status reference; `git rev-parse --verify -q` succeeds only if the name exists (`-q` quiet). The error message cuts the commit id to seven characters with `${new%"${new#???????}"}`: `${new#???????}` is `new` with its first seven characters removed, and `${new%...}` removes that remainder from the end of `new`, leaving the first seven.
  - **Line 42**: `esac` ends the `case`.
- **Line 44**: `exit "$status"` ends with 0 (accept) or 1 (reject the push).

### `scripts/gate-demo.sh`: six pushes against a fake GitHub

This script proves the rules above. It needs `python` and `pytest` on the `PATH` (`make gate-demo` arranges that).

```sh
#!/bin/sh
# Step 2 of the lesson without GitHub: "a failing test cannot merge, and a direct push to main is refused".
# A bare repository plays GitHub. Its pre-receive hook (pipeline/hooks/pre-receive) is the branch protection:
# main only moves forward, only to a commit CI has marked green, and only CI holds the token that marks one.
# Needs python with pytest on PATH (make gate-demo arranges it).
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.test GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.test
token=$(python -c 'import secrets; print(secrets.token_hex(16))')
```

- **Lines 2 to 5** explain the idea: a *bare* repository (a repository that holds history but no working files, which is what a server keeps) plays GitHub; its `pre-receive` hook is the branch protection.
- **Line 6**: `set -eu` stops at the first failing command and treats unset variables as errors. (`-o pipefail`, which makes a pipeline fail if any part fails, is not available in every `sh`, so the script avoids long pipelines.)
- **Line 8**: `root=$(cd "$(dirname "$0")/.." && pwd)`. `$0` is this script's path; `dirname` removes the file name; adding `/..` goes up one folder; `cd` there inside the substitution and `pwd` prints the absolute path. Result: the repository root, whatever folder you started from.
- **Line 9**: `work=$(mktemp -d)` makes a fresh temporary folder. **Line 10**: `trap 'rm -rf "$work"' EXIT` deletes it when the script ends, however it ends.
- **Line 11**: `export` makes variables visible to the programs the script starts. These four give Git an author and committer name and e-mail, so `git commit` works on a machine with no Git identity set up. The `.test` e-mail domain is reserved and can never exist.
- **Line 12**: `token=$(python -c 'import secrets; print(secrets.token_hex(16))')` makes a random 32-character secret: `python -c "code"` runs one line of Python.

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
gate() { (cd "$root" && python -m pipeline gate --repo "$work/dev" --remote origin --sha "$1" --token "$token" --checks "python -m pytest -q -p no:cacheprovider"); }
```

- **Line 14**: `say() { printf '\n== %s\n' "$*"; }` is a function that prints a heading. `"$*"` joins all the arguments into one word.
- **Lines 15 to 23**: `must_be_refused` runs the command it is given (`"$@"`), sending its output to a file in the work folder (`>"$work/out" 2>&1` means output to the file, then errors to the same place). `if "$@" ...; then` is true if the command **succeeded**, which here is a bug (the push should have been refused): it prints what happened, says `UNEXPECTED`, and `exit 1`. If the command failed, as it should, the script shows up to three lines of the server's explanation (`grep -E 'remote:|rejected' ... | head -3`: lines containing `remote:` or `rejected`, first three only) and prints `-> refused`.
- **Line 24**: `gate()` is a function that runs `python -m pipeline gate` for a commit with the shared token, telling it to run `python -m pytest -q -p no:cacheprovider` as the checks. `( cd ... && ... )` runs in a subshell so the `cd` does not affect the rest of the script.

```sh
git init -q --bare "$work/origin.git"
git -C "$work/origin.git" config receive.advertisePushOptions true
cp "$root/pipeline/hooks/pre-receive" "$work/origin.git/hooks/pre-receive"
chmod +x "$work/origin.git/hooks/pre-receive"
printf '%s\n' "$token" >"$work/origin.git/ci-token"

git clone -q "$work/origin.git" "$work/dev" 2>/dev/null
cd "$work/dev"
git checkout -q -b main
printf 'def add(left, right):\n    return left + right\n' >app.py
printf 'from app import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n' >test_app.py
git add . && git commit -q -m "first commit"
git push -q origin main 2>&1 | sed 's/^/   /' || true
echo "main created on the remote (the first push is allowed so a repository can be seeded)"
```

- **Line 26**: `git init -q --bare "$work/origin.git"` creates the fake server repository. **Line 27**: `git config receive.advertisePushOptions true` tells the server to accept push options (off by default).
- **Lines 28 and 29**: copy the hook into place and make it executable (`cp`, `chmod +x`). Git does not copy hooks when cloning, so the demo installs it by hand. **Line 30**: `printf '%s\n' "$token" >"$work/origin.git/ci-token"` writes the secret into the file the hook reads.
- **Line 32**: clone the server into `dev` (the developer's copy); `2>/dev/null` hides the "cloned an empty repository" warning. **Line 33**: `cd` there. **Line 34**: `git checkout -q -b main` creates the branch `main`.
- **Lines 35 to 37**: write two tiny Python files (a function `add` and a test of it) with `printf`, then `git add .` and `git commit -q -m "first commit"`. **Line 38**: push `main`; the first push that creates `main` is allowed. `2>&1 | sed 's/^/   /'` indents the output by three spaces; `|| true` keeps `set -e` from stopping if the push command's status is non-zero. **Line 39** prints a note.

```sh
say "1. A direct push of a new commit to main"
printf '\n# a comment\n' >>app.py && git commit -qam "direct change"
must_be_refused git push origin main

say "2. A change that breaks a test: CI runs the checks, they fail, no status is posted, the merge is refused"
git reset -q --hard origin/main
git checkout -q -b break-add
printf 'def add(left, right):\n    return left - right\n' >app.py && git commit -qam "break add"
broken=$(git rev-parse HEAD)
if gate "$broken"; then echo "UNEXPECTED: the gate passed"; exit 1; fi
must_be_refused git push origin break-add:main
```

- **Scenario 1** (lines 41 to 43): a **direct push** of a new commit to `main`, with no green status. `printf '\n# a comment\n' >>app.py` appends a line (`>>` appends), `git commit -qam` commits all tracked changes. `must_be_refused git push origin main` expects the hook to say no: the commit has no `refs/status/green/...`.
- **Scenario 2** (lines 45 to 51): **a change that breaks a test**. `git reset -q --hard origin/main` discards the previous attempt. A new branch `break-add` changes `add` to subtract, so the test fails. `broken=$(git rev-parse HEAD)` stores that commit's id. `if gate "$broken"; then echo "UNEXPECTED..."; exit 1; fi`: the gate must **fail** (so no status is posted). Then the push of that commit to `main` is refused for lack of a green status.

```sh
say "3. The fix: checks pass, CI posts a green status for that commit, the merge is accepted"
printf 'def add(left, right):\n    return left + right\n\n\n# fixed\n' >app.py && git commit -qam "fix add"
fixed=$(git rev-parse HEAD)
gate "$fixed"
git push -q origin "$fixed:main" 2>&1 | sed 's/^/   /'
echo "-> accepted: main is now $(git -C "$work/origin.git" rev-parse --short main)"
```

- **Scenario 3** (lines 53 to 58): **the fix**. Correct `add`, commit, run the gate (it runs pytest on that commit and, on success, posts `refs/status/green/<sha>` using the token). Now `git push -q origin "$fixed:main"` is accepted: `A:B` means "push my commit A to the remote name B". The script prints the new `main`.

```sh
say "4. A second branch, green on its own, but cut from the old main: not up to date, so refused"
git checkout -q -b stale "$(git rev-parse "$fixed~2")" 2>/dev/null || git checkout -q -b stale "$(git rev-list --max-parents=0 HEAD)"
printf '\n# another change\n' >>app.py && git commit -qam "another change"
stale=$(git rev-parse HEAD)
gate "$stale"
must_be_refused git push origin "$stale:main"
```

- **Scenario 4** (lines 60 to 65): **a stale branch**. A second branch is cut from an older commit (`"$fixed~2"` is two commits before the fix; if that fails, `||` falls back to the very first commit). It is green on its own (the gate posts a status for it), but it does not contain the current `main`, so the "moves forward only" rule refuses it.

```sh
say "5. Posting a status without the CI token (to fake a green check for a commit that never passed)"
printf '\n# unchecked\n' >>app.py && git commit -qam "unchecked change"
unchecked=$(git rev-parse HEAD)
must_be_refused git push origin "$unchecked:refs/status/green/$unchecked"

say "6. Force-pushing or deleting main"
must_be_refused git push --force origin "$stale:main"
must_be_refused git push origin :main

printf '\nall six behaviors confirmed\n'
```

- **Scenario 5** (lines 67 to 70): **forging a status**. A commit that never passed the gate is pushed straight to `refs/status/green/<its id>` without the token. The hook's status rule refuses it.
- **Scenario 6** (lines 72 to 74): `git push --force origin "$stale:main"` tries to overwrite `main` and `git push origin :main` tries to delete it (pushing "nothing" to a name deletes it). Both are refused.
- **Line 76** prints `all six behaviors confirmed`. Because of `set -e`, the script only gets here if every `must_be_refused` saw a refusal and the one acceptance worked.

### Shell lines in the Makefile and the workflow

- `Makefile` line 15, the `help` pipeline; lines 36 to 40, the `for` loop over SQL files; line 97, `$(shell shasum ... | cut ...)`; line 99, `test -n ... -a -n ... || { ...; exit 2; }`; lines 102 and 103, `test -x ... || { ...; }`; line 120, `cd dist && shasum -a 256 -c SHA256SUMS`. Each is explained in [make.md](make.md) with its target.
- `.github/workflows/ci.yml` line 33: `pipeline/changes.sh "$BASE" "${{ github.sha }}" | tee -a "$GITHUB_OUTPUT"`; line 47: `echo "sha256=$(cut -d' ' -f1 dist/SHA256SUMS)" | tee -a "$GITHUB_OUTPUT"` (`cut -d' ' -f1` keeps the first space-separated word of the checksum line, the digest); line 113: `make db PSQL="psql -v ON_ERROR_STOP=1 -q -h localhost -p 5432 -U service -d service"` (psql options: `-h` host, `-p` port, `-U` user, `-d` database); line 114: `make test-artifact WHEEL="$(ls dist/*.whl)" EXPECTED_SHA256="${{ needs.build.outputs.sha256 }}"` (`ls dist/*.whl` expands the wildcard to the wheel's name). See [github-actions.md](github-actions.md).

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
