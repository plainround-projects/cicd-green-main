# import-linter

## What it is

Large programs get messy when any part may use any other part. A common discipline is **layering**: the code is arranged in layers, and a layer may use only the layers below it. The innermost layer holds the rules of the problem and knows nothing about databases, files, networks or screens.

**import-linter** checks such rules automatically. It reads the `import` lines of every module ([python.md](python.md)) to build a map of "which module uses which", called the **import graph**, and compares it with rules ("contracts") that you write in `pyproject.toml`. The command is `lint-imports`. This repository pins import-linter 2.15, which uses a library called `grimp` to build the graph. Two kinds of contract are used:

- A **layers** contract lists modules from top to bottom. A module may import from layers below it, never from layers above.
- A **forbidden** contract says that certain *source* modules must never import certain *forbidden* modules, even indirectly through other modules.

## Why this repository uses it

The service is built in four layers, `interfaces → infrastructure → application → domain`, so that the rules (a cache that expires, a job with a timeout) can be tested in milliseconds with no database. That separation is easy to break with one stray `import psycopg` in the wrong file. The pipeline has its own layers for the same reason: its rules (versions, checksums, flaky-test maths, workflow lint) live in `pipeline/core` and must be testable with no files, no network and no programs started.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 77 to 112 | The settings and five contracts. |
| `Makefile` `lint` | Runs `lint-imports`. |
| `ARCHITECTURE.md` | The same layers in words and a picture. |

## How it works underneath

`grimp` reads every module's `import` statements and builds a directed graph (arrows from the importer to the imported). A *layers* contract checks no arrow goes from a lower layer up to a higher one. A *forbidden* contract searches the graph for any path, direct or through other modules, from a source module to a forbidden one. `include_external_packages = true` lets the contracts name modules that are not part of the project, such as the standard library's `subprocess` or the third-party `psycopg`. The tool never runs your code.

## Walkthrough of this repository's use

```toml
[tool.importlinter]
root_packages = ["small_service", "pipeline"]
include_external_packages = true
```

- `[tool.importlinter]` is the table for the tool's own settings. `root_packages = ["small_service", "pipeline"]` names the two packages to analyse. `include_external_packages = true` (explained above).

```toml
[[tool.importlinter.contracts]]
name = "Service layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = [
    "small_service.interfaces",
    "small_service.infrastructure",
    "small_service.application",
    "small_service.domain",
]
```

- **Contract 1**, "Service layers". `[[tool.importlinter.contracts]]` adds a contract to the list. `name` is the text shown in the report. `type = "layers"`. `layers = [...]` lists the layers top to bottom: `interfaces` may import from `infrastructure`, `application` and `domain`; `infrastructure` may import from `application` and `domain`; `application` only from `domain`; `domain` from none of them.

```toml
[[tool.importlinter.contracts]]
name = "Service domain and application know nothing about PostgreSQL"
type = "forbidden"
source_modules = ["small_service.domain", "small_service.application"]
forbidden_modules = ["psycopg"]
```

- **Contract 2**, "Service domain and application know nothing about PostgreSQL". `type = "forbidden"`: nothing in `small_service.domain` or `small_service.application` may import `psycopg`, even indirectly. The application layer talks to a `JobStore` interface, and only `infrastructure/postgres_store.py` imports the driver.

```toml
[[tool.importlinter.contracts]]
name = "Pipeline layers: cli -> adapters -> core, never upward"
type = "layers"
layers = ["pipeline.cli", "pipeline.adapters", "pipeline.core"]
```

- **Contract 3**, "Pipeline layers". The pipeline's outermost layer is `pipeline.cli`, then `pipeline.adapters` (code that touches the world: programs, Git, files), then `pipeline.core` (pure rules).

```toml
[[tool.importlinter.contracts]]
name = "Pipeline core is pure: no subprocess, no network"
type = "forbidden"
source_modules = ["pipeline.core"]
forbidden_modules = ["subprocess", "socket", "urllib", "http"]
```

- **Contract 4**, "Pipeline core is pure". `pipeline.core` must not import `subprocess` (starting programs), `socket` (raw networking), `urllib` (web requests) or `http`. That is why its tests need no setup at all, and why the rules that decide whether a build may ship can be trusted to be deterministic.

```toml
[[tool.importlinter.contracts]]
name = "The pipeline tooling never imports the service it builds"
type = "forbidden"
source_modules = ["pipeline"]
forbidden_modules = ["small_service"]
```

- **Contract 5**, "The pipeline tooling never imports the service it builds". The code that builds, checks and ships the service must not depend on the service's own code. Otherwise a bug in the service could change how the service is judged.

### In use

`make lint` runs `lint-imports`; with the five contracts it ends with `Contracts: 5 kept, 0 broken.`

## Try it yourself

```bash
.venv/bin/lint-imports
```
Expect each contract on its own line ending in `KEPT`, then `Contracts: 5 kept, 0 broken.`

Break a contract on purpose:
```bash
printf 'import psycopg\n' >> src/small_service/domain/errors.py
.venv/bin/lint-imports | tail -12
git checkout src/small_service/domain/errors.py
```
Expect `BROKEN` for the forbidden-psycopg contract and a chain showing which module imports which.

## Mistakes people make

- Writing the architecture only in a document, where nothing enforces it.
- Layers listed in the wrong order.
- Forgetting indirect imports; here they are checked.
- Skipping `include_external_packages` and so being unable to forbid `psycopg`.

## Check yourself

1. What does a `layers` contract guarantee? *No module in a lower layer imports a higher one.*
2. What does a `forbidden` contract guarantee? *The source modules never reach the forbidden modules, even indirectly.*
3. Why is `pipeline/core` forbidden from `subprocess`? *So its logic stays pure and cheap to test.*
4. Does import-linter run the code? *No, it reads import statements.*
5. Which job runs it? *`lint`, through `make lint`.*

## Further reading

- import-linter: https://import-linter.readthedocs.io/en/stable/ (pinned 2.15)
- Contract types: https://import-linter.readthedocs.io/en/stable/contract_types.html
- grimp: https://grimp.readthedocs.io/
