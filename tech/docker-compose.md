# Docker Compose

## What it is

Starting one container by hand takes a long command (`docker run --name ... -e ... -p ... image`). Starting several, wired together, takes more. **Docker Compose** lets you write that down once in a file, `docker-compose.yml`, and then run the whole set with one command. The file is written in YAML ([yaml.md](yaml.md)). This repository uses the `docker compose` command that is built into Docker (version 2; v2.23.0 here).

Compose words:

- A **service** is one container definition (an image, its settings), such as `db`.
- A **project** is the group of services started together. Compose names everything with the project name (by default, the folder name).
- A **network**: Compose puts a project's containers on a private network where they find each other by service name (the `app` container reaches the database at the host name `db`).
- A **published port** (`ports:`) opens a door from your computer into a container.
- A **volume** or **tmpfs** is where a container stores files that should outlive it (volume) or live in memory only (tmpfs).
- A **profile** hides a service unless you ask for it by name.
- A **health check** is a command Docker runs inside a container to decide whether it is ready. `up --wait` waits for "healthy".

## Why this repository uses it

The service stores its job history in PostgreSQL, and the integration tests must run against a real database. Compose gives every learner the same database with one command, and removes it with another, so nothing is installed on the learner's machine. It also builds and runs the packaged application image for the local "deploy" step.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Two services: `db` and `app`. |
| `Makefile` | `COMPOSE := docker compose`; the targets `up`, `db`, `deploy-local`, `down` use it. |
| `.env` and `.env.example` | The values Compose fills into the file ([dotenv.md](dotenv.md)). |

## How it works underneath

Compose reads the YAML, replaces `${NAME}` placeholders with values from the shell environment or the `.env` file in the project folder, and asks the Docker engine to create the containers, the network and the volumes. `docker compose up -d --wait db` creates and starts `db` in the background and returns once its health check passes. `docker compose exec` runs a command in a running container. `docker compose down -v` stops and removes the containers and deletes their volumes.

Compose has its own placeholder syntax: `${VAR}` (the value), `${VAR:-default}` (the value, or `default` if unset or empty) and `${VAR:?message}` (the value, or stop with `message` if unset). A `$$` writes a literal dollar sign that Compose leaves alone, so that the container's own shell can expand it.

## Walkthrough of this repository's use

```yaml
# The local target: PostgreSQL for the integration tests and the packaged service (profile "app").
# Host port and credentials come from .env (copied from .env.example by `make up`).
services:
```

- **Lines 1 and 2** are comments: the file defines the local target, PostgreSQL for the integration tests plus the packaged service under the profile `app`; host port and credentials come from `.env`, copied from `.env.example` by `make up`.
- **Line 3**: `services:` starts the list of services.

```yaml
  db:
    image: postgres:16.4-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-service}
      POSTGRES_USER: ${POSTGRES_USER:-service}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-55471}:5432"
```

- **Line 4**: `db:` is the first service's name. **Line 5**: `image: postgres:16.4-alpine` says which image to run: the official PostgreSQL 16.4 server on Alpine, a very small Linux. A fixed tag means everyone gets the same database version.
- **Lines 6 to 9**: `environment:` sets environment variables inside the container. The PostgreSQL image reads them on first start to create a database and a user. `POSTGRES_DB: ${POSTGRES_DB:-service}` uses the variable or the default `service`. **Line 9**, `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}`, has **no default**: if the variable is missing, Compose stops with that message. A database should never start with a guessable default password.
- **Lines 10 and 11**: `ports: - "127.0.0.1:${POSTGRES_PORT:-55471}:5432"`. The format is `host-address:host-port:container-port`. PostgreSQL listens on 5432 inside the container. `127.0.0.1` is the loopback address, "this computer only", so other machines cannot connect. The host port is 55471 by default, chosen to avoid clashing with a PostgreSQL you may already run on 5432.

```yaml
    # -h 127.0.0.1: the image first starts a temporary server that listens on the socket only; TCP answers when the real one is up
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 20s
      retries: 30
      start_period: 10s
    tmpfs:
      - /var/lib/postgresql/data
```

