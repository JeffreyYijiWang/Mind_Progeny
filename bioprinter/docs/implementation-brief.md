# Codex implementation prompt: images → SVG → syringe G-code → Duet 2

Implement the following project in the current repository. Deliver working programs, an executable Jupyter notebook, configuration, tests, examples, and documentation. Do not stop at an architecture proposal. Inspect the existing repository and its instructions first, preserve unrelated changes, and work on a feature branch if this is a Git repository. If something cannot be verified in your environment, implement and test the offline functionality and clearly identify the remaining integration checks.

## 1. Goal and workflow

Build a Python application for a modified printer with a liquid-extruding syringe controlled by a Duet 2. The workflow is:

1. Batch-load pictures and/or existing SVGs from a folder in a deterministic, editable order.
2. Convert pictures to actual vector paths using a selectable Inkscape-assisted workflow or a custom Python vectorizer.
3. Normalize physical dimensions and preserve intentional holes, outlines, and empty regions.
4. Turn SVG geometry into printable geometry, slice with PrusaSlicer, and preview the results.
5. Parse the exported G-code, remove heating and fan commands, convert extrusion to calibrated syringe movement, and normalize machine state.
6. Assemble ordered designs into a vertical stack, accounting for where prior toolpaths actually deposited material.
7. Optionally create four independent vertical stacks in four plate quadrants, visiting them clockwise.
8. Export final G-code jobs, ordered SVG folders, manifests, simulations, a display timing JSON, and optionally an FFmpeg MOV.
9. Provide local-network upload and optional job execution through the Duet at `http://hans.local`, with an explicit IP/base-URL override.

All processing must work offline except printer communication and dependency installation. Notebook “Run All,” tests, and example commands must not contact, home, or start the real printer. Printer actions require explicit user invocation. Upload and start are separate operations.

## 2. AGENTS.md and decision record

Create or carefully extend the root `AGENTS.md` (the exact filename, rather than only `agent.md`). Make it the durable source for future Codex work. Include:

- Project goal, module map, setup and verification commands.
- Millimeter units, coordinate conventions, bounding-box definitions, anchor transforms, and quadrant order.
- Which hardware measurements are confirmed, provisional, or unresolved; preserve original user wording.
- Extrusion unit conventions, calibration requirements, and the distinction between needle bore, outer diameter, barrel diameter, and deposited bead width.
- G-code parsing rules, the thermal/fan removal policy, and commands requiring explicit support.
- Height-field assumptions, collision rules, and physical limits of the liquid model.
- Queue semantics, state that crosses job boundaries, and restart behavior.
- Timing/display synchronization limitations and dependency versions actually tested.
- Rules that machine configuration must not be changed silently and no heater/fan commands may appear in executable exports.
- Important architectural decisions with date, reason, alternatives, and consequences; link longer explanations in `docs/decisions/` while retaining their essential conclusion in `AGENTS.md`.

Update this record as implementation choices change. Do not claim tests, OS support, or hardware validation that you did not perform.

## 3. Hardware configuration and confirmed needle specifications

Known requested values:

| Setting | Value |
|---|---|
| Nominal deposited thickness / slice layer height | 0.5 mm |
| Needle gauge | 23 gauge (dimensionless gauge designation) |
| Needle length | 1/2 inch = 12.7 mm |
| Plate X travel | -60 to +60 mm |
| Plate Y travel | -125 to +125 mm |
| Plate XY origin | center |
| Design-local anchor | bottom_left by default |
| Other anchors | center, top_left, top_right, bottom_right |
| Duet address | http://hans.local |

The user explicitly clarified that the original “23 mm gauge” means **23 gauge**, and “1/2 inch” means **needle length**, not diameter. These two specifications are confirmed. Record this clarification in `AGENTS.md`; do not reopen this ambiguity or treat 23 as a millimeter measurement.

Set the defaults to `needle_gauge: 23` and `needle_length_mm: 12.7`, with `needle_gauge_confirmed: true` and `needle_length_confirmed: true`. Keep confirmation at the individual-field level: the gauge and length do not confirm the bore, outer diameter, syringe barrel size, tool mounting geometry, or extrusion calibration. Never use 12.7 mm as a needle or barrel diameter. Expose separate editable fields:

