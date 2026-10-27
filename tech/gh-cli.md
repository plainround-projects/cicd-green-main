# GitHub CLI (`gh`)

## What it is

GitHub has a website, but it also has an **API**: a way for programs to ask GitHub for things and to change things by sending web requests. **`gh`** is GitHub's official command-line program, a convenient way to use that API from a terminal or a script. You sign in once with `gh auth login` (or, in automation, supply a token in the environment variable `GH_TOKEN`). Then `gh run list` lists workflow runs, `gh pr create` opens a pull request, and `gh api -X PUT PATH` sends any request to any API address.

A **token** is a long secret string that proves who you are to a service, like a password that can be limited to certain actions.

## Why this repository uses it

Two things the lesson needs live in GitHub's settings, not in the repository: the **branch-protection rules** that make the checks required, and the **history of workflow runs** that the flaky-test analysis can read. `gh` is the way to reach them from code. It is optional here: nothing in the tests calls it, and no step of the local build needs it.

## Where it appears

| Path | Use |
|---|---|
| `pipeline/adapters/github.py` | `apply_branch_protection` and `list_runs`. |
| `pipeline/core/protection.py` | Builds the JSON body that is sent. |
| `pipeline/core/ghruns.py` | Turns the JSON printed by `gh run list` into run-log rows. |
| `Makefile` | `make protection` and `make protection APPLY=owner/repo`. |
| `pipeline/cli.py` | The sub-commands `protection --apply` and `import-gh-runs`. |

## How it works underneath

`gh` sends HTTPS requests to `api.github.com`, adding the token as credentials. `gh api -X PUT repos/OWNER/REPO/branches/main/protection --input -` sends a `PUT` request (the method that replaces a setting) whose body is read from standard input (`--input -`). `gh run list --repo REPO --limit N --json FIELDS` prints a JSON array with exactly the fields you name.

## Walkthrough of this repository's use

```python
def apply_branch_protection(repo: str, payload: dict[str, Any]) -> None:
    """`PUT /repos/{repo}/branches/main/protection` with `payload`."""
    subprocess.run(  # noqa: S603
        ["gh", "api", "-X", "PUT", f"repos/{repo}/branches/main/protection", "--input", "-"],  # noqa: S607
        input=json.dumps(payload),
        text=True,
        check=True,
    )


def list_runs(repo: str, limit: int) -> str:
    """The JSON that `import-gh-runs` reads: the last `limit` workflow runs."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--limit",
            str(limit),
            "--json",
            "databaseId,headSha,conclusion,createdAt,updatedAt",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
```

- **Lines 10 to 17**, `apply_branch_protection(repo, payload)`: runs `gh api -X PUT repos/<repo>/branches/main/protection --input -` through `subprocess.run`. `input=json.dumps(payload)` is the text fed to its standard input; `text=True` means it is text, not bytes; `check=True` raises an error if `gh` exits non-zero. The command is a Python *list*, so no shell is involved; the `# noqa: S603` and `# noqa: S607` comments silence two security warnings about starting programs, which are acceptable here for that reason ([ruff.md](ruff.md)).
- **Lines 20 to 38**, `list_runs(repo, limit)`: runs `gh run list --repo REPO --limit N --json databaseId,headSha,conclusion,createdAt,updatedAt` and returns what it printed (`capture_output=True`, `text=True`). The five field names are exactly what `parse_gh_runs` reads ([json.md](json.md)).

### What the protection body asks for

`make protection` prints the body ([json.md](json.md)): the checks `build`, `lint`, `unit` and `integration` must pass (`contexts`); the branch must be up to date (`strict`); the rules apply to administrators (`enforce_admins`); a pull request is required; no force pushes; no deletion. `make protection APPLY=owner/repo` sends it. **This was not applied here**: it needs a real GitHub repository and a signed-in `gh`. The README says so.

### Importing run history

`python -m pipeline import-gh-runs FILE` reads a file made by `gh run list --json databaseId,headSha,conclusion,createdAt,updatedAt` and appends one row per completed run to `runs.csv`, so the flaky-test report can use GitHub's real history instead of the local runs ([csv.md](csv.md)). `list_runs` produces the text; the sub-command reads a file you saved.

## Try it yourself

```bash
make protection
```
Prints the branch-protection JSON. Look for the four check names under `contexts`.

```bash
gh --version
```
If `gh` is installed, prints its version. If not, install it from the link below; the rest of the project does not need it.

```bash
.venv/bin/python -c "
from pipeline.core.ghruns import parse_gh_runs
sample = '[{\"databaseId\": 1, \"headSha\": \"abcdef123456\", \"conclusion\": \"success\", \"createdAt\": \"2026-01-01T00:00:00Z\", \"updatedAt\": \"2026-01-01T00:02:30Z\"}]'
print(parse_gh_runs(sample))
"
```
Expect one record with `seconds=150.0`, `result='success'`, `commit='abcdef1'`.

## Mistakes people make

- Applying protection to the wrong repository. The command requires the explicit `OWNER/REPO`.
- Using the workflow name instead of the job names in `contexts`.
- Forgetting `enforce_admins`, so the owner can bypass the rule.
- Storing a token in a script. `gh auth login` keeps it.

## Check yourself

1. What does `--input -` do? *Reads the request body from standard input.*
2. Why does `make protection` print by default? *So you can review before applying.*
3. What does `strict: True` mean? *The branch must be up to date with `main` before merging.*
4. Which `gh` command supplies run history? *`gh run list --json ...`.*
5. Is `gh` needed for the tests? *No.*

## Further reading

- GitHub CLI manual: https://cli.github.com/manual/
- Branch protection API: https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection
