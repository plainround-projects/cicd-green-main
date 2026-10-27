# Python packaging: setuptools, build, wheels and checksums

## What it is

To share a Python program you turn it into a **package**: a single file other people can install with `pip install`. The standard built form is the **wheel**, a file ending in `.whl`. A wheel is a zip archive with the program's files in the layout `pip` expects, plus a folder of information about the package (name, version, which commands to create). Installing a wheel is just unpacking it into a virtual environment ([pip-and-hash-locking.md](pip-and-hash-locking.md)), so it is fast and runs no build step on the user's machine. The name has the shape `name-version-pythontag-abitag-platformtag.whl`; this one is pure Python, so it ends `py3-none-any`: any Python 3 on any system.

**Building** a wheel is done by a *build backend*. `setuptools` is the oldest and most common; `wheel` is the helper that writes the file format; `build` is a small program that starts the backend correctly. Pinned here: build 1.6.1, setuptools 84.2.1, wheel 0.48.0.

A **checksum** is a fingerprint of a file: a long number computed from its bytes. This repository uses SHA-256 (64 hexadecimal characters). Two files with the same checksum are the same file. The programs `shasum -a 256` (macOS) and `sha256sum` (Linux) print it. A **reproducible build** gives *identical bytes* every time it is run on the same input, so you can check a shipped file by rebuilding it.

## Why this repository uses it

The lesson says **build once, test that exact file, ship that exact file.** One job builds the wheel and publishes its checksum; every later job downloads the same file and checks the checksum before using it. If the bytes that were tested were not the bytes that ship, the testing proves nothing.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | `[build-system]`, `[project]`, `[project.scripts]`, `[tool.setuptools.packages.find]` ([toml.md](toml.md)). |
| `pipeline/adapters/builder.py` | `build_wheel`: stamps the version into a copy, runs `python -m build`, writes `dist/SHA256SUMS`. |
| `pipeline/core/version.py` | Rules for `0.1.0+<commit>`. |
| `pipeline/core/checksum.py` | Computes and verifies SHA-256. |
| `Makefile` | `build`, `verify`, `test-artifact`. |
| `.github/workflows/ci.yml` | The `build` job uploads `dist/`; `integration` verifies and installs it. |
| `Dockerfile` | Installs the verified wheel. |

## How it works underneath

- The `[build-system]` table of `pyproject.toml` names what the build needs (`requires`) and the Python object that performs it (`build-backend`).
- `python -m build --wheel --outdir OUT DIR` builds a wheel from the project in `DIR`. By default `build` makes a throw-away environment and downloads the build tools into it (*isolation*). `--no-isolation` uses the tools already installed, which is what the locked environment provides.
- Inside the wheel: the package's files, and a `NAME-VERSION.dist-info/` folder with `METADATA` (name, version, description), `WHEEL`, `entry_points.txt` (the commands to create, from `[project.scripts]`) and `RECORD` (a list of every file with its hash). Zip files store a modification time for each file; a build that uses "now" would give different bytes on every run.
- `SOURCE_DATE_EPOCH` is a standard environment variable: if set to a number of seconds since 1 January 1970, build tools use that as the time for every file instead of the current time. Setting it to the commit's own time makes the wheel depend only on the commit.
- A version like `0.1.0+3fa91bc` has a **local version label** after the `+`, a form Python's version rules allow. It names the commit the build came from.

## Walkthrough of this repository's use

### The package definition in `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cicd-green-main"
version = "0.1.0"
description = "A small service and the CI pipeline that keeps its main branch releasable: parallel jobs, one checksummed artifact, a quarantined flaky test."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "Sumit Srivastava" }]
dependencies = ["psycopg[binary]>=3.2,<4"]
```

`[build-system]` asks for `setuptools>=75` and `wheel`, with `setuptools.build_meta` as the backend. `[project]` names the package `cicd-green-main`, version `0.1.0`, `requires-python = ">=3.12"`, the `README.md` as long description, and the runtime dependency `psycopg[binary]>=3.2,<4`. Every key is explained in [toml.md](toml.md).

```toml
[project.scripts]
small-service = "small_service.interfaces.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

`[project.scripts]` is why the installed package gives a command `small-service`. `[tool.setuptools.packages.find] where = ["src"]` tells setuptools to find packages under `src/`.

### Version rules: `pipeline/core/version.py`

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- `build_version(base, commit_sha, dirty)` first checks both inputs against patterns (`_SEMVER`: three dot-separated numbers; `_SHA`: 7 to 40 characters from `0-9a-f`). Then it returns `base + "+" + the first 7 characters of the commit` and `.dirty` if the working tree had uncommitted changes. Same commit and cleanliness: same version.
- `stamp_pyproject(text, version)` replaces the first `version = "..."` line with the new version, in the text it is given.

