"""Explicit offline integration of both converters and both slicers, with synthetic fixtures."""
import argparse
from pathlib import Path
import socket
from bioprinter.config import demo_profile
from bioprinter.examples import make_inputs
from bioprinter.pipeline import compose, preflight, write_json
from bioprinter.slicing import prusa_slice
from bioprinter.meshing import write_stl
from bioprinter.geometry import read_svg
from shapely.geometry import box


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--summary',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    def no_network(*args,**kwargs): raise AssertionError('Integration verification must remain offline')
    socket.socket.connect=no_network
    inputs=make_inputs(args.output/'inputs');results=[]
    for converter in ('python','inkscape'):
        for slicer in ('direct','prusa'):
            # Keep the invented 0.3 mm bore: never inflate it to evade slicer validation.
            p=demo_profile()
            if slicer=='prusa':
                p=type(p).model_validate({**p.model_dump(),'name':'SYNTHETIC-Prusa-0.2mm-layer-0.4mm-bead-fixture',
                    'deposition_height_mm':.2,'first_deposition_tip_height_mm':.2,
                    'bead_width_mm':.4,'grid_mm':.2,'sample_mm':.2})
            record={'converter':converter,'slicer':slicer,'preset':'small','status':'failed',
                    'layer_height_mm':p.deposition_height_mm,'bead_width_mm':p.bead_width_mm,'needle':p.needle_summary()}
            try:
                run=compose(inputs,p,output_root=args.output/'runs',preset='small',
                            vectorizer=converter,backend=slicer,progress=print)
                _,manifest=preflight(run,production=False)
                assert len(manifest['assets'])==3 and len(manifest['events'])==12
                assert {e['quadrant'] for e in manifest['events']}=={'Q1','Q2','Q3','Q4'}
                assert manifest['needle']['gauge']==23 and manifest['needle']['length_mm']==12.7
                assert manifest['network_contacted'] is False
                for asset in manifest['assets']:
                    exported=read_svg(run/asset['svg_path'])
                    assert all(abs(a-b)<1e-8 for a,b in zip(exported.canvas,(0,0,25,25)))
                record.update(status='passed',run=str(run.resolve()),events=len(manifest['events']),
                              used_mm3=manifest['used_mm3'],diagnostics=manifest['diagnostics'])
            except Exception as exc: record['error']=str(exc)
            results.append(record);print(f'{converter} / {slicer}: {record["status"]}',flush=True)
    mesh=args.output/'incompatible-layer.stl';write_stl(box(0,0,8,8),.5,mesh)
    rejected=False
    try: prusa_slice(mesh,args.output/'incompatible-layer.gcode',demo_profile(),.3)
    except ValueError as exc:
        rejected=True;rejection=str(exc)
    data={'results':results,'passed':sum(r['status']=='passed' for r in results),'expected':4,
          'default_0_5mm_layer_with_synthetic_0_3mm_bore_rejected':rejected,
          'rejection':rejection if rejected else None,'printer_contacted':False,
          'scope':'Windows native CLI software verification. Prusa success uses a separate synthetic 0.2 mm layer / 0.4 mm bead fixture; requested nominal 0.5 mm default is unchanged. Bore is not a measurement of the 23 gauge needle.'}
    write_json(args.summary,data)
    return int(data['passed']!=4 or not rejected)


if __name__=='__main__': raise SystemExit(main())
