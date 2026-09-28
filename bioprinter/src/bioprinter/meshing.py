from pathlib import Path
from collections import Counter
import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry.polygon import orient
from .geometry import polygons


def triangles(geometry, height):
    if height<=0: raise ValueError("Mesh height must be positive")
    faces=[]
    for poly in polygons(geometry):
        poly=orient(poly,sign=1)
        for tri in constrained_delaunay_triangles(poly).geoms:
            coords=list(orient(tri,sign=1).exterior.coords)[:3]
            faces.append([(x,y,height) for x,y in coords])
            faces.append([(x,y,0) for x,y in reversed(coords)])
        for ring in [poly.exterior,*poly.interiors]:
            coords=list(ring.coords)
            for a,b in zip(coords,coords[1:]):
                a0=(*a,0);a1=(*a,height);b0=(*b,0);b1=(*b,height)
                faces.extend([[a0,b0,b1],[a0,b1,a1]])
    edges=Counter()
    for tri in faces:
        for a,b in zip(tri,tri[1:]+tri[:1]): edges[tuple(sorted((a,b)))]+=1
    if not faces or any(count!=2 for count in edges.values()): raise ValueError("Mesh is not watertight")
    return faces


def write_stl(geometry, height, path):
    faces=triangles(geometry,height);out=["solid bioprinter_mm"]
    for tri in faces:
        n=np.cross(np.array(tri[1])-tri[0],np.array(tri[2])-tri[0]);n=n/np.linalg.norm(n)
        out.extend(["facet normal "+" ".join(map(str,n)),"outer loop"])
        out.extend("vertex "+" ".join(f"{v:.9f}" for v in xyz) for xyz in tri)
        out.extend(["endloop","endfacet"])
    out.append("endsolid bioprinter_mm")
    Path(path).write_text('\n'.join(out)+'\n',encoding="ascii")
    return {"triangles":len(faces),"watertight":True,"units":"STL unitless interpreted as millimeters"}
