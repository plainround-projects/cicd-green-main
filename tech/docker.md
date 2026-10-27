# Docker and the Dockerfile

## What it is

Normally a program needs the right operating-system files, libraries and settings to be present on the computer that runs it, and "it works on my machine" fails when they are not. **Docker** solves that by packaging a program together with everything it needs into one unit that runs the same way anywhere Docker is installed.

The words you need:

- A **container** is a running program that Docker has walled off: it sees its own private file system, its own list of processes and its own network, though it shares the computer's kernel (the core of the operating system). It is much lighter than a virtual machine.
- An **image** is the read-only template a container starts from: a stack of file-system **layers** plus settings. You can start many containers from one image.
- A **Dockerfile** is a text file of instructions that builds an image. `docker build` reads it.
- A **layer** is the file-system change made by one instruction. Docker keeps each layer and re-uses it when nothing before it changed, which makes rebuilds quick.
- A **registry** is a server that stores images by name (Docker Hub is a public one). `docker pull` downloads an image; `docker push` uploads one.
- A **tag** such as `3.12.8-slim-bookworm` is a movable label on an image. A **digest** (`sha256:...`) is a fingerprint of the image's exact contents and can never point at something else.
- A **port** is a numbered door (1 to 65535) on a computer that one program listens on. A container's ports are closed to the outside unless you **publish** them.
- A **health check** is a command Docker runs inside the container at intervals to decide whether the program is working.

On a Mac or Windows, Docker Desktop runs a small hidden Linux virtual machine, and the containers live inside it.

## Why this repository uses it

The lesson says the **artifact is built once**, and every later stage uses that exact file. This repository's artifact is a Python wheel ([python-packaging.md](python-packaging.md)). The `Dockerfile` shows the final stage: install exactly that checksum-verified wheel into a clean image and run it. That is `make deploy-local`. Docker also runs the PostgreSQL database for the integration tests, through Compose ([docker-compose.md](docker-compose.md)).

## Where it appears

| Path | Use |
|---|---|
| `Dockerfile` | Builds the image `cicd-green-main:local` from the verified wheel. |
| `.dockerignore` | Lists what Docker must not copy into the build. |
| `docker-compose.yml` | Builds and runs that image as the `app` service, and runs `postgres:16.4-alpine` as `db`. |
| `.github/workflows/ci.yml` | `services: postgres:` starts the same database image on the CI machine. |

## How it works underneath

- `docker build -f Dockerfile .` sends the **build context** (the folder `.`) to the Docker engine. `COPY` can only read files from the context. The file `.dockerignore` removes files from the context before it is sent.
- The engine starts from the **base image** named in `FROM`, then runs the instructions in order, creating a layer for each that changes files. If an instruction and all before it are unchanged since the last build, the stored layer is reused. So the instructions that change least often come first.
- `RUN` executes a command **while building** and keeps the result in the image. `CMD` names the command to run **when a container starts**.
- `ENV` sets environment variables ([dotenv.md](dotenv.md)) that exist both while building later steps and when the container runs.
- `USER` sets which user the following instructions and the final program run as. A process running as a normal user cannot change the system files, which limits the damage if the program is compromised.
- The image name may include a digest after `@`. Docker then uses exactly that image, whatever the tag points at today.

## Walkthrough of this repository's use

### `Dockerfile`

```dockerfile
# The artifact the pipeline built, as an image: installs the checksum-verified wheel from dist/ and nothing else.
# Built by `make deploy-local`, which verifies dist/SHA256SUMS first. Nothing here serves traffic; the health command is the check.
FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0
```

