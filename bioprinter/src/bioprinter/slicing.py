from dataclasses import dataclass
from pathlib import Path
import json
import math
from shapely.geometry import LineString
from .geometry import polygons
from .external import probe,run


@dataclass
class Toolpath:
    points: list
    volume_per_mm: float
    source_line: int = 0


def direct_paths(geometry, profile, perimeters=1, infill_density=0.2, top_solid=0, bottom_solid=0):
    """Inset centerlines with conservative footprint containment; no rectangular substrate."""
    width=profile.bead_width_mm
    if perimeters<0 or not 0<=infill_density<=1: raise ValueError("Invalid direct slice settings")
    paths=[];inset=geometry.buffer(-width/2,join_style=2)
    if inset.is_empty: raise ValueError("Feature narrower than bead: reduce width after calibration or use printable SVG strokes")
    for island in polygons(geometry):
        if island.buffer(-width/2,join_style=2).is_empty:
            raise ValueError("Disconnected island narrower than bead would be lost; enlarge it or explicitly remove it")
    volume=width*profile.deposition_height_mm
    for index in range(perimeters):
        region=geometry.buffer(-width*(index+.5),join_style=2)
        for poly in polygons(region):
            for ring in [poly.exterior,*poly.interiors]:
                paths.append(Toolpath(list(ring.coords),volume))
    density=1.0 if top_solid or bottom_solid else infill_density
    if density:
        area=geometry.buffer(-width*(perimeters+.5),join_style=2)
        if not area.is_empty:
            x0,y0,x1,y1=area.bounds;spacing=width/density;index=0
            y=math.ceil(y0/spacing)*spacing
            while y<=y1+1e-9:
                segments=area.intersection(LineString([(x0-1,y),(x1+1,y)]))
                lines=[segments] if segments.geom_type=="LineString" else getattr(segments,"geoms",[])
                for line in lines:
                    if line.geom_type=="LineString" and line.length>1e-8:
                        points=list(line.coords)
                        paths.append(Toolpath(points if index%2==0 else points[::-1],volume));index+=1
                y+=spacing
    if not paths: raise ValueError("No printable paths; choose perimeter/infill settings")
    for path in paths:
        if not geometry.buffer(1e-7).covers(LineString(path.points).buffer(width/2,cap_style=1,join_style=1)):
            raise ValueError("Bead footprint leaves printable geometry; increase feature width or simplify corners")
    return paths


def prusa_slice(mesh, output, profile, nozzle_diameter_mm, *, perimeters=1, density=20, top=0,bottom=0):
    cap=probe("prusa-slicer")
    if not cap["available"]: raise ValueError("PrusaSlicer unavailable; install/set BIOPRINTER_PRUSA_SLICER or explicitly select direct backend")
    flags=["--export-gcode","--load","--output","--dont-arrange"]
    missing=[f for f in flags if f not in cap["help"]]
    if missing: raise ValueError(f"Installed PrusaSlicer help lacks required flags {missing}; review adapter")
    if nozzle_diameter_mm<=0: raise ValueError("Set measured nozzle/bore dimension; never inflate it to bypass layer-height validation")
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists(): raise ValueError('Use a fresh Prusa output path; stale G-code must not mask a failed slice')
    config={"gcode_flavor":"reprapfirmware","layer_height":profile.deposition_height_mm,
        "first_layer_height":profile.deposition_height_mm,"nozzle_diameter":nozzle_diameter_mm,
        "filament_diameter":profile.slicer_filament_diameter_mm,"extrusion_width":profile.bead_width_mm,
        "first_layer_extrusion_width":profile.bead_width_mm,"perimeters":perimeters,"fill_density":f"{density}%",
        "fill_pattern":"rectilinear","top_solid_layers":top,"bottom_solid_layers":bottom,
        "skirts":0,"brim_width":0,"raft_layers":0,"support_material":0,"wipe_tower":0,
        "retract_length":0,"retract_lift":0,"wipe":0,"temperature":0,"first_layer_temperature":0,
        "bed_temperature":0,"first_layer_bed_temperature":0,"cooling":0,"fan_always_on":0,
        "min_fan_speed":0,"max_fan_speed":0,"bridge_fan_speed":0,"start_gcode":"",
        "end_gcode":"","before_layer_gcode":"","layer_gcode":"","toolchange_gcode":"",
        "binary_gcode":0,"use_relative_e_distances":0,"gcode_comments":1,
        "machine_limits_usage":"time_estimate_only","bed_shape":"-60x-125,60x-125,60x125,-60x125"}
    cfg=output.with_suffix('.ini');cfg.write_text('\n'.join(f"{k} = {v}" for k,v in config.items())+'\n',encoding='utf-8')
    args=[cap["executable"],"--load",str(cfg.resolve()),"--dont-arrange","--export-gcode","--output",str(output.resolve()),str(Path(mesh).resolve())]
    output.with_suffix('.command.json').write_text(json.dumps({"argv":args,"probe":cap,"config":config},indent=2),encoding="utf-8")
    try:
        log=run(args,300)
    except Exception as exc:
        output.with_suffix('.log').write_text(str(exc),encoding='utf-8')
        raise
    output.with_suffix('.log').write_text(log,encoding="utf-8")
    if not output.is_file() or not output.read_bytes().lstrip().startswith((b';',b'G',b'M')):
        raise ValueError("Expected newly generated plain-text G-code output. PrusaSlicer log:\n"+log)
    return output
