# 0006 — Supplied Prusa print, filament and printer exports

Date: 2026-10-05 UTC. The user supplied a ZIP of three PrusaSlicer 2.9.4 INIs
and requested pipeline integration. These are complementary preset roles.
The completed pipeline branch `bioprinter-setup` was selected; main was not merged.

Preserve exact source bytes and their archive/member hashes. Only reviewed print
path options reach the native slicer. The machine YAML controls bed, dimensions,
speeds and raw-E convention; explicit slice arguments override print choices.
Do not pass original INIs directly to `--load`: that could execute postprocessors,
emit custom G-code or apply incompatible calibration/coordinate assumptions.
Inheritance and host credentials reject. Sources and every override are recorded
in each run and covered by preflight hashes.

The supplied 0.05 mm layer, 0.33 mm nozzle, 10.3 mm filament convention, mixed
0.33–0.37 mm widths and 2.85 flow multiplier are not physical confirmations.
A separate synthetic preview profile uses 0.05 mm layer, nominal 0.37 mm width,
the unverified 0.33 mm nozzle, 10.3 mm raw-E convention and 5 mm/s deposition.
Other missing fields remain invented demo values. Keep the nominal 0.5 mm
default, 23 gauge/12.7 mm identity and user-corrected 4 × 5 inch quadrants.
Never inflate a nozzle or relax production confirmation to make a config pass.

The footprint planner models one nominal width, so every role width follows it.
The uncalibrated 2.85 multiplier is replaced by 1; raw E is interpreted using
the exact diameter/mode passed to Prusa, then converted with pipeline calibration.
Source top/bottom layers remain one, making a single-layer slice solid despite
0% sparse infill. This behavior must be visible, not silently replaced by the old
15% default. Hooks, postprocessors, substitutions, thermal/fan, retraction,
firmware setting emission and structures outside the image are disabled.

Native CLI tests are offline and preserve initial failures as well as successful
evidence. No original 45-image report is relabeled as a test of these new configs.
No software outcome proves the real needle or material is calibrated.
