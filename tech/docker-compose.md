# Docker Compose

## What it is

Docker Compose runs several containers together from one YAML file, `docker-compose.yml`. You describe **services** (one container each), their ports, environment variables, health checks and start order. `docker compose up` creates and starts them. This repository uses the `docker compose` command (version 2, built into Docker; this machine has v2.23.0).

## Why this repository uses it

The service stores its job history in PostgreSQL and the integration test needs a real database. Compose gives every learner the same database with one command and removes it with another, so nothing is installed on the machine. See [docker.md](docker.md) for what a container is.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Two services: `db` (PostgreSQL) and `app` (the packaged service, only with the `app` profile). |
| `Makefile` | `COMPOSE := docker compose`; targets `up`, `db`, `deploy-local`, `down` call it. |
| `.env` / `.env.example` | Values Compose substitutes into the file ([dotenv.md](dotenv.md)). |

## How it works underneath

- Compose reads the YAML, replaces `${VAR}` with values from your shell or the `.env` file, then talks to the Docker engine to create a private **network**, containers and volumes. The project name (the folder name) prefixes everything.
- Services on the same network reach each other by **service name**. The `app` container connects to host `db`, not `localhost`.
- A **published port** (`ports:`) opens a door from the host into the container: `127.0.0.1:55471:5432` means "host port 55471 on this machine only, forwarded to container port 5432".
- A **health check** is a command Docker runs inside the container. `docker compose up --wait` waits until it passes.
- A **profile** hides services unless you ask for them.

## Walkthrough of this repository's use

```yaml
services:
  db:
    image: postgres:16.4-alpine
```
Start from the PostgreSQL 16.4 image on Alpine Linux (a very small Linux). A fixed tag means everyone gets the same database version.

```yaml
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-service}
      POSTGRES_USER: ${POSTGRES_USER:-service}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
```
On first start the image creates this database and user. `${NAME:-default}` uses `default` when the variable is unset or empty. `${NAME:?message}` stops with the message when it is unset. So there is **no default password**: you must have a `.env` file.

```yaml
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-55471}:5432"
```
Only this machine can connect (`127.0.0.1`). The host port is unusual (55471) so it does not clash with a PostgreSQL you may already run on 5432.

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 20s
      retries: 30
      start_period: 10s
```
`pg_isready` asks the server if it accepts connections. `-h 127.0.0.1` forces a TCP connection. The PostgreSQL image first starts a temporary server that listens only on a Unix socket while it runs setup, and a check over the socket would say "ready" too early. `$$` writes a literal `$`, so the **container's** shell expands `POSTGRES_USER`, not Compose. `interval` is the time between checks, `timeout` is how long one check may take (20 s because a busy laptop is slow), `retries` is how many failures count as unhealthy, and `start_period` is a grace time when failures do not count.

```yaml
    tmpfs:
      - /var/lib/postgresql/data
```
The data directory lives in memory. It is fast, and it vanishes with the container, so every run starts clean.

```yaml
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
    command: ["small-service", "smoke"]
```
`profiles: ["app"]` means `docker compose up` ignores this service; only `--profile app` starts it (`make deploy-local`). `build` says how to make the image from the [Dockerfile](docker.md). `depends_on` with `service_healthy` starts `app` only after `db` passes its health check. Inside the network the database is at `db:5432`. `command` replaces the Dockerfile's `CMD`.

### How the Makefile drives it

`make up` runs `docker compose up -d --wait db` (`-d` is "in the background"). `make down` runs `docker compose --profile app down -v`: stops and removes the containers and `-v` also deletes volumes.

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
