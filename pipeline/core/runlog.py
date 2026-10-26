"""The run log (`runs.csv`): one row per pipeline run, and the numbers the lesson asks for."""

from __future__ import annotations

import csv
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

HEADER = ("run", "commit", "seconds", "result", "variant", "failed_tests", "message")
SUCCESS = "success"
FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class RunRecord:
    """One pipeline run. `failed_tests` are test ids joined by `;`; `message` is the first failure's first line."""

    run: int
    commit: str
    seconds: float
    result: str
    variant: str
    failed_tests: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class Summary:
    """Count, median and slowest duration of a set of runs."""

    variant: str
    runs: int
    median_seconds: float
    slowest_seconds: float


def read(path: Path) -> list[RunRecord]:
    """Read a run log; a missing file is an empty log."""
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return [
            RunRecord(
                run=int(row["run"]),
                commit=row["commit"],
                seconds=float(row["seconds"]),
                result=row["result"],
                variant=row.get("variant", ""),
                failed_tests=tuple(filter(None, row.get("failed_tests", "").split(";"))),
                message=row.get("message", ""),
            )
            for row in csv.DictReader(handle)
        ]


def append(path: Path, record: RunRecord) -> None:
    """Append one row, writing the header first when the file is new."""
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(HEADER)
        writer.writerow(
            [
                record.run,
                record.commit,
                f"{record.seconds:.1f}",
                record.result,
                record.variant,
                ";".join(record.failed_tests),
                record.message.replace("\n", " ")[:160],
            ]
        )


def next_run_number(records: Sequence[RunRecord]) -> int:
    """The number for the next row: one more than the highest so far."""
    return max((record.run for record in records), default=0) + 1


def summarize(records: Iterable[RunRecord], variant: str) -> Summary | None:
    """Median and slowest duration of the runs of one variant; None when there are none."""
    seconds = [record.seconds for record in records if record.variant == variant]
    if not seconds:
        return None
    return Summary(variant, len(seconds), statistics.median(seconds), max(seconds))


def format_duration(seconds: float) -> str:
    """`1m 05s` for 65 seconds, `42s` under a minute."""
    whole = round(seconds)
    minutes, rest = divmod(whole, 60)
    return f"{minutes}m {rest:02d}s" if minutes else f"{rest}s"


def format_comparison(before: Summary | None, after: Summary | None) -> str:
    """The before-and-after table of step 3, and whether the median is under half the starting time."""
    lines = [f"{'version':<24}{'runs':<7}{'median':<10}slowest"]
    for label, summary in (("1. sequential", before), ("3. cached and parallel", after)):
        if summary is not None:
            lines.append(
                f"{label:<24}{summary.runs:<7}{format_duration(summary.median_seconds):<10}"
                f"{format_duration(summary.slowest_seconds)}"
            )
    if before is not None and after is not None:
        verdict = "yes" if after.median_seconds < before.median_seconds / 2 else "no"
        lines.append(f"median under half of the starting time: {verdict}")
    return "\n".join(lines)
