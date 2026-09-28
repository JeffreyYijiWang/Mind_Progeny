from pathlib import Path
import argparse
import json
import sys
import time
from .config import load_profile,demo_profile,Profile
from .pipeline import compose,preflight,write_json


def main(argv=None):
    parser=argparse.ArgumentParser(prog='bioprinter',description='Offline by default. Printer actions are explicit duet subcommands.')
    sub=parser.add_subparsers(dest='command',required=True)
    doctor=sub.add_parser('doctor');doctor.add_argument('--profile')
    demo=sub.add_parser('demo');demo.add_argument('--output',default='runs');demo.add_argument('--video',action='store_true')
    for command in ('compose','export'):
        p=sub.add_parser(command);p.add_argument('folder');p.add_argument('--profile',required=True)
        p.add_argument('--width-mm',type=float,required=True);p.add_argument('--output',default='runs')
        p.add_argument('--backend',choices=['direct','prusa'],default='direct');p.add_argument('--vectorizer',choices=['python','inkscape'],default='python')
        p.add_argument('--manifest',help='JSON: order, sequences, per_image');p.add_argument('--repeats',type=int,default=1)
        p.add_argument('--registration',choices=['shared_canvas','per_design_bbox'],default='shared_canvas')
        p.add_argument('--anchor',choices=['bottom_left','bottom_right','top_left','top_right','center'],default='bottom_left')
        p.add_argument('--schedule',choices=['round_robin','complete_stack'],default='round_robin')
        p.add_argument('--mode',choices=['overlap_aware','planar_stack'],default='overlap_aware');p.add_argument('--recursive',action='store_true')
        p.add_argument('--production',action='store_true');p.add_argument('--perimeters',type=int,default=1);p.add_argument('--infill',type=float,default=.15)
    vec=sub.add_parser('vectorize');vec.add_argument('input');vec.add_argument('output');vec.add_argument('--width-mm',type=float,required=True)
    vec.add_argument('--backend',choices=['python','inkscape'],default='python');vec.add_argument('--threshold',type=int,default=128);vec.add_argument('--invert',action='store_true')
    sl=sub.add_parser('slice');sl.add_argument('svg');sl.add_argument('output');sl.add_argument('--profile',required=True);sl.add_argument('--width-mm',type=float,required=True);sl.add_argument('--backend',choices=['direct','prusa'],default='direct')
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
            overrides=json.loads(Path(args.manifest).read_text(encoding='utf-8')) if args.manifest else {}
            if set(overrides)-{'order','sequences','per_image'}:raise ValueError('Manifest accepts order, sequences, per_image')
            run=compose(args.folder,load_profile(args.profile),output_root=args.output,width_mm=args.width_mm,
                backend=args.backend,vectorizer=args.vectorizer,repeats=args.repeats,anchor=args.anchor,
                registration=args.registration,schedule_mode=args.schedule,stack_mode=args.mode,recursive=args.recursive,
                production=args.production,perimeters=args.perimeters,infill_density=args.infill,progress=print,**overrides)
            print(run.resolve());return
        if args.command=='vectorize':
            from .vectorization import vectorize
            from .geometry import register,write_svg
            d=register(vectorize(args.input,args.width_mm,backend=args.backend,threshold=args.threshold,invert=args.invert))
            write_svg(d,args.output);print(args.output);return
        if args.command=='slice':
            from .geometry import read_svg,register
            from .slicing import direct_paths,prusa_slice
            from .meshing import write_stl
            from .pipeline import direct_raw
            p=load_profile(args.profile);p.require();d=register(read_svg(args.svg,args.width_mm));out=Path(args.output)
            write_stl(d.geometry,p.deposition_height_mm,out.with_suffix('.stl'))
            if args.backend=='prusa':prusa_slice(out.with_suffix('.stl'),out,p,p.needle_inner_diameter_mm)
            else:out.write_text(direct_raw(direct_paths(d.geometry,p),p),encoding='ascii')
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
