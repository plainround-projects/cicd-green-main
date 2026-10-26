"""SHA-256 of a build artifact, and the check every job that uses it must pass."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


class ChecksumMismatchError(Exception):
    """The artifact on disk is not the artifact the build job produced."""


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sums_line(path: Path, digest: str) -> str:
    """One `sha256sum`-compatible line: `<digest>  <file name>`."""
    return f"{digest}  {path.name}"


def parse_sums(text: str) -> dict[str, str]:
    """Parse the output of `sha256sum` into `{file name: digest}`."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            sums[name.strip()] = digest.strip()
    return sums


def verify(path: Path, expected: str) -> str:
    """Return the digest when `path` matches `expected`; raise `ChecksumMismatchError` otherwise."""
    actual = sha256_of(path)
    if actual != expected.strip().lower():
        raise ChecksumMismatchError(f"{path.name}: expected sha256 {expected}, found {actual}")
    return actual
