# Markdown

## What it is

**Markdown** is a way to write formatted text in a plain text file using a few simple marks. A `#` at the start of a line makes a heading (`##` a smaller one); `- ` starts a bullet; `1.` a numbered item; words in `**double stars**` are bold; words in `` `backticks` `` are shown as code; three backticks on a line of their own start and end a block of code; and rows with `|` between cells make a table, with a second row of dashes (`| --- | --- |`) under the header row. Files ending in `.md` hold Markdown. GitHub shows them as formatted pages; a text editor shows the marks.

## Why this repository uses it

Documentation lives next to the code and goes through the same review. One rule of the lesson is checked by a program: *the README states the pipeline's contract in ten lines or fewer, and says what to do when `main` is red.* So the **structure** of the README matters, not only its words.

## Where it appears

| Path | Use |
|---|---|
| `README.md` | Overview, commands, the "Done when" table, the contract. |
| `ARCHITECTURE.md` | Components and the layers. |
| `CHANGELOG.md` | What changed in each version. |
| `docs/adr/0001...0005` | Architecture decision records: one decision each. |
| `docs/issues/0001-flaky-job-timing-test.md` | A write-up of the flaky test. |
| `pipeline/core/contract.py` | Reads `README.md` as text. |
| `pipeline/changes.sh` | Treats `docs/` and `*.md` as documentation (no code jobs needed). |
| `tech/*.md` | These notes. |

## How it works underneath

Nothing in the pipeline renders Markdown. It is plain text, so the contract check treats the README as a list of lines and looks for the line `## The pipeline's contract`. The marks only matter to the reader and to GitHub's page.

## Walkthrough of this repository's use

### The contract check (`pipeline/core/contract.py`)

```python
"""Check the README's pipeline contract: short, concrete, and it says what to do when `main` is red."""

from __future__ import annotations

import re

_HEADING = re.compile(r"^## ")
CONTRACT_HEADING = "## The pipeline's contract"
MAX_LINES = 10


def contract_lines(readme: str) -> list[str]:
    """The non-empty lines under the contract heading, up to the next `## ` heading."""
    lines = readme.splitlines()
    try:
        start = lines.index(CONTRACT_HEADING) + 1
    except ValueError:
        return []
    body = []
    for line in lines[start:]:
        if _HEADING.match(line):
            break
        if line.strip():
            body.append(line)
    return body


def check(readme: str) -> list[str]:
    """Problems with the contract; an empty list means it fits ten lines and states the red-main rule."""
    body = contract_lines(readme)
    text = " ".join(body).lower()
    problems = []
    if not body:
        problems.append(f"no section titled {CONTRACT_HEADING!r}")
    if len(body) > MAX_LINES:
        problems.append(f"the contract has {len(body)} lines, the limit is {MAX_LINES}")
    if "red `main`" not in text or "fix" not in text or "revert" not in text:
        problems.append("it must say that a red `main` is fixed or reverted before new work merges")
    if not re.search(r"\d+ minutes", text):
        problems.append("it must give the time the required checks should take, in minutes")
    return problems
```

- **Line 7**: `_HEADING = re.compile(r"^## ")` matches a line that starts with `## `, a level-two heading.
- **Lines 8 and 9**: `CONTRACT_HEADING = "## The pipeline's contract"` and `MAX_LINES = 10`.
- **Lines 12 to 26**, `contract_lines(readme)`: split the text into lines; find the heading with `lines.index(CONTRACT_HEADING)` (which raises `ValueError` if absent, caught to return `[]`); collect the following lines until the next `## ` heading, keeping only the non-empty ones (`line.strip()` is empty text, which counts as false, for a blank line).
- **Lines 29 to 41**, `check(readme)`: returns a list of problems.
  - no such section: `no section titled "## The pipeline's contract"`;
  - more than ten lines: `the contract has N lines, the limit is 10`;
  - it must contain the words "red `main`", "fix" and "revert" (after turning everything to lower case);
  - it must give a time in minutes (`re.search(r"\d+ minutes", text)`: one or more digits, a space, "minutes").
  An empty list means the contract is fine. `make lint` runs it through `python -m pipeline check-contract`, which prints `contract ok` or the problems, and exits 1 on problems.

The tests build small READMEs as Python strings (a good one, one over ten lines, one without the rule, one with no section) and check the answers, and a last test checks this repository's own README ([pytest.md](pytest.md)).

### Skipping jobs for documentation changes

`pipeline/changes.sh` decides that a change is "documentation only" when every changed file is under `docs/` or ends in `.md` ([bash-and-sh.md](bash-and-sh.md)). That is why a change to a README or to these notes does not start the code jobs.

### The shape of the other documents

`ARCHITECTURE.md` explains the layers and the flow; `docs/adr/` has one numbered file per decision (one make target per job; build once and test the artifact; skip with `if` never with `paths`; quarantine with a marker and a non-blocking job; a Git hook stands in for branch protection), each with Context, Decision and Consequences; `CHANGELOG.md` lists changes by version.

## Try it yourself

```bash
make contract
```
Expect a line saying the contract is fine.

```bash
.venv/bin/python -c "from pathlib import Path; from pipeline.core import contract; print(len(contract.contract_lines(Path('README.md').read_text())))"
```
A number of 10 or fewer.

```bash
grep -n "^## " README.md
```
Lists the headings.

## Mistakes people make

- Documentation that nothing checks and so goes stale.
- Using bold text where a heading is meant, so tools cannot find it.
- Tables with unequal column counts.

## Check yourself

1. What does the `#` count mean? *Heading level.*
2. Why does CI skip jobs for `.md` changes? *Documentation cannot break the code.*
3. What does `contract.py` check? *Length, the red-`main` rule and a time in minutes.*
4. What is an ADR? *A short record of one design decision.*
5. Is Markdown rendered by the pipeline? *No; it is read as plain text.*

## Further reading

- CommonMark: https://spec.commonmark.org/
- GitHub Flavored Markdown: https://github.github.com/gfm/
