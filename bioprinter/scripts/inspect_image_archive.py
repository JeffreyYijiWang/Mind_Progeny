from pathlib import Path
import argparse
import json
from datetime import datetime,timezone
from PIL import Image,ImageOps,ImageDraw
from bioprinter.archive import extract_images
from bioprinter.ingestion import discover

def inspect(archive,output=None):
    root=Path(__file__).resolve().parents[1]
    run=Path(output) if output else root/'validation'/'dataset-runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    meta=extract_images(archive,run/'inputs',expected_count=45)
    assets=discover(run/'inputs',recursive=True)
    tile=(210,180);cols=6;rows=(len(assets)+cols-1)//cols
    sheet=Image.new('RGB',(cols*tile[0],rows*tile[1]),'#e7e9ee');draw=ImageDraw.Draw(sheet)
    properties=[]
    for i,asset in enumerate(assets):
        with Image.open(asset.path) as original:
            oriented=ImageOps.exif_transpose(original).convert('RGBA')
            img=Image.new('RGBA',oriented.size,'white');img.alpha_composite(oriented)
            prop={**asset.metadata(),'dimensions':list(img.size),'mode':original.mode,'frames':getattr(original,'n_frames',1)}
            properties.append(prop)
            thumb=ImageOps.contain(img.convert('RGB'),(tile[0]-12,tile[1]-30))
        x=(i%cols)*tile[0];y=(i//cols)*tile[1]
        sheet.paste(thumb,(x+(tile[0]-thumb.width)//2,y+4))
        draw.text((x+6,y+tile[1]-23),f'{i+1:02d}  {prop["dimensions"][0]} x {prop["dimensions"][1]}',fill='#111')
    sheet.save(run/'input-contact-sheet.jpg',quality=90)
    (run/'image_inventory.json').write_text(json.dumps(properties,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'run':str(run),'count':len(assets),'dimensions':sorted({tuple(x['dimensions']) for x in properties})},indent=2),flush=True)
    return run

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--output')
    a=p.parse_args();inspect(a.archive,a.output)
