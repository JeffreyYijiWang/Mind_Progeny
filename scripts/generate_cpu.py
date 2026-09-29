"""Read a verified CUDA training checkpoint and generate EMA images on CPU only.

Kept outside neo_r3gan so existing training checkpoints retain their code identity.
No training, optimizer restoration, CUDA tensor allocation, or writer-lock changes.
"""
from pathlib import Path
import tempfile
import uuid

import torch
from PIL import Image
from neo_r3gan.checkpoints import Checkpoints
from neo_r3gan.config import config_hash, load_config
from neo_r3gan.data import grid
from neo_r3gan.io_utils import atomic_write, verified_copy, write_json
from neo_r3gan.upstream import code_version, networks_and_loss, require_pins


def generate_cpu(project, experiment_id, seeds=range(4)):
    seeds = list(seeds)
    if not seeds or len(seeds) > 256 or any(type(s) is not int or not 0 <= s < 2**63 for s in seeds):
        raise ValueError("Use 1..256 integer seeds, each in 0..2**63-1")
    if len(seeds) != len(set(seeds)):
        raise ValueError("Use distinct seeds for distinct output filenames")
    project = Path(project)
    if Path(experiment_id).name != experiment_id or experiment_id in ("", ".", "..") or "\\" in experiment_id:
        raise ValueError("Use the experiment folder name, not a path")
    run = project / "experiments" / experiment_id
    config = load_config(run / "config.json")
    if config["experiment_id"] != experiment_id:
        raise ValueError("Saved configuration belongs to a different experiment")
    require_pins()
    checkpoint, entry = Checkpoints(run, run).latest()
    # Copy before loading so subsequent retention by another runtime cannot
    # remove the file we are reading. No training files are written here.
    with tempfile.TemporaryDirectory(prefix="neohuman-cpu-") as temporary:
        snapshot = Path(temporary) / checkpoint.name
        if verified_copy(checkpoint, snapshot) != entry["sha256"]:
            raise ValueError("Checkpoint changed while copying; retry")
        state = torch.load(snapshot, map_location="cpu", weights_only=True)
    if state["schema"] != 1 or state["code"] != code_version() or state["config_sha256"] != config_hash(config) or state["config"] != config:
        raise ValueError("Checkpoint/config/software mismatch; use the original software package")
    for key in ("step", "training_seconds"):
        if state["counters"][key] != entry[key]:
            raise ValueError("Checkpoint counters differ from its manifest")
    Generator, _, _ = networks_and_loss()
    model = config["model"]
    # Preserve the notebook's CPU random stream; no CUDA RNG is inspected.
    with torch.random.fork_rng(devices=[]):
        generator = Generator(
            NoiseDimension=model["noise_dim"], WidthPerStage=model["widths"],
            BlocksPerStage=model["blocks"], CardinalityPerStage=model["cardinalities"],
            ExpansionFactor=model["expansion"],
        ).to("cpu").eval().requires_grad_(False)
    generator.load_state_dict(state["G_ema"], strict=True)
    del state
    output = run / "generated" / f"cpu-step-{entry['step']:09d}-{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=False)
    print(f"Loaded step {entry['step']} / {entry['training_seconds']/3600:.4f} saved training hours. Generating on CPU.", flush=True)
    paths, images = [], []
    with torch.inference_mode():
        for index, seed in enumerate(seeds, 1):
            noise = torch.randn(1, model["noise_dim"], generator=torch.Generator(device="cpu").manual_seed(seed), device="cpu")
            pixels = ((generator(noise)[0].float() + 1) * 127.5).round().clamp(0, 255).byte()
            image = Image.fromarray(pixels.permute(1, 2, 0).numpy())
            path = output / f"seed-{seed:06d}.png"
            atomic_write(path, lambda f: image.save(f, format="PNG"))
            paths.append(path)
            images.append(image)
            print(f"Saved {index}/{len(seeds)}: {path.name}", flush=True)
    preview = output / "preview.png"
    canvas = grid(images, columns=min(4, len(images)))
    atomic_write(preview, lambda f: canvas.save(f, format="PNG"))
    write_json(output / "generation.json", {"device": "cpu", "torch": str(torch.__version__), "seeds": seeds, "checkpoint": entry, "code": code_version()})
    print("Images saved to:", output, flush=True)
    return {"paths": paths, "preview": preview, "output": output, "checkpoint": entry}
