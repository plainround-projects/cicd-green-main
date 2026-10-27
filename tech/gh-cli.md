# GitHub CLI (`gh`)

## What it is

`gh` is GitHub's official command-line program. It talks to GitHub's web API from your terminal: list workflow runs, open pull requests, and call any API endpoint with `gh api`. It authenticates with `gh auth login`. It is optional in this repository: nothing in the tests calls it.

## Why this repository uses it

Two things in the lesson live in GitHub, not in the repository: the **branch-protection settings** that make the checks required, and the **history of workflow runs** that the flaky-test analysis reads. `gh` is the tool to reach them from code.

## Where it appears

| Path | Use |
|---|---|
| `pipeline/adapters/github.py` | `apply_branch_protection` and `list_runs`. |
| `pipeline/core/protection.py` | Builds the JSON that is sent. |
| `pipeline/core/ghruns.py` | Turns `gh run list --json ...` output into run-log rows. |
| `Makefile` | `make protection` and `make protection APPLY=owner/repo`. |
| `pipeline/cli.py` | Sub-commands `protection --apply` and `import-gh-runs`. |

## How it works underneath

`gh` sends HTTPS requests to `api.github.com` with a token stored by `gh auth login`. `gh api -X PUT repos/OWNER/REPO/branches/main/protection --input -` makes a PUT request whose body is read from standard input (`--input -`). `gh run list --json fields` prints a JSON array with the fields you ask for.

## Walkthrough of this repository's use

```python
subprocess.run(
    ["gh", "api", "-X", "PUT", f"repos/{repo}/branches/main/protection", "--input", "-"],
    input=json.dumps(payload),
    text=True,
    check=True,
)
```
`-X PUT` sets the HTTP method. The body is the JSON from `branch_protection()`: required checks `build`, `lint`, `unit`, `integration`; `strict: True` (the branch must be up to date); `enforce_admins: True` (rules apply to the owner too); no force pushes; no deletions. `check=True` raises if `gh` fails. The argument list never goes through a shell.

```python
["gh", "run", "list", "--repo", repo, "--limit", str(limit), "--json", "databaseId,headSha,conclusion,createdAt,updatedAt"]
```
Asks for exactly the five fields `parse_gh_runs` needs. `conclusion` is `success`, `failure`, and so on.

`make protection` without `APPLY` only **prints** the JSON, so the learner can read the rules before anything is changed on GitHub. This was not run against a real repository here, because it needs a GitHub account and a repository.

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
