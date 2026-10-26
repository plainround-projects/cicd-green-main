"""Lint a GitHub Actions workflow for the mistakes the lesson lists, so they fail a test and not a merge."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

_PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_LATEST = re.compile(r"(:latest\b|@(main|master|latest)\b)")


@dataclass(frozen=True, slots=True)
class Finding:
    """One problem: a stable code and what to change."""

    code: str
    message: str


def load(text: str) -> Mapping[str, Any]:
    """Parse a workflow. PyYAML reads the key `on` as the boolean True; put it back under "on"."""
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("a workflow must be a mapping")
    if True in document:
        document["on"] = document.pop(True)
    return document


def job_names(document: Mapping[str, Any]) -> dict[str, str]:
    """Map job id to the check name GitHub reports: the job's `name`, or its id when it has none."""
    return {job_id: str(job.get("name", job_id)) for job_id, job in document.get("jobs", {}).items()}


def lint(document: Mapping[str, Any], required_checks: Sequence[str], quarantine_jobs: Sequence[str]) -> list[Finding]:
    """Check one workflow. An empty list means it passes every rule.

    The trigger rules (WF002, WF003) apply only to a workflow that carries required checks: pass `required_checks=()`
    for any other workflow, such as a scheduled audit.
    """
    findings: list[Finding] = []
    names = set(job_names(document).values())
    for check in required_checks:
        if check not in names:
            findings.append(
                Finding("WF001", f"required check {check!r} is not the name of any job: it would never report")
            )
    triggers = document.get("on", {})
    for event in ("push", "pull_request") if required_checks else ():
        if event not in (triggers if isinstance(triggers, dict | list) else []):
            findings.append(Finding("WF002", f"the workflow does not run on {event}"))
        trigger = triggers.get(event) if isinstance(triggers, dict) else None
        if isinstance(trigger, dict) and ({"paths", "paths-ignore"} & trigger.keys()):
            findings.append(
                Finding("WF003", f"{event} has a paths filter: a skipped workflow never reports its required checks")
            )
    for job_id, job in document.get("jobs", {}).items():
        if job.get("continue-on-error") and job_id not in quarantine_jobs:
            findings.append(Finding("WF004", f"job {job_id!r} has continue-on-error: only the quarantine job may"))
        for step in job.get("steps", []):
            used = step.get("uses")
            if used and not used.startswith("./") and not _PINNED.match(used):
                findings.append(Finding("WF005", f"{used!r} is not pinned to a full commit SHA"))
            if _LATEST.search(str(step.get("uses", "")) + str(step.get("run", ""))):
                findings.append(Finding("WF006", f"job {job_id!r} uses a moving name (latest, main or master)"))
        if _LATEST.search(str(job.get("services", ""))):
            findings.append(Finding("WF006", f"job {job_id!r} uses a service image with a moving tag"))
    permissions = document.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        findings.append(Finding("WF007", "the workflow must set top-level permissions with contents: read"))
    return findings


def lint_composite(document: Mapping[str, Any]) -> list[Finding]:
    """A composite action's steps get the same pinning rules as workflow steps."""
    findings: list[Finding] = []
    for step in document.get("runs", {}).get("steps", []):
        used = step.get("uses")
        if used and not used.startswith("./") and not _PINNED.match(used):
            findings.append(Finding("WF005", f"{used!r} is not pinned to a full commit SHA"))
    return findings