- **Line 12** (a comment) explains the health check: at first the image starts a temporary server that listens on a Unix socket only, to run set-up, and only then the real server that listens on TCP. A check over the socket would report "ready" too early, so the check forces TCP with `-h 127.0.0.1`.
- **Lines 13 to 18**: `healthcheck:` with `test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]`. `CMD-SHELL` runs the string through the container's shell. `pg_isready` is a PostgreSQL tool that asks the server whether it accepts connections. `$$` makes the *container's* shell expand the variables, not Compose. `interval: 5s` is the time between checks; `timeout: 20s` is how long one check may take (generous, because a busy laptop is slow); `retries: 30` is how many failures count as unhealthy; `start_period: 10s` is a grace period at the start during which failures are not counted.
- **Lines 19 to 21**: `tmpfs: - /var/lib/postgresql/data` keeps the database's data directory in memory. It is fast and disappears with the container, so every run starts empty.

```yaml

  # The artifact the pipeline built, installed into an image and run against the database above:
  #   make deploy-local
  app:
    profiles: ["app"]
    image: cicd-green-main:local
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      db:
        condition: service_healthy
    environment:
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
      POSTGRES_DB: ${POSTGRES_DB:-service}
      POSTGRES_USER: ${POSTGRES_USER:-service}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    command: ["small-service", "smoke"]
```

- **Lines 22 and 23** (comments): the artifact the pipeline built, installed into an image and run against the database; started with `make deploy-local`.
- **Line 24**: `app:` is the second service. **Line 25**: `profiles: ["app"]` hides it from a plain `docker compose up`; it starts only with `--profile app`.
- **Line 26**: `image: cicd-green-main:local` is the name given to the image once built. **Lines 27 to 29**: `build:` tells Compose to build it from `context: .` (the current folder) using `dockerfile: Dockerfile` ([docker.md](docker.md)).
- **Lines 30 to 32**: `depends_on: db: condition: service_healthy` makes Compose start `app` only after `db` passes its health check, not merely after the container starts.
- **Lines 33 to 38**: the environment for the app. `POSTGRES_HOST: db` is the database's host name on the Compose network. `POSTGRES_PORT: "5432"` is the port *inside* the network, not the published one. The value is quoted so YAML keeps it as text.
- **Line 39**: `command: ["small-service", "smoke"]` replaces the image's default `CMD`. `small-service smoke` runs a job twice, reads it back and prints a one-line result.

### How the Makefile drives it

`make up` runs `docker compose up -d --wait db`. `make db` runs SQL through `docker compose exec -T db psql ...` ([make.md](make.md)). `make deploy-local` runs `docker compose --profile app build app` then `docker compose --profile app run --rm app` (`run --rm` starts a one-off container and deletes it afterwards). `make down` runs `docker compose --profile app down -v`.

## Try it yourself

```bash
docker compose config --quiet && echo valid
```
Needs a `.env` (run `make -B .env`, or `cp .env.example .env`). Prints `valid` when the file parses.

```bash
make up && docker compose ps
```
Expect `db` with status `running (healthy)` and the port `127.0.0.1:55471->5432/tcp`.

```bash
docker compose exec db psql -U service -d service -c '\dt'
```
Lists the `job_runs` table.

```bash
make down && docker compose ps
```
Nothing is listed afterwards.

## Mistakes people make

- Using `localhost` as the database host from inside another container.
- Binding the port to all interfaces (`"5432:5432"`) and exposing the database to the network.
- Starting the app before the database is ready; a plain `depends_on` only waits for the container to start.
- Hard-coding passwords in the file. Here `:?` forces them into `.env`.
- Forgetting `$$` in health checks.

## Check yourself

1. What does `${POSTGRES_PASSWORD:?message}` do? *Stops with the message if the variable is not set.*
2. What does `127.0.0.1:55471:5432` mean? *Host port 55471 on this machine only goes to port 5432 in the container.*
3. Why does the health check use `-h 127.0.0.1`? *To test over TCP; the setup-time server listens only on the socket.*
4. What is a profile for? *To keep a service out of the default `up`.*
5. What does `tmpfs` do here? *Keeps the data in memory so each run starts clean.*

## Further reading

- Compose file reference: https://docs.docker.com/reference/compose-file/
- `docker compose up --wait`: https://docs.docker.com/reference/cli/docker/compose/up/
- Image: https://hub.docker.com/_/postgres (16.4-alpine)
