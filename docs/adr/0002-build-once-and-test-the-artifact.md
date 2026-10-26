# 2. Build the wheel once, checksum it, test that wheel

Status: accepted, 2026-10-26

## Context

"What I tested must be what I ship." If every job rebuilds, the thing that ships was never tested, and two jobs can disagree about what version they saw.

## Decision

The `build` job runs `python -m pipeline build` once. The version is `<project version>+<first 7 characters of the commit>` (`0.1.0+3fa91bc`, with `.dirty` when the tree has uncommitted changes), and `SOURCE_DATE_EPOCH` is the commit time, so the same commit gives the same bytes. The job writes `dist/SHA256SUMS`, exposes the digest as a job output and uploads `dist/`. The `integration` job downloads it, verifies the digest against the output (`pipeline verify` exits non-zero on a mismatch), installs the wheel into a clean environment (not the sources) and runs the integration tests there. `tests/integration/test_artifact.py` fails if the package under test is not in `site-packages`.

## Alternatives considered

- **Rebuild in each job:** simpler YAML, but the checksum check in step 4 of the lesson would be meaningless.
- **Publish to a package index and install from it:** the right production step, and a stretch here; it adds an index to run for no new lesson.

## Consequences

- The digest is printed in two places (`build: sha256 ...`, `integration: sha256 ... verified`), which is the lesson's expected output.
- Reproducible bytes make a mismatch a real signal: nothing in a rebuild changes the digest by accident (`tests/pipeline/test_builder_and_runner.py` proves it).
