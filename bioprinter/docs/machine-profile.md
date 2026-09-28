# Machine profile conventions

`config.example.yaml` contains real requested values and null unresolved measurements.
`profiles/synthetic.yaml` contains invented working values and `synthetic: true`.
The latter can never authorize upload/start, even with confirmation flags added.
The generated JSON Schema is `schemas/machine-profile.schema.json`.

Coordinates are mm. Machine XY is centered: X −60..60, Y −125..125. SVG Y-down is
flipped once into Cartesian Y-up. Printable bounds come from visible fill and expanded
strokes, not page bounds. The local anchor is subtracted before a separate placement
translation. No G92 X/Y is emitted and existing firmware offsets are not applied twice.
The manifest records source/local and local/machine matrices and inverses. Slicer
registration is identity under `--dont-arrange`; output outside the input geometry
is rejected. Any future slicer recentering must be explicitly measured and recorded.

| Anchor | Cartesian coordinate |
|---|---|
| bottom_left | xmin, ymin |
| bottom_right | xmax, ymin |
| top_left | xmin, ymax |
| top_right | xmax, ymax |
| center | midpoint of bounds |

Shared-canvas is the default and preserves cropping offsets only when sources share a
canvas/registration. Per-design bounding boxes deliberately align each chosen visible
corner and can destroy alignment across cropped images. Use explicit affine registration
matrices when needed; no stack layer is silently resized to fill its quadrant.

| ID | Position | X mm | Y mm |
|---|---|---|---|
| Q1 | top-right | 0..60 | 0..125 |
| Q2 | bottom-right | 0..60 | −125..0 |
| Q3 | bottom-left | −60..0 | −125..0 |
| Q4 | top-left | −60..0 | 0..125 |

The larger of edge margin, centerline margin and holder radius reserves space in each
quadrant. Bead capsules must fit within the reserved region. Tool bodies must fit machine
limits. Whole-plate collisions include deposits from every quadrant. Oversize designs
fail rather than distorting. The Python `quadrant_order` option allows a different
permutation; CLI default remains Q1→Q2→Q3→Q4.

Before the first job the operator must establish the recorded initial pose
`(0,0,substrate_z_mm + travel_clearance_mm)`, correct selected tool, homed axes, reviewed
firmware configuration and bare substrate. The program emits no homing or tool changes.
Every continuation records its predecessor's final pose/material use/checkpoint and
starts with explicit G21/G90/M83 modal normalization, not a bare-plate initialization.

Grid resolution must be at most half the deposited bead width and segment sampling
at most one grid interval. A half-cell-diagonal halo conservatively captures narrow
features. Narrower grids improve geometry but still do not constitute liquid simulation.
Needle/holder swept envelopes are checked at each segment. Global maximum deposited
height determines travel lift; insufficient maximum Z or an inaccessible valley fails.

`confirmed_fields` is a list of the names returned by `doctor` as `confirm:<name>`.
Two true needle gauge/length flags do not confirm the rest. Production also needs an
actual `firmware_version`, `firmware_tool_number`, `cold_extrusion_reviewed` and
`machine_setup_reviewed`. A firmware/tool mismatch at start rejects the queue.
