from pathlib import Path
import argparse
import json
import sys
import time
from .config import load_profile,demo_profile,Profile
from .pipeline import compose,preflight,write_json
from .presets import PRESETS
from .ingestion import sha256


def trace_arguments(parser):
    parser.add_argument('--preset',choices=list(PRESETS),help='Aspect-preserving physical canvas and tracing defaults')
    parser.add_argument('--threshold',type=int)
    parser.add_argument('--denoise',type=int)
    parser.add_argument('--min-area-mm2',type=float)
    parser.add_argument('--simplify-mm',type=float)
    parser.add_argument('--max-pixels',type=int)
    parser.add_argument('--invert',action='store_true',default=None)


def trace_settings(args):
    return {key:getattr(args,key) for key in ('threshold','denoise','min_area_mm2','simplify_mm','max_pixels','invert')
            if getattr(args,key) is not None}


def slicer_arguments(parser):
    parser.add_argument('--prusa-config',help='Imported bundle.json or its directory; requires --backend prusa')
    parser.add_argument('--perimeters',type=int)
    parser.add_argument('--infill',type=float,help='Fraction 0..1; omitted uses bundle settings or pipeline default')
    parser.add_argument('--top-solid-layers',type=int)
    parser.add_argument('--bottom-solid-layers',type=int)


