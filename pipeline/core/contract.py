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
