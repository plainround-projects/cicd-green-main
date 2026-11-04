# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Drawn architecture and flow figures in `docs/diagrams/`, light and dark, shown in the README.

## [0.1.0] - 2026-10-27

### Added

- A small layered service (a time-limited cache and a background job recorded in PostgreSQL) with unit and integration tests.
- The pipeline as code: `.github/workflows/ci.yml` with `changes`, `build`, `lint`, `unit`, `integration`, `quarantine` and `audit` jobs, every job one `make` target, actions pinned to commit SHAs, read-only permissions.
- One wheel built once, versioned `0.1.0+<commit>`, reproducible from the commit time, with `dist/SHA256SUMS`; every job that uses it verifies the checksum, and the integration job tests the installed wheel.
- A local runner (`make run`, `make run-baseline`, `make bench`) and a run log (`runs.csv`) with flaky-test detection (`make flaky-hunt`, `make flaky-report`).
- The branch-protection payload, a protected-main demo against a git hook (`make gate-demo`) and workflow rules that fail a test instead of a merge.
- The planted flaky test, quarantined with a marker and a non-blocking job, its issue and its fix.
- Decision records, the README contract and its check.
