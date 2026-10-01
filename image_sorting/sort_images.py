"""CPU-only visual features -> 2D PCA -> ShuffleSnap grid assignment."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS'):
    os.environ[key] = '2'
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import time
import uuid
import zipfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import shufflesnap

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_image(path):
    with Image.open(path) as original:
        rgba = ImageOps.exif_transpose(original).convert('RGBA')
        white = Image.new('RGBA', rgba.size, 'white')
        white.alpha_composite(rgba)
        return white.convert('RGB')


def features(paths):
    rows = []
    for path in paths:
        image = ImageOps.pad(read_image(path).convert('L'), (32, 32), color=255)
        ink = 1 - np.asarray(image, dtype=np.float64) / 255
        # Shape has more weight than absolute darkness; blank inputs stay finite.
        shape = ink / max(float(np.linalg.norm(ink)), 1e-8)
        dx, dy = np.gradient(shape)
        rows.append(np.concatenate([shape.ravel(), dx.ravel(), dy.ravel(),
                                    0.5 * ink.mean(axis=0), 0.5 * ink.mean(axis=1)]))
    return np.asarray(rows)


def embed(vectors):
    centered = vectors - vectors.mean(axis=0)
    u, singular, _ = np.linalg.svd(centered, full_matrices=False)
    points = np.zeros((len(vectors), 2), dtype=np.float64)
    used = min(2, len(singular))
    points[:, :used] = u[:, :used] * singular[:used]
    # Fix PCA sign ambiguity for repeatable orientation in the same input set.
    for axis in range(2):
        pivot = int(np.argmax(np.abs(points[:, axis])))
        if points[pivot, axis] < 0:
            points[:, axis] *= -1
        spread = float(np.ptp(points[:, axis]))
        if spread < 1e-12:
            points[:, axis] = 0.5
        else:
            points[:, axis] = (points[:, axis] - points[:, axis].min()) / spread
    variance = singular ** 2
    retained = float(variance[:2].sum() / variance.sum()) if variance.sum() > 1e-20 else 0.0
    return points, retained


def render(paths, assignment, columns, rows, tile):
    canvas = Image.new('RGB', (columns * tile, rows * tile), 'white')
    for path, cell in zip(paths, assignment):
        image = ImageOps.pad(read_image(path), (tile, tile), color='white')
        canvas.paste(image, (int(cell % columns) * tile, int(cell // columns) * tile))
    return canvas


def sort_folder(source, output, columns=10, rows=None):
    paths = sorted(source.glob('seed-*.png'))
    if not 1 <= len(paths) <= 4096:
        raise ValueError('Expected 1..4096 individual seed-*.png images (not a preassembled grid).')
    rows = rows or math.ceil(len(paths) / columns)
    if columns < 1 or rows < 1 or len(paths) > columns * rows:
        raise ValueError('The grid must have a distinct cell for every image.')
    before = {path.name: sha(path) for path in paths}
    points, variance = embed(features(paths))
    grid_points, assignment, size = shufflesnap.snap_to_grid(
        points, width=columns, height=rows, margin=0.0, num_threads=2,
        cleanup_seconds=None, polish_all_offsets=True)
    if len(set(map(int, assignment))) != len(paths) or np.any(assignment < 0) or np.any(assignment >= columns * rows):
        raise RuntimeError('Invalid grid assignment; no images will be rendered.')
    output.mkdir(parents=True, exist_ok=False)
    with Image.open(paths[0]) as first:
        tile = max(first.size)
    tile = min(tile, 512)
    canvas = render(paths, assignment, columns, rows, tile)
    canvas.save(output / 'sorted-grid.png')
    mappings = []
    for i, (path, cell) in enumerate(zip(paths, assignment)):
        mappings.append({'cell': int(cell), 'row': int(cell // columns) + 1,
                         'column': int(cell % columns) + 1, 'filename': path.name,
                         'seed': int(path.stem.split('-')[-1]), 'source_sha256': before[path.name],
                         'embedding': points[i].tolist(), 'grid_point': grid_points[i].tolist()})
    mappings.sort(key=lambda row: row['cell'])
    with (output / 'cell-map.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['row', 'column', 'seed', 'filename', 'source_sha256'], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(mappings)
    metadata = {'source': str(source), 'columns': columns, 'rows': rows, 'tile_pixels': tile,
                'shufflesnap_version': importlib.metadata.version('shufflesnap'),
                'method': '32px grayscale ink/edge/spatial features, 2D PCA, ShuffleSnap; appearance, not quality or semantic ranking',
                'pca_variance_retained': variance, 'num_threads': 2, 'margin': 0.0,
                'cells': mappings}
    (output / 'sort.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    if before != {path.name: sha(path) for path in paths}:
        raise RuntimeError('A source image changed during sorting.')
    print(f'Sorted {len(paths)} images from {source.name}; PCA retained {variance:.1%} variance.', flush=True)
    return paths, assignment, canvas, metadata


def comparison(canvases, titles, output):
    width = max(canvas.width for canvas in canvases)
    height = max(canvas.height for canvas in canvases)
    header = 56
    page = Image.new('RGB', (width * 2, (height + header) * math.ceil(len(canvases) / 2)), 'white')
    draw = ImageDraw.Draw(page)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 26)
    except OSError:
        font = ImageFont.load_default()
    for i, (canvas, title) in enumerate(zip(canvases, titles)):
        x, y = (i % 2) * width, (i // 2) * (height + header)
        draw.text((x + 12, y + 12), title, font=font, fill='black')
        page.paste(canvas, (x, y + header))
    page.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input', type=Path, help='Folder containing individual seed-*.png files')
    group.add_argument('--comparison', type=Path, help='Checkpoint export folder containing generation.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--columns', type=int, default=10)
    parser.add_argument('--rows', type=int)
    args = parser.parse_args()
    if args.columns < 1 or (args.rows is not None and args.rows < 1):
        parser.error('Grid dimensions must be positive.')
    if importlib.metadata.version('shufflesnap') != '0.3.0':
        raise RuntimeError('Install pinned ShuffleSnap 0.3.0; its coordinate API differs from unreleased main.')
    output = (args.output or ROOT / 'workspace/exports' / ('shufflesnap-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])).resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory; existing results are never overwritten.')
    if args.input:
        sort_folder(args.input.resolve(), output, args.columns, args.rows)
    else:
        source = args.comparison.resolve()
        metadata = json.loads((source / 'generation.json').read_text())
        results, titles = [], []
        output.mkdir(parents=True)
        for record in metadata['records']:
            folder = (source / record['images']).resolve()
            if not folder.is_relative_to(source):
                raise ValueError('Image folder must remain inside the source export.')
            result = sort_folder(folder, output / folder.name, args.columns, args.rows)
            results.append(result)
            titles.append(f"Step {record['actual_step']:,} | independently sorted")
        comparison([r[2] for r in results], titles, output / 'sorted-comparison.png')
        # Latest-checkpoint arrangement reused by filename keeps seed correspondence.
        anchor_paths, anchor_assignment, _, anchor_meta = results[-1]
        anchor = {path.name: int(cell) for path, cell in zip(anchor_paths, anchor_assignment)}
        aligned = []
        for (paths, _, _, meta), record in zip(results, metadata['records']):
            if set(p.name for p in paths) != set(anchor):
                raise ValueError('Matched comparison requires the same seed filenames in every set.')
            canvas = render(paths, [anchor[p.name] for p in paths], anchor_meta['columns'], anchor_meta['rows'], anchor_meta['tile_pixels'])
            canvas.save(output / record['images'] / 'matched-seeds-grid.png')
            aligned.append(canvas)
        comparison(aligned, [f"Step {r['actual_step']:,} | latest layout, matching seeds" for r in metadata['records']],
                   output / 'matched-seed-comparison.png')
        (output / 'matched-seed-layout.json').write_text(json.dumps(anchor, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(output / 'sorted-grids-and-maps.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                z.write(path, path.relative_to(output))
    print('COMPLETE:', output, flush=True)


if __name__ == '__main__':
    main()
