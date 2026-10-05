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


def resolve_prusa_config(profile, nozzle_diameter_mm, *, perimeters=None, density=None,
                         top=None, bottom=None, prusa_config=None):
    from .prusa_config import load_bundle
    if nozzle_diameter_mm <= 0 or not math.isfinite(nozzle_diameter_mm):
        raise ValueError("Set measured nozzle/bore dimension; never inflate it to bypass layer-height validation")
    bundle = load_bundle(prusa_config) if prusa_config is not None else None
    config={"gcode_flavor":"reprapfirmware","layer_height":profile.deposition_height_mm,
        "first_layer_height":profile.deposition_height_mm,"nozzle_diameter":nozzle_diameter_mm,
        "filament_diameter":profile.slicer_filament_diameter_mm,"extrusion_width":profile.bead_width_mm,
        "first_layer_extrusion_width":profile.bead_width_mm,"perimeters":1,"fill_density":"20%",
        "fill_pattern":"rectilinear","top_solid_layers":0,"bottom_solid_layers":0,
        "skirts":0,"brim_width":0,"raft_layers":0,"support_material":0,"wipe_tower":0,
        "retract_length":0,"retract_lift":0,"wipe":0,"temperature":0,"first_layer_temperature":0,
        "bed_temperature":0,"first_layer_bed_temperature":0,"cooling":0,"fan_always_on":0,
        "min_fan_speed":0,"max_fan_speed":0,"bridge_fan_speed":0,"start_gcode":"",
        "end_gcode":"","before_layer_gcode":"","layer_gcode":"","toolchange_gcode":"",
        "binary_gcode":0,"use_relative_e_distances":0,"gcode_comments":1,
        "machine_limits_usage":"time_estimate_only",
        "bed_shape":','.join(f'{x:g}x{y:g}' for x,y in [(profile.x_min,profile.y_min),
            (profile.x_max,profile.y_min),(profile.x_max,profile.y_max),(profile.x_min,profile.y_max)])}
    if bundle:
        config.update(bundle.path_options())
    for key, value in [('perimeters', perimeters), ('top_solid_layers', top), ('bottom_solid_layers', bottom)]:
        if value is not None:
            if isinstance(value, bool) or int(value) != value or value < 0:
                raise ValueError(f'{key} must be a nonnegative integer')
            config[key] = value
    if density is not None:
        if not math.isfinite(density) or not 0 <= density <= 100:
            raise ValueError('Prusa density must be between 0 and 100 percent')
        config['fill_density'] = f'{density:g}%'
    # The footprint model uses one nominal bead width. Do not import per-role widths
    # or a second, uncalibrated flow multiplier from the source presets.
    for key in ('external_perimeter_extrusion_width', 'perimeter_extrusion_width',
                'infill_extrusion_width', 'solid_infill_extrusion_width', 'top_infill_extrusion_width',
                'support_material_extrusion_width'):
        config[key] = profile.bead_width_mm
    for key in ('start_filament_gcode', 'end_filament_gcode', 'between_objects_gcode',
                'color_change_gcode', 'pause_print_gcode', 'template_custom_gcode',
                'post_process', 'gcode_substitutions', 'print_host', 'printhost_apikey'):
        config[key] = ''
    config.update(autoemit_temperature_commands=0, extrusion_multiplier=1,
                  use_volumetric_e=int(profile.slicer_e_mode == 'mm3'),
                  arc_fitting='disabled', spiral_vase=0, ironing=0, complete_objects=0,
                  xy_size_compensation=0, elefant_foot_compensation=0,
                  top_solid_min_thickness=0, bottom_solid_min_thickness=0,
                  retract_length_toolchange=0, use_firmware_retraction=0,
                  single_extruder_multi_material=0, z_offset=0, extruder_offset='0x0',
                  max_print_height=profile.z_max, min_layer_height=0,
                  chamber_temperature=0, chamber_minimal_temperature=0,
                  travel_speed=profile.xy_speed_mm_s, travel_speed_z=profile.z_speed_mm_s)
    for key in ('perimeter_speed', 'external_perimeter_speed', 'small_perimeter_speed',
                'infill_speed', 'solid_infill_speed', 'top_solid_infill_speed',
                'first_layer_speed', 'gap_fill_speed', 'bridge_speed', 'max_print_speed'):
        config[key] = profile.deposition_speed_mm_s
    audit = bundle.audit(config) if bundle else {'sources': [], 'settings': []}
    audit.update(effective_config=config, needle=profile.needle_summary(),
                 policy='Only reviewed print-path settings imported. Machine YAML controls dimensions, speeds and E convention. Hooks, networking, thermal/fan, retraction and extra structures disabled. Extrusion multiplier is 1; final syringe E uses the pipeline calibration.',
                 production_approved=False, printer_contacted=False)
    return config, audit, bundle


def prusa_slice(mesh, output, profile, nozzle_diameter_mm, *, perimeters=None, density=None,
                top=None, bottom=None, prusa_config=None):
    config, audit, bundle = resolve_prusa_config(profile, nozzle_diameter_mm,
        perimeters=perimeters, density=density, top=top, bottom=bottom, prusa_config=prusa_config)
    cap=probe("prusa-slicer")
    if not cap["available"]: raise ValueError("PrusaSlicer unavailable; install/set BIOPRINTER_PRUSA_SLICER or explicitly select direct backend")
    flags=["--export-gcode","--load","--output","--dont-arrange"]
    missing=[f for f in flags if f not in cap["help"]]
    if missing: raise ValueError(f"Installed PrusaSlicer help lacks required flags {missing}; review adapter")
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists(): raise ValueError('Use a fresh Prusa output path; stale G-code must not mask a failed slice')
    if bundle:
        snapshot = bundle.snapshot(output.with_suffix('.sources'))
        audit['source_snapshot'] = snapshot.relative_to(output.parent).as_posix()
    output.with_suffix('.config-report.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
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