### Building: `pipeline/adapters/builder.py`

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Lines 33 and 34**: ask Git for the current commit and whether the tree is dirty, and compute the version.
- **Line 35**: a temporary folder that is deleted when the block ends. **Lines 36 to 40**: copy `src/` (without caches) into it, plus `README.md` and `LICENSE`, and write a copy of `pyproject.toml` with the version stamped. **The repository's own files are never modified.** That is why you can build on a clean checkout and get exactly `0.1.0+<commit>`.
- **Lines 42 to 46**: `run_output([python, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out), str(staging)], root, env={"SOURCE_DATE_EPOCH": str(git.commit_epoch(root, sha))})`: build only the wheel, with the installed tools, into `out`, with the clock fixed to the commit's time.
- **Lines 47 to 52**: take the one file built, delete older wheels in `dist/`, copy the new one there (`shutil.copy2` keeps its times).
- **Lines 53 to 55**: compute its SHA-256 and write `dist/SHA256SUMS` containing one line, `<64 hex characters>  <file name>` (two spaces), which is the format `shasum -c` reads. Return the path, version and digest.

### Checksums: `pipeline/core/checksum.py`

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- `sha256_of(path)` reads the file in one-mebibyte pieces and feeds a running hash, so a huge file never sits in memory (`while chunk := handle.read(_CHUNK)` assigns and tests in one step).
- `sums_line` and `parse_sums` write and read the `SHA256SUMS` format.
- `verify(path, expected)` compares the actual digest with the expected one, ignoring case and spaces, and raises `ChecksumMismatchError("name: expected sha256 X, found Y")` on any difference. Every job that uses the artifact calls this first.

### The Make targets

```make
build: $(STAMP) ## build the wheel once: dist/*.whl and dist/SHA256SUMS
	$(PY) -m pipeline build

verify: ## verify dist/*.whl against dist/SHA256SUMS
	cd dist && shasum -a 256 -c SHA256SUMS

```

- `make build` runs `python -m pipeline build`; it prints `build: sha256 <digest>  dist/<wheel name>`.
- `make verify` runs `cd dist && shasum -a 256 -c SHA256SUMS` with the system's own tool: an independent check of the pipeline's checksum code. It prints `<wheel name>: OK`.
- `make test-artifact` verifies the wheel with `python -m pipeline verify`, installs it into a clean environment with `pip install --no-deps --force-reinstall WHEEL` and runs the integration tests there ([make.md](make.md)).

### In CI

The `build` job runs `make build`, publishes the digest as a job output and uploads `dist/`. The `integration` job downloads the same artifact and passes the digest to `make test-artifact` ([github-actions.md](github-actions.md)). The Dockerfile copies `dist/*.whl` into the image and installs it with `--no-deps` ([docker.md](docker.md)). The tests in `tests/pipeline/test_builder_and_runner.py` check: the version is `0.1.0+<commit>`; two builds of one commit have the same SHA-256; the checksum file matches; and a changed file makes the version `.dirty` ([pytest.md](pytest.md)).

## Try it yourself

```bash
make build
ls dist
cat dist/SHA256SUMS
```
Expect one `.whl` named like `cicd_green_main-0.1.0+abc1234-py3-none-any.whl` and a one-line checksum file.

```bash
make verify
```
Prints `cicd_green_main-...whl: OK`.

```bash
first=$(cut -d' ' -f1 dist/SHA256SUMS); make build >/dev/null; second=$(cut -d' ' -f1 dist/SHA256SUMS); [ "$first" = "$second" ] && echo reproducible
```
Prints `reproducible`: the same commit gave the same bytes (on a clean tree).

```bash
python3 -m zipfile -l dist/*.whl
```
Lists the files inside the wheel.

## Mistakes people make

- Rebuilding in each job and testing a different file than the one shipped.
- Builds that embed "now", so two builds of one commit differ.
- Forgetting to verify the checksum after downloading an artifact.
- Shipping from a dirty tree. The `.dirty` label makes that visible.
- Putting the tests inside the package.

## Check yourself

1. What is a wheel? *A built, installable zip package with metadata.*
2. What does `SOURCE_DATE_EPOCH` do? *Fixes the time written into the build so the output repeats.*
3. What does the `+3fa91bc` in a version mean? *A local label that names the commit.*
4. Why does `verify` read the file in chunks? *To keep memory small for large files.*
5. Why build in a temporary copy? *The working tree stays untouched and no stray files enter the wheel.*

## Further reading

- Python Packaging User Guide: https://packaging.python.org/en/latest/
- `pyproject.toml` specification: https://packaging.python.org/en/latest/specifications/pyproject-toml/
- build: https://build.pypa.io/en/stable/ (pinned 1.6.1)
- Reproducible builds and `SOURCE_DATE_EPOCH`: https://reproducible-builds.org/docs/source-date-epoch/
- Wheel format: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