- `needle_gauge` (dimensionless), `needle_inner_diameter_mm`, `needle_outer_diameter_mm`, `needle_length_mm`.
- `syringe_barrel_inner_diameter_mm`, usable plunger stroke, calibrated displacement/volume conversion, and positive extrusion direction.
- `bead_width_mm`, `deposition_height_mm: 0.5`, first-deposition tip height, substrate Z reference, and needle standoff.
- Z minimum/maximum, tool/holder clearance envelope, XY/Z speed and acceleration limits, extrusion speed/acceleration limits, travel clearance, and edge margins.

Gauge alone must not determine a precise internal diameter. Do not invent real-machine speeds, Z travel, tool dimensions, or extrusion calibration. Supply a separately named synthetic simulation profile so the complete offline demo works immediately. Unresolved required real-machine values should prevent production G-code approval/upload/start, while still allowing clearly marked preview output. Explain how to enter confirmed dimensions and calibration without requiring code changes.

## 4. Project deliverables and interfaces

Use a package under `src/` with small reusable modules for configuration, ingestion, vectorization, SVG geometry, meshing, slicing, G-code interpretation, extrusion conversion, stacking, layout, simulation, timing, video, and Duet communication. The notebook must import these modules rather than duplicate the implementation.

Deliver:

- `notebooks/image_to_syringe_pipeline.ipynb` with saved explanatory text and useful example output.
- CLI commands such as `doctor`, `vectorize`, `slice`, `compose`, `simulate`, `export`, `video`, `duet status`, `duet upload`, and `duet run-queue`.
- `config.example.yaml`, a synthetic demo profile, schemas, sample inputs, and a runnable offline demonstration.
- `pyproject.toml`, `requirements.txt`, development requirements, and a reproducible dependency-lock strategy.
- README, calibration guide, machine-profile guide, OS setup instructions, supported-feature matrix, and `AGENTS.md`.
- Automated tests, a fake Duet server/transport, and useful fixtures.

Notebook sections must cover setup/doctor, folder selection, input order, per-image settings, vectorization comparison, dimensions, anchor controls, slice settings, G-code cleanup report, extrusion calibration, stack composition, quadrant preview, 3D motion preview, timeline/JSON export, optional MOV, and separately invoked printer controls. Make widget actions explicit and reruns idempotent. Batch stages should show progress, errors, and cancellable work.

## 5. Batch images and vectorization

- Support PNG, JPEG, TIFF, BMP, and existing SVG. Document treatment of multi-page images and reject unsupported inputs clearly.
- Default to natural filename sorting (`image2` before `image10`); allow drag/order-list or manifest overrides, per-quadrant sequences, repeat counts, and optional recursion.
- Apply EXIF orientation, explicit transparency/background handling, threshold/invert, optional denoising, minimum feature filtering, and simplification with tolerances expressed in physical units where applicable.
- Require a physical size or an explicit scale rule; do not quietly interpret pixels as millimeters.
- Store stable asset IDs, hashes, original names, parameters, and processing results. Preserve originals.
- Distinguish filled silhouette tracing from outline/centerline tracing; do not represent a photograph by merely embedding raster data in an SVG wrapper.

Implement two selectable vectorization routes:

1. **Custom Python:** contour extraction with hierarchy, holes, fill rules, disconnected islands, and controlled simplification. Preserve narrow strokes or flag them as unprintable. Support filled regions and outline paths. Centerline tracing may be an explicitly documented optional mode.
2. **Inkscape-assisted:** inspect the installed version, CLI help, and available actions. Verify the actual tracing mechanism with a fixture. Do not invent a universal headless trace-bitmap action or claim that plain-SVG export traces an image. If tracing is unavailable through that installed CLI, provide a clear manual Inkscape round-trip or documented optional tracer adapter. Name the backend actually used in metadata. Never silently substitute the custom backend for a requested Inkscape backend.

Existing SVGs bypass raster tracing. Resolve supported transforms, viewBox, units, fill rules, strokes, and nested groups. Convert printable strokes to geometry when needed. Handle unsupported text, filters, masks, and external references explicitly; disable unsafe XML/external resource resolution. Blank images and invalid/empty geometry must produce actionable outcomes rather than invalid meshes.

## 6. Coordinate systems and registration

Keep these separate: source SVG coordinates, normalized design-local millimeters, slicer coordinates, and final machine coordinates.

Normalize SVG Y-down coordinates into Cartesian Y-up coordinates exactly once. Define bounds from printable geometry after transforms and stroke expansion, not the SVG page border or invisible objects. For Cartesian bounds `(xmin, ymin, xmax, ymax)`, use these anchors:

