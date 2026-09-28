# Workspace instructions

This repository also contains an existing NeoHuman R3GAN project. Preserve its files and
unrelated working-tree edits. The image-to-syringe project is isolated in `bioprinter/`.
For work there, read `bioprinter/AGENTS.md`, its README and decision records first.
Run bioprinter commands from that folder and use its own `.venv`; do not alter the root
training environment. No notebook, demo, test or doctor command may contact a printer.

## Bioprinter essential decisions (2026-09-28 UTC)

- Millimeters, centered machine XY, Cartesian Y-up. Source SVG Y-down is flipped once.
  Printable geometry bounds include expanded strokes and exclude page/invisible objects.
  `local = normalized - anchor`; machine placement is a separate affine transform.
  Clockwise quadrants are Q1 top-right, Q2 bottom-right, Q3 bottom-left, Q4 top-left.
- The supplied specification states: original “23 mm gauge” means **23 gauge**;
  “1/2 inch” means **needle length**, 12.7 mm, not diameter. These two fields are confirmed
  per that specification. Bore, OD, barrel, mounting, speed, Z and calibration remain
  unresolved. Do not infer those from gauge or length. Nominal deposition is 0.5 mm.
- E is relative calibrated syringe units in exports, never assumed to be needle diameter.
  Volume conversion and capacity are cumulative across all jobs. G92 does not refill.
- Executable allowlist: G21, G90, M83, G1, G4. Parse modal state; reject unknown commands,
  macros/tool changes/arcs. Remove thermal/fan instructions, including off commands.
  Nonthermal or mixed G10 is rejected, not erased. Never change machine configuration.
- Height fields approximate actual bead capsules, not design bounding boxes. Adjoining
  footprints union within an event; repeated events add height. Conservative occupancy
  and holder/needle checks do not establish liquid stability. Unsupported regions block
  production. Lift before lateral travel; honor Z limits.
- Queue jobs carry predecessor, exact starting pose, material use and height checkpoint.
  No homing/reset at boundaries. Filesystem checkpoints do not prove physical resume.
  Standalone RRF lacks authoritative cancellation flags: idle requires operator
  reconciliation, never automatic next-job start or ambiguous restart.
- Estimated timing is trapezoidal with zero junction speed. Display byte position is
  approximate due to buffering. Pause holds the player. Tested versions and commands
  are recorded in `bioprinter/VALIDATION.md`; never claim unperformed hardware/OS tests.

Module map, complete conventions, setup and verification: [bioprinter/AGENTS.md](bioprinter/AGENTS.md).
Rationale/alternatives/consequences: [decision record](bioprinter/docs/decisions/0001-offline-first.md).
