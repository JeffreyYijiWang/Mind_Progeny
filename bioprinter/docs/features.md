# Supported features and explicit limits

| Area | Implemented and offline-tested | Explicit boundary / remaining integration |
|---|---|---|
| Batch | PNG/JPEG/TIFF/BMP/SVG; EXIF; alpha background; natural order; repeats; recursive/order-list; quadrant sequences | Split animated/multi-page sources first; all processing reruns fresh, no cache-resume optimization |
| Raster vectors | OpenCV contour hierarchy; holes/islands; median denoise; threshold/invert; mm simplification/min-area | Filled silhouettes only. Raster outline/centerline extraction not implemented; use stroked SVG input |
| SVG | Paths including flattened curves/arcs, groups, affine transforms, physical units, viewBox, nonzero/evenodd, solid strokes | Text, images, effects, masks, clipping, use/external refs, CSS stylesheets, dashed/vector-effect strokes, nested SVG viewports, rounded rect primitives rejected; convert to plain paths |
| Registration | Five anchors, single Y flip, shared canvas, explicit affine matrices, inverses | Different cropped canvases require explicit registration; no automatic feature alignment |
| Mesh | Watertight thin STL, holes/islands, verified signed volume | STL is unitless on disk with explicit millimeter convention; no 3MF adapter |
| Direct toolpaths | Inset perimeters and sparse rectilinear infill; preserved negative space; thin-island rejection | Centerlines are not extracted from photographs; unprintable thin detail needs user revision |
| PrusaSlicer | Capability probe, strict required flags, syringe INI, mesh/argv/log capture, interpreted result | Executable absent here; actual 0.5 mm/measured-bore profile and RepRapFirmware output require integration testing; never automatic fallback |
| Inkscape | Capability probe and explicit manual trace round-trip | Executable absent; no claimed universal headless trace-bitmap action |
| G-code | G0/G1, XYZ/E modes, G20/G21, G92, feed, dwell; thermal/fan removal report; final allowlist/reparse | G2/G3 and volumetric-inch input reject explicitly; firmware macros/tools/homing/config/expression/checksum/coordinate commands reject; unsupported slicer output requires reviewed adapter changes |
| Extrusion | Filament-volume or explicit volumetric input to measured syringe E; signed direction; cumulative capacity/stroke; output rate limits | Prime/retraction omitted with audit until separately calibrated; selected tool and cold extrusion are operator-reviewed firmware state |
| Stacking | Local bead footprints, cell-local overlap height, per-event union, repeat additions, planar alternative, lift/relocate, needle/holder collisions | Conservative geometry, not fluid mechanics. Uneven/unsupported footprints block production. Zero lateral needle tilt, circular holder envelope, flat substrate; richer tools/substrate models need implementation |
| Quadrants | Four separate sequences or replication; clockwise round robin/complete stack; global clearance; margins | Fixed centered plate ranges; Python order permutation available; no automatic packing |
| Jobs | Combined and ordered continuations, hashes, exact pose/predecessor/material/checkpoint metadata | Physical restart never inferred from files; refill/recovery needs operator reconciliation |
| Timing | Final-byte-based trapezoidal estimate; XYZ/E constraints, dwell, transitions; contiguous intervals/schema | Zero junction speed is a conservative approximation. Transfer/pressure/firmware overhead unknown; no claimed numeric accuracy |
| Display | Offline HTML player; explicit pause-aware live status observer and separate records | Live observer uses buffered file position, not executed markers; no live browser-printer bridge or automatic observed-interval reconstruction |
| Video | MOV H.264/MPEG4, contain/crop/background, active/quadrant frames, cumulative frame rounding, ffprobe check | Render the planned timeline by default; real pauses do not automatically alter movie playback |
| Duet | Standalone RRF 3.x session/status/upload, CRC and byte verification, explicit controls, persistent start-once queue | Hardware not contacted. Automatic successful-completion detection unavailable on standalone; operator confirmation gates successors |
| Notebook | 11 code cells, saved outputs, explicit widgets and interrupt/cancellation, separate printer instructions | Fresh-kernel Windows execution verified; no claim of hardware validation or Linux/macOS runtime testing |

Important approximation: grid occupancy is conservative and per-cell heights preserve
gaps, but a commanded horizontal bead over uneven ground can be partially unsupported.
The preview diagnoses it and cannot turn it into an approved production job. No silent
smoothing, implied structural stability or simulation-as-proof claim is made.
