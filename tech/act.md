# act

## What it is

A GitHub workflow normally runs only on GitHub's machines, so to find out whether you wrote it correctly you would have to push a commit and wait. **act** is a command-line program that runs a workflow's jobs on your own computer instead. It reads the files in `.github/workflows/`, starts a Docker container that pretends to be a GitHub runner ([docker.md](docker.md)), copies your repository into it, and runs each step as GitHub would. Steps that use someone else's action (`uses:`) download that action first. This repository was tried with act 0.2.89.

act is an imitation, not GitHub. The machine image, the artifact service, the cache service and the service containers differ, so some jobs cannot run under it.

## Why this repository uses it

A pipeline is code, and code should be testable before it is shared. `make run` already runs the same jobs through `make` ([make.md](make.md)). act goes one step further: it runs the **workflow file itself**, which catches mistakes in the YAML, in the `needs` graph and in the pinned action references (act fetches each pinned action by its commit id, so a wrong id fails).

## Where it appears

| Path | Use |
|---|---|
| `Makefile` lines 133 to 138 | The target `act` and its variables. |
| `README.md`, section "What act can and cannot do" | Which jobs were run and which cannot be. |

## How it works underneath

act asks Docker for an image that stands in for the runner label (`ubuntu-latest`), starts a container, and runs the job's steps inside it. For `uses:` steps it clones the action's repository at the pinned commit. It talks to Docker through Docker's control socket; on a Mac with Docker Desktop, the socket's path cannot be mounted into a container, which is why one flag below turns that off. Jobs that need the Docker socket, a service container or GitHub's artifact store cannot work in that mode.

## Walkthrough of this repository's use

```make
# Run a job of the real workflow with act (needs Docker; see the README for what act can and cannot do).
# --container-daemon-socket - because the default socket path of Docker Desktop on a Mac cannot be mounted into the job.
ACT_JOB ?= changes
ACT_IMAGE ?= catthehacker/ubuntu:act-22.04
act: ## run one job of ci.yml with act (make act ACT_JOB=lint ACT_IMAGE=<an image with python, make, lsb-release>)
	act pull_request -j $(ACT_JOB) --container-architecture linux/arm64 --container-daemon-socket - -P ubuntu-latest=$(ACT_IMAGE)
```

- **Lines 133 and 134** (comments): run a job of the real workflow with act; `--container-daemon-socket -` is used because the Docker Desktop socket path on a Mac cannot be mounted into the job.
- **Line 135**: `ACT_JOB ?= changes`: the job to run, `changes` by default because it needs nothing but a shell and Git; `?=` lets you change it (`make act ACT_JOB=lint`).
- **Line 136**: `ACT_IMAGE ?= catthehacker/ubuntu:act-22.04`: a community image made to resemble GitHub's runner, about 1.5 GB. The first run downloads it.
- **Line 137**: the target with its description: run one job of `ci.yml` with act.
- **Line 138**, the command:
  - `act pull_request`: pretend the event `pull_request` happened.
  - `-j $(ACT_JOB)`: run only that job.
  - `--container-architecture linux/arm64`: use the ARM version of the image, matching an Apple-silicon Mac, so nothing is slowly emulated.
  - `--container-daemon-socket -`: do not mount Docker's control socket into the job (the `-` means "none").
  - `-P ubuntu-latest=$(ACT_IMAGE)`: when a job says `runs-on: ubuntu-latest`, use this Docker image.

### What was run, and what cannot be

The README records the outcome: the `changes` job works (checkout of a pinned action, the shell script, the job output); `act -l` lists the `needs` graph without running anything; `lint`, `unit` and `quarantine` need an image with Python and `lsb_release` (the stock Ubuntu image used in the test did not have them, and `actions/setup-python` stopped); `integration` cannot work because it needs a PostgreSQL service container and artifacts passed between jobs, which need the Docker socket and an artifact server that this mode disables; `merge_group` (the merge queue) and the branch-protection rules cannot be imitated at all. Those jobs run through the same `make` targets with `make run`.

## Try it yourself

```bash
act --version
```
Expect `act version 0.2.89` here.

```bash
make act
```
Runs the `changes` job in the default image (`catthehacker/ubuntu:act-22.04`, about 1.5 GB to download the first time). On the machine where this repository was built, that image was not pulled; the job was run with a local Ubuntu 24.04 image that has `make`, `git`, `node` and `curl`: `make act ACT_IMAGE=<that image>`. Look for `Job succeeded` at the end.

```bash
act pull_request -l
```
`-l` lists the jobs without running them.

## Mistakes people make

- Expecting `act` to match GitHub exactly. Jobs that use the artifact service, caches keyed on GitHub, or `setup-python` on a bare image can fail for reasons that have nothing to do with your code.
- Forgetting that it needs Docker running.
- Using the default small image and being surprised that `make` is missing.

## Check yourself

1. What does `act` run? *Workflow jobs, in a Docker container.*
2. What does `-j` do? *Selects one job.*
3. What is `-P` for? *Maps a runner label like `ubuntu-latest` to a Docker image.*
4. Why `--container-daemon-socket -`? *Docker Desktop's socket path on a Mac cannot be mounted into the job.*
5. Which job cannot run under `act` here? *`integration`: it needs a PostgreSQL service container and artifacts passed between jobs, which need the Docker socket that `make act` turns off.*

## Further reading

- act: https://nektosact.com and https://github.com/nektos/act (this machine: 0.2.89)
