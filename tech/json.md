# JSON

## What it is

**JSON** ("JavaScript Object Notation") is a text format for data, used by almost every web service and many tools. It has:

- **objects**: `{"name": "value", "count": 3}`, a set of key/value pairs where keys are text in double quotes;
- **arrays**: `[1, 2, 3]`, ordered lists;
- **strings** in double quotes, **numbers**, `true`, `false` and `null`.

Python's `json` module converts between JSON text and Python values: `json.loads(text)` turns text into dictionaries, lists, strings, numbers, booleans and `None`; `json.dumps(value)` turns them back into text (`indent=2` makes it readable). JSON has no dates and no tuples: a `datetime` must be converted to text first.

## Why this repository uses it

Two outside tools exchange JSON with the pipeline. GitHub's API takes the branch-protection settings as a JSON body, and `gh run list --json ...` prints the history of workflow runs as JSON. The pipeline builds the first and reads the second. The logger also borrows `json.dumps` to quote text safely.

## Where it appears

| Path | Use |
|---|---|
| `pipeline/core/protection.py` | Builds the dictionary that becomes the protection body. |
| `pipeline/cli.py` | `json.dumps(payload, indent=2)` prints it. |
| `pipeline/adapters/github.py` | Sends `json.dumps(payload)` to `gh api` on standard input; asks `gh run list` for `--json` fields. |
| `pipeline/core/ghruns.py` | `json.loads` of the run history. |
| `src/small_service/infrastructure/logging.py` | `json.dumps(text)` to quote a log value. |
| `tests/pipeline/test_runlog_and_flaky.py`, `test_builder_and_runner.py` | JSON as test data. |

## How it works underneath

`json.dumps({"ok": True, "none": None})` produces `{"ok": true, "none": null}`. Python's `True` becomes `true`, `None` becomes `null`. A JSON object's keys are always text. Parsing fails with an error if the text is not valid JSON (single quotes, a trailing comma and comments are not allowed).

## Walkthrough of this repository's use

### The branch-protection body (`pipeline/core/protection.py`)

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- A Python dictionary with exactly the shape GitHub's API expects. `required_status_checks` is itself an object with `strict` and `contexts`. `strict: True` means the branch must be up to date with `main` before merging. `contexts` is the list of job names that must pass (`list(checks)` turns the tuple into a list because JSON has arrays, not tuples).
- `enforce_admins: True` applies the rules to repository owners too. `required_pull_request_reviews: {"required_approving_review_count": 0}` requires a pull request without requiring an approval (a one-person project). `restrictions: None` becomes JSON `null`: no limit on who may push beyond these rules. `allow_force_pushes: False` and `allow_deletions: False` forbid rewriting or removing `main`.
- If the list of checks is empty it raises `ValueError("at least one required check is needed")`.

`make protection` prints the dictionary with `print(json.dumps(payload, indent=2))`. `make protection APPLY=owner/repo` calls `github.apply_branch_protection`:

<!-- fmt:off -->
```python
def apply_branch_protection(repo: str, payload: dict[str, Any]) -> None:
    """`PUT /repos/{repo}/branches/main/protection` with `payload`."""
    subprocess.run(  # noqa: S603
        ["gh", "api", "-X", "PUT", f"repos/{repo}/branches/main/protection", "--input", "-"],  # noqa: S607
        input=json.dumps(payload),
        text=True,
        check=True,
    )
```
<!-- fmt:on -->

runs `gh api -X PUT repos/<repo>/branches/main/protection --input -`: `-X PUT` is the HTTP method that replaces the settings, and `--input -` reads the request body from standard input, where `input=json.dumps(payload)` supplies it ([gh-cli.md](gh-cli.md)).

### The run history (`pipeline/core/ghruns.py`)

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Line 13**: `rows = json.loads(json_text)` gives a list of dictionaries, one per run, with keys `databaseId`, `headSha`, `conclusion`, `createdAt`, `updatedAt` (the five fields `list_runs` asked for).
- **Lines 15 to 17**: sort by `createdAt`; skip a run whose `conclusion` is empty (still running).
- **Lines 18 and 19**: the two times are text like `2026-09-01T10:00:00Z`; `datetime.fromisoformat(... .replace("Z", "+00:00"))` parses them (`Z` means UTC).
- **Lines 20 to 28**: build a `RunRecord`: `run=int(row["databaseId"])`, `commit=str(row["headSha"])[:7]`, `seconds=(ended - started).total_seconds()` (subtracting two datetimes gives a `timedelta`), `result=SUCCESS if row["conclusion"] == "success" else FAILURE`.

### Quoting log values (`logging.py`)

<!-- fmt:off -->
```python
def _quote(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char in text for char in ' ="\n') else text
```
<!-- fmt:on -->

`json.dumps(text)` returns the text in double quotes with special characters escaped (`\n` for a newline, `\"` for a quote). `_quote` uses it only when a value is empty or contains a space, `=`, `"` or newline, so `msg="job done"` is unambiguous while `job_key=nightly` stays bare.

## Try it yourself

```bash
make protection | head -12
```
Prints the JSON.

```bash
.venv/bin/python -c "import json; print(json.dumps({'ok': True, 'none': None, 'msg': 'two words'}))"
```
Expect `{"ok": true, "none": null, "msg": "two words"}`.

```bash
.venv/bin/python -c "import json; print(json.loads('{\"a\": [1, 2, {\"b\": null}]}'))"
```
Expect `{'a': [1, 2, {'b': None}]}`.

## Mistakes people make

- Trying to dump a `datetime` or a `set`.
- Using single quotes (not valid JSON).
- Trailing commas (not allowed).
- Assuming big numbers or dates survive without conversion.

## Check yourself

1. What does Python `None` become in JSON? *`null`.*
2. Which function turns text into Python objects? *`json.loads`.*
3. Why does the logger use `json.dumps` on strings? *To quote and escape values that contain spaces or special characters.*
4. How does the pipeline find runs still in progress? *They have no `conclusion`.*
5. Can JSON hold a date? *Only as text; convert it yourself.*

## Further reading

- JSON specification: https://www.json.org/ and RFC 8259
- `json` module: https://docs.python.org/3.12/library/json.html
