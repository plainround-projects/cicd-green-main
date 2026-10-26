"""Find a flaky test in the run log instead of rerunning until green."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pipeline.core.runlog import FAILURE, SUCCESS, RunRecord


@dataclass(frozen=True, slots=True)
class FailedTest:
    """A failed test case from a JUnit report."""

    test_id: str
    message: str


@dataclass(frozen=True, slots=True)
class FlakeReport:
    """What the log says about one failing test."""

    test_id: str
    failures: int
    runs: int
    messages: tuple[tuple[str, int], ...]

    @property
    def rate(self) -> float:
        """Failures divided by runs."""
        return self.failures / self.runs if self.runs else 0.0


def flaky_commits(records: Iterable[RunRecord]) -> list[str]:
    """Commits that have at least one passing and one failing run: the same code gave both answers."""
    outcomes: dict[str, set[str]] = defaultdict(set)
    for record in records:
        outcomes[record.commit].add(record.result)
    return sorted(commit for commit, seen in outcomes.items() if {SUCCESS, FAILURE} <= seen)


def flake_reports(records: Sequence[RunRecord]) -> list[FlakeReport]:
    """For every test that failed in some run, its failure rate and the messages it failed with."""
    failing_ids = {test for record in records for test in record.failed_tests}
    reports = []
    for test_id in sorted(failing_ids):
        failed = [record for record in records if test_id in record.failed_tests]
        messages = Counter(record.message for record in failed if record.message)
        reports.append(FlakeReport(test_id, len(failed), len(records), tuple(messages.most_common())))
    return reports


def parse_junit_failures(xml_text: str) -> list[FailedTest]:
    """Failed or errored test cases of a JUnit XML report (pytest's `--junitxml`)."""
    root = ET.fromstring(xml_text)  # noqa: S314 - our own pytest report, not untrusted input
    failures = []
    for case in root.iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        if problem is not None:
            test_id = f"{case.get('classname', '').replace('.', '/')}.py::{case.get('name', '')}"
            first_line = (problem.get("message") or "").splitlines()[0] if problem.get("message") else ""
            failures.append(FailedTest(test_id, first_line))
    return failures


def format_report(records: Sequence[RunRecord]) -> str:
    """The text `make flaky-report` prints: the commits that disagree with themselves, then each test's failure rate."""
    commits = flaky_commits(records)
    lines = ["commits with both a pass and a fail:", *(f"  {commit}" for commit in commits or ["none"])]
    for report in flake_reports(records):
        lines.append(f"failure rate of {report.test_id}: {report.failures} of {report.runs} runs ({report.rate:.0%})")
        lines.extend(f"  failed {count} times with: {message}" for message, count in report.messages)
    return "\n".join(lines)
