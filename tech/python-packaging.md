# Python packaging: setuptools, build, wheels and checksums

## What it is

**Packaging** turns your source folder into a file other people can install. A **wheel** (`.whl`) is the standard built package: a zip file with a fixed layout plus metadata, ready to unpack into an environment. `setuptools` is the library that knows how to assemble one; `build` is a small tool that calls it; `wheel` is the helper that writes the format. A **checksum** (here SHA-256) is a fingerprint of a file: change one byte and it changes. `shasum -a 256` (macOS) and `sha256sum` (Linux) print it. Pinned: build 1.6.1, setuptools 84.2.1, wheel 0.48.0.

## Why this repository uses it

The lesson says: **build once**. One job builds the wheel and publishes its checksum. Every later job uses that same file and verifies the checksum first. A **reproducible** build gives the same bytes for the same commit, so two builds can be compared.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | `[build-system]`, `[project]` (name, version, scripts), `[tool.setuptools.packages.find]`. |
| `pipeline/adapters/builder.py` | `build_wheel`: stamps the version, runs `python -m build`, writes `dist/SHA256SUMS`. |
| `pipeline/core/version.py` | `0.1.0+<commit>` version rules. |
| `pipeline/core/checksum.py` | Computes and verifies SHA-256. |
| `Makefile` | `build`, `verify`, `test-artifact`. |
| `.github/workflows/ci.yml` | `build` job uploads `dist/`; `integration` verifies and installs it. |

## How it works underneath

- `[build-system]` in `pyproject.toml` names the tool that builds the project: `requires = ["setuptools>=75", "wheel"]`, `build-backend = "setuptools.build_meta"`.
- `python -m build --wheel` builds in an isolated environment by default; the pipeline passes `--no-isolation` to use the locked tools already installed.
- A wheel's file name is `name-version-pythontag-abitag-platformtag.whl`. This one is pure Python: `...-py3-none-any.whl`.
- Inside are the package files and a `.dist-info` folder with `METADATA`, `WHEEL`, `entry_points.txt` and `RECORD` (a list of file hashes).
- **Reproducible builds**: zip files store file times. If those times come from "now", two builds differ. `SOURCE_DATE_EPOCH` is a standard environment variable; build tools use it as the time to write. Setting it to the commit time makes the output depend only on the commit.
- A **version** `0.1.0+3fa91bc` has a **local version label** after `+`. It is valid in Python's version rules (PEP 440), and it names the commit.

## Walkthrough of this repository's use

### `pyproject.toml`

```toml
[project.scripts]
small-service = "small_service.interfaces.cli:main"
```
At install time, pip creates an executable `small-service` that imports the module `small_service.interfaces.cli` and calls `main()`.

### `pipeline/adapters/builder.py`

```python
sha = git.head_sha(root)
version = build_version(base_version((root / "pyproject.toml").read_text()), sha, git.is_dirty(root))
```
Read the base version from `pyproject.toml`, add `+<7 characters of the commit>`, and `.dirty` if there are uncommitted changes.

```python
with tempfile.TemporaryDirectory(prefix="wheel-build-") as workdir:
    staging = Path(workdir) / "source"
    shutil.copytree(root / "src", staging / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    for name in ("README.md", "LICENSE"):
        shutil.copy2(root / name, staging / name)
    (staging / "pyproject.toml").write_text(stamp_pyproject((root / "pyproject.toml").read_text(), version))
```
Build from a **copy** in a temporary folder, with the version line replaced. The working tree is never modified, and stray folders like `__pycache__` cannot leak into the wheel.

```python
run_output(
    [python, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out), str(staging)],
    root,
    env={"SOURCE_DATE_EPOCH": str(git.commit_epoch(root, sha))},
)
```
`--wheel` skips the source archive. `--outdir` says where to put the file. `SOURCE_DATE_EPOCH` is the commit's time in seconds.

```python
digest = sha256_of(target)
(dist / SUMS_FILE).write_text(sums_line(target, digest) + "\n")
```
`dist/SHA256SUMS` has one line, `<64 hex characters>  <file name>`, in the format `shasum -c` understands.

### `pipeline/core/checksum.py`

```python
def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
```
Reads the file in 1 MiB pieces and feeds a running hash, so a large file never sits in memory. `"rb"` is "read bytes". `verify` compares to the expected digest and raises `ChecksumMismatchError` on any difference. The `integration` job runs `python -m pipeline verify` before it installs anything.

### The Makefile

`make verify` runs `cd dist && shasum -a 256 -c SHA256SUMS` (the plain system tool). `make test-artifact` verifies, builds a second environment, runs `pip install --no-deps --force-reinstall $(WHEEL)` and sets `ARTIFACT_TESTS=1`.

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
