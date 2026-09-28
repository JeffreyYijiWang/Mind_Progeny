from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFilter
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union
from .geometry import Design, clean, read_svg


def vectorize(path, width_mm=None, backend="python", threshold=128, invert=False,
              denoise=0, min_area_mm2=0, simplify_mm=0.05, background="white", mode="filled", trace_dir=None, max_pixels=None):
    path=Path(path)
    from .ingestion import EXTENSIONS
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError('Unsupported input extension; use PNG/JPEG/TIFF/BMP/SVG')
    if path.suffix.lower()==".svg": return read_svg(path,width_mm,simplify_mm or 0.01)
    if backend=="inkscape":
        from .inkscape import trace_bitmap
        return trace_bitmap(path,width_mm,threshold=threshold,invert=invert,denoise=denoise,
            min_area_mm2=min_area_mm2,simplify_mm=simplify_mm,background=background,mode=mode,trace_dir=trace_dir,max_pixels=max_pixels)
    if backend!="python": raise ValueError(f"Unknown vectorizer {backend}")
    if max_pixels is not None: raise ValueError('max_pixels is only supported by the Inkscape adapter')
    if mode!="filled": raise ValueError("Raster outline/centerline extraction is not supported; supply stroked SVG paths")
    if width_mm is None or width_mm<=0: raise ValueError("Set a positive width_mm; pixels have no implicit physical size")
    if not 0<=threshold<=255 or denoise<0 or min_area_mm2<0 or simplify_mm<0: raise ValueError("Invalid tracing parameters")
    with Image.open(path) as src:
        if getattr(src,"n_frames",1)!=1: raise ValueError("Multi-page/animated input: export each frame to a separate file")
        rgba=ImageOps.exif_transpose(src).convert("RGBA")
    bg=Image.new("RGBA",rgba.size,background);bg.alpha_composite(rgba)
    gray=bg.convert("L")
    if denoise:
        kernel=int(denoise)
        if kernel<3 or kernel%2!=1: raise ValueError("denoise must be an odd median kernel >=3")
        gray=gray.filter(ImageFilter.MedianFilter(kernel))
    mask=(np.asarray(gray)<threshold)
    if invert: mask=~mask
    scale=width_mm/gray.width
    # Pixel-edge contour coordinates after 2x nearest expansion preserve 1px features.
    pixels=cv2.resize(mask.astype(np.uint8)*255,None,fx=2,fy=2,interpolation=cv2.INTER_NEAREST)
    contours,hierarchy=cv2.findContours(np.pad(pixels,1),cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None: raise ValueError("Blank input after threshold; lower/raise threshold or invert")
    result=[]
    hierarchy=hierarchy[0]
    for i,contour in enumerate(contours):
        depth=0; parent=hierarchy[i][3]
        while parent!=-1: depth+=1;parent=hierarchy[parent][3]
        if depth%2: continue
        exterior=(contour[:,0,:]-1)/2
        if len(exterior)<3: continue
        holes=[]; child=hierarchy[i][2]
        while child!=-1:
            coords=(contours[child][:,0,:]-1)/2
            if len(coords)>=3: holes.append(coords)
            child=hierarchy[child][0]
        poly=Polygon(exterior,holes)
        if poly.area*scale*scale>=min_area_mm2: result.append(poly)
    g=clean(unary_union(result))
    g=affinity.affine_transform(g,[scale,0,0,-scale,0,gray.height*scale])
    before=g.area;g=clean(g.simplify(simplify_mm,preserve_topology=True))
    return Design(g,(0,0,width_mm,gray.height*scale),[[scale,0,0],[0,-scale,gray.height*scale],[0,0,1]],
        {"backend":"python-opencv-contour-hierarchy", "mode":"filled", "width_mm":width_mm,
         "threshold":threshold,"invert":invert,"denoise":denoise,"background":background,
         "min_area_mm2":min_area_mm2,"simplify_mm":simplify_mm,"area_before_simplification_mm2":before,
         "pixel_edge_uncertainty_mm":scale,"size_pixels":[gray.width,gray.height]})
