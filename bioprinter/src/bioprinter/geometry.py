"""Strict SVG subset -> printable polygons. Every transform is explicit."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import math
import re
import numpy as np
from defusedxml import ElementTree as ET
from shapely import affinity, make_valid, STRtree
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, polygonize
from svgpathtools import parse_path


@dataclass
class Design:
    geometry: object
    canvas: tuple
    transform: list
    metadata: dict = field(default_factory=dict)


def polygons(g):
    if g.geom_type == "Polygon":
        return [g]
    if hasattr(g, "geoms"):
        return [p for item in g.geoms for p in polygons(item)]
    return []


def clean(g):
    g = unary_union(polygons(make_valid(g)))
    if g.is_empty or g.area <= 1e-10:
        raise ValueError("No printable filled geometry; check threshold, fill or stroke width")
    return g


def apply(g, m):
    m = np.asarray(m)
    return affinity.affine_transform(g, [m[0,0],m[0,1],m[1,0],m[1,1],m[0,2],m[1,2]])


def anchor_point(bounds, anchor):
    x0,y0,x1,y1 = bounds
    choices = {"bottom_left":(x0,y0), "bottom_right":(x1,y0), "top_left":(x0,y1),
               "top_right":(x1,y1), "center":((x0+x1)/2,(y0+y1)/2)}
    if anchor not in choices:
        raise ValueError(f"Unknown anchor: {anchor}")
    return choices[anchor]


def register(design, anchor="bottom_left", mode="shared_canvas", explicit=None):
    bounds = design.canvas if mode == "shared_canvas" else design.geometry.bounds
    if mode not in {"shared_canvas", "per_design_bbox"}:
        raise ValueError("Registration must be shared_canvas or per_design_bbox")
    x,y = anchor_point(bounds, anchor)
    m = np.array([[1,0,-x],[0,1,-y],[0,0,1]], dtype=float)
    if explicit is not None:
        e = np.asarray(explicit, dtype=float)
        if e.shape != (3,3) or not np.allclose(e[2], [0,0,1]) or abs(np.linalg.det(e)) < 1e-10:
            raise ValueError("Registration requires an invertible 3x3 affine matrix")
        m = e @ m
    total = m @ np.asarray(design.transform)
    return Design(apply(design.geometry, m), apply(box(*design.canvas), m).bounds, total.tolist(),
        {**design.metadata, "anchor":anchor, "registration":mode,
         "source_to_local":total.tolist(), "local_to_source":np.linalg.inv(total).tolist()})


NUM = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def transform(text):
    result = np.eye(3)
    pos = 0
    for match in re.finditer(r"([a-zA-Z]+)\s*\(([^)]*)\)", text or ""):
        if (text[pos:match.start()]).strip(" ,\t\n"):
            raise ValueError("Invalid SVG transform")
        name, raw = match.groups()
        vals = [float(v) for v in re.findall(NUM, raw)]
        if re.sub(NUM, "", raw).strip(" ,\t\n"):
            raise ValueError("Invalid transform arguments")
        m = np.eye(3)
        if name == "matrix" and len(vals) == 6:
            a,b,c,d,e,f = vals
            m = np.array([[a,c,e],[b,d,f],[0,0,1]])
        elif name == "translate" and len(vals) in (1,2):
            m[:2,2] = [vals[0], vals[1] if len(vals)>1 else 0]
        elif name == "scale" and len(vals) in (1,2):
            m[0,0],m[1,1] = vals[0], vals[-1]
        elif name == "rotate" and len(vals) in (1,3):
            a = math.radians(vals[0]); c,s = math.cos(a),math.sin(a)
            m[:2,:2] = [[c,-s],[s,c]]
            if len(vals)==3:
                xy=np.array(vals[1:]); m[:2,2]=xy-m[:2,:2]@xy
        elif name in {"skewX","skewY"} and len(vals)==1:
            m[0 if name=="skewX" else 1,1 if name=="skewX" else 0]=math.tan(math.radians(vals[0]))
        else:
            raise ValueError(f"Unsupported transform {name}")
        result = result @ m
        pos = match.end()
    if (text or "")[pos:].strip(" ,\t\n") or abs(np.linalg.det(result)) < 1e-12:
        raise ValueError("Invalid/singular transform")
    return result


def length(value):
    match = re.fullmatch(rf"\s*({NUM})(mm|cm|in|pt|px)?\s*", str(value))
    if not match:
        raise ValueError(f"Unsupported SVG length {value!r}; percentages require conversion")
    v,u=match.groups()
    return float(v)*{None:1,"px":1,"mm":96/25.4,"cm":96/2.54,"in":96,"pt":96/72}[u]


def winding(point, ring):
    x,y=point; n=0
    for (x0,y0),(x1,y1) in zip(ring,ring[1:]+ring[:1]):
        cross=(x1-x0)*(y-y0)-(x-x0)*(y1-y0)
        if y0<=y<y1 and cross>0: n+=1
        elif y1<=y<y0 and cross<0: n-=1
    return n


def fill_rings(rings, rule):
    if rule not in {"nonzero","evenodd"}:
        raise ValueError("Unsupported fill rule")
    lines=[LineString(r+[r[0]]) for r in rings if len(r)>=3]
    faces=list(polygonize(unary_union(lines)))
    # A closed ring has zero winding outside its bounding box. Query those boxes
    # once per face instead of scanning every segment of every disconnected ring.
    valid_rings=[r for r in rings if len(r)>=3]
    index=STRtree([box(*line.bounds) for line in lines])
    selected=[]
    for face in faces:
        p=face.representative_point()
        w=sum(winding((p.x,p.y),valid_rings[i]) for i in index.query(p))
        if (w%2 if rule=="evenodd" else w!=0): selected.append(face)
    return unary_union(selected)


def flatten_path(data, tolerance):
    result=[]
    for sub in parse_path(data).continuous_subpaths():
        pts=[]
        def sample(seg,a,b,depth=0):
            p,q=seg.point(a),seg.point(b)
            # Quarter samples prevent a closed cubic's midpoint hiding curvature.
            line=LineString([(p.real,p.imag),(q.real,q.imag)])
            error=max(line.distance(Point(seg.point(a+(b-a)*u).real,seg.point(a+(b-a)*u).imag)) for u in (.25,.5,.75))
            if error>tolerance:
                if depth>=18: raise ValueError("Curve exceeds flattening complexity limit")
                sample(seg,a,(a+b)/2,depth+1);sample(seg,(a+b)/2,b,depth+1)
            else: pts.append((q.real,q.imag))
        if len(sub):
            p=sub[0].start;pts=[(p.real,p.imag)]
            for seg in sub: sample(seg,0,1)
            result.append(pts)
    return result


def read_svg(path, width_mm=None, tolerance_mm=0.05):
    root=ET.parse(path).getroot()
    vb=[float(x) for x in re.findall(NUM,root.get("viewBox",""))]
    if not vb:
        vb=[0,0,length(root.get("width","0")),length(root.get("height","0"))]
    if len(vb)!=4 or vb[2]<=0 or vb[3]<=0:
        raise ValueError("SVG needs a valid viewBox or width/height")
    if width_mm is None:
        w=root.get("width","")
        if not re.search(r"(mm|cm|in|pt)$",w):
            raise ValueError("Specify width_mm; SVG pixels are not millimeters")
        width_mm=length(w)*25.4/96
    if width_mm<=0 or tolerance_mm<=0: raise ValueError("Size/tolerance must be positive")
    scale=width_mm/vb[2]; geoms=[]
    allowed={"svg","g","path","rect","circle","ellipse","polygon","polyline","line","title","desc","metadata"}
    style_keys={"fill","fill-rule","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-miterlimit",
                "opacity","fill-opacity","stroke-opacity","display","visibility"}
    def visit(el, parent, inherited):
        tag=el.tag.split("}")[-1]
        if tag not in allowed: raise ValueError(f"Unsupported SVG <{tag}>; convert to plain paths first")
        if tag in {"title","desc","metadata"}: return
        if any(k.split("}")[-1] in {"href","filter","mask","clip-path","vector-effect","stroke-dasharray"} for k in el.attrib):
            raise ValueError("External resources, effects and dashed/vector-effect strokes require conversion")
        style=dict(inherited)
        style.update({k:v for k,v in el.attrib.items() if k in style_keys})
        for decl in el.get("style","").split(";"):
            if not decl.strip(): continue
            k,v=decl.split(":",1); k=k.strip();v=v.strip()
            if k not in style_keys: raise ValueError(f"Unsupported CSS property {k}")
            style[k]=v
        if any("url(" in v for v in style.values()): raise ValueError("SVG paint servers unsupported")
        if style.get("display")=="none" or style.get("visibility")=="hidden" or float(style.get("opacity",1))==0: return
        m=parent@transform(el.get("transform",""))
        if tag in {"svg","g"}:
            if tag=="svg" and el is not root: raise ValueError("Nested SVG viewport unsupported; flatten first")
            for child in el: visit(child,m,style)
            return
        get=lambda k,d="0":length(el.get(k,d))
        rings=[]
        if tag=="path":
            norm=np.linalg.norm(m[:2,:2],2)*scale
            rings=flatten_path(el.get("d",""),tolerance_mm/max(norm,1e-9))
        elif tag=="rect":
            if el.get("rx") or el.get("ry"): raise ValueError("Convert rounded rectangles to paths")
            x,y,w,h=get("x"),get("y"),get("width"),get("height")
            if w<0 or h<0: raise ValueError("Negative rectangle size")
            rings=[[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]]
        elif tag in {"circle","ellipse"}:
            x,y=get("cx"),get("cy"); rx=get("r") if tag=="circle" else get("rx"); ry=rx if tag=="circle" else get("ry")
            n=max(16,math.ceil(2*math.pi*math.sqrt(max(rx,ry)*scale/max(tolerance_mm,1e-9))))
            rings=[[(x+rx*math.cos(a),y+ry*math.sin(a)) for a in np.linspace(0,2*math.pi,n+1)]]
        elif tag in {"polygon","polyline"}:
            values=[float(x) for x in re.findall(NUM,el.get("points",""))]
            if len(values)%2: raise ValueError("Odd SVG point coordinate count")
            ring=list(zip(values[::2],values[1::2]));rings=[ring]
            if tag=="polygon" and ring: ring.append(ring[0])
        elif tag=="line": rings=[[(get("x1"),get("y1")),(get("x2"),get("y2"))]]
        if style.get("fill","black")!="none" and tag!="line" and float(style.get("fill-opacity",1))>0:
            geoms.append(apply(fill_rings(rings,style.get("fill-rule","nonzero")),m))
        if style.get("stroke","none")!="none" and float(style.get("stroke-opacity",1))>0:
            cap={"butt":2,"round":1,"square":3}.get(style.get("stroke-linecap","butt"))
            join={"miter":2,"round":1,"bevel":3}.get(style.get("stroke-linejoin","miter"))
            if cap is None or join is None: raise ValueError("Unsupported stroke cap/join")
            for ring in rings:
                if len(ring)>1:
                    geoms.append(apply(LineString(ring).buffer(length(style.get("stroke-width","1"))/2,
                        cap_style=cap,join_style=join,mitre_limit=float(style.get("stroke-miterlimit",4))),m))
    visit(root,np.eye(3),{})
    g=clean(unary_union(geoms))
    # Exactly one Y flip, based on the source canvas, before registration.
    mat=np.array([[scale,0,-vb[0]*scale],[0,-scale,(vb[1]+vb[3])*scale],[0,0,1]])
    return Design(clean(apply(g,mat)),(0,0,width_mm,vb[3]*scale),mat.tolist(),
                  {"backend":"existing-svg", "source_viewbox":vb,"width_mm":width_mm,"curve_tolerance_mm":tolerance_mm})


def write_svg(design, path):
    g=design.geometry; x0,y0,x1,y1=g.bounds
    paths=[]
    for poly in polygons(g):
        rings=[poly.exterior,*poly.interiors]; data=[]
        for ring in rings:
            pts=list(ring.coords)
            data.append("M "+" L ".join(f"{x:.6f},{-y:.6f}" for x,y in pts)+" Z")
        paths.append('<path fill="black" fill-rule="evenodd" d="'+" ".join(data)+'"/>')
    Path(path).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{x1-x0}mm" height="{y1-y0}mm" viewBox="{x0} {-y1} {x1-x0} {y1-y0}">' + "".join(paths)+"</svg>",encoding="utf-8")
