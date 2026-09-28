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
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from shapely import affinity
from shapely.geometry import LineString
from shapely.ops import unary_union
from bioprinter.config import load_profile, Profile
from bioprinter.layout import placement, quadrant_bounds
from bioprinter.geometry import write_svg, polygons
from bioprinter.ingestion import discover, sha256
from bioprinter.vectorization import vectorize
from bioprinter.meshing import write_stl
from bioprinter.slicing import prusa_slice
from bioprinter.gcode import interpret
from bioprinter.extrusion import convert_slicer


def image_fit(path, settings):
    """Explicit report-only aspect-preserving canvas fit; never a stack registration."""
    with Image.open(path) as src:
        oriented=ImageOps.exif_transpose(src)
        original=list(oriented.size)
        oriented.thumbnail((settings['max_working_pixels'],)*2,Image.Resampling.LANCZOS)
        working=list(oriented.size)
    if settings['sizing']=='fit-quadrant':
        max_w,max_h=settings['usable_size_mm']
        # Sub-micron slack avoids roundoff putting a boundary outside the rectangle.
        width=min(max_w,max_h*working[0]/working[1])*(1-1e-10)
    else: width=settings['width_mm']
    return {'canvas_mm':[width,width*working[1]/working[0]],'original_pixels':original,'working_pixels':working}


def fit_trace_extent(design, usable_size):
    """Allow a tracer's curved boundary overshoot without clipping any geometry."""
    x0,y0,x1,y1=design.geometry.bounds
    factor=min(1,usable_size[0]/(x1-x0),usable_size[1]/(y1-y0))
    if factor<1:
        factor*=1-1e-9
        design.geometry=affinity.scale(design.geometry,factor,factor,origin=(0,0))
        design.canvas=tuple(v*factor for v in design.canvas)
        design.transform=(np.diag([factor,factor,1])@np.asarray(design.transform)).tolist()
    return factor