| Anchor | Anchor coordinate |
|---|---|
| bottom_left | (xmin, ymin) |
| bottom_right | (xmax, ymin) |
| top_left | (xmin, ymax) |
| top_right | (xmax, ymax) |
| center | ((xmin+xmax)/2, (ymin+ymax)/2) |

Compute `p_local = p_normalized - anchor` and then apply the documented placement transform to get `p_machine`. The selected local anchor becomes `(0,0)` in design-local exported paths; final plate placement remains in the centered machine frame. Do not use `G92 X/Y` to pretend the physical machine origin moved.

Per-image bounding-box anchoring can destroy alignment between differently cropped images. Therefore support both `per_design_bbox` and `shared_canvas`/explicit registration transforms for stacks. Preview the chosen behavior, preserve intentional source offsets in shared-canvas mode, and use one common scale/registration per stack by default. Never independently resize layers merely to fill the plate.

Record every transform and its inverse in the manifest. Account for slicer centering/translations and any tool offsets already applied by firmware; do not apply offsets twice. Verify orientation with an asymmetric L-shaped fixture.

## 7. SVG geometry and PrusaSlicer integration

Create a reliable headless route: normalized printable polygons → watertight thin extrusion mesh → supported PrusaSlicer input → plain-text G-code. Prefer a format preserving units; if STL is used, document its millimeter convention. Preserve holes and disjoint islands. Offer a GUI SVG import/embossing workflow if useful, but do not assume GUI SVG features prove headless CLI support.

Probe the installed PrusaSlicer executable and its supported flags, pin/document tested versions, and save exact profile/config and command arguments. Use subprocess argument arrays, timeouts, checked exit codes, captured logs, and paths with spaces/Unicode. Do not use shell interpolation.

The syringe profile must:

- Use 0.5 mm first and subsequent nominal layer heights unless changed explicitly.
- Use an appropriate verified RepRapFirmware flavor and plain-text `.gcode` output.
- Disable unwanted skirt, brim, raft, support, wipe/prime tower, automatic placement, purge lines, and thermal/cooling behavior where supported.
- Expose perimeters, infill pattern/density, top/bottom solid layers, and extrusion width. Make clear that top/bottom solid layers can override an intended sparse single layer.
- Avoid adding a rectangular substrate that fills negative space.
- Preserve raw slicer output for audit, and treat it as untrusted input to the later normalizer.

Do not falsify physical nozzle dimensions to satisfy a slicer constraint. If the real 0.5 mm deposition height/profile is rejected, show the reason and offer an explicitly selected direct SVG toolpath backend, while retaining and documenting the PrusaSlicer path.

## 8. G-code interpreter, cleanup, and calibrated extrusion

Do not sanitize with regular-expression deletion alone. Build/use a tested modal interpreter and a typed motion representation. Track XYZ positioning modes, absolute/relative E, units, feedrate, `G92`, tool state, extrusion resets, dwell, and relevant firmware-specific modal interactions. Normalize final output to documented units, absolute XYZ, and one chosen E convention.

Handle `G0/G1`; support `G2/G3` correctly or tessellate with bounded geometric error before transforming. Reject unsupported arcs, coordinate systems, expressions, macros, checksums, or machine commands explicitly if not implemented. Unknown motion-affecting commands must not silently pass through. Preserve source-to-output mappings.

Remove all executable heating and fan instructions, including zero-target/off commands, from final G-code. The policy must cover at least `M104`, `M109`, `M140`, `M190`, `M106`, and `M107`, and inspect the installed RepRapFirmware dialect for additional commands such as heater/tool-temperature settings in `G10`, `M568`, and other applicable thermal waits/settings. Parse parameters: do not delete every `G10`, because command meaning varies by dialect and parameter form. Reject unreviewed tool-change/macro calls that could invoke heating/fans indirectly. Generate no chamber-heating, thermal-configuration, fan-configuration, or thermal-wait instructions.

Use a documented final command allowlist and produce a cleanup report listing each removal, rewrite, or rejection. After composition, serialize and re-parse the final file and verify the policy again. Comments may explain removed commands but must never be mistaken for executable commands.

Extrusion must be physically calibrated:

- For ordinary slicer filament-length E, convert positive material volume using the configured slicer filament cross-section; if E is volumetric, handle it explicitly.
- Convert volume to actual syringe E units via a measured `mm3_per_e_unit`, or validated barrel cross-section plus known plunger-motion units.
- State every unit and verify conservation of intended volume. Needle diameter is not syringe barrel diameter.
- Separate deposition, prime, pressure release/retraction, and non-depositing moves. Do not blindly reuse filament-printer retract distances with liquid. Defaults should omit uncalibrated priming/retraction.
- Enforce plunger capacity/travel and rate limits across the entire stack/queue; `G92 E0` does not refill the syringe.
- Document any required cold-extrusion firmware setting after checking the actual RepRapFirmware version. Removing heater commands alone may not permit E movement. Do not silently change firmware configuration or send guessed cold-extrusion commands.

