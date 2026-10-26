import json

from pipeline.core import flaky, ghruns, runlog
from pipeline.core.runlog import FAILURE, SUCCESS, RunRecord

JUNIT = """<testsuites><testsuite>
<testcase classname="tests.unit.domain.test_jobs_timing" name="test_job_finishes_in_time">
<failure message="assert False&#10; +  where False = &lt;Job&gt;.done">trace</failure></testcase>
<testcase classname="tests.unit.domain.test_cache" name="test_ok"/>
<testcase classname="tests.unit.x" name="test_broken"><error message="ImportError: nope"/></testcase>
</testsuite></testsuites>"""


def record(
    run: int, commit: str, result: str, variant: str = "v", tests: tuple[str, ...] = (), seconds: float = 10
) -> RunRecord:
    return RunRecord(run, commit, seconds, result, variant, tests, "assert False" if tests else "")


def test_a_log_round_trips_through_the_csv_file(tmp_path):
    path = tmp_path / "runs.csv"
    first = record(1, "3fa91bc", FAILURE, tests=("tests/a.py::t1", "tests/a.py::t2"))
    runlog.append(path, first)
    runlog.append(path, record(2, "b84d20e", SUCCESS))
    assert runlog.read(path)[0] == RunRecord(1, "3fa91bc", 10.0, FAILURE, "v", first.failed_tests, "assert False")
    assert path.read_text().splitlines()[0] == "run,commit,seconds,result,variant,failed_tests,message"


def test_a_missing_log_is_empty_and_numbering_starts_at_one(tmp_path):
    records = runlog.read(tmp_path / "none.csv")
    assert records == []
    assert runlog.next_run_number(records) == 1


def test_the_next_run_number_follows_the_highest(tmp_path):
    assert runlog.next_run_number([record(4, "a", SUCCESS), record(2, "b", SUCCESS)]) == 5


def test_a_message_is_kept_on_one_line_and_truncated(tmp_path):
    path = tmp_path / "runs.csv"
    runlog.append(path, RunRecord(1, "a", 1.0, FAILURE, "v", ("t",), "line one\nline two" + "x" * 300))
    message = runlog.read(path)[0].message
    assert "\n" not in message
    assert len(message) == 160


def test_the_summary_uses_the_median_not_the_mean():
    records = [record(index, "c", SUCCESS, seconds=seconds) for index, seconds in enumerate([100, 110, 400], 1)]
    summary = runlog.summarize(records, "v")
    assert summary is not None
    assert (summary.runs, summary.median_seconds, summary.slowest_seconds) == (3, 110, 400)


def test_a_variant_with_no_runs_has_no_summary():
    assert runlog.summarize([record(1, "a", SUCCESS)], "other") is None


def test_durations_read_as_minutes_and_seconds():
    assert runlog.format_duration(65) == "1m 05s"
    assert runlog.format_duration(42.4) == "42s"


def test_the_comparison_says_whether_the_median_is_under_half_the_start():
    before = runlog.summarize([record(1, "a", SUCCESS, "sequential", seconds=100)], "sequential")
    after = runlog.summarize([record(2, "a", SUCCESS, "parallel", seconds=40)], "parallel")
    table = runlog.format_comparison(before, after)
    assert "1. sequential" in table
    assert "3. cached and parallel" in table
    assert table.endswith("median under half of the starting time: yes")
    slow = runlog.summarize([record(3, "a", SUCCESS, "parallel", seconds=60)], "parallel")
    assert runlog.format_comparison(before, slow).endswith("no")


def test_flaky_commits_are_those_that_both_passed_and_failed():
    records = [
        record(1, "3fa91bc", FAILURE),
        record(2, "3fa91bc", SUCCESS),
        record(3, "aaaaaaa", SUCCESS),
        record(4, "bbbbbbb", FAILURE),
        record(5, "b84d20e", SUCCESS),
        record(6, "b84d20e", FAILURE),
    ]
    assert flaky.flaky_commits(records) == ["3fa91bc", "b84d20e"]


def test_the_failure_rate_and_messages_of_a_test():
    test = ("tests/unit/domain/test_jobs_timing.py::test_job_finishes_in_time",)
    records = [
        record(index, "c", FAILURE if index % 5 == 0 else SUCCESS, tests=test if index % 5 == 0 else ())
        for index in range(1, 11)
    ]
    (report,) = flaky.flake_reports(records)
    assert (report.failures, report.runs, report.rate) == (2, 10, 0.2)
    assert report.messages == (("assert False", 2),)


def test_the_report_text_names_commits_and_rates():
    test = ("t.py::flaky",)
    text = flaky.format_report([record(1, "3fa91bc", FAILURE, tests=test), record(2, "3fa91bc", SUCCESS)])
    assert "3fa91bc" in text
    assert "failure rate of t.py::flaky: 1 of 2 runs (50%)" in text
    assert "failed 1 times with: assert False" in text


def test_the_report_says_none_when_no_commit_disagrees_with_itself():
    assert "  none" in flaky.format_report([record(1, "a", SUCCESS)])


def test_junit_failures_and_errors_are_listed_with_their_first_message_line():
    failures = flaky.parse_junit_failures(JUNIT)
    assert [failure.test_id for failure in failures] == [
        "tests/unit/domain/test_jobs_timing.py::test_job_finishes_in_time",
        "tests/unit/x.py::test_broken",
    ]
    assert failures[0].message == "assert False"


def test_github_runs_become_log_rows_oldest_first_and_unfinished_runs_are_skipped():
    runs = [
        {
            "databaseId": 2,
            "headSha": "b84d20e" + "0" * 33,
            "conclusion": "failure",
            "createdAt": "2026-09-02T10:00:00Z",
            "updatedAt": "2026-09-02T10:03:30Z",
        },
        {
            "databaseId": 1,
            "headSha": "3fa91bc" + "0" * 33,
            "conclusion": "success",
            "createdAt": "2026-09-01T10:00:00Z",
            "updatedAt": "2026-09-01T10:03:05Z",
        },
        {
            "databaseId": 3,
            "headSha": "c" * 40,
            "conclusion": "",
            "createdAt": "2026-09-03T10:00:00Z",
            "updatedAt": "2026-09-03T10:00:10Z",
        },
    ]
    rows = ghruns.parse_gh_runs(json.dumps(runs))
    assert [(row.run, row.commit, row.seconds, row.result) for row in rows] == [
        (1, "3fa91bc", 185.0, SUCCESS),
        (2, "b84d20e", 210.0, FAILURE),
    ]
