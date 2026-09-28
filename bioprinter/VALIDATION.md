# Validation performed

Validated on 2026-09-28 UTC (2026-09-27 EDT at task start), using Python 3.11.9
on Windows-10-10.0.26200-SP0. Feature branch: `codex/bioprinter`.

## Executed checks

- `.venv/Scripts/python.exe -m pytest -q --junitxml=validation/pytest.xml`:
  **69 passed**, 0 failures, 0 errors,
  0 skipped. Includes fake HTTP Duet, local FFmpeg and a fresh notebook kernel.
- `.venv/Scripts/python.exe scripts/execute_notebook.py`: all **11 code cells** executed
  with external HTTP disabled; outputs saved in the delivered notebook. The test suite
  repeats this end-to-end execution through that same script.
- `.venv/Scripts/python.exe scripts/export_example.py`: three distinct generated images,
  intentional hole and disconnected island, partial overlap, **12 segments in all four quadrants**.
  It exported combined/continuation G-code, hashes, SVG/STL, height checkpoints, byte-mapped
  timeline, static/interactive previews, local display player and an H.264 MOV.
- Final run `preflight(production=False)` passed all stored-file hashes and output allowlist checks.
- `python -m pip check`: No broken requirements found.
- `git diff --check`: passed for tracked changes (existing root-file CRLF notices only).

The final tests cover contour holes/islands/transparency/blank/multipage inputs, five
anchors/inverses/Y orientation/shared canvases, SVG units/strokes/unsafe XML, watertight
mesh volume, modal XYZ/E and reset handling, explicit arc/macro/tool/unknown rejection,
thermal off-command cleanup, calibrated volume/direction/capacity, syringe rate caps,
local sparse overlap heights, holder/needle/Z/XY collisions, scheduling/exhausted lists,
continuation state, exact byte ranges and JSON Schema, pause-aware display, timing
fixtures with independently calculated durations, MOV frame rounding, authentication,
disconnect/cancellation/fault/duplicate-start handling and operator-confirmed completion.

Matplotlib emits 14 pyparsing deprecation warnings with this environment; they did not
affect generation/tests. No warnings were suppressed. Full JUnit: `validation/pytest.xml`.
Environment versions: `locks/windows-py311.txt`, `validation/doctor.json`, and each manifest.

## Delivered example

Run: `examples/run/20260928T031615.014227Z_e8911341` (also recorded in `examples/latest.json`).
Estimated timeline **449.443514 s**. ffprobe MOV duration
**449.500000 s**; difference **0.056486 s**,
within the declared **0.501 s** tolerance at 2 fps.
This duration agreement validates video encoding against the estimate, not printer timing.

The example has 8 production-blocking uneven-support event reports.
They are intentional evidence that partial overlap is modeled and diagnosed; the synthetic
preview is not an approved physical print. No real calibration or liquid stability is implied.

## Not verified / unresolved

- No contact with `hans.local`, real printer motion, uploads, cold-extrusion settings,
  firmware/tool configuration or real queue completion was performed.
- Inkscape/PrusaSlicer were absent during the initial 69-test validation above.
  The follow-up installed Inkscape 1.4.4 / PrusaSlicer 2.9.6 and tested their Windows
  CLIs with synthetic geometry. See [application setup](docs/application-setup.md)
  and the follow-up evidence below. Real needle compatibility remains unresolved.
- Windows is the only observed platform. Linux/macOS matrix CI is added but not run here.
- Actual needle bore/OD, barrel diameter, plunger calibration/direction/usable stroke,
  capacity, bead width/spread, first-tip/substrate/standoff Z, safe XY/Z/E rates and
  accelerations, Z range, margins and holder geometry remain unresolved.
- Real firmware version, selected tool, cold-extrusion and machine/macro review are required.
  The two confirmed fields remain 23 gauge and 12.7 mm needle length from the supplied brief.
