# 0002 — Explicit external installation and native CLI validation

Date: 2026-09-28 UTC. Supersedes the absent-application observations in 0001 only.

The user requested setup scripts for Windows/macOS/Linux, installation on this Windows
laptop, and testing on a supplied ZIP of 45 images. We used OS package managers and
their integrity checks, with plan-only defaults and explicit installation. Independent
wrappers share one implementation. Doctor/notebook/demo never install applications.
Mac/Linux command plans are tested in isolation; their installers were not executed.

Installed Inkscape 1.4.4 exposes object-trace. An asymmetric two-island/one-hole fixture
proved native paths and Cartesian orientation. Rather than retaining an obsolete manual
only route, the adapter now thresholds explicitly, invokes Inkscape's real tracer,
removes the source raster by ID after clearing selection, verifies real paths, and
imports strict geometry. An empty authoring defs node may be removed; unsupported
effects/styles still fail. Exact argv, version, raw SVG and logs are retained when a
trace directory is supplied. Missing tracing support fails with a manual-round-trip
instruction, never a silent Python substitution.

PrusaSlicer 2.9.6 executed the existing mesh/profile adapter. It can return zero while
reporting a validation error without creating G-code, so exit status alone is insufficient:
output must be newly generated plain text, stale paths reject, and failure includes its
log. The compatible fixture has an invented 0.8 mm nozzle, 0.5 mm layer and 1 mm bead.
The incompatible 0.3 mm nozzle rejects the 0.5 mm layer. No actual dimensions are inferred
from 23 gauge/12.7 mm needle length and no production profile confirmations were changed.

The images have different canvases and include faint fine line drawings. They are
tested independently, with explicit 40 mm canvas width rather than an invented shared
registration. The initial full-resolution two-worker attempt hit Windows committed-memory
limits. We retained originals and failure logs, lowered working-copy resolution explicitly
to 800 pixels maximum dimension, and used one worker. This trades fine detail for bounded
resource use; the HTML/JSON report exposes trace/slice failures, missing islands and
approximate thin-feature areas. A successful software path is not physical print approval.

Dense native SVGs exposed slow exhaustive winding checks and repeated toolpath-buffer
construction. Ring bounding boxes now exclude impossible winding contributors before
evaluating the same winding rule; reference tests compare nested, overlapping, reversed
and disconnected rings for both nonzero/evenodd rules. The diagnostic runner constructs
its XY tolerance buffer once. Diagnostic continuation validates input hashes/settings,
keeps completed results, and writes fresh folders for interrupted attempts. This is not
physical resume or pipeline cache reuse.

No test imports printer controls, sends jobs, modifies machine/OS settings or interprets
archive instructions. Existing hardware, stability, calibration and queue restrictions remain.
