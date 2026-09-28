# Bioprinter durable engineering record

Read the parent AGENTS.md. Goal: ordered pictures/SVGs -> actual polygons -> optional
PrusaSlicer mesh -> interpreted motions -> calibrated syringe -> adaptive/four-quadrant
job, timeline, preview, optional MOV. Imports and offline workflows have no network effects.

## Module map and verification

`src/bioprinter`: config (validated YAML), ingestion/archive (natural order/hash/safe ZIP), vectorization
(OpenCV hierarchy), inkscape (native object-trace), geometry (strict SVG/registration), meshing (watertight STL), slicing
(direct and probed Prusa adapter), gcode (modal interpreter/output allowlist), extrusion
(volume/stroke), layout (quadrants/schedules), stacking (height/collisions), simulation
(plots), timing/display/video, pipeline (provenance), duet (explicit HTTP/queue), cli.

From this folder: `python -m venv .venv`, then `.venv/Scripts/python -m pip install -r
requirements-dev.txt` (POSIX uses `.venv/bin/python`). `python -m bioprinter doctor`,
`python -m bioprinter demo`, `python -m pytest`, `python scripts/execute_notebook.py`.
Use the environment's Python. Exact tested dependency freeze lives in `locks/`.
Do not claim all platforms/external integrations tested; see VALIDATION.md.

Observed versions: Windows/CPython 3.11.9; NumPy 2.2.6, Pillow 11.3.0, OpenCV headless
4.12.0.88, Shapely 2.1.2, svgpathtools 1.7.1, Pydantic 2.11.7, httpx 0.28.1,
Matplotlib 3.10.5, Plotly 6.3.0, FFmpeg/ffprobe 7.1. Inkscape 1.4.4 and PrusaSlicer
2.9.6 installed on Windows; explicit integration fixture and 45-image batch evidence
are in `validation/`. macOS/Linux install plans tested, OS execution unverified.
Offline suite and 11-cell fresh notebook were executed; exact final count is in VALIDATION.md.

## Geometry and hardware

All modeled lengths mm, volumes mm³; feed mm/min in G-code and speed mm/s in profiles.
Source -> normalized Cartesian -> anchored design -> slicer -> machine are distinct.
Anchors on (xmin,ymin,xmax,ymax): bottom_left=(xmin,ymin), bottom_right=(xmax,ymin),
top_left=(xmin,ymax), top_right=(xmax,ymax), center=midpoint. SVG export flips for display,
without altering Cartesian geometry. Record affine and inverse matrices; no G92 XY.
Shared-canvas registration is default and requires matching canvas sizes/common scale.
Per-design bbox is an explicit alternative that can destroy inter-layer registration.
User correction (2026-09-28): each quadrant is 4 in X × 5 in Y = 101.6 × 127 mm.
The centered 2×2 planning bounds are X -101.6..101.6, Y -127..127, before margins.
This supersedes the original brief; it does not change or verify physical firmware travel.
Q1(+,+), Q2(+,-), Q3(-,-), Q4(-,+). Layout and slicer bed derive from profile XY bounds.
Clockwise round robin skips exhausted lists; complete_stack is explicit. Margins reserve
bead footprints and tool body. No automatic per-image fit-to-plate scaling.

Preserve original clarification from supplied brief: “23 mm gauge” means **23 gauge**;
“1/2 inch” means **needle length**, not diameter. Defaults gauge=23, length=12.7 with
individual confirmation flags true. This does not confirm any other dimension.
Needle bore/OD, syringe barrel diameter and deposited bead width are separate fields.
Real Z range, rates/accelerations, holder envelope, first tip height, substrate/standoff,
stroke/capacity and extrusion conversion are unresolved. `config.example.yaml` has nulls.
`profiles/synthetic.yaml` is invented for simulation and never production approval.

Slicer E either filament length × filament cross-section or explicit mm³. Final E is
relative signed calibrated units; measured mm³/E and mm plunger/E are independent
calibrations checked against usable stroke/capacity. Do not silently substitute barrel
geometry for measured flow. Omit uncalibrated prime/retract with an audit report.

## Motion, deposition and queue rules

RRF dialect assumes independent XYZ/E modes. Track G20/G21, G90/G91, M82/M83, G92,
feed and dwell. Reject arcs (must tessellate upstream), coordinate systems, macros,
checksums, expressions, multiple commands per line, tool changes and unknown parameters.
Pure G10 P/S/R temperature settings are removed; G10 offsets/retraction/mixed forms reject.
All thermal/fan setting/config/wait commands are removed or rejected. Final allowlist is
G21/G90/M83/G1/G4 only; serialize then parse again. Do not add M302, M500, macros,
homing or firmware settings. User must review firmware-version-specific cold extrusion
and select/configure the syringe tool outside this program.

Footprint grid uses half-diagonal expansion conservatively; resolution <= half bead width,
sampling <= resolution. Deposit surface uses pre-event support + nominal height; adjoining
capsules union within a pass, repeats are distinct events. Path volume remains width ×
height × length, so cap/junction occupancy is an approximation, not volume-exact fluid
mechanics. Uneven/unsupported footprint diagnostics block production. No liquid spreading,
curing, sagging or pressure-response validation is implied. Needle and holder swept
envelopes are checked against the whole plate; each quadrant retains its own deposits.
Use global maximum for safe travel lift; descend only after checks. Vertical jumps are
non-depositing. Initial pose is explicit: (0,0,substrate+travel clearance), operator verified.

