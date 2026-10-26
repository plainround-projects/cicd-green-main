"""Run by the pipeline's integration job (ARTIFACT_TESTS=1): the tests exercise the installed wheel, not the sources."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

import small_service
from small_service.interfaces import cli


def test_the_package_under_test_is_the_built_wheel(running_against_the_artifact):
    if not running_against_the_artifact:
        pytest.skip("set ARTIFACT_TESTS=1 (the pipeline does) to require the installed wheel")
    assert "site-packages" in Path(small_service.__file__).parts
    assert "+" in importlib.metadata.version("cicd-green-main"), "a pipeline build carries the commit in its version"


def test_the_smoke_command_runs_a_job_twice_and_reads_it_back(settings, capfd):
    assert cli.main(["smoke"]) == 0
    assert "first_cached=False second_cached=True stored=1" in capfd.readouterr().out


def test_the_installed_command_reports_its_version():
    result = subprocess.run(
        [str(Path(sys.executable).parent / "small-service"), "version"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == cli.installed_version()
