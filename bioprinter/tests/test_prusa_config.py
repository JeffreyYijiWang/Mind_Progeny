import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from bioprinter.config import demo_profile, load_profile
from bioprinter.prusa_config import import_zip, load_bundle, parse_ini
from bioprinter.slicing import resolve_prusa_config, prusa_slice


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT/'profiles/prusaslicer/supplied-2026-05'


def archive(tmp_path, extra='', member='presets/print.ini'):
    path = tmp_path/'presets.zip'
    with ZipFile(path, 'w') as z:
        z.writestr(member.replace('\\','/'), 'layer_height = 0.05\nfill_density = 0%\n'+extra)
        z.writestr('presets/filament.ini', 'filament_diameter = 10.3\nextrusion_multiplier = 2.85\n')
        z.writestr('presets/printer.ini', 'nozzle_diameter = 0.33\nend_gcode = M84\\n\n')
    if '\\' in member:
        path.write_bytes(path.read_bytes().replace(member.replace('\\','/').encode(),member.encode()))
    return path


def test_source_settings_and_profile_precedence():
    p = load_profile(ROOT/'profiles/supplied-prusa-preview.yaml')
    config, audit, _ = resolve_prusa_config(p, p.needle_inner_diameter_mm, prusa_config=BUNDLE)
    assert config['perimeters'] == '1' and config['fill_density'] == '0%'
    assert config['top_solid_layers'] == config['bottom_solid_layers'] == '1'
    assert config['perimeter_generator'] == 'arachne' and config['fill_angle'] == '45'
    assert config['layer_height'] == .05 and config['filament_diameter'] == 10.3
    assert config['bed_shape'] == '-101.6x-127,101.6x-127,101.6x127,-101.6x127'
    assert config['extrusion_multiplier'] == 1 and config['first_layer_extrusion_width'] == .37
    assert config['end_gcode'] == config['post_process'] == config['start_filament_gcode'] == ''
    assert config['cooling'] == config['autoemit_temperature_commands'] == 0
    records = {r['key']:r for r in audit['settings']}
    assert records['extrusion_multiplier']['source'] == '2.85'
    assert records['extrusion_multiplier']['action'] == 'overridden'
    assert records['machine_max_feedrate_x']['action'] == 'ignored'
    assert records['nozzle_diameter']['source'] == '0.33'
    with pytest.raises(ValueError, match='synthetic profile'):
        p.require(production=True)
    assert p.confirmed_fields == [] and demo_profile().deposition_height_mm == .5


def test_explicit_slice_overrides_and_volume_convention():
    p = demo_profile().model_copy(update={'slicer_e_mode':'mm3'})
    config, _, _ = resolve_prusa_config(p, .3, prusa_config=BUNDLE,
        perimeters=2, density=35, top=0, bottom=0)
    assert config['perimeters'] == 2 and config['fill_density'] == '35%'
    assert config['top_solid_layers'] == config['bottom_solid_layers'] == 0
    assert config['layer_height'] == .5 and config['nozzle_diameter'] == .3
    assert config['use_volumetric_e'] == 1


def test_import_preserves_bytes_snapshot_and_detects_tampering(tmp_path):
    source = archive(tmp_path)
    target = import_zip(source, tmp_path/'imported')
    bundle = load_bundle(target)
    copied = bundle.snapshot(tmp_path/'snapshot')
    assert copied.read_bytes() == target.read_bytes()
    with ZipFile(source) as z:
        assert (target.parent/'print.ini').read_bytes() == z.read('presets/print.ini')
    (target.parent/'print.ini').write_text('changed')
    with pytest.raises(ValueError, match='hash changed'):
        load_bundle(target)
    assert load_bundle(copied).path_options() == {'fill_density':'0%'}
    with pytest.raises(ValueError, match='never overwritten'):
        import_zip(source, target.parent)


@pytest.mark.parametrize('member', ['../print.ini', '/print.ini', 'C:/print.ini', 'bad\\print.ini'])
def test_unsafe_archive_rejected_before_writes(tmp_path, member):
    with pytest.raises(ValueError, match='Unsafe'):
        import_zip(archive(tmp_path, member=member), tmp_path/'imported')
    assert not (tmp_path/'imported').exists()


@pytest.mark.parametrize('text', ['perimeters = 1\nperimeters = 2', '[print:inherited]',
    'inherits = external', 'printhost_apikey = secret', 'print_host = http://printer',
    'fill_pattern = rectilinear\x00'])
def test_invalid_or_private_ini_rejected(text):
    with pytest.raises(ValueError):
        parse_ini(text.encode())


def test_hooks_never_reach_subprocess(tmp_path, monkeypatch):
    from bioprinter import slicing
    extra = 'post_process = powershell.exe evil.ps1\nstart_gcode = G28\\nM500\ngcode_substitutions = M83;M500\n'
    bundle = import_zip(archive(tmp_path, extra), tmp_path/'bundle')
    monkeypatch.setattr(slicing, 'probe', lambda _: {'available':True, 'executable':'prusa',
        'help':'--export-gcode --load --output --dont-arrange'})
    def fake_run(args, timeout):
        assert args.count('--load') == 1
        ini = Path(args[args.index('--load')+1]).read_text()
        assert all(word not in ini for word in ['powershell', 'evil', 'G28', 'M500', 'M84'])
        assert 'post_process = \n' in ini
        Path(args[args.index('--output')+1]).write_text('; fixture\nG1 X1\n')
        return 'ok'
    monkeypatch.setattr(slicing, 'run', fake_run)
    out = prusa_slice(tmp_path/'mesh.stl',tmp_path/'out.gcode',demo_profile(),.3,prusa_config=bundle)
    audit = json.loads(out.with_suffix('.config-report.json').read_text())
    assert len(audit['sources']) == 3
    assert (out.with_suffix('.sources')/'bundle.json').is_file()
    assert (out.parent/audit['source_snapshot']).is_file()


def test_direct_backend_rejects_selected_prusa_config(tmp_path):
    from bioprinter.pipeline import compose
    with pytest.raises(ValueError, match='requires backend prusa'):
        compose(tmp_path, output_root=tmp_path/'runs', prusa_config=BUNDLE)
    assert not (tmp_path/'runs').exists()


def test_cli_preserves_bundle_defaults(monkeypatch, tmp_path):
    from bioprinter import cli
    received = {}
    def fake_compose(folder, profile, **kwargs):
        received.update(kwargs)
        return tmp_path
    monkeypatch.setattr(cli, 'compose', fake_compose)
    cli.main(['compose', 'examples/inputs', '--profile',str(ROOT/'profiles/supplied-prusa-preview.yaml'),
              '--preset','small','--backend','prusa','--prusa-config',str(BUNDLE)])
    assert received['prusa_config'] == str(BUNDLE)
    assert received['perimeters'] is None and received['infill_density'] is None
    assert received['top_solid_layers'] is None and received['bottom_solid_layers'] is None
