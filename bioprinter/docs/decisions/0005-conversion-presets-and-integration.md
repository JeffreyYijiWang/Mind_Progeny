# 0005 — Needle identity, converter presets and complete offline integration

Date: 2026-09-28 UTC. The user confirmed 23 gauge × ½ inch needle length and requested
different image-to-SVG settings for different sizes, both converters, and branch
integration. They clarified that only the other bioprinter branch should be merged
into the current branch, excluding main.

All fetched setup refs shared commit 245da5b; `origin/bioprinter` at 35ff7cb was
already its ancestor. The merge therefore reported already up to date. Earlier local
quadrant/report work was preserved in e053479; subsequent integration stays on
`bioprinter-setup`. Main remains at its original commit. No remote push is performed.
The root Colab notebook contains the GAN workflow; it has not been replaced or edited.
The integrated Python converter is the existing `bioprinter/vectorization.py` code,
not an unverified replacement advertised as a separate Colab implementation.

Size presets are explicit physical canvas limits and tracing defaults. They change
resolution, simplification tolerance and minimum island area, with threshold and
median filtering independently adjustable. We retain aspect ratio and originals.
Needle bore, deposited bead size, layer height and calibration are not derived from
image size, gauge or length. Python and Inkscape remain explicitly selected backends.
The same options reach CLI conversion, the notebook, widgets and full composition.

Shared-canvas registration remains the default. Pipeline/standalone SVG exports now
preserve the source canvas rather than implicitly recentering a cropped drawing on
reimport. Diagnostic comparison SVGs use content bounds for inspection only. Actual
geometry still undergoes placement checks and cannot be cropped to hide oversize
traces or nonmanifold boundaries. Direct slicing still rejects lost narrow islands.
Both converters also record the resize affine and include it in the original-pixel
to-local transform, preserving provenance when the working resolution changes.

The needle identity is visible in the UI, report, sidecars and manifest, with a named
unmeasured profile. Production requires its confirmation flags and existing measured
dimensions/calibration checks. Earlier 0.8 mm slicer compatibility tests remain
historical synthetic evidence. Full integration uses an explicit 0.2 mm layer / 0.4 mm
bead Prusa fixture with the unchanged invented 0.3 mm bore, rather than inflating the
bore to bypass slicer checks. The requested nominal 0.5 mm default remains unchanged.

Validation compares three supplied images at four sizes through two real converters,
and separately exercises both slicers through all four quadrants with synthetic shapes.
All commands, hashes, initial rejected settings and successful runs are retained.
No software test constitutes physical needle, liquid, firmware or printer validation.
