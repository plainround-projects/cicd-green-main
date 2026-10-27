# Dependabot

## What it is

Dependabot is a GitHub service that watches your dependency files and opens pull requests when newer versions exist. You configure it with `.github/dependabot.yml` ([yaml.md](yaml.md)). Each pull request runs the normal pipeline, so a bad update shows up as a red check, not as a surprise.

## Why this repository uses it

Hash-locked, pinned dependencies and SHA-pinned actions are safe but go stale. Dependabot makes updating a routine, reviewed, tested change instead of a rare risky one.

## Where it appears

| Path | Use |
|---|---|
| `.github/dependabot.yml` | Two update streams, both weekly. |

## How it works underneath

On a schedule GitHub reads the files for each ecosystem, compares pinned versions with the registry, and opens one pull request per update. For `pip` it reads requirements and `pyproject.toml`; for `github-actions` it reads `uses:` lines (including full-SHA pins, and it updates the SHA and the version comment).

## Walkthrough of this repository's use

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```
`version: 2` is the file format version. Each list item is one stream. `package-ecosystem` selects the kind of dependency. `directory: /` is where to look. `interval: weekly` batches the work into one day per week.

Note: Dependabot updates the version numbers it finds in the repository's dependency files. This repository regenerates `requirements*.lock` with `uv pip compile` ([pip-and-hash-locking.md](pip-and-hash-locking.md)); a Dependabot pull request for the lock files should be checked with that command before merging. This was not run here, because Dependabot only works on GitHub.

## Try it yourself

```bash
cat .github/dependabot.yml
```

```bash
.venv/bin/python -c "import yaml; print(len(yaml.safe_load(open('.github/dependabot.yml'))['updates']))"
```
Expect `2`.

```bash
grep -rhn "uses: .*@" .github | wc -l
```
The number of pinned action references Dependabot watches.

## Mistakes people make

- Merging update pull requests without reading the changelog.
- Letting them pile up. Weekly keeps them small.
- Unpinned actions (nothing for Dependabot to update, and unsafe).

## Check yourself

1. What triggers a Dependabot pull request? *A newer version of a pinned dependency exists.*
2. Why does the pipeline matter here? *It tests each update before merge.*
3. What are the two ecosystems? *`pip` and `github-actions`.*
4. What does `interval: weekly` do? *Checks once per week.*
5. Does Dependabot run locally? *No; it is a GitHub service.*

## Further reading

- Dependabot options reference: https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference
