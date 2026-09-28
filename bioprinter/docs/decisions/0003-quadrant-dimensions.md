# 0003 — User-corrected quadrant space

Date: 2026-09-28. The user clarified that each quadrant has 4 inches in X and 5 inches
in Y available. Exact conversion gives 101.6 × 127 mm per quadrant. With the existing
centered 2×2 arrangement, total area is 203.2 × 254 mm, X ±101.6 and Y ±127 mm.
These dimensions supersede the smaller values in the original attached brief.

Profile defaults, supplied YAML files and their schema now use those planning bounds.
Quadrants and PrusaSlicer bed shape derive from the active profile, preventing separate
hardcoded limits from disagreeing. Existing edge/centerline/holder margins remain applied;
the synthetic 4 mm margin leaves 93.6 × 119 mm within each quadrant. No image is silently
rescaled and no firmware settings or physical travel limits are changed/verified.

Historical example runs and the 45-image report retain their recorded inputs, settings,
hashes and geometry. That report used 40 mm-wide independent images and is not a rerun
at the new quadrant size. Future runs use the revised profile. Calibration, Z limits,
machine setup review and production approval requirements remain unresolved.
