# Markdown

## What it is

Markdown is a lightweight way to write formatted text in a plain file: `#` for headings, `-` for bullets, backticks for code, `|` for tables. GitHub shows `.md` files as formatted pages. Every document in this repository (`README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, the decision records, these notes) is Markdown.

## Why this repository uses it

Documentation lives next to the code and goes through the same review. One rule of the lesson, "the README states the pipeline's contract in ten lines", is checked by code, so the Markdown structure matters.

## Where it appears

| Path | Use |
|---|---|
| `README.md` | Overview, commands, the contract. |
| `ARCHITECTURE.md` | Components and layers. |
| `CHANGELOG.md` | Changes by version. |
| `docs/adr/*.md` | Architecture decision records: one decision each. |
| `docs/issues/0001-*.md` | The flaky-test write-up. |
| `pipeline/core/contract.py` | Reads `README.md`. |
| `pipeline/changes.sh` | Treats `*.md` as documentation. |
| `tech/*.md` | These notes. |

## How it works underneath

Markdown is just text. A renderer turns it into HTML. The pipeline does not render it; `contract.py` reads it as lines.

## Walkthrough of this repository's use

```python
CONTRACT_HEADING = "## The pipeline's contract"
MAX_LINES = 10

def contract_lines(readme: str) -> list[str]:
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
```
Find the heading line, then collect the non-empty lines until the next `## ` heading. `check` then requires at most ten lines, a mention that a red `main` is fixed or reverted, and a time in minutes (`\d+ minutes`). `make contract` (also run by `make lint`) fails if the README stops satisfying that. Documentation-only commits are skipped by CI because `changes.sh` ignores `docs/` and `*.md`.

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
