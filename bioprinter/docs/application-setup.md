# Inkscape and PrusaSlicer setup and local testing

Run these commands from `bioprinter/`. The setup scripts use Python's standard library
and do not modify the root training environment. Installation is explicit; imports,
doctor, tests and notebook execution never install applications.

## Windows

```powershell
.\scripts\setup-tools.ps1 -Install
# One application at a time:
.\.venv\Scripts\python.exe -X utf8 scripts/setup_inkscape.py --install
.\.venv\Scripts\python.exe -X utf8 scripts/setup_prusaslicer.py --install
```

Requires Python 3.11+ and Microsoft's App Installer/WinGet. The wrapper prefers this
project's `.venv`, otherwise `py -3.11`. Setup uses exact package IDs
`Inkscape.Inkscape` and `Prusa3D.PrusaSlicer`, the `winget` source, and normal installer
hash verification. It accepts package/source agreements when explicitly installing.
Windows may show an administrator prompt from an official installer. No hash, TLS,
SmartScreen or execution-policy bypass is used.

The applications were installed on this laptop and verified on 2026-09-28 UTC:
Inkscape **1.4.4 (dcaf3e7, 2026-05-05)** and **PrusaSlicer 2.9.6**. See
`validation/installations/` for installer logs, exact commands and version probes.
They are available in the Windows Start menu; CLI paths are registered locally.

## macOS and Linux

```sh
sh scripts/setup-tools.sh --install
# Or one at a time:
python3 scripts/setup_inkscape.py --install
python3 scripts/setup_prusaslicer.py --install
```

On macOS, install [Homebrew](https://brew.sh/) first. The script uses the
[Inkscape cask](https://formulae.brew.sh/cask/inkscape) and
[PrusaSlicer cask](https://formulae.brew.sh/cask/prusaslicer). Homebrew selects the
compatible architecture/version; unsupported systems fail with the package-manager log.

On Linux, existing Flatpak is preferred, with a per-user Flathub remote and applications
`org.inkscape.Inkscape` / `com.prusa3d.PrusaSlicer`. This follows the
[Prusa installation guidance](https://help.prusa3d.com/article/install-prusaslicer_1903).
Otherwise apt-get, dnf, pacman or zypper installs distro packages. Non-root distro
installation uses sudo. Package availability/version depends on the distribution;
the script reports failures without silently changing repositories.

Flatpak gets project-local executable wrappers in `.tools/launchers/`, with workspace
and `/tmp` access for CLI artifacts. Keep artifacts under this project. No persistent
Flatpak permission override is installed. These OS branches have command-plan tests;
**macOS/Linux installation and runtime were not executed on this Windows laptop**.

## Plans, reruns and discovery

Omit `--install` (PowerShell `-Install`) for a plan only. Existing detected applications
are skipped and reprobed during installation. `--upgrade --install` upgrades existing
Windows/macOS applications; Linux follows its package manager's normal install behavior.
Reports/logs live in `validation/installations/`. The ignored `external-tools.local.json`
registers verified binaries for the pipeline. Environment overrides take precedence:
`BIOPRINTER_INKSCAPE` and `BIOPRINTER_PRUSA_SLICER` are executable paths, not shell strings.

## Repeat the offline fixture and 45-image test

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/verify_external.py --output validation/new-fixture
.\.venv\Scripts\python.exe -X utf8 scripts/inspect_image_archive.py "C:\Users\Jeffr\Downloads\DATA SET-20260926T223837Z-1-001.zip" --output validation/dataset-runs/new-inputs
.\.venv\Scripts\python.exe -X utf8 scripts/test_image_dataset.py validation/dataset-runs/new-inputs/inputs --output validation/dataset-runs/new-results
```

Use fresh output folders. Extraction validates all paths, count, size limits and ZIP
CRCs; it hashes and retains originals. No archive instructions or executables are run.
The fixture asserts holes, islands, Cartesian Y orientation, mesh closure, actual slicer
placement, one layer, thermal/fan cleanup, and rejection of a 0.5 mm layer with an
incompatible synthetic 0.3 mm nozzle. It deliberately uses a separate invented 0.8 mm
nozzle for the compatible test; no real hardware dimensions are inferred.

The batch uses native Inkscape Potrace after documented grayscale/threshold preprocessing,
then watertight STL export, actual PrusaSlicer execution, strict G-code parsing and
synthetic volume conversion. Exact SVG, mesh, INI, commands, logs and per-image JSON
remain in each numbered folder. Raw G-code is **not a printer-ready syringe job**.

The delivered run is `validation/dataset-runs/45-image-integration/native-800px/report.html`.
It tests each image independently at 40 mm canvas width, 0.5 mm layer height, synthetic
0.8 mm slicer nozzle, nominal 1 mm bead, one perimeter and 20% infill. Working copies
are limited to 800 pixels on the longest side, then median-filtered (3), thresholded
(128), filtered at 0.01 mm² island area and simplified to 0.05 mm. Originals stay intact.
Different aspect ratios are not treated as registered layers. Small/thin details can
disappear, and a successful slice is not a printability or liquid-stability approval.

The initial full-resolution, two-worker attempt hit the laptop's committed-memory
limit and was stopped; logs are retained in `native-test/`. The successful-processing
strategy uses one worker and explicit smaller working images. No OS memory settings
or unrelated processes were changed. No test contacts a printer.

`--resume-tests` can continue this diagnostic batch after checking completed input hashes,
ordering and settings. It retains incomplete attempts in their original folders and writes
retries to new folders. This option belongs only to the application test runner; it cannot
resume a printer, compose a production job or authorize reuse of a physical checkpoint.

For a completed batch, generate original-image thumbnails, a result contact sheet and a
compact summary with `scripts/finalize_dataset_report.py RUN --inventory INVENTORY.json
--summary SUMMARY.json`. The delivered compact result is `validation/dataset-45-summary.json`.

Inkscape action semantics were checked against its
[official implementation](https://gitlab.com/inkscape/inkscape/-/blob/INKSCAPE_1_4_3/src/actions/actions-object.cpp).
The seven trace arguments create two-color, stacked, background-removed paths. Selection
is cleared before deleting the embedded source image; output must contain real paths
and no raster image. Only empty authoring `defs` are removed before strict SVG import.