def process_one(job):
    index,path,output,settings=job;path=Path(path);folder=Path(output)/f'{index:02d}'
    if folder.exists(): folder=folder.with_name(folder.name+'-retry-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    result={'index':index,'input':path.name,'sha256':sha256(path),'status':'failed','stage':'inkscape',
            'folder':folder.name,'production_approved':False,'printer_contacted':False}
    try:
        fit=image_fit(path,settings);width=fit['canvas_mm'][0];result['size']=fit
        profile=Profile.model_validate(settings['profile'])
        d=vectorize(path,width_mm=width,backend='inkscape',threshold=128,denoise=3,
                    min_area_mm2=.01,simplify_mm=.05,trace_dir=folder/'inkscape',max_pixels=settings['max_working_pixels'])
        result['trace']=d.metadata
        # Test each source at an explicit independent size, centered on the plate.
        cx=(d.canvas[0]+d.canvas[2])/2;cy=(d.canvas[1]+d.canvas[3])/2
        d.geometry=affinity.translate(d.geometry,-cx,-cy)
        d.canvas=(-cx,-cy,cx,cy)
        d.transform=(np.array([[1,0,-cx],[0,1,-cy],[0,0,1]])@np.asarray(d.transform)).tolist()
        if settings['sizing']=='fit-quadrant':
            factor=fit_trace_extent(d,settings['usable_size_mm'])
            fit['trace_extent_adjustment']=factor
            fit['canvas_mm']=[v*factor for v in fit['canvas_mm']]
            matrix,allowed=placement(d.geometry.bounds,'Q1',profile)
            dx,dy=matrix[0][2],matrix[1][2]
            d.geometry=affinity.translate(d.geometry,dx,dy)
            d.canvas=(d.canvas[0]+dx,d.canvas[1]+dy,d.canvas[2]+dx,d.canvas[3]+dy)
            d.transform=(np.asarray(matrix)@np.asarray(d.transform)).tolist()
            result['placement']={'quadrant':'Q1','translation_mm':[dx,dy],'allowed_bounds':list(allowed.bounds),
                                 'printable_bounds_mm':list(d.geometry.bounds),'source_to_machine':d.transform}
        write_svg(d,folder/'normalized.svg')
        result.update(trace_passed=True,stage='mesh',area_mm2=d.geometry.area,
                      islands=len(polygons(d.geometry)),holes=sum(len(p.interiors) for p in polygons(d.geometry)))
        result['mesh']=write_stl(d.geometry,.5,folder/'model.stl');result['stage']='prusa'
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
        fig,ax=plt.subplots(figsize=(4.4,5.3) if settings['sizing']=='fit-quadrant' else (4,4))
        for p in polygons(d.geometry):
            ax.fill(*p.exterior.xy,color='#bec8d1',linewidth=0)
            for hole in p.interiors: ax.fill(*hole.xy,color='white',linewidth=0)
        from matplotlib.collections import LineCollection
        ax.add_collection(LineCollection([[m.start[:2],m.end[:2]] for m in deposits],colors='#c93131',linewidths=.3))
        ax.set_aspect('equal');ax.autoscale();ax.set_title(f'{index:02d} | {len(deposits):,} extrusion moves',fontsize=9)
        if settings['sizing']=='fit-quadrant':
            from matplotlib.patches import Rectangle
            qw,qh=settings['quadrant_size_mm'];x0,y0,x1,y1=result['placement']['allowed_bounds']
            ax.add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor='#557b96',linestyle='--',linewidth=.8))
            ax.set(xlim=(0,qw),ylim=(0,qh),ylabel='Y (mm)')
        ax.set_xlabel('X (mm; synthetic slicing profile)');fig.tight_layout();fig.savefig(folder/'preview.png',dpi=110);plt.close(fig)
    except Exception as exc:
        result['error']=str(exc)
        if hasattr(exc,'report'): result['rejection_report']=exc.report
    result['elapsed_seconds']=round(time.monotonic()-start,2)
    (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


def report(output,results,meta):
    output=Path(output);results=sorted(results,key=lambda x:x['index'])
    data={**meta,'completed':len(results),'trace_passed':sum(bool(x.get('trace_passed')) for x in results),
          'prusa_passed':sum(bool(x.get('prusa_passed')) for x in results),'passed':sum(x['status']=='passed' for x in results),
          'results':results}
    (output/'report.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    fitting=meta.get('sizing')=='fit-quadrant'
    comparison=meta.get('comparison') or {};prior=comparison.get('results',{})
    def metric(value,suffix=''):
        return '—' if value is None else f'{value:,.1f}{suffix}'
    cards=[]
    for r in results:
        folder=r['folder'];error=html.escape(r.get('error',''))
        lost=r.get('islands_without_paths',0)>0 or r.get('nominal_footprint_uncovered_percent',0)>5
        state='failed' if r['status']!='passed' else 'review' if lost else 'generated'
        label='Needs adjustment' if state=='failed' else 'Generated · review coverage' if lost else 'Toolpaths generated'
        links=' · '.join(f'<a href="{folder}/{filename}">{title}</a>' for filename,title in
            [('result.json','Measurements'),('normalized.svg','SVG'),('model.stl','STL'),('raw.gcode','Raw test G-code')]
            if (output/folder/filename).exists())
        images=[]
        for filename,title in [('source-thumb.jpg','Original'),('preview.png','Traced shape + toolpaths')]:
            if (output/folder/filename).exists():
                images.append(f'<figure><img loading="lazy" src="{folder}/{filename}" alt="{title}"><figcaption>{title}</figcaption></figure>')
        if not (output/folder/'preview.png').exists():
            images.append(f'<div class="empty">No toolpath preview<br><small>Stopped at {html.escape(r["stage"])}</small></div>')
        physical=r.get('size',{}).get('canvas_mm')
        size=f'{physical[0]:.2f} × {physical[1]:.2f} mm' if physical else 'Size unavailable'
        before=prior.get(r['sha256'])
        delta=''
        if before:
            old_label='generated' if before['status']=='passed' else 'stopped at '+before['stage']
            delta=f'<p class="before">40 mm baseline: {html.escape(old_label)} · {before.get("deposition_moves",0):,} extrusion moves → {r.get("deposition_moves",0):,} now</p>'
        error_block=f'<details><summary>Diagnostic / reason</summary><pre>{error}</pre></details>' if error else ''
        cards.append(f'<article data-state="{state}"><div class="card-head"><span class="number">{r["index"]:02d}</span>'
          f'<h2>{html.escape(r["input"])}</h2></div><p class="badge {state}">{label}</p>'
          f'<div class="images">{"".join(images)}</div><p><b>Image canvas:</b> {size}</p>'
          f'<div class="metrics"><span>Missing islands<b>{r.get("islands_without_paths","—")}</b></span>'
          f'<span>Uncovered design area<b>{metric(r.get("nominal_footprint_uncovered_percent"),"%")}</b></span></div>'
          f'{delta}{error_block}<p class="links">{links}</p></article>')
    if fitting:
        qw,qh=meta['quadrant_size_mm'];uw,uh=meta['usable_size_mm']
        sizing=f'4 × 5 in per quadrant · {qw:g} × {qh:g} mm. With {meta["margin_mm"]:g} mm margins: <b>{uw:g} × {uh:g} mm</b> for each image.'
        explanation='Each image canvas is fitted independently, preserving its aspect ratio. The drawing is centered inside Q1 for demonstration; the other quadrants offer the same space. Dashed lines mark the margin boundary. These are separate image tests, not registered stack layers.'
    else:
        sizing=f'Each image independently tested at {meta.get("width_mm",40):g} mm canvas width.'
        explanation='Images are independent software tests, not registered stack layers.'
    old_count=f'<p>Previous 40 mm test: {comparison["passed"]}/{meta["expected"]} generated toolpaths. Per-image comparisons appear below.</p>' if comparison else ''
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Bioprinter · Image review</title>\n<style>\n*{box-sizing:border-box}body{font:15px/1.55 system-ui,sans-serif;margin:0;background:#edf2f5;color:#182d3b}header,main{max-width:1480px;margin:auto;padding:28px}header{padding-top:38px}h1{font-size:34px;line-height:1.2;margin:10px 0 18px}h2{font-size:15px;margin:0;overflow-wrap:anywhere}a{color:#166b9b}p{margin:12px 0}.eyebrow{font-size:12px;letter-spacing:2px;font-weight:700;color:#527183}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}.stats div{background:#fff;border:1px solid #d7e0e7;border-radius:10px;padding:15px}.stats b{font-size:28px;display:block}.note{border-left:4px solid #dc9f39;background:#fff6e4;padding:12px 18px;border-radius:3px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px;padding-top:12px}article{background:#fff;border:1px solid #d4e0e8;border-radius:13px;padding:18px;min-width:0}.card-head{display:flex;gap:12px;align-items:center}.number{color:#657e8e;font-size:21px;font-weight:600}.badge{font-size:12px;display:inline-block;padding:4px 9px;border-radius:6px}.generated{background:#e0f3e8;color:#236440}.review{background:#fff0ce;color:#715114}.failed{background:#fbe5e4;color:#953e39}.images{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:center;background:#fbfcfd;padding:8px;border-radius:8px;min-height:180px}figure{margin:0;min-width:0}img{width:100%;height:220px;object-fit:contain}figcaption{font-size:11px;text-align:center;color:#587083}.empty{text-align:center;color:#7a8992;font-size:13px}.metrics{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#627685}.metrics b{display:block;font-size:20px;color:#223e50}.before{font-size:12px;background:#eff5f9;padding:9px;border-radius:5px}.links{font-size:12px}details{font-size:12px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto}button{border:1px solid #a9bfcc;background:#fff;color:#173b50;border-radius:6px;padding:8px 14px;cursor:pointer;margin:5px 4px 0 0}button.active{background:#1f536c;color:white}.legend{color:#557084;font-size:13px}footer{padding:20px 28px;color:#657e8e;text-align:center}@media(max-width:600px){header,main{padding:18px}main{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:27px}img{height:180px}}\n</style><header><div class="eyebrow">BIOPRINTER / OFFLINE IMAGE REVIEW</div>'
    page+=f'<h1>Image report · {"4 × 5 inch quadrants" if fitting else "40 mm baseline"}</h1><p>{sizing}</p><p>{explanation}</p>'
    needle=meta.get('needle')
    if needle:
        page+=f'<p><b>Specified needle: {needle["gauge"]} gauge × {needle["length_inches"]:g} inch ({needle["length_mm"]:g} mm) long.</b> Actual bore and deposited line width require separate measurements; slicing dimensions below are synthetic.</p>'
    if meta.get('svg_comparison_href'):
        page+=f'<p><a href="{html.escape(meta["svg_comparison_href"],quote=True)}">Compare four SVG sizes in Inkscape and Python</a></p>'
    page+=f'<div class="stats"><div>Images checked<b>{data["completed"]} / {meta["expected"]}</b></div><div>Native traces<b>{data["trace_passed"]}</b></div><div>Toolpaths generated<b>{data["passed"]}</b></div><div>Stopped / need adjustment<b>{data["completed"]-data["passed"]}</b></div></div>{old_count}'
    page+='<p class="note"><b>Synthetic slicing test.</b> One 0.5 mm layer, invented 0.8 mm slicer nozzle, nominal 1 mm bead and 20% infill. These are not measured needle dimensions or approved printer jobs. No printer was contacted.</p>'
    page+='<p class="legend">Gray = traced filled geometry; red = actual extrusion paths. Missing islands and uncovered area are approximate 1 mm bead-footprint diagnostics. Uncovered area includes intentional gaps from 20% infill. A missing island or more than 5% uncovered area adds a review flag, not a physical pass/fail judgment. Working copies: 800 px maximum side, threshold 128, median 3, minimum island 0.01 mm², simplification 0.05 mm. Originals remain intact; preprocessing can lose fine detail.</p>'
    page+='''<nav aria-label="Filter images"><button class="active" onclick="filterCards(this,'all')">All images</button><button onclick="filterCards(this,'failed')">Stopped</button><button onclick="filterCards(this,'review')">Generated with coverage flags</button><button onclick="filterCards(this,'generated')">Generated without flags</button></nav></header>'''
    page+='<main>'+''.join(cards)+'</main><footer>Local report · detailed commands, source hashes and diagnostics retained with every image</footer>'
    page+='<script>function filterCards(button,state){document.querySelectorAll("article").forEach(card=>card.hidden=state!=="all"&&card.dataset.state!==state);document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b===button));}</script></html>'
    (output/'report.html').write_text(page,encoding='utf-8')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=1);parser.add_argument('--limit',type=int)
    parser.add_argument('--fit-quadrant',action='store_true',help='Explicitly fit each independent image inside one quadrant, preserving aspect ratio')
    parser.add_argument('--width-mm',type=float,default=40)
    parser.add_argument('--compare-report',type=Path)
    parser.add_argument('--resume-tests',action='store_true',help='Reuse completed diagnostic results only after input hash checks; never resumes printing')
    parser.add_argument('--retry-index',type=int,action='append',default=[],help='With --resume-tests, repeat this image in a new attempt folder')
    args=parser.parse_args();assets=discover(args.inputs,recursive=True)
    if args.limit: assets=assets[:args.limit]
    args.output.mkdir(parents=True,exist_ok=args.resume_tests)
    profile=load_profile(Path(__file__).resolve().parents[1]/'profiles'/'synthetic.yaml')
    x0,y0,x1,y1=quadrant_bounds(profile)['Q1']
    margin=max(profile.edge_margin_mm,profile.centerline_margin_mm,profile.holder_radius_mm)
    settings={'sizing':'fit-quadrant' if args.fit_quadrant else 'fixed-width','width_mm':args.width_mm,
              'quadrant_size_mm':[x1-x0,y1-y0],'usable_size_mm':[x1-x0-2*margin,y1-y0-2*margin],
              'margin_mm':margin,'max_working_pixels':800,'profile':profile.model_dump()}
    if args.width_mm<=0 or min(settings['usable_size_mm'])<=0: raise ValueError('Invalid size or margins')
    comparison=None
    if args.compare_report:
        old=json.loads(args.compare_report.read_text(encoding='utf-8'))
        comparison={'path':str(args.compare_report.resolve()),'sha256':sha256(args.compare_report),
                    'passed':old['passed'],'width_mm':old.get('width_mm'),
                    'results':{r['sha256']:r for r in old['results']}}
    meta={'started_utc':datetime.now(timezone.utc).isoformat(),'expected':len(assets),'width_mm':None if args.fit_quadrant else args.width_mm,
          'synthetic_slicer_nozzle_mm':.8,'deposition_height_mm':.5,'bead_width_mm':1,'max_working_pixels':800,
          'registration':'independent images; Q1 demonstration' if args.fit_quadrant else 'independent centered canvas per image',
          'sizing':settings['sizing'],'quadrant_size_mm':settings['quadrant_size_mm'],
          'usable_size_mm':settings['usable_size_mm'],'margin_mm':margin,'profile_sha256':profile.digest(),
          'needle':profile.needle_summary(),
          'comparison':comparison,'production_approved':False,'printer_contacted':False}
    if not args.resume_tests:
        (args.output/'profile.json').write_text(json.dumps(profile.model_dump(),indent=2),encoding='utf-8')
    results=[]
    previous_attempts={}
    if args.resume_tests:
        old=json.loads((args.output/'report.json').read_text(encoding='utf-8'))
        if any(old.get(k)!=v for k,v in meta.items() if k!='started_utc'):
            raise ValueError('Diagnostic resume settings/count changed; use a fresh output folder')
        for r in old['results']:
            asset=assets[r['index']-1]
            if asset.path.name!=r['input'] or sha256(asset.path)!=r['sha256']:
                raise ValueError('Diagnostic resume input hash/order changed')
            if not (args.output/r['folder']/'result.json').is_file(): raise ValueError('Completed result is missing')
            if r['index'] in args.retry_index: previous_attempts[r['index']]=r
            else: results.append(r)
        meta['started_utc']=old['started_utc']
        meta['diagnostic_resumed_utc']=datetime.now(timezone.utc).isoformat()
    done={r['index'] for r in results}
    if args.workers==1:
        for i,a in enumerate(assets,1):
            if i in done: continue
            r=process_one((i,str(a.path),str(args.output.resolve()),settings))
            if i in previous_attempts: r['previous_attempt']=previous_attempts[i]
            results.append(r);report(args.output,results,meta)
            print(f'{len(results)}/{len(assets)}: {r["index"]:02d} {r["status"]} ({r["elapsed_seconds"]} s) {r.get("error","")}',flush=True)
        return int(any(r['status']!='passed' for r in results))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(process_one,(i,str(a.path),str(args.output.resolve()),settings)) for i,a in enumerate(assets,1) if i not in done]
        for future in as_completed(futures):
            r=future.result()
            if r['index'] in previous_attempts: r['previous_attempt']=previous_attempts[r['index']]
            results.append(r);report(args.output,results,meta)
            print(f'{len(results)}/{len(assets)}: {r["index"]:02d} {r["status"]} ({r["elapsed_seconds"]} s) {r.get("error","")}',flush=True)
    print(json.dumps({k:v for k,v in report(args.output,results,meta).items() if k!='results'},indent=2),flush=True)
    return int(any(r['status']!='passed' for r in results))


if __name__=='__main__': raise SystemExit(main())
