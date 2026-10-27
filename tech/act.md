# act

## What it is

`act` is a command-line tool that runs GitHub Actions workflows on your own machine. It reads the YAML files in `.github/workflows/`, starts a Docker container that pretends to be a GitHub runner, and runs the steps inside it.

## Why this repository uses it

The lesson wants the pipeline to be testable before it reaches GitHub. `make run` already runs the same jobs through `make`. `act` goes one step further: it runs the **workflow file itself**.

## Where it appears

| Path | Use |
|---|---|
| `Makefile`, target `act` | `act pull_request -j $(ACT_JOB) --container-architecture linux/arm64 --container-daemon-socket - -P ubuntu-latest=$(ACT_IMAGE)` |
| `README.md` | States which jobs work under `act` and which do not. |

## How it works underneath

`act` asks Docker for an image, starts a container, copies the repository in, and runs each step as GitHub would. `uses:` actions are downloaded from GitHub. Service containers are started through the Docker socket. `act` is not GitHub: the machine image, the cache service and the artifact service differ.

## Walkthrough of this repository's use

```make
ACT_JOB ?= changes
ACT_IMAGE ?= catthehacker/ubuntu:act-22.04
act:
	act pull_request -j $(ACT_JOB) --container-architecture linux/arm64 --container-daemon-socket - -P ubuntu-latest=$(ACT_IMAGE)
```
- `pull_request` is the event to simulate.
- `-j changes` runs only that job. The default `changes` job needs no extra tools.
- `--container-architecture linux/arm64` matches an Apple Silicon Mac, so no slow emulation.
- `--container-daemon-socket -` tells act not to mount the Docker socket into the job. Docker Desktop on a Mac keeps the socket at a path that cannot be mounted; `-` turns the mount off.
- `-P ubuntu-latest=<image>` says which Docker image stands in for the runner label `ubuntu-latest`. The image must contain Python, `make` and `lsb-release` for the jobs that use `setup-python`.

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
