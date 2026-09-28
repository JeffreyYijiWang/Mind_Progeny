import json
from pathlib import Path
import pytest
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Point
from bioprinter.config import Profile
from bioprinter.presets import PRESETS, resolve
from bioprinter.vectorization import vectorize
from bioprinter.pipeline import compose, preflight


@pytest.mark.parametrize('preset,limit', [('small',(25,31.25)),('medium',(50,62.5)),
                                          ('large',(75,93.75)),('quadrant',(93.6,119))])
@pytest.mark.parametrize('pixels', [(200,100),(100,200)])
def test_size_envelopes_keep_aspect(preset,limit,pixels,tmp_path,profile):
    source=tmp_path/'picture.png';Image.new('RGB',pixels,'white').save(source)
    options,meta=resolve(source,preset,profile=profile)
    w,h=meta['canvas_mm']
    assert w<=limit[0]+1e-8 and h<=limit[1]+1e-8
    assert w/h==pytest.approx(pixels[0]/pixels[1])
    assert w==pytest.approx(min(limit[0],limit[1]*pixels[0]/pixels[1]))
    assert options['width_mm']==w and meta['needle_diameter_inferred'] is False


def test_explicit_settings_and_unmeasured_margins(tmp_path,profile):
    source=tmp_path/'picture.png';Image.new('RGB',(100,200),'white').save(source)
    with pytest.raises(ValueError,match='explicit profile'):
        resolve(source,'quadrant',profile=Profile())
    with pytest.raises(ValueError,match='exceeds'):
        resolve(source,'small',width_mm=25)
    settings,meta=resolve(source,'medium',width_mm=20,overrides={'threshold':220,'denoise':3})
    assert settings['threshold']==220 and settings['denoise']==3
    assert meta['canvas_mm']==[20,40]
    assert PRESETS['medium']['threshold']==128
    settings,_=resolve(source,'medium',overrides={'width_mm':15})
    assert settings['width_mm']==15
    with pytest.raises(ValueError,match='Unknown tracing'):
        resolve(source,'small',overrides={'typo':42})


def test_python_working_copy_preserves_hole_and_original(tmp_path):
    source=tmp_path/'ring.png';im=Image.new('RGB',(400,400),'white');draw=ImageDraw.Draw(im)
    draw.rectangle((40,40,359,359),fill='black');draw.rectangle((140,140,259,259),fill='white');im.save(source)
    design=vectorize(source,40,max_pixels=100)
    assert not design.geometry.covers(Point(20,20))
    assert design.geometry.covers(Point(8,8))
    assert design.metadata['original_size_pixels']==[400,400]
    assert design.metadata['size_pixels']==[100,100]
    assert Image.open(source).size==(400,400)
    assert np.asarray(design.transform)@[80,80,1]==pytest.approx([8,32,1])


def test_inkscape_resize_transform_starts_at_original_pixels(tmp_path,monkeypatch):
    from bioprinter import inkscape
    source=tmp_path/'source.png';im=Image.new('L',(100,100),255)
    ImageDraw.Draw(im).rectangle((20,20,80,80),fill=0);im.save(source)
    monkeypatch.setattr(inkscape,'probe',lambda name:{'available':True,'actions':'object-trace',
        'executable':'fake-inkscape','version':'fixture'})
    def native(argv,timeout):
        output=next(v.split('=',1)[1] for v in argv if v.startswith('--export-filename='))
        Path(output).write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M4 4H16V16H4Z"/></svg>')
        return 'fixture'
    monkeypatch.setattr(inkscape,'run',native)
    d=vectorize(source,40,backend='inkscape',max_pixels=20,trace_dir=tmp_path/'trace')
    assert d.metadata['size_pixels']==[20,20] and d.metadata['original_size_pixels']==[100,100]
    assert np.asarray(d.transform)@[25,25,1]==pytest.approx([10,30,1])


def test_needle_identity_is_independent_from_diameters():
    p=Profile();summary=p.needle_summary()
    assert (summary['gauge'],summary['length_mm'],summary['length_inches'])==(23,12.7,.5)
    assert summary['inner_diameter_mm'] is None and summary['outer_diameter_mm'] is None
    assert summary['dimensions_are_synthetic'] is False
    p.needle_gauge_confirmed=False;p.needle_length_confirmed=False
    assert {'needle_gauge_confirmed','needle_length_confirmed'}<=set(p.missing(production=True))


def test_preset_reaches_complete_pipeline_and_manifest(inputs,tmp_path,profile):
    run=compose(inputs,profile,output_root=tmp_path/'runs',preset='small',
                order=['image1_ring.png'],sequences={'Q1':['image1_ring.png']},
                trace_options={'threshold':180})
    _,manifest=preflight(run,production=False)
    assert manifest['status']=='complete' and manifest['needle']['gauge']==23
    assert manifest['needle']['length_mm']==12.7 and manifest['needle']['dimensions_are_synthetic']
    preset=manifest['assets'][0]['geometry']['svg_preset']
    assert preset['name']=='small' and preset['settings']['threshold']==180
    assert (run/'reports'/'needle.json').is_file()
    assert (run/'combined'/'combined.gcode').read_text().startswith(';')
    assert manifest['network_contacted'] is False


def test_cli_preset_svg_settings_sidecar(inputs,tmp_path,capsys):
    from bioprinter.cli import main
    out=tmp_path/'medium.svg'
    main(['vectorize',str(inputs/'image1_ring.png'),str(out),'--preset','medium','--threshold','190'])
    record=json.loads(out.with_suffix('.settings.json').read_text())
    assert out.is_file() and record['needle']['gauge']==23 and record['needle']['inner_diameter_mm'] is None
    assert record['geometry']['svg_preset']['name']=='medium'
    assert record['geometry']['threshold']==190
    assert record['printer_contacted'] is False
    from bioprinter.geometry import read_svg
    assert read_svg(out).canvas==pytest.approx((0,0,50,50))


def test_svg_export_preserves_shared_canvas_offsets(tmp_path):
    from bioprinter.geometry import Design, write_svg, read_svg
    from shapely.geometry import box
    for name,x in [('left',3),('right',9)]:
        d=Design(box(x,5,x+4,11),(0,0,25,30),[[1,0,0],[0,1,0],[0,0,1]])
        out=tmp_path/(name+'.svg');write_svg(d,out,preserve_canvas=True)
        reread=read_svg(out)
        assert reread.canvas==pytest.approx(d.canvas)
        assert reread.geometry.bounds==pytest.approx(d.geometry.bounds)