## 9. Stack assembly and overlap-aware Z planning

Accept an ordered sequence of image/SVG-derived designs and export one longer composed job. Do not concatenate standalone files with repeated startup, homing, resets, purge, shutdown, or parking sections. Assemble normalized motions, preserve their provenance, and regenerate one coherent prologue/epilogue and transitions.

Provide two explicit modes:

1. `planar_stack`: advance the plane by 0.5 mm per nominal layer, document unsupported regions, and preview support/overhang problems.
2. `overlap_aware`: maintain a calibrated approximate height field based on actual deposited toolpath footprints, including sparse infill, perimeters, holes, bead width, and footprint overlap. This is the requested adaptive mode; a single global Z offset per image is insufficient.

For overlap-aware planning:

- Start from a substrate height field. Track intended material additions in execution order and distinguish repeat passes from geometric overlap of adjoining bead footprints.
- Define the deposition model explicitly: how deposited volume/footprint estimates the new surface, when the model is updated, and how tip standoff relates to the existing surface. Do not confuse tip Z, layer thickness, and material surface height.
- Use nominal 0.5 mm additions where applicable, with calibrated spread/height parameters. Preserve empty gaps as empty. Do not automatically count one whole layer over an entire SVG bounding rectangle.
- Subdivide paths at changes in underlying support height or bounded sampling intervals. Validate resolution and use conservative collision envelopes so narrow features are not missed.
- Plan non-depositing lifts and relocations across discontinuities; do not extrude through a vertical height jump or silently smooth into existing material. Recheck volume, support, slope, and axis speeds if paths are modified.
- Check the needle and holder envelope, not only the mathematical tip. A valley may be inaccessible even when its XY point is inside the bed.
- Lift before lateral travel, clear relevant existing deposits, and descend only at a validated target. Enforce maximum Z and all travel bounds.
- If support or collision constraints cannot be satisfied, report the location and alternatives. Never silently produce a path through deposited material.
- Save height-field checkpoints and show 3D motion/deposition previews with layer/design/quadrant coloring, travel moves, and collisions.

This is a geometric deposition approximation, not a verified fluid simulation. Flow, spreading, curing, sagging, and pressure response require experiments; describe how measured results update the model. Do not present a successful preview as proof that a liquid structure is physically stable.

## 10. Four-quadrant mode and queues

Use this mapping with positive Y upward:

| Quadrant ID | Position | X range (mm) | Y range (mm) |
|---|---|---|---|
| Q1 | top-right | 0 to 60 | 0 to 125 |
| Q2 | bottom-right | 0 to 60 | -125 to 0 |
| Q3 | bottom-left | -60 to 0 | -125 to 0 |
| Q4 | top-left | -60 to 0 | 0 to 125 |

Default clockwise order: `Q1 → Q2 → Q3 → Q4`, starting top-right and configurable. Apply edge and centerline margins plus bead/tool envelopes. Each quadrant is nominally 60 × 125 mm before margins. Keep deposited material inside its quadrant. Cross-quadrant travel is allowed at validated clearance height inside the machine envelope.

Allow either four different ordered sequences or replication of one sequence. Maintain independent deposited height fields per stack while collision checking against the whole plate.

Support both schedules:

- `round_robin` (default): print the next design in Q1, Q2, Q3, Q4, then repeat, skipping exhausted sequences deterministically.
- `complete_stack`: finish one quadrant's stack before continuing clockwise.

Export a single combined G-code option and an ordered list of jobs option. Label jobs as standalone or continuation jobs with explicit preconditions, current material/height state, offsets, remaining syringe capacity, and predecessor IDs. A continuation must not home through an existing stack, reset Z to a bare plate, or pretend earlier deposits vanished. Do not call continuation jobs independently printable.

## 11. Run folders and provenance

Create a new collision-resistant timestamped run directory every time. Use zero-padded numbering and safe filenames. Suggested structure:

