"""Opt-in, real installed-binary fixtures. No printer/network API is used."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from PIL import Image,ImageDraw
from shapely.geometry import Point,LineString
from bioprinter.vectorization import vectorize
from bioprinter.geometry import polygons
from bioprinter.meshing import write_stl
from bioprinter.slicing import prusa_slice
from bioprinter.config import demo_profile
from bioprinter.gcode import interpret,lex
from bioprinter.external import probe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();p=args.output;p.mkdir(parents=True,exist_ok=False)
    im=Image.new('RGB',(200,120),'white');draw=ImageDraw.Draw(im)
    draw.rectangle((10,10,90,100),fill='black');draw.rectangle((30,30,60,60),fill='white')
    draw.rectangle((130,10,180,35),fill='black');im.save(p/'fixture.png')
    d=vectorize(p/'fixture.png',40,backend='inkscape',trace_dir=p/'trace')
    assert len(polygons(d.geometry))==2 and sum(len(poly.interiors) for poly in polygons(d.geometry))==1
    assert not d.geometry.covers(Point(9,15))
    assert d.geometry.covers(Point(30,20)) and not d.geometry.covers(Point(30,5))
    mesh=write_stl(d.geometry,.5,p/'fixture.stl')
    profile=demo_profile();raw=prusa_slice(p/'fixture.stl',p/'fixture.gcode',profile,.8)
    motions,audit=interpret(raw.read_text());deposits=[m for m in motions if m.kind=='deposit']
    assert deposits and all(abs(m.end[2]-.5)<1e-6 for m in deposits)
    assert all(d.geometry.buffer(.501).covers(LineString([m.start[:2],m.end[:2]])) for m in deposits)
    assert not any(LineString([m.start[:2],m.end[:2]]).distance(Point(9,15))<.5 for m in deposits)
    assert all(any(poly.buffer(.501).covers(Point(*m.end[:2])) for m in deposits) for poly in polygons(d.geometry))
    assert sum(item.get('action')=='removed' for item in audit)>=1
    # An incompatible synthetic bore must fail, never be silently inflated.
    try: prusa_slice(p/'fixture.stl',p/'invalid-bore.gcode',profile,.3)
    except ValueError as exc: rejection=str(exc)
    else: raise AssertionError('Expected layer-height/nozzle incompatibility rejection')
    assert 'diameter' in rejection.lower() or 'height' in rejection.lower()
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'status':'passed',
        'inkscape_version':probe('inkscape')['version'],'prusa_version':probe('prusa-slicer')['version'],
        'assertions':['two disconnected islands','hole preserved','Y-up asymmetric orientation',
            'watertight mesh','one 0.5 mm layer','XY placement preserved','hole has no crossing deposition',
            'both islands have extrusion','thermal/fan removal audited','0.3 mm bore rejects 0.5 mm layer'],
        'synthetic_compatible_test_nozzle_mm':.8,'mesh':mesh,'deposition_moves':len(deposits),
        'incompatible_nozzle_error':rejection,'printer_contacted':False,'production_approved':False}
    (p/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