Standalone and continuation jobs share material use, pose, field, offsets and predecessor
identity; neither automatically homes. Only the first is bare-substrate standalone.
Queue writes a durable start intent before sending exactly once. Disconnect or uncertain
completion means reconcile. Official RRF object model says lastFileCancelled/Aborted are
DSF/DWC-only; do not infer success from idle/filePosition. Host queues require operator
confirmation between standalone-Duet jobs unless a future authoritative adapter is added.
Never write firmware/macros/homing files; only unique `/gcodes/bioprinter/<run>/` paths.

## Timing and decisions

Final exact bytes determine line/byte mapping. Zero junction velocity trapezoidal estimate
includes XYZ, E, dwell, transitions; transfer/firmware delays are unknown, not zero.
Display starts first image at first motion, holds outgoing lift and final frame. Live file
position means processed/buffered, not physically executed; polling latency is measured,
pause freezes image/time, and observed records remain separate. Video rounds cumulative
boundaries and verifies ffprobe duration; pauses require an observed timeline to re-render.

2026-09-28 UTC: selected Python 3.11, offline custom vectorizer/direct paths for tested
demo because Inkscape/PrusaSlicer were absent. Keep explicit optional adapters/manual
round-trip; never silently substitute. Chose fail-closed production checks and operator
queue reconciliation rather than unsupported completion flags. Details/alternatives:
[0001](docs/decisions/0001-offline-first.md). Update this record when decisions change.

2026-09-28 follow-up: user explicitly requested OS-aware app setup, Windows installation
and tests on a 45-image ZIP. `scripts/setup_external.py` installs only with `--install`;
WinGet/Homebrew/distro/Flatpak supply packages, no hash/TLS bypass. Local registry is
ignored. `inkscape.py` performs explicit threshold preprocessing then native object-trace,
clears selection before deleting raster, rejects raster-only output, removes only empty
defs, and strictly parses resulting geometry. `max_pixels` is an explicit Inkscape-only
working-copy limit (now supported by Python too; see 0005). `archive.py` validates original ZIP header names as well as resolved
paths (Python normalizes Windows separators). No archive content is executed.
`test_image_dataset.py` defaults to separate 40 mm images, not a registered stack. A synthetic
0.8 mm slicer nozzle is only a compatibility fixture, never a claim about the real needle.
The initial full-resolution parallel attempt exhausted Windows commit memory; retry
uses one worker and 800 px working copies, with originals/logs preserved. Thin/faint
features can fail or disappear. A successful external slice does not authorize printing.
See [0002](docs/decisions/0002-external-app-setup.md) and [setup](docs/application-setup.md).

2026-09-28 report follow-up: the user requested an updated report after correcting the
quadrant size. Explicit `--fit-quadrant` fits independent comparison images within the
synthetic 93.6 × 119 mm margin rectangle, preserving aspect ratio and centering actual
traced bounds in Q1. Tracer curve overshoot triggers a recorded uniform contraction,
never clipping. This does not enable automatic scaling of registered stack layers.
`--compare-report` retains the original 40 mm results by source hash; both successful
and failed new results remain visible. Inkscape gets a unique `--app-id-tag` per trace
and must produce its expected new SVG. Parallel CLI work must not share app instances.
Current report: `validation/dataset-runs/45-image-integration/quadrant-4x5in-verified/report.html`.
Exact validation, counts and remaining failures: VALIDATION.md and [0004](docs/decisions/0004-quadrant-image-report.md).

2026-09-28 pipeline integration: user reconfirmed 23 gauge × ½ inch length and asked
for size settings for both converters. `presets.py` supplies small/medium/large/quadrant
canvas limits and trace defaults; explicit width and per-image options take precedence
within the selected envelope. `vectorization.py` now accepts a working-pixel limit
for Python too. No preset infers needle dimensions or changes calibrated motion values.
CLI, notebook and batch UI pass the same resolved options into `compose`. Shared-canvas
registration still rejects mismatched canvases. CLI and pipeline SVG exports preserve
canvas offsets with `write_svg(..., preserve_canvas=True)`; diagnostic thumbnails may
use content bounds. Needle identity is written in sidecars/manifests/`reports/needle.json`.
For resized rasters, source/local affine matrices start from EXIF-oriented original
pixels. Both converters record original-to-working and working-to-normalized matrices;
do not mistake resized working pixels for the original source coordinates.
`profiles/needle-23g-half-inch.yaml` is unmeasured; synthetic bores remain labelled.
Production now also requires the two needle identity confirmation flags.

User corrected branch scope to merge the other bioprinter branch into this one, excluding
main. Work stays on `bioprinter-setup`; `origin/bioprinter` was already an ancestor.
No main ref, root GAN files/environment, remote branch or printer is modified.
See [0005](docs/decisions/0005-conversion-presets-and-integration.md),
[settings](docs/conversion-settings.md), and final validation evidence.
