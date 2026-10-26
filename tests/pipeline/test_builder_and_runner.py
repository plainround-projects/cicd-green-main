import json
import subprocess
import sys
from pathlib import Path

import pytest
from pipeline.adapters import builder, git, local_runner
from pipeline.adapters.process import Command, Job, run_job

from pipeline import cli

PYPROJECT = """[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demo-pkg"
version = "0.1.0"

[tool.setuptools.packages.find]
where = ["src"]
"""


def git_run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src" / "demo_pkg").mkdir(parents=True)
    (tmp_path / "src" / "demo_pkg" / "__init__.py").write_text("VALUE = 1\n")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "README.md").write_text("demo\n")
    (tmp_path / "LICENSE").write_text("MIT\n")
    (tmp_path / ".gitignore").write_text("dist*/\n")
    git_run(tmp_path, "init", "-q", "-b", "main")
    git_run(tmp_path, "add", ".")
    git_run(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_the_wheel_is_versioned_from_the_commit(repo):
    artifact = builder.build_wheel(repo, repo / "dist", sys.executable)
    assert artifact.version == f"0.1.0+{git.head_sha(repo)[:7]}"
    assert artifact.path.name == f"demo_pkg-{artifact.version}-py3-none-any.whl"


def test_building_the_same_commit_twice_gives_the_same_bytes(repo):
    first = builder.build_wheel(repo, repo / "dist", sys.executable)
    second = builder.build_wheel(repo, repo / "dist2", sys.executable)
    assert first.sha256 == second.sha256


def test_the_checksum_file_matches_the_wheel(repo):
    artifact = builder.build_wheel(repo, repo / "dist", sys.executable)
    assert (repo / "dist" / builder.SUMS_FILE).read_text() == f"{artifact.sha256}  {artifact.path.name}\n"


def test_an_uncommitted_change_makes_the_version_dirty(repo):
    (repo / "src" / "demo_pkg" / "__init__.py").write_text("VALUE = 2\n")
    assert builder.build_wheel(repo, repo / "dist", sys.executable).version.endswith(".dirty")


def test_a_job_runs_its_steps_in_order_and_logs_them(tmp_path):
    job = Job("demo", (Command(("echo", "one")), Command(("echo", "two"))))
    outcome = run_job(job, tmp_path, tmp_path / "logs")
    assert outcome.ok
    assert outcome.log.read_text().count("$ echo") == 2


def test_a_job_stops_at_its_first_failing_step(tmp_path):
    job = Job("demo", (Command(("false",)), Command(("echo", "never"))))
    outcome = run_job(job, tmp_path, tmp_path / "logs")
    assert not outcome.ok
    assert "never" not in outcome.log.read_text()
    assert "[exit status 1]" in outcome.log.read_text()


def test_a_step_sees_the_environment_it_was_given(tmp_path):
    job = Job("demo", (Command(("sh", "-c", "echo $PIPELINE_DEMO"), {"PIPELINE_DEMO": "hello"}),))
    assert "hello" in run_job(job, tmp_path, tmp_path / "logs").log.read_text()


def test_the_integration_job_is_the_make_target_that_verifies_and_tests_the_wheel(tmp_path):
    job = local_runner.integration_job(tmp_path / "dist" / "a.whl", "abc")
    assert job.steps[0].argv == (
        "make",
        "--no-print-directory",
        "test-artifact",
        f"WHEEL={tmp_path / 'dist' / 'a.whl'}",
        "EXPECTED_SHA256=abc",
    )


def test_the_unit_job_excludes_quarantined_tests_unless_asked():
    assert "UNIT_MARKERS=not flaky_quarantine" in local_runner.unit_job(False).steps[0].argv
    assert "UNIT_MARKERS=" in local_runner.unit_job(True).steps[0].argv


def test_the_digest_is_read_from_the_checksum_file(tmp_path):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / builder.SUMS_FILE).write_text("ab" * 32 + "  a-1.0.whl\n")
    assert local_runner._read_digest(tmp_path) == (tmp_path / "dist" / "a-1.0.whl", "ab" * 32)


def test_the_baseline_starts_from_a_cold_environment_and_installs_without_the_cache(tmp_path):
    steps = [" ".join(step.argv) for step in local_runner.sequential_job(tmp_path).steps]
    assert "venv --clear" in steps[0]
    assert "--no-cache-dir" in steps[1]
    assert steps[-1].endswith("-m pipeline build")


def test_the_parser_accepts_every_command():
    parser = cli.build_parser()
    for argv in (
        ["version"],
        ["build"],
        ["run"],
        ["flaky"],
        ["protection"],
        ["lint-workflows"],
        ["check-contract"],
        ["verify", "a.whl", "--expected", "ab"],
        ["gate", "--sha", "abc", "--token", "t"],
    ):
        parser.parse_args(argv)


def test_verify_exits_one_on_a_mismatch_and_zero_on_a_match(tmp_path, capsys):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    good = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert cli.main(["verify", str(artifact), "--expected", good, "--job", "integration"]) == 0
    assert f"integration: sha256 {good}  verified" in capsys.readouterr().out
    assert cli.main(["verify", str(artifact), "--expected", "00" * 32]) == 1
    assert "MISMATCH" in capsys.readouterr().err


def test_protection_prints_json_and_flaky_reads_the_log(tmp_path, capsys):
    assert cli.main(["protection"]) == 0
    assert '"contexts"' in capsys.readouterr().out
    assert cli.main(["flaky", "--runs-csv", str(tmp_path / "none.csv")]) == 0
    assert "none" in capsys.readouterr().out


def test_importing_github_runs_appends_rows(tmp_path):
    source = tmp_path / "runs.json"
    run = {
        "databaseId": 7,
        "headSha": "abcdef0123",
        "conclusion": "success",
        "createdAt": "2026-09-01T10:00:00Z",
        "updatedAt": "2026-09-01T10:02:00Z",
    }
    source.write_text(json.dumps([run]))
    csv_path = tmp_path / "runs.csv"
    assert cli.main(["import-gh-runs", str(source), "--runs-csv", str(csv_path)]) == 0
    assert csv_path.read_text().splitlines()[1].startswith("7,abcdef0,120.0,success,github")
