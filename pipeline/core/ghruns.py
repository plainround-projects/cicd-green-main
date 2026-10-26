"""Turn `gh run list --json databaseId,headSha,conclusion,createdAt,updatedAt` into run-log rows."""

from __future__ import annotations

import json
from datetime import datetime

from pipeline.core.runlog import FAILURE, SUCCESS, RunRecord


def parse_gh_runs(json_text: str, variant: str = "github") -> list[RunRecord]:
    """Completed runs only, oldest first. A conclusion of `success` is a pass; every other conclusion is a failure."""
    rows = json.loads(json_text)
    records = []
    for row in sorted(rows, key=lambda item: item["createdAt"]):
        if not row.get("conclusion"):
            continue  # still running
        started = datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(row["updatedAt"].replace("Z", "+00:00"))
        records.append(
            RunRecord(
                run=int(row["databaseId"]),
                commit=str(row["headSha"])[:7],
                seconds=(ended - started).total_seconds(),
                result=SUCCESS if row["conclusion"] == "success" else FAILURE,
                variant=variant,
            )
        )
    return records
