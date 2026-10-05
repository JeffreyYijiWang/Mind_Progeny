from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import math
import shutil
import uuid
import numpy as np
import yaml
from shapely.ops import unary_union
from shapely.geometry import LineString
from .config import demo_profile
from .ingestion import discover,sha256
from .vectorization import vectorize
from .geometry import register,write_svg,Design,apply
from .meshing import write_stl
from .slicing import direct_paths,prusa_slice,Toolpath
from .gcode import interpret,serialize,GCodeError
from .extrusion import convert_slicer
from .layout import schedule,placement,FOLDERS
from .stacking import Planner,CollisionError
from .timing import timeline


def write_json(path,data):
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def new_run(root):
    run=Path(root)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'_'+uuid.uuid4().hex[:8])
    for folder in ['inputs','meshes','slicer_raw','gcode_cleaned','jobs','combined','previews','simulation','timing','video','reports','checkpoints','logs']:
        (run/folder).mkdir(parents=True,exist_ok=False)
    for folder in FOLDERS.values(): (run/'quadrants'/folder/'svgs').mkdir(parents=True)
    return run


def direct_raw(paths,profile):
    lines=['; Direct polygon backend: plain mm filament E','G21','G90','M82'];e=0
    area=math.pi*(profile.slicer_filament_diameter_mm/2)**2 if profile.slicer_e_mode=='filament_mm' else 1
    z=profile.deposition_height_mm
    for path in paths:
        x,y=path.points[0];lines.append(f'G1 X{x:.8f} Y{y:.8f} Z{z:.8f} F{profile.xy_speed_mm_s*60}')
        for a,b in zip(path.points,path.points[1:]):
            if math.dist(a,b)<1e-9: continue
            e+=math.dist(a,b)*path.volume_per_mm/area
            lines.append(f'G1 X{b[0]:.8f} Y{b[1]:.8f} E{e:.10f} F{profile.deposition_speed_mm_s*60}')
    return '\n'.join(lines)+'\n'


