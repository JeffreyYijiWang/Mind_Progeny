"""Fixture-verified Inkscape object-trace adapter (1.4.4 on Windows).

Thresholding is explicit preprocessing; Potrace inside Inkscape creates the paths.
No raster fallback is returned and arbitrary SVG sanitization is not performed.
"""
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as XML
from defusedxml import ElementTree as SafeXML
import numpy as np
from PIL import Image, ImageOps, ImageFilter
from shapely.ops import unary_union
from .geometry import read_svg, clean, polygons
from .external import probe, run


def trace_bitmap(path, width_mm, *, threshold=128, invert=False, denoise=0,
                 min_area_mm2=0, simplify_mm=.05, background='white', mode='filled', trace_dir=None, max_pixels=None):
    cap=probe('inkscape')
    if not cap['available'] or 'object-trace' not in cap.get('actions',''):
        raise ValueError('Inkscape manual round-trip required: this executable lacks object-trace; '
                         'trace the bitmap, delete the raster, then save Plain SVG. '+str(cap))
    if width_mm is None or width_mm<=0: raise ValueError('Set a positive width_mm')
    if mode!='filled': raise ValueError('Inkscape adapter supports filled binary traces only')
    if not 0<=threshold<=255 or min_area_mm2<0 or simplify_mm<0: raise ValueError('Invalid tracing parameters')
    if denoise and (denoise<3 or int(denoise)!=denoise or denoise%2!=1):
        raise ValueError('denoise must be an odd median kernel >=3')
    if max_pixels is not None and (max_pixels<16 or int(max_pixels)!=max_pixels):
        raise ValueError('max_pixels must be an integer >=16')
    if trace_dir is None:
        with TemporaryDirectory(prefix='bioprinter-trace-') as temp:
            design=trace_bitmap(path,width_mm,threshold=threshold,invert=invert,denoise=denoise,
                min_area_mm2=min_area_mm2,simplify_mm=simplify_mm,background=background,mode=mode,trace_dir=temp,max_pixels=max_pixels)
            design.metadata.pop('trace_directory',None)
            return design
    folder=Path(trace_dir);folder.mkdir(parents=True,exist_ok=True)
    if any((folder/name).exists() for name in ('trace.raw.svg','trace.paths.svg')):
        raise ValueError('Use a fresh Inkscape trace directory; stale paths must not mask a failed trace')
    with Image.open(path) as src:
        if getattr(src,'n_frames',1)!=1: raise ValueError('Multi-page/animated input unsupported')
        oriented=ImageOps.exif_transpose(src);original_size=oriented.size
        if max_pixels is not None:
            oriented.thumbnail((max_pixels,max_pixels),Image.Resampling.LANCZOS)
        rgba=oriented.convert('RGBA')
    bg=Image.new('RGBA',rgba.size,background);bg.alpha_composite(rgba);gray=bg.convert('L')
    del rgba,bg
    if denoise: gray=gray.filter(ImageFilter.MedianFilter(int(denoise)))
    foreground=np.asarray(gray)<threshold
    if invert: foreground=~foreground
    if not foreground.any() or foreground.all(): raise ValueError('Blank or entirely filled threshold mask; review threshold')
    Image.fromarray((~foreground).astype('uint8')*255).save(folder/'threshold.png')
    del foreground
    encoded=base64.b64encode((folder/'threshold.png').read_bytes()).decode('ascii')
    source=folder/'embedded.svg';raw=folder/'trace.raw.svg';plain=folder/'trace.paths.svg'
    source.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{gray.width}" height="{gray.height}" viewBox="0 0 {gray.width} {gray.height}">'
        f'<image id="raster" width="{gray.width}" height="{gray.height}" '
        f'xlink:href="data:image/png;base64,{encoded}"/></svg>',encoding='utf-8')
    actions='select-by-id:raster;object-trace:2,false,true,true,0,1.0,0.2;select-clear;select-by-id:raster;delete;export-do'
    argv=[cap['executable'],str(source.resolve()),'--batch-process','--actions='+actions,
          '--export-plain-svg','--export-type=svg','--export-filename='+str(raw.resolve())]
    (folder/'command.json').write_text(json.dumps({'argv':argv,'version':cap['version']},indent=2),encoding='utf-8')
    try: log=run(argv,300)
    except Exception as exc:
        (folder/'inkscape.log').write_text(str(exc),encoding='utf-8');raise
    (folder/'inkscape.log').write_text(log,encoding='utf-8')
    root=SafeXML.parse(raw).getroot()
    for child in list(root):
        if child.tag.split('}')[-1]=='defs' and len(child)==0: root.remove(child)
    tags=[node.tag.split('}')[-1] for node in root.iter()]
    if 'image' in tags or 'path' not in tags: raise ValueError('Native trace did not produce raster-free paths')
    # Only the known empty authoring defs is removed; unsupported geometry stays fail-closed.
    XML.ElementTree(root).write(plain,encoding='utf-8',xml_declaration=True)
    design=read_svg(plain,width_mm,max(simplify_mm,.005))
    before=design.geometry.area
    kept=[poly for poly in polygons(design.geometry) if poly.area>=min_area_mm2]
    design.geometry=clean(unary_union(kept).simplify(simplify_mm,preserve_topology=True))
    design.metadata.update(backend='inkscape-object-trace',version=cap['version'],threshold=threshold,
        invert=invert,denoise=denoise,background=background,min_area_mm2=min_area_mm2,simplify_mm=simplify_mm,
        area_before_filter_mm2=before,area_removed_mm2=before-design.geometry.area,
        original_size_pixels=list(original_size),size_pixels=[gray.width,gray.height],max_pixels=max_pixels,
        width_mm=width_mm,trace_directory=str(folder.resolve()))
    return design
