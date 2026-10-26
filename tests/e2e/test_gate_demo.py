"""The protected-main scenario end to end, in temporary git repositories (no network, no database)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.e2e


def test_the_gate_demo_refuses_what_a_protected_main_refuses_and_accepts_the_green_merge():
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"}
    result = subprocess.run(
        [str(ROOT / "scripts" / "gate-demo.sh")], capture_output=True, text=True, env=env, check=False, timeout=300
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("-> refused") == 6
    assert "-> accepted" in result.stdout
    assert "GH006 protected branch: required status checks have not passed" in result.stdout
    assert "the branch is not up to date" in result.stdout
    assert "only CI may post a status" in result.stdout
    assert "all six behaviors confirmed" in result.stdout


def test_changes_script_skips_only_documentation_changes(tmp_path):
    def git(*args: str) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
        }
        return subprocess.run(
            ["git", *args], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
        ).stdout.strip()

    def decide(base: str, head: str) -> str:
        result = subprocess.run(
            [str(ROOT / "pipeline" / "changes.sh"), base, head],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("doc\n")
    (tmp_path / "README.md").write_text("readme\n")
    git("add", ".")
    git("commit", "-qm", "docs only")
    docs_only = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text("x = 2\n")
    git("commit", "-qam", "code")
    assert decide(base, docs_only) == "code=false"
    assert decide(base, "HEAD") == "code=true"
    assert decide("", "HEAD") == "code=true"
    assert decide("0" * 40, "HEAD") == "code=true"
    assert decide("f" * 40, "HEAD") == "code=true"