def compose(folder, profile=None, *, output_root='runs', width_mm=None, sequences=None, order=None,
            repeats=1, schedule_mode='round_robin', stack_mode='overlap_aware', anchor='bottom_left',
            registration='shared_canvas', backend='direct', vectorizer='python', per_image=None,
            recursive=False, perimeters=None, infill_density=None, production=False, progress=None,
            cancelled=None, quadrant_order=('Q1','Q2','Q3','Q4'), preset=None, trace_options=None,
            prusa_config=None, top_solid_layers=None, bottom_solid_layers=None):
    profile=profile or demo_profile();profile.require(production)
    if repeats<1: raise ValueError('Repeat count must be positive')
    if prusa_config is not None and backend != 'prusa':
        raise ValueError('prusa_config requires backend prusa; it cannot be silently ignored')
    if prusa_config is None:
        perimeters = 1 if perimeters is None else perimeters
        infill_density = .15 if infill_density is None else infill_density
    if infill_density is not None and (not math.isfinite(infill_density) or not 0 <= infill_density <= 1):
        raise ValueError('infill_density must be between 0 and 1')
    if prusa_config is not None:
        from .prusa_config import load_bundle
        prusa_config = load_bundle(prusa_config)  # immutable source bytes for the entire run
    run=new_run(output_root);assets=discover(folder,recursive,order);per_image=per_image or {}
    settings=dict(width_mm=width_mm,repeats=repeats,schedule=schedule_mode,stack_mode=stack_mode,
                  anchor=anchor,registration=registration,backend=backend,vectorizer=vectorizer,
                  perimeters=perimeters,infill_density=infill_density,per_image=per_image,
                  svg_preset=preset,trace_options=trace_options or {},
                  top_solid_layers=top_solid_layers,bottom_solid_layers=bottom_solid_layers,
                  prusa_config='slicer-config/bundle.json' if prusa_config else None)
    (run/'config.resolved.yaml').write_text(yaml.safe_dump(profile.model_dump(),sort_keys=True),encoding='utf-8')
    manifest={'schema_version':'1.0','run_id':run.name,'status':'processing','production':production,
        'profile_sha256':profile.digest(),'needle':profile.needle_summary(),'settings':settings,'assets':[], 'network_contacted':False,
        'cache_policy':'No reuse; every invocation creates a fresh isolated run. Checkpoints never imply physical resume.'}
    try:
        write_json(run/'reports'/'needle.json', profile.needle_summary())
        if prusa_config:
            from .slicing import resolve_prusa_config
            prusa_config.snapshot(run/'slicer-config')
            _, report, _ = resolve_prusa_config(profile,profile.needle_inner_diameter_mm,
                prusa_config=prusa_config,perimeters=perimeters,
                density=None if infill_density is None else infill_density*100,
                top=top_solid_layers,bottom=bottom_solid_layers)
            write_json(run/'reports'/'prusa-config.json',report)
        designs={};toolpaths={};by_name={}
        for index,asset in enumerate(assets):
            if cancelled and cancelled(): raise InterruptedError('Cancelled between assets; run is incomplete')
            if progress: progress(f'Prepare {index+1}/{len(assets)}: {asset.path.name}')
            if asset.asset_id in designs: continue
            copy=run/'inputs'/(asset.asset_id+asset.path.suffix.lower());shutil.copy2(asset.path,copy)
            opts={**(trace_options or {}),**per_image.get(asset.path.name,{})};explicit=opts.pop('registration_matrix',None)
            asset_preset=opts.pop('preset',preset);preset_record=None
            asset_width=opts.pop('width_mm',width_mm)
            if asset_preset:
                from .presets import resolve
                opts,preset_record=resolve(asset.path,asset_preset,profile=profile,width_mm=asset_width,overrides=opts)
                asset_width=opts.pop('width_mm')
            elif asset_width is None: asset_width=24
            if vectorizer=='inkscape': opts['trace_dir']=run/'inputs'/(asset.asset_id+'.inkscape')
            d=vectorize(asset.path,width_mm=asset_width,backend=vectorizer,**opts)
            if preset_record: d.metadata['svg_preset']=preset_record
            d=register(d,anchor,registration,explicit)
            designs[asset.asset_id]=d;by_name[asset.path.relative_to(Path(folder).resolve()).as_posix()]=asset.asset_id
            svg=run/'inputs'/(asset.asset_id+'.normalized.svg');write_svg(d,svg,preserve_canvas=True)
            mesh=run/'meshes'/(asset.asset_id+'.stl');mesh_info=write_stl(d.geometry,profile.deposition_height_mm,mesh)
            raw=run/'slicer_raw'/(asset.asset_id+'.gcode')
            if backend=='direct':
                paths=direct_paths(d.geometry,profile,perimeters,infill_density,
                                   top_solid=top_solid_layers or 0,bottom_solid=bottom_solid_layers or 0)
                raw.write_text(direct_raw(paths,profile),encoding='ascii')
            elif backend=='prusa':
                prusa_slice(mesh,raw,profile,profile.needle_inner_diameter_mm,perimeters=perimeters,
                    density=None if infill_density is None else infill_density*100,
                    top=top_solid_layers,bottom=bottom_solid_layers,prusa_config=prusa_config)
            else: raise ValueError('Select backend direct or prusa')
            motions,cleanup=interpret(raw.read_text(encoding='utf-8'),e_units=profile.slicer_e_mode)
            converted,volume=convert_slicer(motions,profile)
            if any(m.dwell for m in converted): raise ValueError('Slice dwell requires explicit composition support; remove in audited profile')
            paths=[];allowed_source=d.geometry.buffer(profile.bead_width_mm/2+1e-5)
            for m in converted:
                if m.kind=='deposit' and m.e_delta:
                    if abs(m.start[2]-m.end[2])>1e-6: raise ValueError('Nonplanar slicer deposition requires separate layer import')
                    if abs(m.end[2]-profile.deposition_height_mm)>1e-4: raise ValueError('Expected a single nominal slice layer')
                    if m.length<=0: raise ValueError('Deposit must have a nonzero path')
                    if not allowed_source.covers(LineString([m.start[:2],m.end[:2]])):
                        raise ValueError('Slicer changed placement; resolve and record slicer registration before import')
                    paths.append(Toolpath([m.start[:2],m.end[:2]],abs(m.e_delta)*profile.mm3_per_e_unit/m.length,m.source_line))
            if not paths: raise ValueError('Slicer produced no deposition')
            toolpaths[asset.asset_id]=paths
            write_json(run/'gcode_cleaned'/(asset.asset_id+'.motions.json'),[m.dict() for m in converted])
            write_json(run/'reports'/(asset.asset_id+'.cleanup.json'),{'actions':cleanup+volume['report'],'volume_mm3':volume['volume_mm3']})
            thin=d.geometry.difference(d.geometry.buffer(-profile.bead_width_mm/2).buffer(profile.bead_width_mm/2))
            record={**asset.metadata(),'input_copy':copy.relative_to(run).as_posix(),'svg_path':svg.relative_to(run).as_posix(),
                    'mesh_path':mesh.relative_to(run).as_posix(),'raw_gcode':raw.relative_to(run).as_posix(),
                    'cleaned_motions':f'gcode_cleaned/{asset.asset_id}.motions.json','geometry':d.metadata,
                    'slicer_to_local':np.eye(3).tolist(),'local_to_slicer':np.eye(3).tolist(),
                    'mesh':mesh_info,'uncovered_feature_area_mm2':thin.area}
            manifest['assets'].append(record)
        if registration=='shared_canvas':
            canvases=[d.canvas for d in designs.values()]
            if any(not np.allclose(canvases[0],c,atol=1e-5) for c in canvases[1:]):
                raise ValueError('shared_canvas requires matching common canvases; provide explicit registration or matching source sizes')
        if sequences is None:
            ids=[a.asset_id for a in assets]*repeats;sequences={q:ids[:] for q in FOLDERS}
        else:
            sequences={q:[by_name.get(name,name) for name in values]*repeats for q,values in sequences.items()}
        execution=schedule(sequences,schedule_mode,quadrant_order)
        if not execution: raise ValueError('No scheduled designs')
        placements={}
        for q,ids in sequences.items():
            if not ids: continue
            if any(i not in designs for i in ids): raise ValueError(f'Unknown asset in {q} sequence')
            common=unary_union([designs[i].geometry for i in ids]).bounds
            placements[q]=placement(common,q,profile)
        planner=Planner(profile,stack_mode,run/'checkpoints')
        records={a['asset_id']:a for a in manifest['assets']}
        for n,(q,index,aid) in enumerate(execution,1):
            if cancelled and cancelled(): raise InterruptedError('Cancelled between segments; run incomplete')
            if progress: progress(f'Compose {n}/{len(execution)}: {q} design {index+1}')
            mat,allowed=placements[q];d=designs[aid]
            svg=run/'quadrants'/FOLDERS[q]/'svgs'/f'{index+1:04d}_{aid}.svg';write_svg(d,svg,preserve_canvas=True)
            transformed=[]
            for path in toolpaths[aid]:
                coords=[tuple((np.asarray(mat)@[*p,1])[:2]) for p in path.points]
                transformed.append(Toolpath(coords,path.volume_per_mm,path.source_line))
            planner.add(transformed,{'event_id':f'event-{n:04d}','global_execution_index':n,'asset_id':aid,
                'source_path':records[aid]['input_copy'],'source_sha256':records[aid]['sha256'],
                'svg_path':svg.relative_to(run).as_posix(),'quadrant':q,'sequence_index':index,
                'nominal_layer_index':index,'local_to_machine':mat,'machine_to_local':np.linalg.inv(mat).tolist()},allowed)
        if production and planner.plan.diagnostics:
            raise ValueError('Production blocked by support diagnostics; inspect reports/diagnostics.json')
        manifest['initial_xyz']=planner.initial;manifest['used_mm3']=planner.plan.used_mm3
        data,ranges,parsed=serialize(planner.plan.motions,preview=not production)
        combined=run/'combined'/'combined.gcode';combined.write_bytes(data)
        digest=sha256(combined)
        # Serialized numerical values, not raw slicer estimates, drive timing.
        for original,rounded in zip(planner.plan.motions,parsed):
            rounded.event=original.event;rounded.kind=original.kind;rounded.source=original.source
        tl=timeline(planner.plan.events,parsed,ranges,profile,digest)
        write_json(run/'timing'/'display_timeline.json',tl)
        write_json(run/'reports'/'source_map.json',ranges)
        write_json(run/'reports'/'diagnostics.json',planner.plan.diagnostics)
        write_json(run/'simulation'/'motions.json',[m.dict() for m in parsed])
        planner.field.save(run/'checkpoints'/'final.npz')
        jobs=[]
        for n,event in enumerate(planner.plan.events,1):
            subset=planner.plan.motions[event['motion_start']:event['motion_end']]
            jobdata,jobranges,_=serialize(subset,preview=not production)
            name=f'{n:04d}_job-{n:04d}.gcode';path=run/'jobs'/name;path.write_bytes(jobdata)
            jobs.append({'job_id':f'job-{n:04d}','path':'jobs/'+name,'sha256':sha256(path),
                'type':'standalone' if n==1 else 'continuation','predecessor_id':None if n==1 else f'job-{n-1:04d}',
                'start_xyz':event['start_xyz'],'end_xyz':event['end_xyz'],
                'used_before_mm3':event['used_before_mm3'],'used_after_mm3':event['used_after_mm3'],
                'remaining_capacity_mm3':profile.capacity_mm3-event['used_after_mm3'],
                'height_checkpoint':None if n==1 else f'checkpoints/{n-1:04d}_event-{n-1:04d}.npz',
                'preconditions':['Operator-verified pose/tool/cold-extrusion settings','No homing or bare-plate reset','Predecessor physically completed'],
                'event_id':event['event_id'],'line_start':jobranges[0]['line'],'line_end':jobranges[-1]['line'],
                'byte_start':jobranges[0]['byte_start'],'byte_end':jobranges[-1]['byte_end']})
        write_json(run/'timing'/'jobs.json',{'schema_version':'1.0','jobs':jobs,'combined_sha256':digest})
        from .simulation import previews
        previews(run,parsed,planner.field,tl)
        from .display import write_player
        write_player(run,tl)
        from .external import doctor
        capabilities=doctor(profile);write_json(run/'reports'/'doctor.json',capabilities)
        manifest.update(status='complete',combined_sha256=digest,events=planner.plan.events,
                        diagnostics=planner.plan.diagnostics,versions=capabilities,validation='offline geometric checks only')
        manifest['files']={p.relative_to(run).as_posix():sha256(p) for p in sorted(run.rglob('*')) if p.is_file()}
        write_json(run/'manifest.json',manifest)
        return run
    except BaseException as exc:
        manifest.update(status='cancelled' if isinstance(exc,(KeyboardInterrupt,InterruptedError)) else 'failed',error=str(exc))
        if 'planner' in locals(): write_json(run/'reports'/'diagnostics.json',planner.plan.diagnostics)
        if isinstance(exc,CollisionError) and 'planner' in locals():
            from .simulation import collision_preview
            collision_preview(run,planner,exc)
            write_json(run/'reports'/'collision.json',{'error':str(exc),'location':exc.location,'status':'rejected'})
        if isinstance(exc,GCodeError): write_json(run/'reports'/'gcode_rejection.json',exc.report)
        write_json(run/'manifest.json',manifest)
        raise


def preflight(run,production=True):
    from .config import load_profile
    run=Path(run);manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    profile=load_profile(run/'config.resolved.yaml');profile.require(production)
    if manifest['status']!='complete' or (production and not manifest['production']): raise ValueError('Run not approved for production')
    if profile.digest()!=manifest['profile_sha256']: raise ValueError('Resolved profile changed; recompose')
    for name,digest in manifest['files'].items():
        path=(run/name).resolve()
        if not path.is_relative_to(run.resolve()) or sha256(path)!=digest: raise ValueError(f'Run content changed: {name}')
    for path in [run/'combined'/'combined.gcode',*(run/'jobs').glob('*.gcode')]:
        interpret(path.read_text(encoding='ascii'),initial=manifest['initial_xyz'],final_policy=True)
    if production and manifest['diagnostics']: raise ValueError('Unresolved production diagnostics')
    return profile,manifest