```text
runs/<timestamp>_<run-id>/
  config.resolved.yaml
  manifest.json
  inputs/
  quadrants/
    01_top_right/svgs/0001_<asset-id>.svg
    02_bottom_right/svgs/0001_<asset-id>.svg
    03_bottom_left/svgs/0001_<asset-id>.svg
    04_top_left/svgs/0001_<asset-id>.svg
  meshes/
  slicer_raw/
  gcode_cleaned/
  jobs/0001_<job-id>.gcode
  combined/combined.gcode
  previews/
  simulation/
  timing/display_timeline.json
  timing/jobs.json
  video/display.mov
  reports/
  checkpoints/
  logs/
```

Within each quadrant, enumerate SVGs in their print sequence. Also retain a global execution index for interleaving and repeated assets. Map original image → normalized SVG → mesh → raw slice → cleaned motions → composed output byte/line ranges → display event. Store hashes, versions, settings, transforms, diagnostics, estimates, and validation status. Resume preprocessing only when cached inputs/configuration match. Never infer safe physical print resume from a filesystem checkpoint alone.

## 12. Motion simulation, timing JSON, and image display

Estimate duration from the final composed, filtered G-code, including added XYZ travel, Z transitions, calibrated extrusion, priming, dwell, and all job overhead. Do not reuse the raw slicer estimate after modifying motion.

Implement a kinematic estimate with feed rates, per-axis constraints, acceleration/deceleration, and a documented junction/lookahead approximation. Include axis-only extrusion moves and simultaneous XYZ/E limitations. Mark unknown waits/macros as unknown rather than zero. Report motion time, dwell time, transfer/transition time, and estimated uncertainty separately. No claim of exact firmware timing or physically simulated liquid dynamics.

Write a versioned JSON schema and `display_timeline.json` containing per event:

- event ID, source asset paths/hashes, SVG path, quadrant, sequence/nominal-layer indices, and job ID.
- output G-code line and byte ranges generated from the exact bytes uploaded.
- `start_s`, `end_s`, `duration_s`, relative to a defined origin, and separate deposition versus display intervals.
- transition/dwell allocation and `display_action` (`show`, `hold`, `blank`, etc.).
- timing model, assumptions, estimate/observed status, optional uncertainty, and optional observed timestamps.

Use continuous, non-overlapping, complete display intervals unless explicitly configured otherwise. Default: show an asset at its print-segment start, hold through that segment and its outgoing transition, then show the next asset; document startup and final-frame behavior. Allow alternative transition policies. Validate positive durations and that the full timeline matches the job schedule.

Provide a display preview/player driven by this JSON. Estimated durations alone cannot guarantee synchronization. Implement optional live Duet status polling and pause/resume-aware display state, with measured polling latency and explicit uncertainty from firmware buffering/file position. If reliable executed-segment markers are unavailable, label live synchronization approximate; do not equate a comment or uploaded byte with completed physical motion. Do not embed unsupported synchronization commands. Preserve planned and observed timing as separate records.

## 13. Optional FFmpeg MOV

Render associated images/SVGs at a consistent configurable resolution with contain/crop/background policy, then build a `.mov` from the display timeline using a supported FFmpeg timing method. Default to the active design; optionally show a four-quadrant composition with the active quadrant indicated.

Expose frame rate, codec/quality, background, output dimensions, and estimated versus observed timeline. Document and validate MOV codec availability. Account for variable durations, last-frame handling, and frame quantization; use cumulative timestamp rounding to avoid drift from rounding every event independently. Verify actual duration with ffprobe, declare tolerance, and report the difference. Never claim the video remains synchronized through arbitrary real-printer pauses. Missing FFmpeg must affect only video generation.

## 14. Duet 2 network integration and execution

The user's computer connects to the same local network/Wi-Fi as the printer; this software should not reconfigure Wi-Fi automatically. Default to `http://hans.local`, allow an IP address and custom port/base URL, and explain mDNS troubleshooting.

Detect/report the actual firmware and available API. Use the documented API appropriate to a standalone Duet 2; do not assume a Duet Software Framework/SBC endpoint or native queue exists. Verify API endpoints and command semantics against official documentation and actual capability checks. Keep passwords in environment variables or a local ignored secrets file, never manifests/logs/notebook output.

Implement status and upload with timeouts, bounded retries where safe, error handling, and remote file verification where supported. Provide a manual Duet Web Control upload fallback. Do not contact the real printer during development unless the user explicitly requests it.

If no reliable native queue exists, implement a host-managed persistent queue that starts one job, verifies its identity/running state, waits for actual successful completion, and only then starts its successor. Idle alone is not proof of successful completion: distinguish cancellation, abort, fault, disconnect, and finished state. Never automatically restart an ambiguous job after connection loss. Reconcile with the operator and current printer state, including material already deposited.

