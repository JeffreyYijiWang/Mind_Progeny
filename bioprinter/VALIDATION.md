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
- Inkscape and PrusaSlicer were not installed; manual tracing and actual slicer CLI/profile
  integration remain unverified. The direct polygon backend is the exercised route.
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
