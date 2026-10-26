"""The branch-protection settings that make the pipeline a required check on `main`."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

REQUIRED_CHECKS = ("build", "lint", "unit", "integration")


def branch_protection(checks: Sequence[str] = REQUIRED_CHECKS) -> dict[str, Any]:
    """The JSON body for `PUT /repos/{owner}/{repo}/branches/main/protection`.

    `strict` is "branch must be up to date", `enforce_admins` applies the rules to the owner too, and the pull request
    rule refuses direct pushes. The check names are job names, not the workflow name.
    """
    if not checks:
        raise ValueError("at least one required check is needed")
    return {
        "required_status_checks": {"strict": True, "contexts": list(checks)},
        "enforce_admins": True,
        "required_pull_request_reviews": {"required_approving_review_count": 0},
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }
