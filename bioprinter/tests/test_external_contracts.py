from pathlib import Path
import pytest
from bioprinter.config import demo_profile
from bioprinter import slicing


def fake_probe(_):
    return {'available':True,'executable':'fixture-executable',
            'help':'--export-gcode --load --output --dont-arrange','version':'fixture'}


def test_prusa_zero_exit_without_output_is_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(slicing,'probe',fake_probe)
    monkeypatch.setattr(slicing,'run',lambda *args:'First layer height cannot exceed nozzle diameter')
    with pytest.raises(ValueError,match='nozzle diameter'):
        slicing.prusa_slice(tmp_path/'mesh.stl',tmp_path/'out.gcode',demo_profile(),.3)
    assert 'height' in (tmp_path/'out.log').read_text()


def test_prusa_stale_file_cannot_mask_failure(tmp_path,monkeypatch):
    output=tmp_path/'out.gcode';output.write_text('; stale job\nG1 X1\n')
    monkeypatch.setattr(slicing,'probe',fake_probe)
    def forbidden(*args): raise AssertionError('Do not run with an existing output')
    monkeypatch.setattr(slicing,'run',forbidden)
    with pytest.raises(ValueError,match='fresh Prusa output'):
        slicing.prusa_slice(tmp_path/'mesh.stl',output,demo_profile(),.8)
    assert output.read_text()=='; stale job\nG1 X1\n'


def test_inkscape_stale_paths_are_not_reused(tmp_path,monkeypatch):
    from bioprinter import inkscape
    stale=tmp_path/'trace.raw.svg';stale.write_text('<svg/>')
    monkeypatch.setattr(inkscape,'probe',lambda name:{'available':True,'actions':'object-trace'})
    with pytest.raises(ValueError,match='fresh Inkscape trace directory'):
        inkscape.trace_bitmap(tmp_path/'missing-input.png',40,trace_dir=tmp_path)
    assert stale.read_text()=='<svg/>'


def test_native_traces_have_distinct_application_instances(tmp_path,monkeypatch):
    from bioprinter import inkscape
    from PIL import Image
    source=tmp_path/'input.png';im=Image.new('L',(10,10),255);im.putpixel((3,3),0);im.save(source)
    monkeypatch.setattr(inkscape,'probe',lambda name:{'available':True,'actions':'object-trace',
        'executable':'fake-inkscape','version':'fixture'})
    commands=[]
    def fake_trace(argv,timeout):
        commands.append(argv)
        output=next(v.split('=',1)[1] for v in argv if v.startswith('--export-filename='))
        Path(output).write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M1 1 H8 V8 H1 Z"/></svg>')
        return 'fixture trace'
    monkeypatch.setattr(inkscape,'run',fake_trace)
    for index in range(2):inkscape.trace_bitmap(source,40,trace_dir=tmp_path/str(index))
    tags=[next(v for v in argv if v.startswith('--app-id-tag=')) for argv in commands]
    assert tags[0]!=tags[1] and all(v.startswith('--app-id-tag=bioprinter') for v in tags)
