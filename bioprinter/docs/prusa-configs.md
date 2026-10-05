# Supplied PrusaSlicer configuration set

The three INIs from `PRUSACONFIGS-20261005T003011Z-1-001.zip` are a matching
**print + filament + printer** set, exported by PrusaSlicer 2.9.4. They are saved
unchanged in `profiles/prusaslicer/supplied-2026-05/`. `bundle.json` records each
original archive filename, role and SHA-256, plus the archive hash. Selecting
the bundle loads all three roles; it is not three alternative print presets.

## Run an offline preview

From `bioprinter/`, using the existing environment:

```powershell
# Inspect every original setting, its effective value and the override policy.
.\.venv\Scripts\python.exe -m bioprinter prusa-config profiles/prusaslicer/supplied-2026-05 --profile profiles/supplied-prusa-preview.yaml

# Use Python tracing, the small SVG size preset, and native PrusaSlicer.
.\.venv\Scripts\python.exe -m bioprinter compose examples/inputs --profile profiles/supplied-prusa-preview.yaml --preset small --backend prusa --prusa-config profiles/prusaslicer/supplied-2026-05

# Use Inkscape tracing with the same slicer configuration.
.\.venv\Scripts\python.exe -m bioprinter compose examples/inputs --profile profiles/supplied-prusa-preview.yaml --preset small --vectorizer inkscape --backend prusa --prusa-config profiles/prusaslicer/supplied-2026-05
```

Replace `examples/inputs` with the desired input folder. The usual SVG size,
threshold, registration, image order and quadrant options still apply. Existing
SVGs bypass tracing. `slice` also accepts `--prusa-config`, but its raw G-code
must go through composition before any production handoff.

The notebook has `PRUSA_CONFIG`, `PERIMETERS`, `INFILL_DENSITY`,
`TOP_SOLID_LAYERS` and `BOTTOM_SOLID_LAYERS` variables. Select `BACKEND='prusa'`
and load the preview YAML explicitly for the example above. The batch widget
has a **Prusa bundle** path field and uses the current notebook `PROFILE`.
Changing the bundle does not silently replace that profile. Notebook Run All
continues to use the direct synthetic demo unless these choices are changed.

## Settings and precedence

The bundle supplies reviewed path-generation settings: perimeter count/generator,
thin-wall and gap-fill choices, sparse/solid infill patterns, angle, density,
overlap, anchors, seams and wall transitions. Explicit `--perimeters`, `--infill`
(fraction 0–1), `--top-solid-layers` and `--bottom-solid-layers` override the bundle.
Omit them to retain source settings. Without a bundle, composition keeps its
existing one-perimeter / 15% infill defaults.

The active YAML profile and offline export policy take precedence for physical
dimensions, speeds, extrusion interpretation and executable output:

| Setting | Supplied INIs | Effective behavior |
| --- | --- | --- |
| Needle identity | No gauge/length measurement | Remains 23 gauge × 12.7 mm length |
| Bed | X ±60, Y ±125 mm | Active profile: X ±101.6, Y ±127; each quadrant 4 × 5 inches |
| Layer height | 0.05 mm | Active YAML; the separate preview uses 0.05 mm; nominal default remains 0.5 mm |
| Nozzle | 0.33 mm | Active YAML; preview uses this unverified slicer value, not a confirmed bore |
| Bead widths | Mostly 0.37, first 0.35, top 0.33 mm | One active nominal bead width; preview uses 0.37 mm |
| Filament diameter | 10.3 mm | Active raw-E convention; preview uses 10.3, not a barrel measurement |
| Extrusion multiplier | 2.85 | 1; final relative syringe E uses pipeline volume calibration |
| Perimeters / sparse infill | 1 / 0% | Retained unless explicitly overridden |
| Top / bottom solid layers | 1 / 1 | Retained: a single-layer model is solid-filled despite 0% sparse infill |
| Speeds | Perimeter/first 5; infill 80 mm/s | Active profile; preview deposition 5 mm/s, travel 30 mm/s |
| Minimum layer height | 0.07 mm | 0 in the resolved slicer config; layer is explicitly set by YAML |
| End/custom G-code | Includes M84, M600, M601 | Cleared, including filament, pause, color and object hooks |
| Cooling / fan | Enabled / up to 100% | Disabled; generated raw instructions still pass strict cleanup |
| Postprocessing / substitutions | Empty in supplied set | Always cleared; archive contents are never executed |
| Machine limits / firmware settings | Contains generic limits | Not imported as calibration or emitted to hardware |

`profiles/supplied-prusa-preview.yaml` is explicitly **synthetic**. It combines
the stated slicer dimensions with invented existing demo values for remaining
fields. It has no hardware confirmations and cannot authorize production. The
real needle profile remains unmeasured. Using the nominal 0.5 mm profile with
a 0.33 mm bore is not made compatible by importing this bundle; Prusa may reject
it. The adapter never enlarges a bore to bypass its checks.

Prusa settings outside the reviewed set are recorded as ignored rather than
passed through. Nonempty inheritance, duplicate keys, INI sections, private host
credentials and malformed values reject. Importing a config file is not evidence
of measured bore, barrel, mounting, motion limits, Z offsets or extrusion calibration.

## Provenance and future imports

Each composed run snapshots `slicer-config/bundle.json` and the three originals.
`reports/prusa-config.json` lists every source value as retained, overridden or
ignored, with the effective configuration and reason. Each raw slice also has
its resolved `.ini`, `.config-report.json`, `.sources/`, `.command.json` and log.
These files are included in the run hashes checked by preflight. One immutable
snapshot is used across the whole batch, even if the source folder changes later.

To import another ZIP containing exactly one standalone export of each role:

```powershell
.\.venv\Scripts\python.exe -m bioprinter import-prusa-configs C:\path\to\configs.zip profiles/prusaslicer/my-new-set
```

The destination must be new. ZIP paths, entry types, sizes and roles are checked
before writing. Private host/API fields must be cleared before import. Full
Prusa configuration bundles with INI sections or unresolved `inherits` are not
supported; export each individual preset instead. Originals are not installed
into the user's global Prusa preferences, and no printer is contacted.

Native validation commands and outcomes are recorded in `VALIDATION.md`.
