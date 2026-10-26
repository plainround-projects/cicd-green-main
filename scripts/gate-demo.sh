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

say "3. The fix: checks pass, CI posts a green status for that commit, the merge is accepted"
printf 'def add(left, right):\n    return left + right\n\n\n# fixed\n' >app.py && git commit -qam "fix add"
fixed=$(git rev-parse HEAD)
gate "$fixed"
git push -q origin "$fixed:main" 2>&1 | sed 's/^/   /'
echo "-> accepted: main is now $(git -C "$work/origin.git" rev-parse --short main)"

say "4. A second branch, green on its own, but cut from the old main: not up to date, so refused"
git checkout -q -b stale "$(git rev-parse "$fixed~2")" 2>/dev/null || git checkout -q -b stale "$(git rev-list --max-parents=0 HEAD)"
printf '\n# another change\n' >>app.py && git commit -qam "another change"
stale=$(git rev-parse HEAD)
gate "$stale"
must_be_refused git push origin "$stale:main"

say "5. Posting a status without the CI token (to fake a green check for a commit that never passed)"
printf '\n# unchecked\n' >>app.py && git commit -qam "unchecked change"
unchecked=$(git rev-parse HEAD)
must_be_refused git push origin "$unchecked:refs/status/green/$unchecked"

say "6. Force-pushing or deleting main"
must_be_refused git push --force origin "$stale:main"
must_be_refused git push origin :main

printf '\nall six behaviors confirmed\n'