- Standalone RRF does not prove successful completion from idle; operator reconciliation
  gates queued successors. Live display is approximate processed-byte observation, not
  executed-segment synchronization. Raster centerline/outline extraction and automatic
  physical recovery/refill are not implemented; unsupported features reject explicitly.

Full scope/boundaries: [supported feature matrix](docs/features.md). Required setup and
calibration steps: [machine profile](docs/machine-profile.md), [calibration](docs/calibration.md).
The original attached implementation brief is preserved in `docs/implementation-brief.md`.

## External application follow-up

2026-09-28 UTC, branch `codex/bioprinter-setup`, same private Windows/Python environment.

- Installed **Inkscape 1.4.4 (dcaf3e7, 2026-05-05)** and **PrusaSlicer 2.9.6** using
  WinGet's official installer sources and SHA-256 verification. Actual commands, logs,
  probes and the local doctor report are under `validation/installations/`.
- `.venv/Scripts/python.exe -X utf8 -m pytest -q --junitxml=validation/pytest-setup.xml`:
  **91 passed**, 0 failures/skips, 14 existing Matplotlib/pyparsing deprecation warnings.
  Includes fresh execution of all 11 notebook code cells, installer plan-only behavior,
  Windows/macOS/Linux command selection, Flatpak quoting, ZIP path normalization,
  stale-output rejection, missing slicer output, and spatial/exhaustive winding equivalence.
- `scripts/verify_external.py --output validation/integration-fixture/verified-final`:
  passed real installed-binary assertions for two islands, a preserved hole, asymmetric
  Y orientation, 44 watertight mesh triangles, one 0.5 mm layer, preserved XY placement,
  80 deposition moves, no deposition crossing the hole, and audited thermal/fan removal.
  The invented 0.8 mm test nozzle succeeded; 0.3 mm rejected the 0.5 mm layer.
  PrusaSlicer returned zero for that rejection but created no output: the adapter now
  requires fresh output and includes its diagnostic text, rather than trusting exit code.
- `pip check`: no broken requirements. `git diff --check`: passed.
- The supplied ZIP contains exactly 45 readable, CRC-checked images. Originals, hashes,
  inventory, per-image native traces/meshes/slices/logs, HTML report and contact sheets
  are retained in `validation/dataset-runs/45-image-integration/`. Compact results are
  in `validation/dataset-45-summary.json`.

Completed dataset result: **45/45 checked**, **44 native traces**, **37 slices with parsed
deposition paths**. Five slices were empty at the chosen width/bead settings; one faint
input became blank after preprocessing; two valid 2D polygons had point-touching boundaries
whose extrusions created vertical edges shared by four faces (nonmanifold meshes, rejected).
The diagnostics identify 35/37 completed slices with at least one island lacking nearby
extrusion; 4,318 islands total under the nominal-footprint diagnostic. The report therefore
does not equate a completed slice with faithful detail preservation or physical printability.

The original full-resolution/two-worker attempt exhausted Windows committed memory and
was stopped. The reported batch uses single-worker execution, 800 px maximum working
dimension, explicit 40 mm canvas width, threshold 128, median 3, 0.01 mm² minimum islands,
0.05 mm simplification, one 0.5 mm layer, invented 0.8 mm slicer nozzle, nominal 1 mm
bead and 20% infill. Originals are unchanged. Completed diagnostic results were reused
after hash/settings checks while geometry-performance fixes were applied; interrupted
attempts were retained, and retries used fresh folders. The final report records stages
and failures, rather than treating every image as printable.

Successful CLI execution can still lose thin details/islands. These independently scaled
images are not registered stack layers or approved printer jobs. No GUI interaction,
macOS/Linux runtime, physical printer, actual needle calibration or liquid behavior was
tested. Existing hardware/queue restrictions above remain in force.

## Quadrant dimension correction

