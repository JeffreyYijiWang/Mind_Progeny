"""Explicit physical image sizes and tracing defaults shared by both converters.

Presets describe an image canvas, not a needle bore or a calibrated bead width.
They are starting points; the same settings need not preserve every source feature.
"""
from copy import deepcopy
from pathlib import Path
import math
from PIL import Image, ImageOps
from .geometry import read_svg
from .layout import quadrant_bounds


PRESETS = {
    'small': {'canvas_limit_mm': [25.0, 31.25], 'max_pixels': 800,
              'threshold': 128, 'denoise': 0, 'min_area_mm2': .001, 'simplify_mm': .01},
    'medium': {'canvas_limit_mm': [50.0, 62.5], 'max_pixels': 1200,
               'threshold': 128, 'denoise': 0, 'min_area_mm2': .0025, 'simplify_mm': .025},
    'large': {'canvas_limit_mm': [75.0, 93.75], 'max_pixels': 1600,
              'threshold': 128, 'denoise': 0, 'min_area_mm2': .005, 'simplify_mm': .04},
    'quadrant': {'canvas_limit_mm': None, 'max_pixels': 1600,
                 'threshold': 128, 'denoise': 0, 'min_area_mm2': .01, 'simplify_mm': .05},
}


def catalog():
    return deepcopy(PRESETS)


def usable_canvas(profile):
    fields = ('edge_margin_mm', 'centerline_margin_mm', 'holder_radius_mm')
    if profile is None or any(getattr(profile, name) is None for name in fields):
        raise ValueError('Quadrant preset needs an explicit profile with edge, centerline and holder margins')
    margin = max(getattr(profile, name) for name in fields)
    x0, y0, x1, y1 = quadrant_bounds(profile)['Q1']
    size = [x1 - x0 - 2 * margin, y1 - y0 - 2 * margin]
    if min(size) <= 0:
        raise ValueError('Margins leave no usable quadrant area')
    return size


def source_size(path, max_pixels=None):
    """Canvas aspect in the same working coordinates used by the converter."""
    path = Path(path)
    if path.suffix.lower() == '.svg':
        d = read_svg(path, width_mm=1)
        return [d.canvas[2] - d.canvas[0], d.canvas[3] - d.canvas[1]]
    with Image.open(path) as image:
        if getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Multi-page/animated input: export separate images')
        image = ImageOps.exif_transpose(image)
        if max_pixels is not None:
            image.thumbnail((max_pixels, max_pixels), Image.Resampling.LANCZOS)
        return list(image.size)


def resolve(path, name, *, profile=None, width_mm=None, overrides=None):
    """Resolve a named preset; explicit width overrides must still fit its envelope."""
    if name not in PRESETS:
        raise ValueError(f'Unknown SVG preset {name!r}; choose {", ".join(PRESETS)}')
    settings = deepcopy(PRESETS[name])
    limit = settings.pop('canvas_limit_mm')
    if name == 'quadrant':
        limit = usable_canvas(profile)
    elif profile is not None and all(getattr(profile, k) is not None
            for k in ('edge_margin_mm', 'centerline_margin_mm', 'holder_radius_mm')):
        limit = [min(a, b) for a, b in zip(limit, usable_canvas(profile))]
    overrides = dict(overrides or {})
    width_mm = overrides.pop('width_mm', width_mm)
    allowed = {'max_pixels', 'threshold', 'denoise', 'min_area_mm2', 'simplify_mm',
               'invert', 'background', 'mode'}
    if set(overrides) - allowed:
        raise ValueError(f'Unknown tracing settings: {sorted(set(overrides) - allowed)}')
    settings.update(overrides)
    pixels = settings.get('max_pixels')
    if pixels is not None and (not isinstance(pixels, int) or pixels < 16):
        raise ValueError('max_pixels must be an integer >=16')
    w, h = source_size(path, pixels)
    width = min(limit[0], limit[1] * w / h) if width_mm is None else width_mm
    if not math.isfinite(width) or width <= 0:
        raise ValueError('Set a finite positive width_mm')
    height = width * h / w
    if width > limit[0] + 1e-8 or height > limit[1] + 1e-8:
        raise ValueError(f'Explicit canvas {width:g} × {height:g} mm exceeds {name} limit {limit}')
    settings['width_mm'] = width
    metadata = {'name': name, 'canvas_limit_mm': limit, 'canvas_mm': [width, height],
                'settings': deepcopy(settings), 'aspect_policy': 'uniform fit; no crop',
                'needle_diameter_inferred': False}
    return settings, metadata
