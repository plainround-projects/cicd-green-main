# JUnit XML test reports

## What it is

When a test run ends you usually want more than "it failed": you want a list of every test with its result, in a form a program can read. **JUnit XML** is a de-facto standard format for that, born in the Java world and now understood by most test and CI tools. **XML** is a text format built from nested **tags**: `<name attribute="value">contents</name>`. A tag can be self-closing, `<testcase name="x"/>`.

A JUnit report has a root `<testsuites>`, containing `<testsuite>` elements, containing one `<testcase classname="..." name="...">` per test. A test that failed has a child `<failure message="...">`; a test that crashed unexpectedly has a child `<error message="...">`. pytest writes such a file when you add `--junitxml=PATH`.

Python reads XML with the standard library module `xml.etree.ElementTree`. `fromstring(text)` parses text into a tree of elements; `element.find("tag")` returns the first child with that tag (or `None`); `root.iter("testcase")` walks every element of that name at any depth; `element.get("name")` reads an attribute.

## Why this repository uses it

The flaky-test step needs to know *which test* failed in each run. "The run was red" is not enough to find a test that fails one time in five. So after every local run the pipeline reads the JUnit reports, extracts the failing test ids and the first line of each message, and stores them in `runs.csv` ([csv.md](csv.md)). Counting those rows is how the flaky test is found.

## Where it appears

| Path | Use |
|---|---|
| `Makefile` | `--junitxml=reports/unit.xml` (in `test` and `test-domain`), `reports/integration.xml`, `reports/quarantine.xml`. |
| `.github/workflows/ci.yml` | Uploads the `reports/` folder as an artifact after each job. |
| `pipeline/core/flaky.py` | `parse_junit_failures`. |
| `pipeline/adapters/local_runner.py` | `_failures` reads `reports/unit.xml` and `reports/integration.xml`. |
| `tests/pipeline/test_runlog_and_flaky.py` | A sample report as test data. |

## How it works underneath

An XML parser reads the characters, checks that the tags are properly nested, and builds a tree. Special characters inside attribute values are written as **entities**: `&lt;` for `<`, `&gt;` for `>`, `&#10;` for a newline. The parser turns them back. A line break inside an attribute value is normalised to a space by the XML rules, so a long failure message arrives on one line.

## Walkthrough of this repository's use

A shortened sample, as used in the tests:

```python
JUNIT = """<testsuites><testsuite>
<testcase classname="tests.unit.domain.test_jobs_timing" name="test_job_finishes_in_time">
<failure message="assert False&#10; +  where False = &lt;Job&gt;.done">trace</failure></testcase>
<testcase classname="tests.unit.domain.test_cache" name="test_ok"/>
<testcase classname="tests.unit.x" name="test_broken"><error message="ImportError: nope"/></testcase>
</testsuite></testsuites>"""
```

Three test cases: the first has a `<failure>` with a multi-line message, the second passed (no child), the third has an `<error>`.

```python
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
```

- **Line 57**: `root = ET.fromstring(xml_text)` parses the report. The `# noqa: S314` comment silences a security warning about parsing XML from strangers; it is justified because this file was written by our own test run.
- **Line 58**: `failures = []` collects the results. **Line 59**: `for case in root.iter("testcase"):` visits every test case.
- **Line 60**: `problem = case.find("failure") if case.find("failure") is not None else case.find("error")`: the `<failure>` child if there is one, otherwise the `<error>` child, otherwise `None`.
- **Line 61**: `if problem is not None:` only failed or errored cases continue.
- **Line 62**: builds the test id the way pytest prints it: `case.get('classname', '')` is a dotted path like `tests.unit.domain.test_jobs_timing`; `.replace('.', '/')` turns it into a folder path; adding `.py::` and the case name gives `tests/unit/domain/test_jobs_timing.py::test_job_finishes_in_time`.
- **Line 63**: `first_line = (problem.get("message") or "").splitlines()[0] if problem.get("message") else ""` takes the first line of the message, or an empty string if there is none.
- **Line 64** appends `FailedTest(test_id, first_line)`; **line 65** returns the list.

### Where the reports are read

```python
def _failures(root: Path) -> list[FailedTest]:
    """Failed tests of the unit and integration reports, so a failed run says where it failed."""
    reports = [root / "reports" / "unit.xml", root / "reports" / "integration.xml"]
    return [failure for report in reports if report.exists() for failure in parse_junit_failures(report.read_text())]
```

`_failures` looks for `reports/unit.xml` and `reports/integration.xml`; for each that exists it parses it and flattens the results into one list. `run_pipeline` and `hunt` store the test ids (joined with `;`) and the first message in the `failed_tests` and `message` columns of the run log. Then `flaky_commits` and `flake_reports` count them ([python.md](python.md)).

### In CI

The `unit`, `integration` and `quarantine` jobs upload `reports/` with `if: always()`, so the reports exist even when the tests fail ([github-actions.md](github-actions.md)).

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