2026-09-28: user specified 4 in X × 5 in Y per quadrant. Profiles/schema now use
X ±101.6 and Y ±127 mm; layout and PrusaSlicer bed derive from the active profile.
New checks cover all four quadrant sizes, a 90 × 110 mm placement, margin/oversize
rejection, custom-profile bounds and exported slicer bed coordinates.

`pytest -q --junitxml=validation/pytest-quadrant-dimensions.xml` passed **97 tests**;
the notebook subprocess failed on Windows committed-memory exhaustion (a 1.57 MiB
allocation failed). The notebook was then run separately using
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` in that process environment:
`python -X utf8 scripts/execute_notebook.py` successfully executed and saved all
**11 code cells** with external HTTP disabled. No system memory settings were changed.
`git diff --check` passed. Historical dataset/example artifacts were not rescaled or
rewritten; the 45-image report still describes its original 40 mm-wide test images.

## Updated quadrant image report

2026-09-28 UTC: reran all **45 images** with explicit independent aspect-preserving
fits inside each 4 × 5 inch quadrant. Synthetic 4 mm margins leave **93.6 × 119 mm**;
actual traced geometry is centered in Q1. Same native application versions and
800 px / threshold 128 / median 3 / 0.01 mm² / 0.05 mm preprocessing settings as
the 40 mm baseline. Slicing remains one 0.5 mm layer, invented 0.8 mm nozzle,
nominal 1 mm bead, one perimeter and 20% infill. Exact commands are in each image
folder under `validation/dataset-runs/45-image-integration/quadrant-4x5in-verified/`.

Results: **44 native traces**, **40 generated and parsed toolpaths**, **5 stopped**.
Images 1 and 13 produced empty slices; image 12 became blank after preprocessing;
images 26 and 41 failed the watertight mesh check. Compared with the 37/45 baseline,
images 11, 15, 16 and 23 now generated paths, while image 26 newly failed the mesh
check. All failures remain visible, including the new failure. 37/40 generated
results have missing islands (7,455 total). More geometry survives the fixed area
threshold at the larger scale, so island counts alone are not a direct measure of
improved fidelity. Uncovered area also includes intentional 20% infill gaps.

The updated HTML shows original images, quadrant/margin previews, physical sizes,
per-image baseline comparisons and filters for stopped/generated/coverage flags.
The unchanged baseline JSON is hash-verified; its old HTML is preserved as
`native-800px/report-40mm.html`. The original `native-800px/report.html` entry point
now forwards to the updated report. Summaries: `validation/dataset-45-summary.json`
(baseline) and `validation/dataset-45-quadrant-summary.json` (updated).

An initial parallel invocation returned without a new SVG; unique Inkscape
`--app-id-tag` values now isolate native traces and missing output fails explicitly.
Another trace extended slightly beyond its image canvas: image 2 was retried with
a recorded uniform factor of 0.9996804074, without clipping. Interrupted attempts
were retained. Completed results were reused after hash/order/settings checks.
The final run used two workers and process-local `OPENBLAS_NUM_THREADS=1` and
`OMP_NUM_THREADS=1`; no system settings or unrelated processes were changed.

Verification:

- `python -X utf8 -m pytest tests/test_dataset_report.py tests/test_quadrant_dimensions.py tests/test_external_contracts.py tests/test_geometry.py -q --junitxml=validation/pytest-report-update.xml`:
  **33 passed**. Covers aspect-preserving fit, actual tracer overshoot, all quadrant
  dimensions, native instance isolation, geometry and report content/link escaping.
- All 45 original source hashes and unchanged baseline JSON hash verified; all 44
  traced bounds fit the margin rectangle. HTML contains 45 cards, 85 image assets
  and 256 existing local references. Audit: `validation/dataset-45-quadrant-audit.json`.
- Generated contact sheet and a full-size quadrant preview inspected directly.
  Browser automation rejected the local `file:` URL, so rendered HTML layout and
  filter clicks were not GUI-tested; no alternate browser access was attempted.
- `git diff --check` passed. No printer contact or physical printability test.
