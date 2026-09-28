"""Summarize a completed diagnostic batch, preserving failures and original hashes."""
from pathlib import Path
import argparse
from collections import Counter
import json
import os
from bioprinter.config import Profile
from PIL import Image,ImageOps,ImageDraw
from test_image_dataset import report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--summary',type=Path,required=True)
    parser.add_argument('--svg-comparison',type=Path,help='Link an existing converter/size comparison HTML report')
    args=parser.parse_args()
    data=json.loads((args.run/'report.json').read_text(encoding='utf-8'))
    if data['completed']!=data['expected']: raise ValueError('Batch is incomplete')
    snapshot=args.run/'profile.json'
    if snapshot.is_file():
        data['needle']=Profile.model_validate(json.loads(snapshot.read_text(encoding='utf-8'))).needle_summary()
    if args.svg_comparison:
        if not args.svg_comparison.is_file(): raise ValueError('SVG comparison report does not exist')
        data['svg_comparison_href']=os.path.relpath(args.svg_comparison,args.run).replace('\\','/')
    inputs=json.loads(args.inventory.read_text(encoding='utf-8'))
    lookup={r['sha256']:r for r in inputs}
    results=data.pop('results')
    tiles=[]
    for r in results:
        source=lookup[r['sha256']]['source_path'];folder=args.run/r['folder']
        with Image.open(source) as im:
            im=ImageOps.exif_transpose(im).convert('RGBA')
            bg=Image.new('RGBA',im.size,'white');bg.alpha_composite(im)
            thumb=ImageOps.contain(bg.convert('RGB'),(400,300))
        thumb.save(folder/'source-thumb.jpg',quality=85)
        tile=Image.new('RGB',(230,260),'white');draw=ImageDraw.Draw(tile)
        preview=folder/'preview.png'
        if preview.exists():
            with Image.open(preview) as im: rendered=ImageOps.contain(im.convert('RGB'),(230,230))
        else: rendered=ImageOps.contain(thumb,(210,210))
        tile.paste(rendered,((230-rendered.width)//2,8))
        label=f'{r["index"]:02d}: '+('toolpaths' if r['status']=='passed' else r['stage']+' failed')
        draw.text((10,242),label,fill='#17663f' if r['status']=='passed' else '#a51d26');tiles.append(tile)
    sheet=Image.new('RGB',(5*230,((len(tiles)+4)//5)*260),'#dae1e8')
    for i,tile in enumerate(tiles):sheet.paste(tile,((i%5)*230,(i//5)*260))
    sheet.save(args.run/'results-contact-sheet.jpg',quality=90)
    refreshed=report(args.run,results,data)
    failures=[{'index':r['index'],'input':r['input'],'stage':r['stage'],'error':r.get('error')}
              for r in results if r['status']!='passed']
    summary={k:v for k,v in refreshed.items() if k!='results'}
    comparison=summary.get('comparison') or {}
    if comparison:
        prior=comparison['results']
        summary['comparison']={k:v for k,v in comparison.items() if k!='results'}
        summary['comparison']['newly_generated']=[r['input'] for r in results if r['status']=='passed'
            and prior.get(r['sha256'],{}).get('status')!='passed']
        summary['comparison']['newly_stopped']=[r['input'] for r in results if r['status']!='passed'
            and prior.get(r['sha256'],{}).get('status')=='passed']
    summary.update(report=str((args.run/'report.html').resolve()),
        failure_stages=dict(Counter(r['stage'] for r in failures)),failures=failures,
        passed_with_missing_islands=sum(r.get('islands_without_paths',0)>0 for r in results),
        total_missing_islands=sum(r.get('islands_without_paths',0) for r in results),
        artifact_note='Raw slicer files are diagnostic, not approved syringe jobs. Originals and per-image details are retained locally.')
    args.summary.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
