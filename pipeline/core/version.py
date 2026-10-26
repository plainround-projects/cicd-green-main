"""Version a build from its commit, so one commit always gives one version (`0.1.0+3fa91bc`)."""

from __future__ import annotations

import re
import tomllib

_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_VERSION_LINE = re.compile(r'^(version\s*=\s*)"[^"]*"', re.MULTILINE)


class VersionError(ValueError):
    """A version or commit could not be used."""


def base_version(pyproject_text: str) -> str:
    """The `project.version` of a pyproject.toml, which must be MAJOR.MINOR.PATCH."""
    version = tomllib.loads(pyproject_text)["project"]["version"]
    if not _SEMVER.match(version):
        raise VersionError(f"project.version must be MAJOR.MINOR.PATCH, got {version!r}")
    return str(version)


def build_version(base: str, commit_sha: str, dirty: bool = False) -> str:
    """`base+<first 7 characters of the commit>`, with `.dirty` when the working tree has uncommitted changes."""
    if not _SEMVER.match(base):
        raise VersionError(f"base version must be MAJOR.MINOR.PATCH, got {base!r}")
    if not _SHA.match(commit_sha):
        raise VersionError(f"commit must be 7 to 40 lowercase hex characters, got {commit_sha!r}")
    return f"{base}+{commit_sha[:7]}{'.dirty' if dirty else ''}"


def stamp_pyproject(pyproject_text: str, version: str) -> str:
    """Replace the first `version = "..."` line (the one in `[project]`) with `version`."""
    stamped, count = _VERSION_LINE.subn(lambda match: f'{match.group(1)}"{version}"', pyproject_text, count=1)
    if count != 1:
        raise VersionError("pyproject.toml has no version line to stamp")
    return stamped
