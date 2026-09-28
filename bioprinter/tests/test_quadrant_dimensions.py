import pytest
from bioprinter.config import demo_profile
from bioprinter.layout import quadrant_bounds,placement
from bioprinter import slicing


@pytest.mark.parametrize('quadrant',['Q1','Q2','Q3','Q4'])
def test_four_by_five_inch_quadrants(quadrant):
    p=demo_profile();x0,y0,x1,y1=quadrant_bounds(p)[quadrant]
    assert x1-x0==pytest.approx(4*25.4)
    assert y1-y0==pytest.approx(5*25.4)
    matrix,allowed=placement((0,0,90,110),quadrant,p)
    assert allowed.area==pytest.approx(93.6*119)
    assert allowed.bounds[0]<=matrix[0][2]<=allowed.bounds[2]-90
    assert allowed.bounds[1]<=matrix[1][2]<=allowed.bounds[3]-110


def test_margins_still_limit_printable_area():
    with pytest.raises(ValueError,match='do not fit'):
        placement((0,0,94,110),'Q1',demo_profile())


def test_custom_profile_drives_quadrants():
    p=demo_profile().model_copy(update={'x_min':-40,'x_max':40,'y_min':-50,'y_max':50})
    _,allowed=placement((0,0,30,40),'Q3',p)
    assert allowed.bounds==(-36,-46,-4,-4)
    with pytest.raises(ValueError,match='do not fit'):placement((0,0,90,110),'Q1',p)


def test_prusa_bed_uses_profile_bounds(tmp_path,monkeypatch):
    monkeypatch.setattr(slicing,'probe',lambda _:{'available':True,'executable':'fixture',
        'help':'--load --output --dont-arrange --export-gcode'})
    def fake_slice(argv,timeout):
        from pathlib import Path
        Path(argv[argv.index('--output')+1]).write_text('; fixture G-code\n')
        return 'fixture completed'
    monkeypatch.setattr(slicing,'run',fake_slice)
    output=tmp_path/'out.gcode'
    slicing.prusa_slice(tmp_path/'mesh.stl',output,demo_profile(),.8)
    assert 'bed_shape = -101.6x-127,101.6x-127,101.6x127,-101.6x127' in output.with_suffix('.ini').read_text()