def main(argv=None):
    parser=argparse.ArgumentParser(prog='bioprinter',description='Offline by default. Printer actions are explicit duet subcommands.')
    sub=parser.add_subparsers(dest='command',required=True)
    doctor=sub.add_parser('doctor');doctor.add_argument('--profile')
    sub.add_parser('presets',help='List physical canvas and converter settings')
    imp=sub.add_parser('import-prusa-configs',help='Import three exported INIs from a ZIP without running them')
    imp.add_argument('archive');imp.add_argument('destination')
    review=sub.add_parser('prusa-config',help='Review effective settings and every source override offline')
    review.add_argument('bundle');review.add_argument('--profile',required=True)
    demo=sub.add_parser('demo');demo.add_argument('--output',default='runs');demo.add_argument('--video',action='store_true')
    for command in ('compose','export'):
        p=sub.add_parser(command);p.add_argument('folder');p.add_argument('--profile',required=True)
        p.add_argument('--width-mm',type=float);p.add_argument('--output',default='runs');trace_arguments(p)
        p.add_argument('--backend',choices=['direct','prusa'],default='direct');p.add_argument('--vectorizer',choices=['python','inkscape'],default='python')
        p.add_argument('--manifest',help='JSON: order, sequences, per_image');p.add_argument('--repeats',type=int,default=1)
        p.add_argument('--registration',choices=['shared_canvas','per_design_bbox'],default='shared_canvas')
        p.add_argument('--anchor',choices=['bottom_left','bottom_right','top_left','top_right','center'],default='bottom_left')
        p.add_argument('--schedule',choices=['round_robin','complete_stack'],default='round_robin')
        p.add_argument('--mode',choices=['overlap_aware','planar_stack'],default='overlap_aware');p.add_argument('--recursive',action='store_true')
        p.add_argument('--production',action='store_true');slicer_arguments(p)
    vec=sub.add_parser('vectorize');vec.add_argument('input');vec.add_argument('output');vec.add_argument('--width-mm',type=float)
    vec.add_argument('--backend',choices=['python','inkscape'],default='python');vec.add_argument('--profile');trace_arguments(vec)
    sl=sub.add_parser('slice');sl.add_argument('svg');sl.add_argument('output');sl.add_argument('--profile',required=True);sl.add_argument('--width-mm',type=float,required=True);sl.add_argument('--backend',choices=['direct','prusa'],default='direct')
    slicer_arguments(sl)
    sim=sub.add_parser('simulate');sim.add_argument('run')
    vid=sub.add_parser('video');vid.add_argument('run');vid.add_argument('--fps',type=float,default=24);vid.add_argument('--width',type=int,default=640);vid.add_argument('--height',type=int,default=480);vid.add_argument('--codec',default='libx264');vid.add_argument('--quadrants',action='store_true');vid.add_argument('--timeline');vid.add_argument('--policy',choices=['contain','crop'],default='contain');vid.add_argument('--background',default='white')
    duet=sub.add_parser('duet');duet.add_argument('--url',default='http://hans.local');ds=duet.add_subparsers(dest='action',required=True)
    ds.add_parser('status')
    up=ds.add_parser('upload');up.add_argument('run');up.add_argument('--jobs',action='store_true')
    q=ds.add_parser('run-queue');q.add_argument('run');q.add_argument('--start',action='store_true');q.add_argument('--confirm-completed');q.add_argument('--poll-seconds',type=float,default=2);q.add_argument('--watch',action='store_true')
    live=ds.add_parser('display');live.add_argument('run');live.add_argument('--poll-seconds',type=float,default=2);live.add_argument('--samples',type=int,default=10)
    for action in ['pause','resume','cancel']:
        control=ds.add_parser(action);control.add_argument('--reviewed-macros',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.command=='import-prusa-configs':
            from .prusa_config import import_zip
            print(import_zip(args.archive,args.destination).resolve());return
        if args.command=='prusa-config':
            from .slicing import resolve_prusa_config
            profile=load_profile(args.profile);profile.require()
            _,audit,_=resolve_prusa_config(profile,profile.needle_inner_diameter_mm,prusa_config=args.bundle)
            print(json.dumps(audit,indent=2));return
        if args.command=='presets':
            from .presets import catalog
            print(json.dumps(catalog(),indent=2));return
        if args.command=='doctor':
            from .external import doctor
            report=doctor(load_profile(args.profile) if args.profile else Profile())
            for cap in report['external'].values():cap.pop('help',None);cap.pop('actions',None)
            print(json.dumps(report,indent=2));return
        if args.command=='demo':
            from .examples import make_inputs
            folder=make_inputs(Path(args.output)/'_demo_inputs')
            run=compose(folder,output_root=args.output,progress=print)
            if args.video:
                from .video import create_video
                create_video(run,fps=2,size=(320,240))
            print(run.resolve());return
        if args.command in {'compose','export'}:
            if args.width_mm is None and args.preset is None: raise ValueError('Specify --width-mm or --preset')
            overrides=json.loads(Path(args.manifest).read_text(encoding='utf-8')) if args.manifest else {}
            if set(overrides)-{'order','sequences','per_image'}:raise ValueError('Manifest accepts order, sequences, per_image')
            run=compose(args.folder,load_profile(args.profile),output_root=args.output,width_mm=args.width_mm,
                backend=args.backend,vectorizer=args.vectorizer,repeats=args.repeats,anchor=args.anchor,
                registration=args.registration,schedule_mode=args.schedule,stack_mode=args.mode,recursive=args.recursive,
                production=args.production,perimeters=args.perimeters,infill_density=args.infill,progress=print,
                prusa_config=args.prusa_config,top_solid_layers=args.top_solid_layers,bottom_solid_layers=args.bottom_solid_layers,
                preset=args.preset,trace_options=trace_settings(args),**overrides)
            print(run.resolve());return
        if args.command=='vectorize':
            from .vectorization import vectorize
            from .geometry import register,write_svg
            from .presets import resolve
            p=load_profile(args.profile) if args.profile else Profile()
            options=trace_settings(args);resolved=None
            if args.preset:
                options,resolved=resolve(args.input,args.preset,profile=p,width_mm=args.width_mm,overrides=options)
            else:
                if args.width_mm is None: raise ValueError('Specify --width-mm or --preset')
                options['width_mm']=args.width_mm
            output=Path(args.output)
            output.parent.mkdir(parents=True,exist_ok=True)
            if args.backend=='inkscape':
                from uuid import uuid4
                options['trace_dir']=output.with_name(output.stem+'.trace-'+uuid4().hex[:8])
            d=register(vectorize(args.input,backend=args.backend,**options))
            if resolved: d.metadata['svg_preset']=resolved
            write_svg(d,output,preserve_canvas=True)
            write_json(output.with_suffix('.settings.json'),{'needle':p.needle_summary(),'geometry':d.metadata,
                'source':str(Path(args.input).resolve()),'source_sha256':sha256(args.input),
                'production_approved':False,'printer_contacted':False})
            print(output);return
        if args.command=='slice':
            from .geometry import read_svg,register
            from .slicing import direct_paths,prusa_slice
            from .meshing import write_stl
            from .pipeline import direct_raw
            p=load_profile(args.profile);p.require();d=register(read_svg(args.svg,args.width_mm));out=Path(args.output)
            if args.prusa_config and args.backend!='prusa':raise ValueError('--prusa-config requires --backend prusa')
            if args.infill is not None and not 0<=args.infill<=1:raise ValueError('--infill must be 0..1')
            write_stl(d.geometry,p.deposition_height_mm,out.with_suffix('.stl'))
            if args.backend=='prusa':
                prusa_slice(out.with_suffix('.stl'),out,p,p.needle_inner_diameter_mm,prusa_config=args.prusa_config,
                    perimeters=args.perimeters,density=None if args.infill is None else args.infill*100,
                    top=args.top_solid_layers,bottom=args.bottom_solid_layers)
            else:
                paths=direct_paths(d.geometry,p,1 if args.perimeters is None else args.perimeters,
                    .2 if args.infill is None else args.infill,args.top_solid_layers or 0,args.bottom_solid_layers or 0)
                out.write_text(direct_raw(paths,p),encoding='ascii')
            print('Untrusted raw slice; compose before upload:',out);return
        if args.command=='simulate':
            p,m=preflight(args.run,production=False)
            print(json.dumps({'valid':True,'used_mm3':m['used_mm3'],'diagnostics':m['diagnostics'],
                'preview':str(Path(args.run)/'previews'/'motion3d.html')},indent=2));return
        if args.command=='video':
            from .video import create_video
            print(json.dumps(create_video(args.run,fps=args.fps,size=(args.width,args.height),codec=args.codec,
                quadrants=args.quadrants,timeline_path=args.timeline,policy=args.policy,background=args.background),indent=2));return
        if args.command=='duet':
            from .duet import Duet,Queue,DuetError
            client=Duet(args.url)
            try:
                if args.action=='status':print(json.dumps(client.status(),indent=2))
                elif args.action=='upload':print(json.dumps(client.upload(args.run,combined=not args.jobs),indent=2))
                elif args.action in {'pause','resume','cancel'}:print(json.dumps(client.control(args.action,reviewed=args.reviewed_macros),indent=2))
                elif args.action=='display':
                    from .display import LiveDisplay
                    if args.poll_seconds<.5 or args.samples<1:raise ValueError('Polling >=0.5 seconds; samples >=1')
                    root=Path(args.run);player=LiveDisplay(json.loads((root/'timing'/'display_timeline.json').read_text(encoding='utf-8')))
                    for _ in range(args.samples):
                        status=client.status();print(player.update(status,time.time(),status['poll_latency_s']))
                        write_json(root/'timing'/'observed.json',player.observed);time.sleep(args.poll_seconds)
                else:
                    root=Path(args.run);p,m=preflight(root,production=True)
                    status=client.status()
                    if status['firmware_version']!=p.firmware_version or status['current_tool']!=p.firmware_tool_number:
                        raise DuetError('Current firmware/tool differs from reviewed machine profile')
                    receipt=json.loads((root/'upload.receipt.json').read_text(encoding='utf-8'))
                    if receipt['base_url']!=client.base:raise DuetError('Upload receipt belongs to a different printer URL')
                    receipt_by_name={Path(f['path']).name:f for f in receipt['files']}
                    jobs=json.loads((root/'timing'/'jobs.json').read_text(encoding='utf-8'))['jobs']
                    for job in jobs:
                        rec=receipt_by_name.get(Path(job['path']).name)
                        if not rec or rec['sha256']!=job['sha256']:raise DuetError('Upload ordered jobs with --jobs first')
                        job['remote_path']=rec['path']
                    queue=Queue(root/'queue.state.json',jobs)
                    if queue.state['jobs']!=jobs:raise DuetError('Persistent queue differs from verified run')
                    if args.confirm_completed:print(queue.confirm_completed(client,args.confirm_completed))
                    if args.poll_seconds<.5:raise ValueError('Polling >=0.5 seconds required')
                    while True:
                        phase=queue.step(client,start=args.start);print(phase)
                        if not args.watch or phase not in {'starting','running','paused'}:break
                        time.sleep(args.poll_seconds)
            finally:client.close()
    except (ValueError,RuntimeError,OSError) as exc:
        parser.exit(2,f'Error: {exc}\n')


if __name__=='__main__':main()
