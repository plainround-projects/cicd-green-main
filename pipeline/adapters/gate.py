"""A local stand-in for "required status checks": CI posts a green status for a commit, and the remote refuses `main`
without it. See pipeline/hooks/pre-receive and scripts/gate-demo.sh."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pipeline.adapters.process import run_output


def run_checks_on_commit(repo: Path, sha: str, command: Sequence[str]) -> bool:
    """Check out `sha` in a throwaway worktree and run `command` there. True when it exits 0."""
    with tempfile.TemporaryDirectory(prefix="gate-") as workdir:
        tree = Path(workdir) / "tree"
        run_output(["git", "worktree", "add", "--detach", str(tree), sha], repo)
        try:
            return subprocess.run(list(command), cwd=tree, check=False).returncode == 0  # noqa: S603
        finally:
            run_output(["git", "worktree", "remove", "--force", str(tree)], repo)


def post_green_status(repo: Path, remote: str, sha: str, token: str) -> None:
    """Push `refs/status/green/<sha>` to `remote`. The remote accepts it only with the CI token as a push option."""
    run_output(["git", "push", "--push-option", f"ci-token={token}", remote, f"{sha}:refs/status/green/{sha}"], repo)
