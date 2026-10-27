# Docker and the Dockerfile

## What it is

Docker runs programs inside **containers**. A container is an ordinary process on your machine that sees its own private view of the file system, network and process list. It is lighter than a virtual machine because it shares the host's kernel. An **image** is the read-only template a container starts from: a stack of file-system **layers** plus settings. A **Dockerfile** is a text file of instructions that builds an image. A **registry** (Docker Hub, for example) stores images by name and tag.

On a Mac, Docker Desktop runs a small Linux virtual machine and starts the containers inside it.

## Why this repository uses it

The lesson says the **artifact** (the wheel) is built once. The Dockerfile shows the last step: install exactly that verified wheel into a clean image and run it. That is the local "deploy" (`make deploy-local`). PostgreSQL also runs as a container, through [docker-compose.md](docker-compose.md).

## Where it appears

| Path | Use |
|---|---|
| `Dockerfile` | Builds the `cicd-green-main:local` image from the verified wheel. |
| `.dockerignore` | Lists what the build must not copy into the image. |
| `docker-compose.yml` | Builds and runs that image as the `app` service; runs `postgres:16.4-alpine` as `db`. |
| `.github/workflows/ci.yml` | `services: postgres:` starts the same database image on the CI runner. |

## How it works underneath

- `docker build` starts from a **base image** (`FROM`), then runs each instruction in order. Every instruction that changes files makes a new **layer**. Docker caches layers: if an instruction and everything before it is unchanged, it reuses the layer. So you put rarely-changing steps first.
- The **build context** is the folder sent to the builder. `COPY` can only read from it. `.dockerignore` removes files from the context.
- `RUN` executes at **build time** and its result is saved in the image. `CMD` runs at **start time**.
- An image name can carry a **digest** (`@sha256:...`): the hash of the exact image. A tag like `3.12` can move; a digest cannot.

## Walkthrough of this repository's use

```dockerfile
FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0
```
Base image: Python 3.12.8 on Debian "bookworm", the `slim` variant (smaller, fewer tools). The `@sha256:` part pins the exact bytes, so a rebuild next year gets the same base.

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
```
`ENV` sets environment variables for the image. No `.pyc` files are written. Output is not buffered, so logs appear at once. pip keeps no download cache (smaller image) and does not check for a newer pip.

```dockerfile
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
```
`WORKDIR` sets the folder for the next instructions (and creates it). The runtime dependencies are copied and installed **before** the wheel. Dependencies change rarely and the wheel changes every commit, so this layer stays cached. `--require-hashes` rejects any file whose hash is not in the lock ([pip-and-hash-locking.md](pip-and-hash-locking.md)).

```dockerfile
COPY dist/*.whl ./
RUN pip install --no-deps ./*.whl && rm ./*.whl
```
Copy the wheel built by the pipeline. `--no-deps` installs only the wheel because the dependencies are already in place. `&& rm` deletes it in the same layer so it does not stay in the image.

```dockerfile
RUN useradd --system --uid 10001 --no-create-home app
USER app
```
Create a system user with a fixed number and switch to it. Everything after runs, and the service runs, as a non-root user. If the process is compromised it cannot change the image's files.

```dockerfile
HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["small-service", "health"]
CMD ["small-service", "health"]
```
`HEALTHCHECK` tells Docker how to test the container. Every 30 seconds it runs `small-service health`, which exits 0 when the database answers. Three failures in a row mark the container unhealthy. The list form `["a", "b"]` (**exec form**) runs the program directly without a shell. `CMD` is the default command.

### `.dockerignore`

```
.git
.venv
tests
docs
pipeline
...
```
Keeps the context small and keeps the image honest: the image contains the installed wheel, not tests or pipeline code. `.env` is excluded so a local password can never be copied in.

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
