# 0004 — Explicit quadrant-sized image comparison

Date: 2026-09-28 UTC. The user requested an updated image report after specifying
4 inches in X and 5 inches in Y per quadrant. This supersedes only the observation
in 0003 that the dataset report had not yet been rerun.

The report runner now offers explicit `--fit-quadrant`. It fits each independent
image canvas to the active profile's usable quadrant dimensions, preserving aspect
ratio. For this synthetic profile, 101.6 × 127 mm minus 4 mm on each edge leaves
93.6 × 119 mm. Actual traced bounds are centered in Q1; all four quadrants have the
same size. A tracer curve can extend slightly beyond a raster edge, so a final
uniform contraction checks actual traced bounds and records its factor. Geometry
is not clipped. Independent fitting is confined to this diagnostic runner; registered
stack layers still require a shared scale and registration.

The rerun keeps 800 px working copies, threshold 128, median 3, minimum island area
0.01 mm², simplification 0.05 mm, one 0.5 mm layer, nominal 1 mm bead, invented
0.8 mm slicer nozzle, one perimeter and 20% infill. Originals remain unchanged.
These choices permit a scale comparison but do not recover details removed by
preprocessing or establish physical printability.

An initial parallel trace returned success without its expected SVG. Native traces
now use unique Inkscape application IDs to isolate concurrent invocations, and
missing output is checked explicitly. Both this interrupted attempt and the later
oversize trace attempt remain on disk. Diagnostic continuation reused completed
results only after source hash, ordering and setting checks; retries used fresh
folders. Two workers ran with process-local BLAS/OMP thread limits of one.

The updated HTML pairs originals and actual toolpaths, reports physical canvas size,
compares each result with the 40 mm baseline by source hash, and filters failures
and potential detail loss. Failed mesh or slice stages remain failures. The old
HTML is archived as `native-800px/report-40mm.html`; its JSON and native artifacts
remain unchanged. Its original HTML entry point links to the new report. The new
summary is `validation/dataset-45-quadrant-summary.json`; measured outcomes are in
VALIDATION.md. No printer was contacted and no hardware configuration was changed.
