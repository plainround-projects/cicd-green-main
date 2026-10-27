# Dependabot

## What it is

A **dependency** is a library your project uses. Libraries get new versions all the time: bug fixes and security fixes. **Dependabot** is a GitHub service that watches your project's dependency files, notices when a newer version exists and opens a **pull request** (a proposed change) that updates it. You review the pull request; the project's normal checks run on it, so a bad update shows up as a red check rather than as a surprise in production. It is configured by a file in the repository, `.github/dependabot.yml`, written in YAML ([yaml.md](yaml.md)).

## Why this repository uses it

This project pins every Python package to an exact version with a checksum ([pip-and-hash-locking.md](pip-and-hash-locking.md)) and every GitHub Action to an exact commit ([github-actions.md](github-actions.md)). Exact pins are safe, but they go stale, and a stale pin eventually hides a security fix. Dependabot turns "update the pins" into a small, regular, reviewed, tested change.

## Where it appears

| Path | Use |
|---|---|
| `.github/dependabot.yml` | Two update streams, both weekly. |

## How it works underneath

On a schedule, GitHub reads the files for each *ecosystem* named in the configuration, compares each pinned version with the newest published one, and opens one pull request per update. For the `pip` ecosystem it reads requirement and project files in the folder you name. For the `github-actions` ecosystem it reads the `uses:` lines of workflows (including full-commit pins; it updates the commit id and the version comment). It runs only on GitHub, never on your machine.

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

- **Line 1**: `version: 2` is the version of the configuration format (required).
- **Line 2**: `updates:` starts a list; each list item (a line starting `- `) is one stream of updates.
- **Lines 3 to 6**, the first stream: `package-ecosystem: pip` means "Python packages"; `directory: /` is the folder to look in (`/` is the repository root); `schedule: interval: weekly` is how often to check (once a week, batching the work).
- **Lines 7 to 10**, the second stream: `package-ecosystem: github-actions` and the same `directory` and `schedule`. This is the stream that keeps the pinned actions in `ci.yml`, `audit.yml` and the composite action up to date.

One caution this repository records: its Python pins are produced by `uv pip compile` into `requirements-dev.lock` ([uv.md](uv.md)). A Dependabot pull request against a lock file should be checked by regenerating the lock with that command before merging. This was not exercised here, because Dependabot works only on GitHub.

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
