# 0001 — Explicit offline planning and conservative printer handoff

Date: 2026-09-28 UTC. Status: implemented, hardware integration unverified.

The task brief requested a usable offline pipeline plus separately invoked printer
operations. The repository already contained unrelated training work. We isolated the
new package/environment under `bioprinter/` on `codex/bioprinter`, added scoped durable
instructions, and left the existing working-tree edits untouched.

**Vector and slice backends.** Inkscape and PrusaSlicer were absent. We implemented
OpenCV hierarchy tracing, strict SVG geometry, watertight mesh export and explicitly
selected direct perimeters/infill. Optional executables are probed rather than assumed.
Inkscape uses a manual trace round-trip; a custom fallback is never disguised as Inkscape.
PrusaSlicer has an audited subprocess adapter but no installed-binary validation claim.
Alternatives were installing large external GUIs or pretending plain-SVG export traces
bitmaps; neither was necessary for the offline result. Consequence: users must validate
the installed Prusa CLI/profile before production and may need a profile adapter change.

**Geometry and state.** We chose separate source/local/slicer/machine transforms with
shared-canvas registration by default. Per-design fitting would misalign crops; G92 XY
would disguise a physical origin error. Consequence: inconsistent canvases and oversize
designs fail explicitly and require a supplied physical registration/scale.

**Deposition.** A conservative sampled height field represents deposited bead capsules.
Within an event, adjoining footprints union at each cell's own pre-event height + nominal
addition; later events add another nominal height. Using one maximum height for an entire
capsule was rejected after a regression test showed an overlap step spreading too far.
Tip height uses conservative support and explicit non-depositing transitions. The holder
and needle are checked, not just the tip. Consequence: local overlap/non-overlap differ,
but uneven support remains production-blocking and the preview is not a fluid solver.

**G-code and extrusion.** Use a small modal interpreter and typed motions, fail closed on
unknown semantics, strip known thermal/fan commands, then generate a tiny output allowlist
and reparse exact bytes. Regex-only deletion could corrupt G10 offsets or miss macros.
Capacity tracks physical volume despite E resets. Final E is relative measured syringe
units; no automatic prime/retract or cold-extrusion setting is sent. Consequence: some
ordinary slicer profiles need reviewed changes instead of silently ignored commands.

**Queue completion.** Official standalone RRF object-model documentation excludes
lastFileCancelled/Aborted; idle alone cannot distinguish success from cancellation.
We persist start intent and reject ambiguous retries. The implemented host queue waits
for operator-confirmed physical completion before moving to a successor. Alternatives
were guessing completion from byte position or installing a machine-side reporting macro;
both would violate the current evidence/no-silent-config requirements. Consequence:
fully automatic unattended queue progression is deliberately unavailable on this adapter.

**Timing.** Use final rounded G-code, trapezoidal axes/E limits and zero junction speed.
It is a reproducible conservative lookahead approximation, not exact firmware timing.
Live observations retain uncertainty from buffered byte offsets; paused state holds the
display. MOV cumulative frame rounding and ffprobe duration are verified independently.

**Reproducibility.** Direct dependencies are pinned, the complete tested Windows 3.11
environment is frozen, external capabilities are recorded per run, and every run is
fresh. No preprocessing cache is trusted and no filesystem state authorizes print resume.
This costs disk/time but avoids invalid cache reuse while core geometry is evolving.
