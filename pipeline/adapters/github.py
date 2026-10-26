"""Talk to GitHub through the `gh` CLI (needs `gh auth login`; nothing here runs in the tests)."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def apply_branch_protection(repo: str, payload: dict[str, Any]) -> None:
    """`PUT /repos/{repo}/branches/main/protection` with `payload`."""
    subprocess.run(  # noqa: S603
        ["gh", "api", "-X", "PUT", f"repos/{repo}/branches/main/protection", "--input", "-"],  # noqa: S607
        input=json.dumps(payload),
        text=True,
        check=True,
    )


def list_runs(repo: str, limit: int) -> str:
    """The JSON that `import-gh-runs` reads: the last `limit` workflow runs."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--limit",
            str(limit),
            "--json",
            "databaseId,headSha,conclusion,createdAt,updatedAt",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
