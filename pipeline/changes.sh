#!/bin/sh
# Decide whether a change can affect the code: prints `code=true` or `code=false`.
# usage: changes.sh BASE HEAD     (BASE may be empty or all zeros, for a new branch)
# `false` only when every changed file is documentation (docs/ or *.md). Anything unknown runs the pipeline.
# The pipeline's jobs are skipped with `if:`, not with a `paths` filter: a skipped job reports as passed to a required
# check, while a workflow that never starts reports nothing and blocks the merge for ever.
base=$1
head=${2:-HEAD}
zero=0000000000000000000000000000000000000000

if [ -z "$base" ] || [ "$base" = "$zero" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  echo "code=true"
  exit 0
fi

changed=$(git diff --name-only "$base" "$head" 2>/dev/null) || { echo "code=true"; exit 0; }
[ -n "$changed" ] || { echo "code=true"; exit 0; }

if printf '%s\n' "$changed" | grep -qvE '^(docs/|.*\.md$)'; then
  echo "code=true"
else
  echo "code=false"
fi
