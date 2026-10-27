# JSON

## What it is

JSON is a text format for data made of objects (`{"key": value}`), arrays (`[1, 2]`), strings, numbers, `true`, `false` and `null`. Nearly every web API speaks it. Python's `json` module converts between JSON text and Python dicts, lists, strings, numbers, booleans and `None`.

## Why this repository uses it

Two outside tools exchange JSON with the pipeline: GitHub's API (the branch-protection body) and `gh run list --json` (the run history). JSON is also how the pipeline prints the protection rules.

## Where it appears

| Path | Use |
|---|---|
| `pipeline/core/protection.py` | Builds the dict that becomes the protection body. |
| `pipeline/adapters/github.py` | `json.dumps(payload)` to send, via [gh](gh-cli.md). |
| `pipeline/core/ghruns.py` | `json.loads(json_text)` to read run history. |
| `src/small_service/infrastructure/logging.py` | `json.dumps(text)` to quote a log value that contains spaces or quotes. |

## How it works underneath

`json.loads(text)` parses text into Python objects. `json.dumps(obj)` writes them back. Only these types round-trip: dict (with string keys), list, str, int, float, bool, None. Anything else (like a `datetime`) must be converted first.

## Walkthrough of this repository's use

```python
rows = json.loads(json_text)
for row in sorted(rows, key=lambda item: item["createdAt"]):
    if not row.get("conclusion"):
        continue  # still running
    started = datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
```
`sorted(..., key=...)` orders by creation time (ISO 8601 strings sort correctly as text). A run with no `conclusion` is still going, so it is skipped. `fromisoformat` in Python 3.12 accepts `Z` too, but replacing it with `+00:00` is explicit and works on every version.

```python
def _quote(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char in text for char in ' ="\n') else text
```
The logger uses `json.dumps` for one trick: it puts quotes around a string and escapes the special characters. A value with a space, quote, equals sign or newline becomes `"two words"`; a simple word stays bare. So the line `msg="job finished"` is easy to parse back.

```python
{"required_status_checks": {"strict": True, "contexts": [...]}, "enforce_admins": True, ..., "restrictions": None}
```
Python `True` and `None` become JSON `true` and `null`.

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
