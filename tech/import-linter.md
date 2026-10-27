# import-linter

## What it is

import-linter checks the **import graph** of a Python project against rules you write. An import graph says which module imports which. A rule such as "the domain package must never import the database library" is a **contract**. The command `lint-imports` reads the contracts and fails if any import breaks one. Pinned: import-linter 2.15 (it uses `grimp` 3.18 to build the graph).

## Why this repository uses it

The service has layers: `interfaces → infrastructure → application → domain`. The domain holds the logic and must know nothing about PostgreSQL. That separation is easy to break by accident with one stray `import psycopg`. A contract turns the architecture into a check that runs in the `lint` job.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.importlinter]` | Five contracts. |
| `Makefile` target `lint` | `$(VENV)/bin/lint-imports`. |
| `ARCHITECTURE.md` | Describes the same layers in words. |

## How it works underneath

`grimp` parses each module's `import` statements and builds a directed graph. The contract types:
- **layers**: modules are listed from top to bottom. A higher layer may import a lower one; a lower layer must never import a higher one.
- **forbidden**: some source modules must not import (directly or through other modules) some forbidden modules.

import-linter checks **indirect** imports too: if `domain` imports `util`, and `util` imports `psycopg`, the contract still fails.

## Walkthrough of this repository's use

```toml
[tool.importlinter]
root_packages = ["small_service", "pipeline"]
include_external_packages = true
```
Two packages are analysed. `include_external_packages` lets contracts mention third-party names like `psycopg` and standard-library names like `subprocess`.

```toml
[[tool.importlinter.contracts]]
name = "Service layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = ["small_service.interfaces", "small_service.infrastructure", "small_service.application", "small_service.domain"]
```
Top to bottom. `domain` imports nothing from the three above it.

```toml
name = "Service domain and application know nothing about PostgreSQL"
type = "forbidden"
source_modules = ["small_service.domain", "small_service.application"]
forbidden_modules = ["psycopg"]
```
The application layer talks to a `JobStore` protocol; only `infrastructure/postgres_store.py` imports `psycopg`.

```toml
name = "Pipeline layers: cli -> adapters -> core, never upward"
layers = ["pipeline.cli", "pipeline.adapters", "pipeline.core"]
```
```toml
name = "Pipeline core is pure: no subprocess, no network"
source_modules = ["pipeline.core"]
forbidden_modules = ["subprocess", "socket", "urllib", "http"]
```
`pipeline/core` holds the rules (version, checksum, flaky detection) as pure functions, so tests need no processes or network. Everything that touches the world is in `adapters`.

```toml
name = "The pipeline tooling never imports the service it builds"
source_modules = ["pipeline"]
forbidden_modules = ["small_service"]
```
The tool that builds and tests the service must not depend on it.

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
