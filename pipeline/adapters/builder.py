"""Build the wheel once, versioned from the commit, with a checksum file next to it."""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pipeline.adapters import git
from pipeline.adapters.process import run_output
from pipeline.core.checksum import sha256_of, sums_line
from pipeline.core.version import base_version, build_version, stamp_pyproject

SUMS_FILE = "SHA256SUMS"


@dataclass(frozen=True, slots=True)
class BuiltArtifact:
    """The wheel that was built, its version and its SHA-256."""

    path: Path
    version: str
    sha256: str


def build_wheel(root: Path, dist: Path, python: str = sys.executable) -> BuiltArtifact:
    """Stamp the version into a copy of the sources, build the wheel in a temporary folder and write `dist/SHA256SUMS`.

    The commit time is the build's clock (`SOURCE_DATE_EPOCH`), so the same commit gives the same bytes.
    """
    sha = git.head_sha(root)
    version = build_version(base_version((root / "pyproject.toml").read_text()), sha, git.is_dirty(root))
    with tempfile.TemporaryDirectory(prefix="wheel-build-") as workdir:
        staging = Path(workdir) / "source"
        shutil.copytree(root / "src", staging / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for name in ("README.md", "LICENSE"):
            shutil.copy2(root / name, staging / name)
        (staging / "pyproject.toml").write_text(stamp_pyproject((root / "pyproject.toml").read_text(), version))
        out = Path(workdir) / "out"
        run_output(
            [python, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out), str(staging)],
            root,
            env={"SOURCE_DATE_EPOCH": str(git.commit_epoch(root, sha))},
        )
        built = next(out.glob("*.whl"))
        dist.mkdir(parents=True, exist_ok=True)
        for old in dist.glob("*.whl"):
            old.unlink()
        target = dist / built.name
        shutil.copy2(built, target)
    digest = sha256_of(target)
    (dist / SUMS_FILE).write_text(sums_line(target, digest) + "\n")
    return BuiltArtifact(target, version, digest)
