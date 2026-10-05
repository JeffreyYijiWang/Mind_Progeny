"""Explicit native offline test of the imported set through both vectorizers."""
import argparse
from collections import Counter
import json
from pathlib import Path
import socket
from bioprinter.config import load_profile
from bioprinter.examples import make_inputs
from bioprinter.pipeline import compose, preflight, write_json
from bioprinter.prusa_config import load_bundle
from bioprinter.slicing import resolve_prusa_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    def no_network(*args, **kwargs):
        raise AssertionError('No printer/network contact during verification')
    socket.socket.connect = no_network
    profile = load_profile('profiles/supplied-prusa-preview.yaml')
    bundle = load_bundle('profiles/prusaslicer/supplied-2026-05')
    _, audit, _ = resolve_prusa_config(profile, profile.needle_inner_diameter_mm, prusa_config=bundle)
    write_json(args.output/'config-review.json', audit)
    inputs = make_inputs(args.output/'inputs')
    results = []
    for converter in ('python', 'inkscape'):
        record = {'converter':converter, 'status':'failed'}
        try:
            run = compose(inputs, profile, output_root=args.output/'runs', preset='small',
                          vectorizer=converter, backend='prusa', prusa_config=bundle, progress=print)
            _, manifest = preflight(run, production=False)
            assert len(manifest['assets']) == 3 and len(manifest['events']) == 12
            assert {e['quadrant'] for e in manifest['events']} == {'Q1','Q2','Q3','Q4'}
            assert load_bundle(run/'slicer-config').manifest_bytes == bundle.manifest_bytes
            assert not manifest['network_contacted']
            for asset in manifest['assets']:
                sidecar = (run/asset['raw_gcode']).with_suffix('.config-report.json')
                effective = json.loads(sidecar.read_text())['effective_config']
                assert effective['fill_density'] == '0%' and effective['top_solid_layers'] == '1'
                assert effective['layer_height'] == .05 and effective['extrusion_multiplier'] == 1
            record.update(status='passed',run=str(run.resolve()),assets=3,events=12,
                          volume_mm3=manifest['used_mm3'],diagnostics=manifest['diagnostics'])
        except Exception as exc:
            record['error'] = str(exc)
        results.append(record)
        print(converter, record['status'], record.get('error',''), flush=True)
    summary = {'results':results,'passed':sum(r['status']=='passed' for r in results),'expected':2,
               'bundle_sha256':audit['bundle_sha256'], 'sources':audit['sources'],
               'setting_actions':dict(Counter(r['action'] for r in audit['settings'])),
               'profile':profile.model_dump(),'printer_contacted':False,'production_approved':False,
               'scope':'Native Windows CLI, synthetic fixtures; original 45-image report is not a rerun with these configs.'}
    write_json(args.summary, summary)
    return int(summary['passed'] != 2)


if __name__ == '__main__':
    raise SystemExit(main())
