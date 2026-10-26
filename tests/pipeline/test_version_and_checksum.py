import pytest
from pipeline.core import checksum
from pipeline.core.version import VersionError, base_version, build_version, stamp_pyproject

PYPROJECT = '[build-system]\nrequires = ["x"]\n\n[project]\nname = "demo"\nversion = "0.1.0"\n'


def test_the_base_version_is_read_from_pyproject():
    assert base_version(PYPROJECT) == "0.1.0"


def test_a_base_version_that_is_not_major_minor_patch_is_refused():
    with pytest.raises(VersionError):
        base_version(PYPROJECT.replace("0.1.0", "0.1"))


def test_the_version_carries_the_first_seven_characters_of_the_commit():
    assert build_version("0.1.0", "3fa91bcdeadbeef") == "0.1.0+3fa91bc"


def test_the_same_commit_always_gives_the_same_version():
    assert build_version("0.1.0", "3fa91bc") == build_version("0.1.0", "3fa91bc")


def test_uncommitted_changes_mark_the_version_dirty():
    assert build_version("0.1.0", "3fa91bc", dirty=True) == "0.1.0+3fa91bc.dirty"


@pytest.mark.parametrize("sha", ["", "abc", "ZZZZZZZ", "3FA91BC"])
def test_a_bad_commit_is_refused(sha):
    with pytest.raises(VersionError):
        build_version("0.1.0", sha)


def test_stamping_replaces_only_the_project_version():
    stamped = stamp_pyproject(PYPROJECT, "0.1.0+3fa91bc")
    assert 'version = "0.1.0+3fa91bc"' in stamped
    assert 'requires = ["x"]' in stamped


def test_stamping_a_file_with_no_version_is_refused():
    with pytest.raises(VersionError):
        stamp_pyproject("[project]\nname = 'x'\n", "1.0.0")


def test_the_sha256_matches_a_known_value(tmp_path):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    assert checksum.sha256_of(artifact) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_verify_accepts_the_matching_digest_in_any_case(tmp_path):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    assert checksum.verify(artifact, "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD")


def test_verify_refuses_an_artifact_that_changed(tmp_path):
    artifact = tmp_path / "a.whl"
    artifact.write_bytes(b"abc")
    expected = checksum.sha256_of(artifact)
    artifact.write_bytes(b"abd")
    with pytest.raises(checksum.ChecksumMismatchError, match="expected sha256"):
        checksum.verify(artifact, expected)


def test_sums_lines_round_trip(tmp_path):
    artifact = tmp_path / "a-1.0.whl"
    line = checksum.sums_line(artifact, "ab" * 32)
    assert checksum.parse_sums(line + "\n\n") == {"a-1.0.whl": "ab" * 32}