Separate upload from start. Use explicit controls such as `--start` plus a validated machine profile and job preflight. Polling/status must not mutate machine state. Provide documented pause/resume/cancel controls with feedback; explain that host control is not a physical emergency stop. Never overwrite firmware configuration, macros, or homing files. Only write to a designated G-code run directory on the printer.

## 15. Windows, macOS, and Linux dependencies

Provide `requirements.txt` for Python dependencies, `pyproject.toml` for the package, and development/test dependencies. Choose supported Python versions based on compatible wheels. Separate optional backends so lack of Inkscape, PrusaSlicer, or FFmpeg does not break unrelated imports.

Candidate libraries include Pillow, NumPy, OpenCV headless, Shapely, an SVG parser, a mesh/triangulation library, Pydantic, PyYAML, Typer, a HTTP client, JupyterLab, ipywidgets, plotting libraries, pytest, and notebook execution tooling. Select only what is used, pin/lock reproducibly, check current compatibility, and document licenses.

External executables are not installed by Python requirements alone. Provide separate Windows/macOS/Linux installation instructions and version checks for Inkscape, PrusaSlicer, optional tracing tools, FFmpeg/ffprobe, and native rendering dependencies. Handle executable overrides, PATH discovery, Windows `.exe/.com`, and macOS application bundle paths. Offer PowerShell and POSIX bootstrap scripts that explain system prerequisites. Do not claim all three operating systems are tested if only one was available; add CI for the portable core and distinguish skipped external/hardware integration tests.

`doctor` must report dependency versions, backend capabilities, unresolved hardware fields, and available integration checks without initiating printer motion. Use a mock transport for CI.

## 16. Required meaningful verification

Include fixtures/tests proving:

- Correct holes, disconnected shapes, transparent images, thin strokes, and empty inputs.
- Correct five-anchor transforms, physical units, Y flip, shared-canvas registration, and a deliberately asymmetric design.
- Full deposited footprints fit the selected quadrant and machine envelope; oversized inputs fail without silent distortion.
- G-code modal handling, E resets and modes, arcs or explicit rejection, and no accidental deletion of nonthermal `G10` semantics.
- No executable heater/fan commands or unreviewed macro/tool-change paths remain after final composition.
- Volume-to-syringe conversion, capacity accounting, extrusion direction, and independence from needle diameter.
- Repeated segments do not repeat startup/shutdown/homing and continuation jobs preserve material state.
- Two partially overlapping sparse designs create different overlap/non-overlap heights; holes remain empty, skipped quadrants work, and crossing taller deposits requires clearance.
- Tool-envelope collisions and inaccessible valleys are detected, not only out-of-range endpoints.
- Simple timing fixtures have independently calculated expected values; dwell, E-only, Z-only, and transition time are included.
- Timeline ranges map to exact exported bytes; pauses do not advance the live player as if printing continued.
- MOV duration matches the timeline within its declared frame tolerance when FFmpeg is installed.
- Fake Duet upload/status/queue handling covers disconnect, auth failure, cancellation, completion, duplicate-start prevention, and ambiguous restart.
- A fresh-kernel notebook executes end-to-end with the synthetic profile and no network/motion side effects.

Finish with an offline demo using at least three distinct images, partial overlap, intentional holes, and all four quadrants. Supply example run outputs and explain commands to reproduce them. Report what works, the exact tests executed, unresolved real-machine measurements, and external integrations not verified. Implement all achievable stages; do not hide missing core functionality behind TODO stubs or label mocks as hardware validation.

## 17. Official documentation to consult during implementation

Resolve current official documentation and inspect installed CLI help before relying on particular flags, firmware commands, or API routes:

- Inkscape CLI manual: https://inkscape.org/doc/inkscape-man.html
- Inkscape release documentation: https://wiki.inkscape.org/wiki/Release_notes/1.3
- PrusaSlicer repository: https://github.com/prusa3d/PrusaSlicer
- PrusaSlicer SVG tool: https://help.prusa3d.com/article/svg-embossing-tool_686167
- Duet documentation and G-code dictionary: https://docs.duet3d.com/ and https://docs.duet3d.com/User_manual/Reference/Gcodes
- FFmpeg format documentation: https://ffmpeg.org/ffmpeg-formats.html

Do not assume the latest software behaves like an old tutorial. Record the specific versions and capabilities used in `AGENTS.md` and each run manifest.
