# CSV (the run log, `runs.csv`)

## What it is

CSV ("comma-separated values") is a plain text table: one row per line, columns separated by commas, the first line naming the columns. Spreadsheets and Python's `csv` module read it. Text containing a comma or a quote is wrapped in quotes.

## Why this repository uses it

The lesson asks for numbers: how long a run takes, and whether the same commit sometimes passes and sometimes fails. Those need a **log of runs**. A CSV file is the simplest log that a person can open in a spreadsheet and a program can read.

## Where it appears

| Path | Use |
|---|---|
| `runs.csv` (git-ignored) | One row per local pipeline run. |
| `docs/measurements/bench.csv`, `flake-hunt.csv` | The measured results kept in the repository as evidence. |
| `pipeline/core/runlog.py` | `read`, `append`, `summarize`, `format_comparison`. |
| `pipeline/core/flaky.py` | Turns rows into failure rates. |

## How it works underneath

`csv.writer` joins values with commas and quotes where needed. `csv.DictReader` reads the header line and gives each row as a dictionary. Everything read is text, so numbers must be converted. Opening the file with `newline=""` stops Python from altering line endings that the csv module handles itself.

## Walkthrough of this repository's use

```python
HEADER = ("run", "commit", "seconds", "result", "variant", "failed_tests", "message")
```
Seven columns. `variant` is `sequential`, `parallel` or `flake-hunt`. `failed_tests` joins several test ids with `;` so they fit in one cell.

```python
def append(path: Path, record: RunRecord) -> None:
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(HEADER)
        writer.writerow([record.run, record.commit, f"{record.seconds:.1f}", record.result, record.variant,
                         ";".join(record.failed_tests), record.message.replace("\n", " ")[:160]])
```
Open in append mode (`"a"`). Write the header only if the file is new or empty. Seconds are rounded to one decimal. The message has line breaks removed and is cut to 160 characters.

```python
with path.open(newline="") as handle:
    return [RunRecord(run=int(row["run"]), ..., seconds=float(row["seconds"]), ...,
                      failed_tests=tuple(filter(None, row.get("failed_tests", "").split(";")))) for row in csv.DictReader(handle)]
```
`DictReader` gives each row as a dict. `int(...)` and `float(...)` convert the text. `.split(";")` then `filter(None, ...)` drops empty pieces, so an empty cell becomes an empty tuple. A missing file reads as an empty log.

```python
seconds = [record.seconds for record in records if record.variant == variant]
return Summary(variant, len(seconds), statistics.median(seconds), max(seconds))
```
The **median** is the middle value after sorting, which a single slow run barely moves. `format_comparison` prints the before and after table and answers: is the new median under half of the old?

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
