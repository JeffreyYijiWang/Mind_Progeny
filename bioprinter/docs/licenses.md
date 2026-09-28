# Dependency license notes

These are pointers for reviewing redistribution, not bundled license replacements.
Installed distribution metadata/individual upstream license files are authoritative.

| Direct dependency | Upstream license family |
|---|---|
| Python | PSF |
| NumPy | BSD-3-Clause |
| Pillow | MIT-CMU / HPND |
| OpenCV headless wheels | Apache-2.0; bundled components have their own notices |
| Shapely | BSD-3-Clause; GEOS LGPL |
| svgpathtools / svgwrite | MIT |
| defusedxml | PSF |
| Pydantic | MIT |
| PyYAML | MIT |
| httpx | BSD-3-Clause |
| Matplotlib | Matplotlib/PSF-based license |
| Plotly.py | MIT |
| jsonschema | MIT |
| pytest | MIT |
| Jupyter, nbformat, nbclient, ipykernel, ipywidgets | BSD-3-Clause family |
| Inkscape (external) | GPL |
| PrusaSlicer (external) | AGPL-3.0 |
| FFmpeg (external) | LGPL/GPL depending on build; tested build has GPL enabled |

No external application binaries are redistributed in this project. Self-contained
Plotly previews include the installed Plotly.js runtime and its upstream license notice.
The synthetic example images are drawn by this project's Pillow example generator.
