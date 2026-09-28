# Bioprinter: images to syringe motion

An offline Python application and Jupyter notebook for a Duet 2 syringe printer.
It traces real vector geometry, preserves holes, creates meshes and toolpaths,
composes overlap-aware or planar stacks in four quadrants, and exports audited
G-code, motion previews, display timelines and optional MOV video.

Each quadrant has **4 in X × 5 in Y** available (101.6 × 127 mm). The centered 2×2
planning area is **8 × 10 in** (203.2 × 254 mm), before the configured edge/tool margins.
Both placement and the PrusaSlicer bed use the profile's XY bounds.

**The included profile and example jobs are synthetic previews.** The actual bore,
barrel, calibration, Z limits, holder envelope and motion limits have not been measured.
The demo deliberately includes uneven support and reports those regions. Production
export/upload/start requires a measured profile and no unresolved support diagnostics.

## Open and run

From `bioprinter/` on Windows:

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe -m jupyterlab notebooks/image_to_syringe_pipeline.ipynb
```

For the environment created during this implementation, skip bootstrap. Select its
Python kernel and **Run All**. Saved example outputs are already in the notebook.
Run All never contacts the printer. The notebook includes folder/order controls and
an explicit cancellable offline batch widget.

```powershell
.\.venv\Scripts\python.exe -m bioprinter doctor
.\.venv\Scripts\python.exe -m bioprinter demo --video
.\.venv\Scripts\python.exe -m pytest -q
```

POSIX: run `sh scripts/bootstrap.sh` and use `.venv/bin/python`.
Python 3.11/Windows is the tested environment; other platforms have CI configuration
but were not executed here. External Inkscape/PrusaSlicer/FFmpeg are separate installs.

Install both graphical applications with the OS-aware setup script:

```powershell
.\scripts\setup-tools.ps1 -Install
# Or individually:
.\.venv\Scripts\python.exe scripts/setup_inkscape.py --install
.\.venv\Scripts\python.exe scripts/setup_prusaslicer.py --install
```

macOS/Linux: `sh scripts/setup-tools.sh --install`. Without `--install` (PowerShell:
without `-Install`), setup only reports a plan. It uses WinGet on Windows, Homebrew
casks on macOS, and existing Flatpak or a supported distro package manager on Linux.
See [application setup and dataset tests](docs/application-setup.md) for prerequisites,
logs, executable registration, and the delivered 45-image report.

The updated [45-image comparison report](validation/dataset-runs/45-image-integration/quadrant-4x5in-verified/report.html)
fits each independent image into one 4 × 5 inch quadrant, preserving aspect ratio.
The synthetic 4 mm margins leave **93.6 × 119 mm**. Cards compare original images,
actual toolpaths and the earlier 40 mm test, with filters for failures and detail loss.
This explicit diagnostic fit does not change stack-layer registration.

## Your own inputs

```powershell
.\.venv\Scripts\python.exe -m bioprinter compose C:\path\to\pictures --profile profiles/synthetic.yaml --width-mm 24
.\.venv\Scripts\python.exe -m bioprinter compose examples/inputs --profile profiles/synthetic.yaml --width-mm 24 --manifest examples/order.json
.\.venv\Scripts\python.exe -m bioprinter vectorize picture.png traced.svg --width-mm 24
.\.venv\Scripts\python.exe -m bioprinter slice traced.svg raw.gcode --profile profiles/synthetic.yaml --width-mm 24 --backend direct
.\.venv\Scripts\python.exe -m bioprinter simulate runs/RUN_DIRECTORY
.\.venv\Scripts\python.exe -m bioprinter video runs/RUN_DIRECTORY --fps 24 --width 640 --height 480
```

PNG, JPEG, TIFF, BMP and strict-subset SVG are accepted. Natural sorting puts image2
before image10. Every source is copied unchanged and hashed. Raster width is explicit
in millimeters; EXIF orientation and alpha compositing occur before thresholding.
Multi-page TIFF/animated images must be split into individual files.

`--manifest` accepts `order`, `sequences` and `per_image`; see `examples/order.json`.
Per-image options include width_mm, threshold, invert, denoise (odd median kernel),
min_area_mm2, simplify_mm, background and a 3×3 registration_matrix. Shared-canvas
registration requires matching common canvases. Never independently resize stack
layers just to fill quadrants. Use `--anchor`, `--registration`, `--repeats`, `--mode
planar_stack`, `--schedule complete_stack`, `--recursive`, `--perimeters` and `--infill`
for explicit alternatives. Default is a common scale, bottom-left local anchor,
overlap-aware stacking, clockwise round robin starting top-right.

Existing SVG bypasses tracing. `--vectorizer inkscape` uses Inkscape's native
`object-trace` action, fixture-tested on Windows with 1.4.4. Older versions without
that action require a manual tracing round-trip; it never silently runs Python.
`--backend prusa` uses the mesh adapter and records exact executable/config/argv.
The real PrusaSlicer 2.9.6 CLI was tested using synthetic geometry/dimensions.
This does not confirm the actual needle bore or compatibility with 0.5 mm deposition.
Raw slicer files are untrusted and cannot be uploaded through this application.

## What each run contains

Every run gets a collision-resistant UTC timestamp/UUID directory. The manifest links
original hashes, normalized SVGs, watertight STL meshes, raw slices, calibrated motions,
transform matrices/inverses, final byte ranges, display events and dependency versions.
The run contains:

- `combined/combined.gcode`: one coherent file with relative calibrated E and no homing.
- `jobs/` plus `timing/jobs.json`: ordered jobs with predecessor, pose, material and height
  preconditions. Only the first is standalone; later jobs require earlier physical deposits.
- `quadrants/`: zero-padded SVGs in each quadrant's print sequence.
- `previews/plate.png`, `motion3d.html`, `display_player.html`: local previews with no CDN.
- `timing/display_timeline.json`: exact combined-file byte/line intervals and estimated timing.
- `checkpoints/`: conservative height grids, for inspection only, never automatic print resume.
- `reports/`: cleanup decisions, support diagnostics, source mapping and capability probes.
- `video/display.mov` when explicitly requested, plus ffprobe duration verification.

Previews and demonstration outputs are under `examples/run/`; `examples/latest.json`
points to the delivered run. The asymmetric L, transparent ring and disconnected bridge
images overlap partially and are repeated in all four quadrants.

## Printer controls

Read [calibration](docs/calibration.md), [machine profiles](docs/machine-profile.md) and
[Duet operations](docs/duet.md) first. Copy the real profile, fill measurements and
individual confirmations, review the actual firmware/tool setup, then compose using
`--production`. This does not modify machine settings. The app will refuse synthetic
profiles, missing confirmations, changed export bytes and unresolved support diagnostics.

Status, upload and start are separate explicit `duet` commands. The default is
`http://hans.local`; an IP/custom port/base URL can be supplied. No automatic network
discovery, Wi-Fi changes, homing, firmware edits or heater/fan commands are generated.
Standalone RRF does not provide authoritative cancellation flags, so queued successors
wait for operator confirmation of successful physical completion.

See [supported features and limitations](docs/features.md), [setup](docs/setup.md),
[decision record](docs/decisions/0001-offline-first.md), [official references](docs/references.md),
and [validation evidence](VALIDATION.md).
