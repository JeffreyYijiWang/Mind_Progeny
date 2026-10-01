"""Generate matched 100-seed EMA grids without resuming training."""
import gc
import os
from pathlib import Path
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--latest-only', action='store_true')
    cli = parser.parse_args()
    import torch
    from PIL import Image, ImageDraw, ImageFont
    from neo_r3gan.checkpoints import Checkpoints, RunLock
    from neo_r3gan.config import config_hash, load_config
    from neo_r3gan.io_utils import sha256, safe_child, write_json
    from neo_r3gan.upstream import require_pins, code_version, networks_and_loss

    run = ROOT / 'workspace/experiments/neohuman-local-002-24h'
    config = load_config(run / 'config.json')
    require_pins()
    output = ROOT / 'workspace/exports' / ('checkpoint-grids-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True)
    records, grids = [], []
    with RunLock(run):
        manager = Checkpoints(run, run)
        entries = manager.manifest()['entries']
        latest_path, latest = manager.latest()
        selections = [(str(target), min(entries, key=lambda e: (abs(e['step'] - target), e['step'])))
                      for target in (5000, 10000, 20000)] + [('latest', latest)]
        if cli.latest_only:
            selections = [('latest', latest)]
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; no automatic training or CPU fallback.')
        free, total = torch.cuda.mem_get_info()
        limit = min(total * 0.75, free - 1024**3)
        if limit < 1024**3:
            raise RuntimeError('Insufficient free GPU memory for inference with headroom.')
        torch.cuda.set_per_process_memory_fraction(limit / total, 0)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.use_deterministic_algorithms(True)
        Generator, _, _ = networks_and_loss()
        model = config['model']
        for requested, entry in selections:
            checkpoint = safe_child(run, entry['path'])
            if checkpoint.stat().st_size != entry['bytes'] or sha256(checkpoint) != entry['sha256']:
                raise RuntimeError('Checkpoint verification failed: ' + str(checkpoint))
            state = torch.load(checkpoint, map_location='cpu', weights_only=True)
            if state['code'] != code_version() or state['config_sha256'] != config_hash(config) or state['config'] != config:
                raise RuntimeError('Checkpoint software or configuration mismatch.')
            if state['counters']['step'] != entry['step']:
                raise RuntimeError('Checkpoint step differs from manifest.')
            generator = Generator(NoiseDimension=model['noise_dim'], WidthPerStage=model['widths'],
                                  BlocksPerStage=model['blocks'], CardinalityPerStage=model['cardinalities'],
                                  ExpansionFactor=model['expansion']).eval().requires_grad_(False)
            generator.load_state_dict(state['G_ema'], strict=True)
            del state
            generator.to('cuda')
            folder = output / f"step-{entry['step']:09d}"
            folder.mkdir()
            size = config['dataset']['resolution']
            canvas = Image.new('RGB', (10 * size, 10 * size), 'white')
            print(f"Requested {requested}: generating step {entry['step']} ({entry['training_seconds']/3600:.4f} h)", flush=True)
            with torch.inference_mode():
                for seed in range(100):
                    noise = torch.randn(1, model['noise_dim'], generator=torch.Generator(device='cpu').manual_seed(seed))
                    pixels = ((generator(noise.to('cuda'))[0].float() + 1) * 127.5).round().clamp(0, 255).byte()
                    image = Image.fromarray(pixels.permute(1, 2, 0).cpu().numpy())
                    image.save(folder / f'seed-{seed:03d}.png')
                    canvas.paste(image, ((seed % 10) * size, (seed // 10) * size))
            grid_path = output / f"grid-step-{entry['step']:09d}.png"
            canvas.save(grid_path)
            grids.append(canvas)
            records.append({'requested_step': requested, 'actual_step': entry['step'],
                            'training_hours': entry['training_seconds'] / 3600,
                            'checkpoint': str(checkpoint), 'checkpoint_sha256': entry['sha256'],
                            'grid': grid_path.name, 'images': folder.name})
            print('Saved:', grid_path, flush=True)
            del generator
            gc.collect()
            torch.cuda.empty_cache()
        write_json(output / 'generation.json', {'experiment': config['experiment_id'], 'records': records,
                   'seeds': list(range(100)), 'seed_layout': 'row-major: row 1 = seeds 0..9',
                   'weights': 'G_ema', 'device': torch.cuda.get_device_name(0), 'torch': str(torch.__version__),
                   'image_resolution': size, 'grid_shape': [10, 10], 'training_resumed': False})
    # Add a labelled overview without changing the four full-resolution grids.
    width = grids[0].width
    header = 60
    overview = Image.new('RGB', (width * min(2, len(grids)), (width + header) * ((len(grids) + 1) // 2)), 'white')
    draw = ImageDraw.Draw(overview)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 30)
    except OSError:
        font = ImageFont.load_default()
    for i, (grid, record) in enumerate(zip(grids, records)):
        x, y = (i % 2) * width, (i // 2) * (width + header)
        draw.text((x + 12, y + 12), f"Step {record['actual_step']:,} | {record['training_hours']:.2f} h | seeds 0-99", font=font, fill='black')
        overview.paste(grid, (x, y + header))
    overview.save(output / 'comparison.png')
    with zipfile.ZipFile(output / f'all-{len(records) * 100}-images-and-grids.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.relative_to(output))
    print('COMPLETE:', output, flush=True)


if __name__ == '__main__':
    main()