- **Lines 1 and 2** are comments: the image installs the wheel the pipeline built and nothing else; `make deploy-local` verifies `dist/SHA256SUMS` first; the image serves no traffic, so its health command is the check.
- **Line 3**, `FROM python:3.12.8-slim-bookworm@sha256:2199...`. `FROM` names the starting image: the official Python image, version 3.12.8, built on Debian "bookworm", in its `slim` variant (smaller, fewer extra programs). The part after `@` is the digest of that exact image, so a rebuild in a year starts from the same bytes even if the tag has since moved.

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
```

- **Lines 5 to 8**: one `ENV` instruction (the backslashes continue the line) with four variables. `PYTHONDONTWRITEBYTECODE=1` stops Python writing `.pyc` cache files (pointless in a throw-away container). `PYTHONUNBUFFERED=1` makes output appear at once instead of being held back, so logs show up live. `PIP_NO_CACHE_DIR=1` makes `pip` not keep a download cache (a smaller image). `PIP_DISABLE_PIP_VERSION_CHECK=1` stops it phoning home to check its own version.

```dockerfile
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY dist/*.whl ./
RUN pip install --no-deps ./*.whl && rm ./*.whl
```

- **Line 10**: `WORKDIR /app` sets the working folder for the following instructions and for the container, creating `/app` if it does not exist.
- **Lines 11 and 12**: `COPY requirements.lock ./` copies the runtime lock file into `/app`, then `RUN pip install --require-hashes -r requirements.lock` installs the exact locked packages and refuses any whose checksum is not in the file ([pip-and-hash-locking.md](pip-and-hash-locking.md)). This comes **before** the wheel on purpose: the dependencies change rarely, and the wheel changes with every commit, so this layer is reused from the cache on almost every build.
- **Line 14**: `COPY dist/*.whl ./` copies the wheel built by the pipeline (the star matches its versioned name). **Line 15**: `RUN pip install --no-deps ./*.whl && rm ./*.whl` installs it (`--no-deps` because the dependencies are already in place) and deletes the file in the same layer, so it does not remain in the image. `&&` runs the second command only if the first succeeded.

```dockerfile
RUN useradd --system --uid 10001 --no-create-home app
USER app

HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["small-service", "health"]
CMD ["small-service", "health"]
```

- **Line 17**: `RUN useradd --system --uid 10001 --no-create-home app` makes an operating-system user named `app` with the fixed number 10001, as a *system* user (for running a service, not a person), with no home folder. **Line 18**: `USER app` makes everything after, including the final program, run as that user.
- **Line 20**: `HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["small-service", "health"]`. Every 30 seconds Docker runs `small-service health` inside the container; the command must finish within 20 seconds; after three failures in a row the container is marked unhealthy. The square-bracket form, a list of words, is called the **exec form**: Docker runs the program directly, with no shell in between, which avoids quoting surprises.
- **Line 21**: `CMD ["small-service", "health"]` is the command a container runs when started without another: it checks that the database answers and exits.

### `.dockerignore`

```
.git
.venv
.cache
reports
logs
tests
docs
pipeline
**/__pycache__
.mypy_cache
.ruff_cache
.pytest_cache
.coverage
.env
build
```

Files and folders that must not be sent to Docker as part of the build context, one pattern per line: `.git` (the history), `.venv` and `.cache` (local environments), `reports` and `logs` (generated output), `tests`, `docs` and `pipeline` (not needed in the image), `**/__pycache__` (compiled Python files at any depth; `**` means "any number of folders"), the tool caches `.mypy_cache`, `.ruff_cache`, `.pytest_cache` and `.coverage`, `.env` (local settings, possibly a password: it must never be copied into an image) and `build`. This keeps the build fast and the image honest: it contains the installed wheel, not the repository.

### Where else Docker is used

`docker-compose.yml` builds this Dockerfile and starts the database ([docker-compose.md](docker-compose.md)); the workflow starts the same database image as a *service container* ([github-actions.md](github-actions.md)); `make deploy-local` runs `docker compose --profile app build app` and `docker compose --profile app run --rm app` ([make.md](make.md)).

## Try it yourself

```bash
docker --version
docker compose version
```

```bash
make deploy-local
```
Builds the wheel, verifies its checksum, builds the image and runs `small-service smoke`. Expect a line like `version=0.1.0+abc1234 first_cached=False second_cached=True stored=1`.

```bash
docker image inspect cicd-green-main:local --format '{{.Config.User}} {{.Config.Cmd}}'
```
Expect `app [small-service health]`.

```bash
docker history cicd-green-main:local
```
Lists the layers; you can see the dependency layer is separate from the wheel layer.

## Mistakes people make

- Running as root inside the container. Here `USER app`.
- Copying the whole project and installing in one layer, so every code change reinstalls everything.
- Using `latest` or a moving tag. Here the base image is pinned by digest.
- Leaving secrets in an image layer. A later `rm` does not remove them from earlier layers.
- Forgetting `.dockerignore`, so `.git` and `.venv` get copied.

## Check yourself

1. What is the difference between `RUN` and `CMD`? *`RUN` happens at build time and is saved in the image; `CMD` is the default command at start.*
2. Why copy `requirements.lock` before the wheel? *So the dependency layer is cached when only the code changes.*
3. What does the digest after `@sha256:` give you? *The exact image, which cannot change like a tag can.*
4. Why `USER app`? *The process runs without root rights.*
5. What does `HEALTHCHECK` do? *Docker runs the command regularly and marks the container healthy or unhealthy by its exit status.*

## Further reading

- Dockerfile reference: https://docs.docker.com/reference/dockerfile/
- Build cache: https://docs.docker.com/build/cache/
- Image: Python 3.12.8 on bookworm-slim, https://hub.docker.com/_/python
