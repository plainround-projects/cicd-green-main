# YAML

## What it is

YAML is a text format for structured data. It has **mappings** (`key: value`), **lists** (lines that start with `- `) and **scalars** (text, numbers, true/false). **Indentation with spaces** shows nesting. (Tabs are not allowed.) GitHub Actions workflows, Docker Compose files and the Dependabot configuration are all YAML. The library PyYAML 6.0.3 reads it in Python.

## Why this repository uses it

Three tools the pipeline depends on read YAML: GitHub Actions, Docker Compose and Dependabot. The repository also **parses its own workflow files** with PyYAML and checks them against rules (`pipeline/core/workflow.py`).

## Where it appears

| Path | Reader |
|---|---|
| `.github/workflows/ci.yml`, `audit.yml` | GitHub Actions; PyYAML in `lint-workflows` |
| `.github/actions/setup/action.yml` | GitHub Actions |
| `.github/dependabot.yml` | Dependabot |
| `docker-compose.yml` | Docker Compose |
| `pipeline/core/workflow.py` | `yaml.safe_load` |

## How it works underneath

A YAML parser turns the text into plain data: dicts, lists, strings, numbers, booleans, null. The meaning of those keys belongs to the tool reading the file.

Rules a beginner needs:
- `key: value` needs a space after the colon.
- `- item` makes a list. A list of mappings looks like `- name: a` then `  uses: b`.
- Quotes matter. `"5432"` is text; `5432` is a number. `"3.12"` is text; `3.12` is a number that would lose a trailing zero (3.10 becomes 3.1).
- `|` keeps line breaks in a multi-line text. `>` folds lines into one. A trailing `-` (`>-`) removes the final newline.
- `# comment` runs to the end of the line.
- Anchors and types can surprise: `yes`, `no`, `on`, `off` are booleans in YAML 1.1.

## Walkthrough of this repository's use

### The `on:` surprise

```python
def load(text: str) -> Mapping[str, Any]:
    document = yaml.safe_load(text)
    if True in document:
        document["on"] = document.pop(True)
    return document
```
PyYAML follows YAML 1.1, where the bare word `on` means true. So the workflow key `on:` becomes the boolean key `True`. `load` moves it back under the string `"on"` so the rules can look at `document["on"]`. `safe_load` is the safe parser: it builds only plain data and never runs code.

### Folded text in `ci.yml`

```yaml
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U service -d service"
          --health-interval 5s
```
`>-` joins these lines into one string with single spaces and no final newline. Docker receives one long options string.

### Quoted numbers

```yaml
POSTGRES_PORT: "5432"
python-version: "3.12"
```
Quoted, so the value stays text. Environment variables are always text.

### Inline mappings

```yaml
with: { name: wheel, path: dist/ }
```
The compact form of a two-key mapping. (The repository's files mostly use the long form.)

### Compose

`docker-compose.yml` uses mappings (`services:` → `db:` → `image:`) and lists (`ports:` with `- "127.0.0.1:...:5432"`), plus `${VAR:-default}` substitution that Compose, not YAML, performs ([docker-compose.md](docker-compose.md)).

## Try it yourself

```bash
.venv/bin/python -c "import yaml, json; print(json.dumps(yaml.safe_load(open('docker-compose.yml'))['services']['db']['ports']))"
```
Expect `["127.0.0.1:${POSTGRES_PORT:-55471}:5432"]`.

```bash
.venv/bin/python -c "import yaml; d = yaml.safe_load(open('.github/workflows/ci.yml')); print(list(d.keys()))"
```
Expect `['name', True, 'permissions', 'concurrency', 'jobs']`. The `True` is the key `on`.

```bash
.venv/bin/python -c "import yaml; print(yaml.safe_load('v: 3.10'), yaml.safe_load('v: \"3.10\"'))"
```
Expect `{'v': 3.1} {'v': '3.10'}`.

## Mistakes people make

- Tabs for indentation.
- Unquoted version numbers that lose digits.
- Treating `on`, `yes` and `no` as text.
- Mixing up the indentation of list items and their keys.
- Using `yaml.load` on untrusted text instead of `safe_load`.

## Check yourself

1. What shows nesting in YAML? *Indentation with spaces.*
2. Why is the Python version written `"3.12"` in quotes? *Unquoted, it is a number; `3.10` would become `3.1`.*
3. Why does `workflow.py` repair the `on` key? *PyYAML reads `on` as the boolean true.*
4. What does `>-` do? *Folds the lines into one string without a trailing newline.*
5. Why `safe_load`? *It builds only plain data and cannot run code.*

## Further reading

- YAML 1.2 specification: https://yaml.org/spec/1.2.2/
- PyYAML: https://pyyaml.org/wiki/PyYAMLDocumentation (6.0.3)
- GitHub's note on workflow syntax: https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions
