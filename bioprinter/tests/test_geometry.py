import numpy as np
import pytest
from PIL import Image,ImageDraw
from shapely.geometry import Point,box
from bioprinter.geometry import read_svg,register,anchor_point,polygons,write_svg
from bioprinter.vectorization import vectorize
from bioprinter.ingestion import discover
from bioprinter.meshing import triangles


def svg(tmp_path,body,attrs='width="20mm" height="20mm" viewBox="0 0 100 100"'):
    path=tmp_path/'fixture.svg';path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}>{body}</svg>',encoding='utf-8');return path


def test_holes_transparency_islands_and_order(inputs):
    assets=discover(inputs)
    assert [a.path.name for a in assets]==['image1_ring.png','image2_asymmetric_L.png','image10_bridge_island.png']
    ring=vectorize(assets[0].path,24)
    assert not ring.geometry.covers(Point(12,12))
    assert len(polygons(ring.geometry)[0].interiors)==1
    assert len(polygons(vectorize(assets[-1].path,24).geometry))==2
    assert len(discover(inputs,order=[assets[-1].path.name]*2))==2


def test_blank_size_and_multiframe(tmp_path):
    blank=tmp_path/'blank.png';Image.new('RGB',(20,20),'white').save(blank)
    with pytest.raises(ValueError,match='Blank'):vectorize(blank,20)
    with pytest.raises(ValueError,match='width_mm'):vectorize(blank)
    tiff=tmp_path/'pages.tiff';Image.new('RGB',(20,20)).save(tiff,save_all=True,append_images=[Image.new('RGB',(20,20))])
    with pytest.raises(ValueError,match='Multi-page'):vectorize(tiff,20)
    with pytest.raises(ValueError,match='Unsupported input extension'):vectorize(tmp_path/'unsupported.gif',20)


@pytest.mark.parametrize('anchor',['bottom_left','bottom_right','top_left','top_right','center'])
def test_five_anchors_inverse(tmp_path,anchor):
    d=read_svg(svg(tmp_path,'<path d="M 10,10 L 30,10 L 30,70 L 85,70 L 85,90 L 10,90 Z"/>'))
    a=anchor_point(d.geometry.bounds,anchor);local=register(d,anchor,'per_design_bbox')
    assert anchor_point(local.geometry.bounds,anchor)==pytest.approx((0,0))
    assert np.allclose(np.asarray(local.metadata['local_to_source'])@local.transform,np.eye(3))
    # L leg on left; lower horizontal bar after the single Y flip.
    assert d.geometry.covers(Point(3,3)) and d.geometry.covers(Point(16,3))
    assert not d.geometry.covers(Point(16,16))


def test_shared_canvas_preserves_offsets(tmp_path):
    a=register(read_svg(svg(tmp_path,'<rect x="10" y="20" width="20" height="30"/>')))
    b=register(read_svg(svg(tmp_path,'<rect x="30" y="20" width="20" height="30"/>')))
    assert b.geometry.bounds[0]-a.geometry.bounds[0]==pytest.approx(4)
    assert register(a,'bottom_left','per_design_bbox').geometry.bounds[0]==0


def test_transforms_holes_fill_rules_and_strokes(tmp_path):
    d=read_svg(svg(tmp_path,'<g transform="translate(10,10) scale(2)"><path fill-rule="evenodd" d="M0 0H30V30H0Z M10 10H20V20H10Z"/></g>'))
    assert len(polygons(d.geometry)[0].interiors)==1
    assert d.geometry.bounds==pytest.approx((2,6,14,18))
    d=read_svg(svg(tmp_path,'<path fill="none" stroke="black" stroke-width="10" d="M20 20L80 20"/>'))
    assert d.geometry.area==pytest.approx(24)


def test_thin_stroke_and_watertight_hole_mesh(tmp_path,profile,inputs):
    from bioprinter.slicing import direct_paths
    d=read_svg(svg(tmp_path,'<path fill="none" stroke="black" stroke-width="0.2" d="M20 20L80 20"/>'))
    with pytest.raises(ValueError,match='narrower'):direct_paths(d.geometry,profile)
    ring=vectorize(inputs/'image1_ring.png',24)
    faces=triangles(ring.geometry,.5)
    volume=sum(np.dot(a,np.cross(b,c))/6 for a,b,c in faces)
    assert volume==pytest.approx(ring.geometry.area*.5)


@pytest.mark.parametrize('body',['<text>no</text>','<image href="http://bad/"/>','<g filter="url(#f)"><rect width="4" height="4"/></g>','<use href="#a"/>'])
def test_unsupported_svg_fails(tmp_path,body):
    with pytest.raises(ValueError):read_svg(svg(tmp_path,body))


def test_no_external_entity_resolution(tmp_path):
    p=tmp_path/'unsafe.svg';p.write_text('<!DOCTYPE svg [<!ENTITY a SYSTEM "file:///secrets">]><svg width="1mm" height="1mm">&a;</svg>')
    with pytest.raises(Exception,match='EntitiesForbidden'):read_svg(p)


def test_pixel_units_require_scale_and_round_trip(tmp_path):
    p=svg(tmp_path,'<rect x="10" y="10" width="20" height="20"/>',attrs='width="100px" height="100px"')
    with pytest.raises(ValueError,match='width_mm'):read_svg(p)
    d=register(read_svg(p,20));out=tmp_path/'out.svg';write_svg(d,out)
    reread=read_svg(out)
    assert reread.geometry.area==pytest.approx(d.geometry.area)


def test_inkscape_request_never_silently_uses_python(inputs,monkeypatch):
    monkeypatch.setattr('bioprinter.external.probe',lambda name:{'available':False})
    with pytest.raises(ValueError,match='manual round-trip'):vectorize(inputs/'image1_ring.png',24,backend='inkscape')
