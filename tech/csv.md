# CSV (the run log, `runs.csv`)

## What it is

**CSV** stands for "comma-separated values". It is the simplest way to store a table in a text file: one row per line, the cells of a row separated by commas, and the first line holding the column names. A spreadsheet program opens it as a table; so does Python's `csv` module. If a cell contains a comma or a quote, it is wrapped in double quotes (and quotes inside are doubled). Everything in a CSV file is text: a program that wants a number must convert it.

## Why this repository uses it

The lesson asks for evidence: how long a run takes before and after the speed-ups, and whether the same commit sometimes passes and sometimes fails. That needs a **log of runs**, one row for each. A CSV file is the simplest log that both a person (in a spreadsheet) and a program can read, and it can be committed as evidence.

## Where it appears

| Path | Use |
|---|---|
| `runs.csv` (ignored by Git) | The local log; each pipeline run appends one row. |
| `docs/measurements/bench.csv`, `docs/measurements/flake-hunt.csv` | Measured results kept in the repository as evidence. |
| `pipeline/core/runlog.py` | `read`, `append`, `summarize`, `format_comparison`. |
| `pipeline/core/flaky.py` | Turns rows into failure rates. |
| `pipeline/core/ghruns.py` | Turns GitHub's run history into rows. |

## How it works underneath

`csv.writer(handle).writerow([...])` writes one row, quoting where needed. `csv.DictReader(handle)` reads the first line as the header and returns each following row as a dictionary keyed by the column names. Files are opened with `newline=""` so that Python does not change line endings the csv module is already managing. Opening in mode `"a"` appends; mode `"w"` replaces.

## Walkthrough of this repository's use

### The columns

```
run,commit,seconds,result,variant,failed_tests,message
1,af1d6c5,415.9,success,sequential,,
2,af1d6c5,345.9,success,sequential,,
3,af1d6c5,376.8,success,sequential,,
```

`run` is the run number, `commit` the first 7 characters of the commit, `seconds` how long the run took, `result` is `success` or `failure`, `variant` names the kind of run (`sequential`, `parallel`, `flake-hunt`), `failed_tests` the ids of failed tests joined with `;`, and `message` the first line of the first failure. In `runlog.py`:

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

`HEADER` is the tuple of the seven names; `RunRecord` is the matching frozen dataclass ([python.md](python.md)).

### Writing a row

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 60**: `is_new = not path.exists() or path.stat().st_size == 0` is true if the file is missing or empty; then **lines 63 and 64** write the header first.
- **Line 61**: `with path.open("a", newline="") as handle:` opens for appending. **Line 62**: `csv.writer(handle)`.
- **Lines 65 to 75** write the row: run number, commit, the seconds formatted with one decimal (`f"{record.seconds:.1f}"`), result, variant, the failed test ids joined by `;`, and the message with newlines replaced by spaces and cut to 160 characters (`[:160]`).

### Reading the log

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

`read` returns an empty list for a missing file. `csv.DictReader` gives each row as a dictionary. The values are converted: `int(row["run"])`, `float(row["seconds"])`. `row.get("variant", "")` tolerates a missing column. `tuple(filter(None, row.get("failed_tests", "").split(";")))` splits the failed-tests cell at semicolons and removes empty pieces, so an empty cell becomes an empty tuple.

### Summarising it

<!-- fmt:off -->
```python

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
```
<!-- fmt:on -->

- `next_run_number`: highest number plus one (`max(..., default=0)`).
- `summarize`: the durations of one variant, then the count, the **median** and the slowest. The median is the middle value after sorting; one very slow run barely moves it, which is why it is used instead of the average.
- `format_duration`: `divmod(whole, 60)` gives minutes and seconds; `f"{rest:02d}"` pads seconds to two digits.
- `format_comparison`: prints the before-and-after table and whether the new median is under half of the old.

### The evidence files

`docs/measurements/bench.csv` holds the five sequential and five parallel runs; its medians are 6 minutes 41 seconds against 1 minute 55 seconds. `flake-hunt.csv` holds the 40 repeated runs of the domain tests used to find the flaky test; its 3 rows where `result` is `failure`, with `failed_tests` naming `test_job_finishes_in_time`, are the evidence (3 of 40 runs, on one commit).

## Try it yourself

```bash
head -4 docs/measurements/bench.csv
```
Expect the header and rows with `sequential` times of several hundred seconds.

```bash
.venv/bin/python -c "
from pathlib import Path
from pipeline.core import runlog
records = runlog.read(Path('docs/measurements/bench.csv'))
print(runlog.format_comparison(runlog.summarize(records, 'sequential'), runlog.summarize(records, 'parallel')))
"
```
Prints the before and after table with medians.

```bash
make flaky-report
```
Reads `runs.csv` (empty until you run `make run` or `make flaky-hunt`).

## Mistakes people make

- Forgetting `newline=""` and getting blank lines on Windows.
- Splitting lines on commas by hand instead of using the `csv` module (breaks on quoted commas).
- Using the average of times, which one slow run distorts.
- Reading numbers as text.

## Check yourself

1. What does `DictReader` return per row? *A dictionary keyed by the header names.*
2. Why `;` inside the `failed_tests` cell? *To store several ids in one column without extra commas.*
3. Why the median? *A single outlier barely moves it.*
4. Why check `st_size == 0` before writing the header? *An empty file needs the header too.*
5. Why is `runs.csv` in `.gitignore`? *It is a local measurement log, not source.*

## Further reading

- `csv` module: https://docs.python.org/3.12/library/csv.html
- `statistics.median`: https://docs.python.org/3.12/library/statistics.html#statistics.median
