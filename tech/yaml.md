# YAML

## What it is

**YAML** is a text format for writing structured information that people can read comfortably. Many tools are configured with it. This repository's GitHub workflows, Docker Compose file and Dependabot settings are all YAML. In Python the library **PyYAML** (version 6.0.3 here) reads it.

The building blocks:

- A **mapping** is a set of `key: value` pairs. After the colon there must be a space.
- A **list** is a series of lines each starting with `- ` (dash and space). A list of mappings looks like `- name: a` followed by indented `  uses: b`.
- A **scalar** is a single value: text, a number, `true`/`false`, or `null`.
- **Indentation shows nesting**, with spaces. Tabs are not allowed. Lines indented further belong to the line above.
- `#` starts a comment.
- **Quotes** matter: `"5432"` is text, but `5432` is a number. `"3.12"` is text, but `3.12` is a number, and `3.10` would be read as `3.1`, losing the zero. When a value must stay exactly as written, quote it.
- `|` after a key keeps the line breaks of the indented text below it; `>` folds those lines into one line; adding `-` (`|-`, `>-`) removes the final newline.
- In YAML 1.1 (the version PyYAML follows) the plain words `on`, `off`, `yes` and `no` are read as booleans.

A YAML parser turns the text into plain Python data: dictionaries, lists, strings, numbers, booleans. The *meaning* of the keys belongs to whichever tool reads the file.

## Why this repository uses it

Three tools this pipeline depends on read YAML: GitHub Actions, Docker Compose and Dependabot. The repository also **reads its own workflow files with PyYAML** and checks them against rules (`pipeline/core/workflow.py`), so a mistake in the pipeline definition is caught by a test.

## Where it appears

| Path | Reader |
|---|---|
| `.github/workflows/ci.yml`, `audit.yml` | GitHub Actions; PyYAML in `make lint-workflows` ([github-actions.md](github-actions.md)). |
| `.github/actions/setup/action.yml` | GitHub Actions (a composite action). |
| `.github/dependabot.yml` | Dependabot ([dependabot.md](dependabot.md)). |
| `docker-compose.yml` | Docker Compose ([docker-compose.md](docker-compose.md)). |
| `pipeline/core/workflow.py` | `yaml.safe_load`. |
| `tests/pipeline/test_workflow_protection_contract.py` | Workflow text as test data, loaded with `workflow.load`. |

## How it works underneath

PyYAML's `yaml.safe_load(text)` returns the data. The "safe" version builds only plain data and never creates arbitrary Python objects, so loading a file cannot run code. (`yaml.load` without safety can, which is why it is avoided for files you did not write.)

## Walkthrough of this repository's use

Every YAML file's keys are explained where the file is explained: `ci.yml`, `audit.yml` and `action.yml` in [github-actions.md](github-actions.md); `dependabot.yml` in [dependabot.md](dependabot.md); `docker-compose.yml` in [docker-compose.md](docker-compose.md). This note covers the YAML features those files use and the code that reads them.

### The features used

- **Mappings nested by indentation**: `jobs:` then two spaces `lint:` then two more `name: lint`. Reading `ci.yml` from the top, the keys are `name`, `on`, `permissions`, `concurrency` and `jobs`.
- **Lists with dashes**: `steps:` followed by `- uses: ...` items; `needs: [changes, build]` is the same kind of list written on one line in square brackets (called *flow style*); `ports: - 5432:5432` in the service.
- **Quoted numbers and versions**: `POSTGRES_PORT: "5432"` and `python-version: "3.12"` stay text. Environment variables are always text anyway, and `3.12` as a number would be fine but `3.10` would not.
- **A folded string**: in `ci.yml` the service's options:

```yaml
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U service -d service"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
```

  `options: >-` followed by indented lines joins them with single spaces into one line, with no final newline. Docker receives `--health-cmd "pg_isready ..." --health-interval 5s --health-timeout 5s --health-retries 10`.
- **A literal block** `|`: the `run: |` form keeps line breaks; this repository's `ci.yml` uses single-line `run:` values, so it does not need it.
- **Comments** after values: `- uses: actions/checkout@11bd... # v4.2.2`.
- **Empty values** as "all of these": under `on:`, the keys `push:`, `pull_request:` and `merge_group:` have nothing after the colon, which YAML reads as `null`; GitHub treats it as "this event, with no filters".

### The `on:` trap and how the code handles it

<!-- fmt:off -->
```python
def load(text: str) -> Mapping[str, Any]:
    """Parse a workflow. PyYAML reads the key `on` as the boolean True; put it back under "on"."""
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("a workflow must be a mapping")
    if True in document:
        document["on"] = document.pop(True)
    return document
```
<!-- fmt:on -->

- **Line 26**: `yaml.safe_load(text)` parses the workflow into a dictionary.
- **Lines 27 and 28**: if the result is not a dictionary (`isinstance(document, dict)`), the file is not a workflow: raise `ValueError`.
- **Lines 29 and 30**: because PyYAML follows YAML 1.1, the key `on` is read as the boolean `True`. `if True in document:` detects that, and `document["on"] = document.pop(True)` removes the `True` key and re-inserts its value under the text key `"on"`. All the later rules can then look at `document["on"]`.

### Reading the files

`_lint_workflows` in `pipeline/cli.py` reads every `*.yml` under `.github/workflows` and every `action.yml` under `.github/actions/*/`, calls `workflow.load(path.read_text())` and lints the result. The tests feed `workflow.load` small workflow strings built with Python f-strings ([pytest.md](pytest.md)).

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
