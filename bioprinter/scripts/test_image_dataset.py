"""Explicit offline Inkscape -> mesh -> PrusaSlicer integration batch.

Independent images, NOT a registered stack or a printer-ready export.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import time
import uuid
from PIL import Image, ImageDraw, ImageOps
from shapely import affinity
from shapely.geometry import LineString
from shapely.ops import unary_union
from bioprinter.config import load_profile
from bioprinter.geometry import write_svg, polygons
from bioprinter.ingestion import discover, sha256
from bioprinter.vectorization import vectorize
from bioprinter.meshing import write_stl
from bioprinter.slicing import prusa_slice
from bioprinter.gcode import interpret
from bioprinter.extrusion import convert_slicer


def process_one(job):
    index,path,output,width=job;path=Path(path);folder=Path(output)/f'{index:02d}'
    if folder.exists(): folder=folder.with_name(folder.name+'-retry-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    result={'index':index,'input':path.name,'sha256':sha256(path),'status':'failed','stage':'inkscape',
            'folder':folder.name,'production_approved':False,'printer_contacted':False}
    try:
        d=vectorize(path,width_mm=width,backend='inkscape',threshold=128,denoise=3,
                    min_area_mm2=.01,simplify_mm=.05,trace_dir=folder/'inkscape',max_pixels=800)
        result['trace']=d.metadata
        # Test each source at an explicit independent size, centered on the plate.
        cx=(d.canvas[0]+d.canvas[2])/2;cy=(d.canvas[1]+d.canvas[3])/2
        d.geometry=affinity.translate(d.geometry,-cx,-cy)
        d.canvas=(-cx,-cy,cx,cy)
        write_svg(d,folder/'normalized.svg')
        result.update(trace_passed=True,stage='mesh',area_mm2=d.geometry.area,
                      islands=len(polygons(d.geometry)),holes=sum(len(p.interiors) for p in polygons(d.geometry)))
        result['mesh']=write_stl(d.geometry,.5,folder/'model.stl');result['stage']='prusa'
        profile=load_profile(Path(__file__).resolve().parents[1]/'profiles'/'synthetic.yaml')
        raw=prusa_slice(folder/'model.stl',folder/'raw.gcode',profile,.8,density=20)
        result.update(prusa_passed=True,stage='interpret')
        motions,cleanup=interpret(raw.read_text(encoding='utf-8'),e_units='filament_mm')
        deposits=[m for m in motions if m.kind=='deposit']
        if not deposits: raise ValueError('PrusaSlicer generated no deposition at this size/width')
        if any(abs(m.end[2]-.5)>1e-5 for m in deposits): raise ValueError('Expected exactly one 0.5 mm layer')
        permitted_xy=d.geometry.buffer(.5001)
        if any(not permitted_xy.covers(LineString([m.start[:2],m.end[:2]])) for m in deposits):
            raise ValueError('Slicer changed source XY placement')
        converted,volume=convert_slicer(motions,profile)
        (folder/'interpreted-motions.json').write_text(json.dumps([m.dict() for m in converted]),encoding='utf-8')
        (folder/'cleanup.json').write_text(json.dumps(cleanup+volume['report'],indent=2),encoding='utf-8')
        centerlines=unary_union([LineString([m.start[:2],m.end[:2]]) for m in deposits])
        # Diagnostic only: nominal 1 mm capsules are not exact Arachne width or liquid physics.
        footprint=centerlines.buffer(.5)
        missing_islands=sum(not footprint.intersects(poly) for poly in polygons(d.geometry))
        result.update(status='passed',stage='complete',deposition_moves=len(deposits),
            volume_mm3=volume['volume_mm3'],thermal_fan_commands_removed=sum(x.get('action')=='removed' for x in cleanup),
            nominal_footprint_uncovered_percent=100*d.geometry.difference(footprint).area/d.geometry.area,
            islands_without_paths=missing_islands,
            thin_feature_area_percent=100*d.geometry.difference(d.geometry.buffer(-.5).buffer(.5)).area/d.geometry.area)
        # Local preview: normalized filled geometry (gray) and actual slicer extrusion (red).
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(4,4))
        for p in polygons(d.geometry):
            ax.fill(*p.exterior.xy,color='#bec8d1',linewidth=0)
            for hole in p.interiors: ax.fill(*hole.xy,color='white',linewidth=0)
        from matplotlib.collections import LineCollection
        ax.add_collection(LineCollection([[m.start[:2],m.end[:2]] for m in deposits],colors='#c93131',linewidths=.3))
        ax.set_aspect('equal');ax.autoscale();ax.set_title(f'{index:02d} | {len(deposits):,} extrusion moves',fontsize=9)
        ax.set_xlabel('mm (synthetic scale)');fig.tight_layout();fig.savefig(folder/'preview.png',dpi=100);plt.close(fig)
    except Exception as exc:
        result['error']=str(exc)
        if hasattr(exc,'report'): result['rejection_report']=exc.report
    result['elapsed_seconds']=round(time.monotonic()-start,2)
    (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


def report(output,results,meta):
    results=sorted(results,key=lambda x:x['index'])
    data={**meta,'completed':len(results),'trace_passed':sum(bool(x.get('trace_passed')) for x in results),
          'prusa_passed':sum(bool(x.get('prusa_passed')) for x in results),'passed':sum(x['status']=='passed' for x in results),
          'results':results}
    (output/'report.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    cards=[]
    for r in results:
        path=r['folder'];err=html.escape(r.get('error',''))
        links=' · '.join(f'<a href="{path}/{filename}">{label}</a>' for filename,label in
            [('result.json','Measurements'),('normalized.svg','SVG'),('model.stl','STL'),('raw.gcode','Raw slicer test file')]
            if (output/path/filename).exists())
        image=f'<img src="{path}/preview.png" alt="Actual slicer paths">' if (output/path/'preview.png').exists() else ''
        if (output/path/'source-thumb.jpg').exists():
            image=f'<img src="{path}/source-thumb.jpg" alt="Original image thumbnail">'+image
        cards.append(f'<article><h2>{r["index"]:02d}. {html.escape(r["input"])}</h2>{image}'
          f'<p>{r["status"].upper()} — {html.escape(r["stage"])}</p><p>{err}</p>'
          f'<p>Islands without paths: {r.get("islands_without_paths","n/a")}; thin-feature area: {r.get("thin_feature_area_percent",0):.1f}%</p>'
          f'{links}</article>')
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>45-image application test</title>'
      '<style>body{font:16px system-ui;margin:30px;background:#eff3f6;color:#203040}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}article{background:white;padding:18px;border-radius:10px}img{width:100%;max-width:400px}h2{font-size:16px;overflow-wrap:anywhere}</style>'
      f'<h1>Inkscape + PrusaSlicer: {data["completed"]}/{meta["expected"]} checked; {data["passed"]} produced toolpaths</h1>'
      f'<p>Inkscape geometry: {data["trace_passed"]}; PrusaSlicer exports: {data["prusa_passed"]}. Windows CLI test. No printer contacted.</p>'
      '<p><b>Synthetic software test only.</b> Each image independently scaled to 40 mm canvas width. '
      'Working copies limited to 800 pixels on the longest side; originals unchanged. '
      'Threshold 128, median 3, minimum island 0.01 mm², simplification 0.05 mm. One 0.5 mm layer; '
      'invented 0.8 mm slicer nozzle and nominal 1 mm bead. These are not needle measurements or a registered stack. '
      'Thin features can disappear in tracing/filtering/slicing. Raw files are not approved syringe jobs.</p>'
      '<p>Gray: traced geometry. Red: actual PrusaSlicer extrusion paths. Uncovered-footprint and thin-feature metrics are approximate.</p>'
      '<main>'+''.join(cards)+'</main>',encoding='utf-8')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=1);parser.add_argument('--limit',type=int)
    parser.add_argument('--resume-tests',action='store_true',help='Reuse completed diagnostic results only after input hash checks; never resumes printing')
    args=parser.parse_args();assets=discover(args.inputs,recursive=True)
    if args.limit: assets=assets[:args.limit]
    args.output.mkdir(parents=True,exist_ok=args.resume_tests)
    meta={'started_utc':datetime.now(timezone.utc).isoformat(),'expected':len(assets),'width_mm':40,
          'synthetic_slicer_nozzle_mm':.8,'deposition_height_mm':.5,'bead_width_mm':1,'max_working_pixels':800,
          'registration':'independent centered canvas per image','production_approved':False,'printer_contacted':False}
    results=[]
    if args.resume_tests:
        old=json.loads((args.output/'report.json').read_text(encoding='utf-8'))
        if any(old.get(k)!=v for k,v in meta.items() if k!='started_utc'):
            raise ValueError('Diagnostic resume settings/count changed; use a fresh output folder')
        for r in old['results']:
            asset=assets[r['index']-1]
            if asset.path.name!=r['input'] or sha256(asset.path)!=r['sha256']:
                raise ValueError('Diagnostic resume input hash/order changed')
            if not (args.output/r['folder']/'result.json').is_file(): raise ValueError('Completed result is missing')
            results.append(r)
        meta['started_utc']=old['started_utc']
        meta['diagnostic_resumed_utc']=datetime.now(timezone.utc).isoformat()
    done={r['index'] for r in results}
    if args.workers==1:
        for i,a in enumerate(assets,1):
            if i in done: continue
            r=process_one((i,str(a.path),str(args.output.resolve()),40));results.append(r);report(args.output,results,meta)
            print(f'{len(results)}/{len(assets)}: {r["index"]:02d} {r["status"]} ({r["elapsed_seconds"]} s) {r.get("error","")}',flush=True)
        return int(any(r['status']!='passed' for r in results))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(process_one,(i,str(a.path),str(args.output.resolve()),40)) for i,a in enumerate(assets,1) if i not in done]
        for future in as_completed(futures):
            r=future.result();results.append(r);report(args.output,results,meta)
            print(f'{len(results)}/{len(assets)}: {r["index"]:02d} {r["status"]} ({r["elapsed_seconds"]} s) {r.get("error","")}',flush=True)
    print(json.dumps({k:v for k,v in report(args.output,results,meta).items() if k!='results'},indent=2),flush=True)
    return int(any(r['status']!='passed' for r in results))


if __name__=='__main__': raise SystemExit(main())
