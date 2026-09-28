"""Compare explicit sizes and installed converters without slicing or printer contact."""
import argparse
import html
import json
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image, ImageOps
from bioprinter.config import load_profile
from bioprinter.ingestion import discover
from bioprinter.vectorization import vectorize
from bioprinter.geometry import write_svg, polygons
from bioprinter.presets import PRESETS, resolve
from bioprinter.pipeline import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=Path(__file__).resolve().parents[1]/'profiles/synthetic.yaml')
    parser.add_argument('--presets',nargs='+',choices=list(PRESETS),default=list(PRESETS))
    parser.add_argument('--backends',nargs='+',choices=['python','inkscape'],default=['python','inkscape'])
    parser.add_argument('--manifest',type=Path,help='Optional order and per_image tracing overrides')
    args=parser.parse_args()
    overrides=json.loads(args.manifest.read_text(encoding='utf-8')) if args.manifest else {}
    if set(overrides)-{'order','per_image'}: raise ValueError('Comparison manifest accepts order and per_image only')
    assets=discover(args.inputs,recursive=True,order=overrides.get('order'))
    profile=load_profile(args.profile)
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for index,asset in enumerate(assets,1):
        thumb=args.output/f'original-{index:02d}.jpg'
        if asset.path.suffix.lower()!='.svg':
            with Image.open(asset.path) as src:
                rgba=ImageOps.exif_transpose(src).convert('RGBA')
                bg=Image.new('RGBA',rgba.size,'white');bg.alpha_composite(rgba)
                ImageOps.contain(bg.convert('RGB'),(440,360)).save(thumb,quality=90)
        for name in args.presets:
            for backend in args.backends:
                folder=args.output/f'{index:02d}-{name}-{backend}';folder.mkdir()
                r={'input':asset.path.name,'sha256':asset.sha256,'preset':name,'backend':backend,
                   'folder':folder.name,'status':'failed','original':thumb.name if thumb.exists() else None}
                try:
                    settings,record=resolve(asset.path,name,profile=profile,
                        overrides=overrides.get('per_image',{}).get(asset.path.name,{}))
                    r['resolved']=record
                    if backend=='inkscape': settings['trace_dir']=folder/'native-trace'
                    design=vectorize(asset.path,backend=backend,**settings)
                    design.metadata['svg_preset']=record
                    write_svg(design,folder/'image.svg')
                    r.update(status='generated',area_mm2=design.geometry.area,islands=len(polygons(design.geometry)),
                             holes=sum(len(p.interiors) for p in polygons(design.geometry)),geometry=design.metadata)
                except Exception as exc: r['error']=str(exc)
                write_json(folder/'settings.json',r);results.append(r)
                print(f'{len(results)}: {asset.path.name} / {name} / {backend}: {r["status"]}',flush=True)
    data={'created_utc':datetime.now(timezone.utc).isoformat(),'needle':profile.needle_summary(),
          'profile':profile.model_dump(),'presets':list(args.presets),'backends':list(args.backends),
          'source_count':len(assets),'generated':sum(r['status']=='generated' for r in results),
          'expected':len(assets)*len(args.presets)*len(args.backends),'results':results,
          'production_approved':False,'printer_contacted':False}
    write_json(args.output/'report.json',data)
    cards=[]
    for r in results:
        title=html.escape(f'{r["input"]} · {r["preset"]} · {r["backend"]}')
        original=f'<img src="{r["original"]}" alt="Original image">' if r['original'] else ''
        preview=f'<img src="{r["folder"]}/image.svg" alt="Generated SVG">' if r['status']=='generated' else '<p>'+html.escape(r['error'])+'</p>'
        resolved=r.get('resolved',{});w,h=resolved.get('canvas_mm',[0,0]);s=resolved.get('settings',{})
        cards.append(f'<article><h2>{title}</h2><div class="pair">{original}{preview}</div>'
            f'<p>{w:.2f} × {h:.2f} mm · threshold {s.get("threshold","—")} · '
            f'{s.get("max_pixels","—")} px max · simplify {s.get("simplify_mm","—")} mm</p>'
            f'<p>{r.get("islands","—")} islands · {r.get("holes","—")} holes · {r["status"]}</p>'
            f'<a href="{r["folder"]}/settings.json">Exact settings and diagnostics</a></article>')
    needle=profile.needle_summary()
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SVG size and converter comparison</title>
<style>body{font:15px/1.55 system-ui;margin:28px;background:#eef3f6;color:#193446}header{max-width:1050px}h1{font-size:30px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px}article{padding:18px;background:white;border:1px solid #cfdce5;border-radius:10px}h2{font-size:16px;overflow-wrap:anywhere}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}img{width:100%;height:230px;object-fit:contain}a{color:#176989}@media(max-width:500px){body{margin:14px}main{grid-template-columns:1fr}}</style>'''
    page+=f'<header><h1>SVG sizes · Inkscape and Python</h1><p><b>Specified needle: {needle["gauge"]} gauge × {needle["length_inches"]:g} inch ({needle["length_mm"]:g} mm) long.</b> Gauge and length do not determine the bore, bead width or tracing threshold.</p>'
    page+=f'<p>{data["generated"]}/{data["expected"]} SVG conversions generated from {len(assets)} sources. Each source is independently fitted with its aspect ratio preserved. These are conversion comparisons, not registered stack layers or print approvals. Bore, bead and motion/calibration values in this comparison profile are synthetic. No printer was contacted.</p><p>Small: 25 × 31.25 mm; medium: 50 × 62.5 mm; large: 75 × 93.75 mm; full quadrant: active profile minus margins. Detailed settings and source hashes are retained with every result.</p></header><main>'+''.join(cards)+'</main></html>'
    (args.output/'report.html').write_text(page,encoding='utf-8')
    print(args.output/'report.html')
    return int(data['generated']!=data['expected'])


if __name__=='__main__': raise SystemExit(main())
