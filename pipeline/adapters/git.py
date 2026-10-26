"""The few git facts the pipeline needs."""

from __future__ import annotations

from pathlib import Path

from pipeline.adapters.process import run_output


def head_sha(repo: Path) -> str:
    """Full SHA of HEAD."""
    return run_output(["git", "rev-parse", "HEAD"], repo).strip()


def commit_epoch(repo: Path, sha: str) -> int:
    """Commit time of `sha` in seconds since the epoch: the fixed clock for a reproducible build."""
    return int(run_output(["git", "show", "-s", "--format=%ct", sha], repo).strip())


def is_dirty(repo: Path) -> bool:
    """True when tracked files changed or untracked files exist that git does not ignore."""
    return bool(run_output(["git", "status", "--porcelain"], repo).strip())


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    """Files changed between two commits (three-dot: since `head` branched from `base`)."""
    return run_output(["git", "diff", "--name-only", f"{base}...{head}"], repo).split()
