import pytest
from shapely.geometry import LineString, box
from shapely.ops import unary_union, polygonize
from bioprinter.geometry import fill_rings,winding


@pytest.mark.parametrize('rule',['nonzero','evenodd'])
def test_spatial_winding_matches_exhaustive_reference(rule):
    rings=[]
    for x in range(12):
        outer=list(box(x*10,0,x*10+8,8).exterior.coords)
        hole=list(box(x*10+2,2,x*10+6,6).exterior.coords)[::-1]
        island=list(box(x*10+3,3,x*10+5,5).exterior.coords)
        overlap=list(box(x*10+7,4,x*10+9,10).exterior.coords)
        rings.extend([outer,hole,island,overlap])
    faces=polygonize(unary_union([LineString(r+[r[0]]) for r in rings]))
    reference=[]
    for face in faces:
        p=face.representative_point();w=sum(winding((p.x,p.y),r) for r in rings)
        if (w%2 if rule=='evenodd' else w!=0):reference.append(face)
    assert fill_rings(rings,rule).symmetric_difference(unary_union(reference)).area<1e-9
