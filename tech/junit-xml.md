# JUnit XML test reports

## What it is

JUnit XML is a report format born in the Java world and now understood by most CI systems and test tools. It is an XML file with a `<testsuite>` containing one `<testcase>` per test. A failed test has a child `<failure message="...">`; a test that crashed has `<error>`. pytest writes it when you pass `--junitxml=path`.

## Why this repository uses it

The flaky-test step needs to know **which test** failed in each run, not just "red". The pipeline reads the JUnit report after every run and stores the failing test ids and the first line of the message in `runs.csv` ([csv.md](csv.md)).

## Where it appears

| Path | Use |
|---|---|
| `Makefile` | `--junitxml=reports/unit.xml` (also `integration.xml`, `quarantine.xml`). |
| `.github/workflows/ci.yml` | Uploads `reports/` as artifacts. |
| `pipeline/core/flaky.py` | `parse_junit_failures`. |
| `pipeline/adapters/local_runner.py` | Reads the reports of the job that failed. |

## How it works underneath

XML is nested tags: `<tag attribute="value">text</tag>`. A parser builds a tree. `xml.etree.ElementTree` is Python's built-in parser. A pytest report looks like this (shortened):

```xml
<testsuites><testsuite name="pytest" tests="2" failures="1">
  <testcase classname="tests.unit.domain.test_jobs_timing" name="test_job_finishes_in_time">
    <failure message="assert False">...traceback...</failure>
  </testcase>
</testsuite></testsuites>
```

## Walkthrough of this repository's use

```python
root = ET.fromstring(xml_text)  # noqa: S314 - our own pytest report, not untrusted input
for case in root.iter("testcase"):
    problem = case.find("failure") if case.find("failure") is not None else case.find("error")
    if problem is not None:
        test_id = f"{case.get('classname', '').replace('.', '/')}.py::{case.get('name', '')}"
        first_line = (problem.get("message") or "").splitlines()[0] if problem.get("message") else ""
        failures.append(FailedTest(test_id, first_line))
```
- `fromstring` parses the text. `root.iter("testcase")` walks every test case anywhere in the tree.
- `find("failure")` returns the child tag or `None`. A failed assertion is a `failure`; an exception outside an assertion is an `error`. Both count.
- The test id is rebuilt in pytest's own style: the class name `tests.unit.domain.test_jobs_timing` becomes `tests/unit/domain/test_jobs_timing.py`, then `::` and the test name.
- Only the first line of the message is kept, so the log stays short.
- The `# noqa: S314` comment explains why parsing XML here is acceptable: ruff warns that XML from untrusted sources can be malicious, but this file was written by our own pytest.

`flake_reports` then counts, for each test id, how many runs it failed in, and `flaky_commits` lists commits that had **both** a pass and a fail.

## Try it yourself

```bash
make test
head -c 600 reports/unit.xml
```
Look for `<testsuite` and the counts `tests=`, `failures=`.

```bash
.venv/bin/python -c "
from pipeline.core.flaky import parse_junit_failures
xml = '<testsuite><testcase classname=\"a.b\" name=\"t\"><failure message=\"boom\nmore\"/></testcase></testsuite>'
print(parse_junit_failures(xml))
"
```
Expect `[FailedTest(test_id='a/b.py::t', message='boom more')]`. (An XML parser turns the line break inside an attribute into a space, so the whole text arrives on one line; real pytest messages put the summary in the first line of the `<failure>` element text as well.)

```bash
make flaky-hunt HUNT_RUNS=10
```
Fills `runs.csv` and prints the failure rate of the quarantined test.

## Mistakes people make

- Parsing untrusted XML with the standard parser (it has known denial-of-service tricks). Here only our own report is read.
- Matching on test **names** only, so two tests with the same name in different files merge.
- Keeping the full traceback in the log.

## Check yourself

1. What does `--junitxml` do? *Makes pytest write its results as JUnit XML.*
2. What is the difference between `failure` and `error`? *A failed assertion versus an unexpected exception.*
3. Why is the first line of the message enough? *The log stays short and still says why.*
4. What does `flaky_commits` look for? *Commits with at least one passing and one failing run.*
5. Why is the S314 warning silenced here? *The XML is produced by our own pytest, not by an outsider.*

## Further reading

- `xml.etree.ElementTree`: https://docs.python.org/3.12/library/xml.etree.elementtree.html
- pytest `--junitxml`: https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files
