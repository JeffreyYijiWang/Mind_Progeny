# Installation and reproducibility

Tested here: Windows, CPython 3.11.9, package versions in `locks/windows-py311.txt`.
The project allows Python 3.11–3.13, with 3.11 the reproducible reference. Platform
matrix CI is supplied but macOS/Linux results were not observed in this session.

## Windows

Install Python 3.11 with the Python launcher. Run `scripts/bootstrap.ps1` from PowerShell.
The script creates a private `.venv` and installs Python packages only. Windows Store
Python may require execution outside a restricted shell sandbox. A pip 24 build-isolation
subprocess initially failed certificate verification here; upgrading pip using Windows
trust (`--use-feature=truststore`) fixed it. Do not disable TLS verification.

For the exact tested environment, create a fresh Python 3.11 venv, install
`-r locks/windows-py311.txt`, then `pip install --no-deps -e .`. The editable application
is kept separate from the dependency freeze so no absolute checkout path is in the lock.

## macOS / Linux

Install Python 3.11 with working venv/pip support, then run `sh scripts/bootstrap.sh`.
Use `.venv/bin/python` and `.venv/bin/jupyter-lab`. On Debian/Ubuntu, the distro's
Python venv package may be needed; on macOS a Python.org installer or package manager
Python can supply it. Use the pinned direct dependencies on these platforms, then
record a separate full `pip freeze --all` after successful CI. The Windows lock contains
platform-specific packages and is not a universal cross-platform lock.

## External applications

Use `scripts/setup-tools.ps1 -Install` on Windows or `sh scripts/setup-tools.sh --install`
on macOS/Linux. Individual `setup_inkscape.py` and `setup_prusaslicer.py` wrappers are
also supplied. See [application setup](application-setup.md) for prerequisites, command
plans, executable registration and the 45-image integration test. They are not installed
by requirements.txt and missing executables do not break the offline core.

| Application | Windows | macOS | Linux |
|---|---|---|---|
| Inkscape | Official installer; bin/inkscape.com | Official app bundle | Official distro/package distribution |
| PrusaSlicer | Official installer, prusa-slicer-console.exe | Official app bundle | Official distribution; a wrapper may be needed for a sandboxed package |
| FFmpeg / ffprobe | Build listed by FFmpeg's download page; add bin to PATH | Install a supported distribution/build | Distribution packages or supported build |

Doctor searches PATH and common Windows/macOS app paths. Override exact binaries with
`BIOPRINTER_INKSCAPE`, `BIOPRINTER_PRUSA_SLICER`, `BIOPRINTER_FFMPEG` and
`BIOPRINTER_FFPROBE`. Overrides are executable paths, never interpolated shell commands.
Paths with spaces/Unicode are passed as subprocess argument arrays with timeouts and
checked status. PrusaSlicer captures config, full command arguments and logs. When its
installed CLI lacks required flags, it fails explicitly for adapter review.

Inkscape 1.4.4 and PrusaSlicer 2.9.6 are installed and CLI-tested on this Windows laptop.
The native Inkscape `object-trace` adapter verifies raster-free paths, with a hole/island/
orientation fixture. Plain-SVG export alone does not trace a bitmap. Executables without
that action require a manual Trace Bitmap → remove raster → Plain SVG round-trip.

FFmpeg 7.1 (Windows Gyan essentials build) and ffprobe 7.1 were found. H.264 MOV and
duration verification ran successfully. The PNG/SVG display frame renderer uses Pillow
and the same strict vector parser, so it has no Cairo/browser/native-renderer dependency.

## Locks and upgrades

`pyproject.toml` pins all direct runtime dependencies. Development dependencies are pinned
in `requirements-dev.txt`. `locks/windows-py311.txt` pins the entire tested environment,
including build tools, but does not pin wheel hashes; wheel artifacts can differ across
platforms. For archival supply-chain reproduction, download the lock's wheels into a
separate wheelhouse, record SHA-256 for each, and install with `--no-index --find-links`.
Do not claim a hash-locked universal environment. Regenerate a platform lock only after
the tests and fresh notebook pass; record Python/OS and external executable versions.
`scripts/build_artifacts.py` regenerates notebook source and clears saved outputs, so
run `scripts/execute_notebook.py` after it to restore verified example output.
