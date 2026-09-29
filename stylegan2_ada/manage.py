"""Prepare, inspect, then manually launch an isolated 256px or 1024px ADA experiment."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor/stylegan2-ada-pytorch"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def local(value):
    return (ROOT / value).resolve()


def config(profile="1024"):
    if str(profile) not in ("256", "1024"):
        raise ValueError("Choose profile 256 or 1024.")
    cfg = read(ROOT / ("config-256.json" if str(profile) == "256" else "config.json"))
    from gpu_policy import validate
    validate(cfg["gpu"])
    if cfg["resolution"] != int(profile) or cfg["expected_images"] != 45:
        raise ValueError("Resolution must match the selected profile, with 45 images.")
    expected_batch = (4, 8) if int(profile) == 256 else (1, 4)
    if (cfg["microbatch"], cfg["effective_batch"]) != expected_batch:
        raise ValueError(f"This profile requires microbatch/effective batch {expected_batch}.")
    if not isinstance(cfg["total_kimg"], int) or cfg["total_kimg"] < 1:
        raise ValueError("total_kimg must be a positive integer (thousands of image presentations).")
    if cfg["snapshot_kimg"] != 1 or cfg["preview_images"] != 4:
        raise ValueError("The validated preview/snapshot configuration is 4 images, every 1 kimg.")
    if cfg["backend"] != "pytorch-reference" or cfg["required_predecessor_hours"] != 24:
        raise ValueError("Keep the prepared reference backend and 24-hour predecessor guard.")
    return cfg


def weights_url(cfg):
    lock = read(ROOT / "upstream-lock.json")
    return lock["weights_url_256" if cfg["resolution"] == 256 else "weights_url"]


def check_source():
    lock = read(ROOT / "upstream-lock.json")
    actual = subprocess.check_output(["git", "-C", str(VENDOR), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(VENDOR), "status", "--porcelain", "--untracked-files=no"], text=True)
    if actual != lock["commit"] or dirty.strip():
        raise RuntimeError("NVIDIA checkout must match the unmodified pinned commit.")
    return lock


def fetch(cfg):
    lock = read(ROOT / "upstream-lock.json")
    if not VENDOR.exists():
        VENDOR.parent.mkdir(parents=True, exist_ok=True)
        git = ["git"] + (["-c", "http.sslBackend=schannel"] if os.name == "nt" else [])
        subprocess.run(git + ["clone", lock["repository"], str(VENDOR)], check=True)
        subprocess.run(["git", "-C", str(VENDOR), "checkout", "--detach", lock["commit"]], check=True)
    check_source()
    target = local(cfg["pretrained"])
    receipt = target.with_suffix(".json")
    if target.exists() and receipt.exists():
        verify_pretrained(cfg)
        print("Pinned source and downloaded weight checksum verified; no model loaded.")
        return
    if target.exists():
        raise RuntimeError("Weights exist without a download receipt; refusing to trust them automatically.")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".partial")
    print(f"Downloading NVIDIA's FFHQ {cfg['resolution']}px transfer-learning source (not executing it)...", flush=True)
    with urllib.request.urlopen(weights_url(cfg), timeout=120) as response, tmp.open("wb") as f:
        total = 0
        while chunk := response.read(4 * 1024 * 1024):
            f.write(chunk)
            total += len(chunk)
        expected = response.headers.get("Content-Length")
        if expected and total != int(expected):
            raise IOError("Incomplete pretrained weight download.")
    if total < 50_000_000:
        raise IOError("Unexpectedly small pretrained download; it was not published as a model.")
    digest = sha(tmp)
    tmp.replace(target)
    write(receipt, {"url": weights_url(cfg), "sha256": digest, "bytes": total,
                    "downloaded_at": time.time(), "checksum_origin": "local download receipt, not publisher signature"})
    print(f"Downloaded {total:,} bytes; SHA256 {digest}. No pickle/model was loaded.")


def verify_pretrained(cfg):
    target = local(cfg["pretrained"])
    receipt = read(target.with_suffix(".json"))
    if receipt["url"] != weights_url(cfg):
        raise ValueError("Pretrained source does not match the pinned NVIDIA URL.")
    if target.stat().st_size != receipt["bytes"] or sha(target) != receipt["sha256"]:
        raise IOError("Pretrained weight checksum failed.")
    return target


def prepare(cfg):
    from PIL import Image, ImageOps, ImageDraw
    resolution = cfg["resolution"]
    source = local(cfg["original_zip"])
    if sha(source) != cfg["original_sha256"]:
        raise IOError("Original dataset checksum does not match the approved 45-image archive.")
    target = local(cfg["dataset"])
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        validate_data(cfg)
        legacy_contact = target.parent / "contact-sheet.jpg"
        contact_path = target.parent / f"contact-sheet-{resolution}.jpg"
        if resolution == 1024 and not contact_path.exists() and legacy_contact.exists():
            shutil.copyfile(legacy_contact, contact_path)
        print(f"Existing 45-image {resolution}px dataset verified.")
        return
    rows = []
    contact = Image.new("RGB", (9 * 144, 5 * 164), "white")
    draw = ImageDraw.Draw(contact)
    tmp = target.with_suffix(".partial")
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as dst:
        names = sorted(n for n in src.namelist() if not n.endswith("/") and Path(n).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"} and not n.startswith("__MACOSX/"))
        if len(names) != cfg["expected_images"]:
            raise ValueError(f"Expected 45 images, found {len(names)}.")
        for i, name in enumerate(names):
            raw = src.read(name)
            with Image.open(io.BytesIO(raw)) as opened:
                source_size = list(opened.size)
                im = ImageOps.exif_transpose(opened).convert("RGBA")
                oriented_size = list(im.size)
                background = Image.new("RGBA", im.size, "white")
                background.alpha_composite(im)
                rgb = background.convert("RGB")
                scaled = ImageOps.contain(rgb, (resolution, resolution), Image.Resampling.LANCZOS)
                padded = Image.new("RGB", (resolution, resolution), "white")
                padded.paste(scaled, ((resolution - scaled.width) // 2, (resolution - scaled.height) // 2))
                buffer = io.BytesIO()
                padded.save(buffer, format="PNG")
                member = f"img{i:05d}.png"
                dst.writestr(member, buffer.getvalue())
                rows.append({"source": name, "source_sha256": hashlib.sha256(raw).hexdigest(),
                             "original_size": source_size, "oriented_size": oriented_size,
                             "resized_content_size": list(scaled.size), "upscaled": max(oriented_size) < resolution,
                             "prepared": member, "prepared_sha256": hashlib.sha256(buffer.getvalue()).hexdigest()})
                contact.paste(padded.resize((140, 140)), ((i % 9) * 144 + 2, (i // 9) * 164))
                draw.text(((i % 9) * 144 + 4, (i // 9) * 164 + 142), f"{i + 1:02d}: {source_size[0]}x{source_size[1]}", fill="black")
        dst.writestr("dataset.json", json.dumps({"labels": None}))
    tmp.replace(target)
    contact.save(target.parent / f"contact-sheet-{resolution}.jpg", quality=90)
    write(target.with_suffix(".json"), {"source_sha256": cfg["original_sha256"], "dataset_sha256": sha(target),
          "resolution": resolution, "count": len(rows), "transform": "EXIF orientation; white alpha composite; Lanczos fit; centered white padding; no crop",
          "upscaled_count": sum(r["upscaled"] for r in rows), "images": rows})
    validate_data(cfg)
    print(f"Prepared all {len(rows)} originals at {resolution}x{resolution}; {sum(r['upscaled'] for r in rows)} upscaled.")


def validate_data(cfg):
    from PIL import Image
    target = local(cfg["dataset"])
    manifest = read(target.with_suffix(".json"))
    if manifest["resolution"] != cfg["resolution"]:
        raise ValueError("Dataset resolution does not match the selected profile.")
    if manifest["source_sha256"] != cfg["original_sha256"] or sha(target) != manifest["dataset_sha256"]:
        raise IOError("Dataset checksum mismatch.")
    with zipfile.ZipFile(target) as archive:
        names = [n for n in archive.namelist() if n.endswith(".png")]
        if len(names) != 45 or len(manifest["images"]) != 45:
            raise ValueError("Expected exactly 45 prepared images.")
        for row in manifest["images"]:
            raw = archive.read(row["prepared"])
            if hashlib.sha256(raw).hexdigest() != row["prepared_sha256"]:
                raise IOError("Image checksum mismatch.")
            with Image.open(io.BytesIO(raw)) as im:
                if im.size != (cfg["resolution"], cfg["resolution"]) or im.mode != "RGB":
                    raise ValueError("Prepared image must match the selected RGB resolution.")
                im.verify()
    return manifest


def predecessor_status(cfg):
    run = local(cfg["predecessor"])
    if (run / "writer.lock").exists():
        return False, "The original R3GAN still has a writer lock. Leave it running."
    try:
        envelope = read(run / "manifest.json")
        manifest = envelope["manifest"]
        if canonical_sha(manifest) != envelope["sha256"]:
            return False, "Original R3GAN checkpoint manifest checksum failed."
        budget = max(24 * 3600, read(run / "config.json")["schedule"]["budget_seconds"])
        for entry in reversed(manifest["entries"]):
            if entry["training_seconds"] < budget:
                continue
            checkpoint = (run / entry["path"]).resolve()
            if not checkpoint.is_relative_to(run) or checkpoint.stat().st_size != entry["bytes"]:
                continue
            if sha(checkpoint) == entry["sha256"]:
                return True, f"Original R3GAN completed {entry['training_seconds'] / 3600:.4f} training hours; checkpoint verified."
        return False, "Original R3GAN has not saved a verified checkpoint completing its 24-hour budget."
    except (OSError, KeyError, ValueError) as exc:
        return False, f"Could not verify predecessor completion: {exc}"


def require_predecessor(cfg):
    ready, message = predecessor_status(cfg)
    if not ready:
        raise RuntimeError(message + " New model execution is blocked; nothing was started.")
    print(message)


def upstream_args(cfg, resume=None):
    check_source()
    validate_data(cfg)
    sys.path.insert(0, str(VENDOR))
    import train as upstream_train
    from compat import install
    install()
    _, args = upstream_train.setup_training_loop_kwargs(
        gpus=1, snap=1, metrics=[], seed=cfg["seed"], data=str(local(cfg["dataset"])),
        mirror=False, cfg=f"paper{cfg['resolution']}", gamma=float(cfg["r1_gamma"]), kimg=cfg["total_kimg"],
        batch=cfg["effective_batch"], aug="ada", target=float(cfg["ada_target"]), augpipe="bg",
        resume=str(resume or local(cfg["pretrained"])), fp32=False, nobench=True, workers=1,
        allow_tf32=cfg["gpu"]["allow_tf32"], nhwc=cfg["gpu"]["fp16_channels_last"])
    args.batch_gpu = cfg["microbatch"]
    args.D_kwargs.epilogue_kwargs.mbstd_group_size = cfg["microbatch"]
    args.loss_kwargs.pl_batch_shrink = 1 if cfg["microbatch"] == 1 else 2
    args.data_loader_kwargs = dict(pin_memory=False, num_workers=0)
    args.G_opt_kwargs.foreach = args.D_opt_kwargs.foreach = False
    args.G_opt_kwargs.betas = [0.0, 0.99]
    args.D_opt_kwargs.betas = [0.0, 0.99]
    args.kimg_per_tick = cfg["snapshot_kimg"]
    # Preserve upright artwork/text. ADA uses translation and isotropic scaling.
    for key in ("xflip", "rotate90", "rotate", "aniso"):
        args.augment_kwargs[key] = 0
    return args


def plan(cfg):
    # Explicitly make this process CPU-only before importing any PyTorch code.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    args = upstream_args(cfg)
    import torch
    if torch.cuda.is_initialized():
        raise RuntimeError("CPU-only planning unexpectedly initialized CUDA.")
    weights = verify_pretrained(cfg)
    ready, message = predecessor_status(cfg)
    result = {"mode": "prepared-not-started", "model_loaded": False, "cuda_initialized": False,
              "predecessor_ready": ready, "predecessor_message": message,
              "gpu_policy": cfg["gpu"],
              "pretrained_sha256": sha(weights), "training_options": dict(args),
              "planned_optimizer_steps": cfg["total_kimg"] * 1000 // cfg["effective_batch"]}
    write(ROOT / f"data/prepared-plan-{cfg['resolution']}.json", result)
    print(json.dumps(result, indent=2))


@contextlib.contextmanager
def writer_lock():
    lock = ROOT / "writer.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError("StyleGAN2-ADA has an active or stale writer.lock; inspect before retrying.") from None
    owner = lock / "owner.json"
    write(owner, {"pid": os.getpid(), "host": socket.gethostname(), "created": time.time()})
    try:
        yield
    finally:
        owner.unlink()
        lock.rmdir()


def resolve_snapshot(value, cfg=None):
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT / "runs") or path.suffix != ".pkl":
        raise ValueError("Only a verified snapshot produced in this project's runs folder may be loaded.")
    receipt = read(path.with_suffix(".verified.json"))
    if path.stat().st_size != receipt["bytes"] or sha(path) != receipt["sha256"]:
        raise IOError("Snapshot checksum failed. Choose an earlier verified snapshot.")
    if cfg is not None and read(path.parent / "config.json")["resolution"] != cfg["resolution"]:
        raise ValueError("Snapshot belongs to a different resolution. Select the matching profile.")
    return path


def train_model(cfg, cli):
    if not cli.execute:
        raise RuntimeError("Training is opt-in: use train --execute after the original 24-hour run finishes.")
    require_predecessor(cfg)  # Before PyTorch import, model loading, or CUDA initialization.
    with writer_lock():
        resume = resolve_snapshot(cli.resume, cfg) if cli.resume else verify_pretrained(cfg)
        # Snapshot retention is intentional; reserve an estimate for the entire segment.
        estimated_disk = int(resume.stat().st_size * (cfg["total_kimg"] + 2) * 1.2)
        free_disk = shutil.disk_usage(ROOT).free
        if free_disk < estimated_disk:
            raise RuntimeError(f"About {estimated_disk / 1024**3:.1f} GiB free disk is required for this segment's snapshots; "
                               f"only {free_disk / 1024**3:.1f} GiB is available. Free space or reduce total_kimg.")
        args = upstream_args(cfg, resume)
        import torch
        from training import training_loop
        from torch_utils import training_stats
        import dnnlib
        from compat import small_preview
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU unavailable. Training was not started; CPU fallback is disabled.")
        free, total = torch.cuda.mem_get_info()
        if free < 6 * 1024**3:
            raise RuntimeError(f"Only {free / 1024**3:.2f} GiB GPU memory free. Close GPU-heavy apps before training.")
        from gpu_policy import configure, memory_status
        gpu_budget = configure(torch, cfg["gpu"])
        import psutil
        if psutil.virtual_memory().available < 4 * 1024**3:
            raise RuntimeError("Less than 4 GiB physical RAM available; close unused apps before training.")
        battery = psutil.sensors_battery()
        if battery is not None and not battery.power_plugged:
            raise RuntimeError("Connect the laptop charger before training.")
        run = ROOT / "runs" / (f"{cfg['resolution']}-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        run.mkdir(parents=True)
        args.run_dir = str(run)
        write(run / "training_options.json", dict(args))
        write(run / "config.json", cfg)
        write(run / "provenance.json", {"upstream": check_source(), "source_weights": str(resume),
              "source_weights_sha256": sha(resume), "torch": torch.__version__, "gpu": torch.cuda.get_device_name(),
              "gpu_bytes": total, "gpu_budget": gpu_budget,
              "snapshot_semantics": "network weights only; optimizer/RNG and kimg counter restart"})
        stop = ROOT / "STOP"
        stop.unlink(missing_ok=True)
        previous_handler = signal.getsignal(signal.SIGINT)

        def request_stop(*_):
            stop.write_text("Stop at next maintenance tick.\n", encoding="utf-8")
            print("Stop requested; waiting for the next maintenance tick and snapshot. Keep this window open.", flush=True)

        def progress(kimg, total_kimg):
            # Called only after upstream has closed snapshot files and flushed statistics.
            for snapshot in run.glob("network-snapshot-*.pkl"):
                stat = snapshot.stat()
                receipt = snapshot.with_suffix(".verified.json")
                old = read(receipt) if receipt.exists() else {}
                if old.get("mtime_ns") != stat.st_mtime_ns or old.get("bytes") != stat.st_size:
                    write(receipt, {"sha256": sha(snapshot), "bytes": stat.st_size,
                                    "mtime_ns": stat.st_mtime_ns, "kimg_floor": kimg})
            write(run / "status.json", {"kimg_floor": kimg, "total_kimg": total_kimg,
                                        "gpu_memory": memory_status(torch), "gpu_budget": gpu_budget,
                                        "stop_requested": stop.exists(), "updated_at": time.time()})

        signal.signal(signal.SIGINT, request_stop)
        training_loop.setup_snapshot_image_grid = small_preview
        training_stats.init_multiprocessing(rank=0, sync_device=None)
        try:
            with dnnlib.util.Logger(file_name=str(run / "log.txt"), file_mode="a", should_flush=True):
                print("8 GiB profile: fit and speed are not guaranteed. An OOM stops this run; no automatic restart.")
                training_loop.training_loop(**args, abort_fn=stop.exists, progress_fn=progress)
            write(run / "result.json", {"status": "stopped" if stop.exists() else "completed", "time": time.time()})
        except BaseException as exc:
            write(run / "result.json", {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "time": time.time()})
            raise
        finally:
            signal.signal(signal.SIGINT, previous_handler)


def generate(cfg, cli):
    if not cli.execute:
        raise RuntimeError("Generation is opt-in: add --execute after the original 24-hour run finishes.")
    require_predecessor(cfg)
    with writer_lock():
        snapshot = resolve_snapshot(cli.snapshot, cfg)
        check_source()
        sys.path.insert(0, str(VENDOR))
        import numpy as np
        import torch
        import legacy
        from PIL import Image
        from compat import install
        install()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable. This launcher requires a GPU.")
        from gpu_policy import configure
        gpu_budget = configure(torch, cfg["gpu"])
        with snapshot.open("rb") as f:
            model = legacy.load_network_pkl(f)["G_ema"].eval().requires_grad_(False).to("cuda")
        if model.img_resolution != cfg["resolution"]:
            raise ValueError("Generator resolution must match the selected profile.")
        out = ROOT / "generated" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        out.mkdir(parents=True)
        seeds = [int(x) for x in cli.seeds.split(",")]
        with torch.no_grad():
            for seed in seeds:
                z = torch.from_numpy(np.random.RandomState(seed).randn(1, model.z_dim)).to("cuda")
                image = model(z, torch.zeros((1, model.c_dim), device="cuda"), truncation_psi=cli.truncation, noise_mode="const")
                image = (image.permute(0, 2, 3, 1) * 127.5 + 128).clamp(0, 255).to(torch.uint8)[0].cpu().numpy()
                Image.fromarray(image).save(out / f"seed-{seed:06d}.png")
        write(out / "generation.json", {"snapshot": str(snapshot), "sha256": sha(snapshot), "seeds": seeds,
                                       "truncation_psi": cli.truncation, "gpu_budget": gpu_budget})
        print(f"Saved {len(seeds)} native {cfg['resolution']}x{cfg['resolution']} PNGs to {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("256", "1024"), default="1024")
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "prepare", "plan", "status", "stop"):
        subs.add_parser(name)
    train = subs.add_parser("train")
    train.add_argument("--execute", action="store_true")
    train.add_argument("--resume", help="Own verified .pkl snapshot; starts a new segment with fresh optimizer and counters")
    gen = subs.add_parser("generate")
    gen.add_argument("--execute", action="store_true")
    gen.add_argument("--snapshot", required=True)
    gen.add_argument("--seeds", default="0,1,2,3")
    gen.add_argument("--truncation", type=float, default=0.7)
    cli = parser.parse_args()
    cfg = config(cli.profile)
    if cli.command in ("fetch", "prepare", "plan"):
        globals()[cli.command](cfg)
    elif cli.command == "status":
        ready, message = predecessor_status(cfg)
        print(message)
        print("New model: " + ("writer lock present" if (ROOT / "writer.lock").exists() else "no writer lock"))
        print("Manual launch eligible: " + str(ready))
    elif cli.command == "stop":
        if (ROOT / "writer.lock").exists():
            (ROOT / "STOP").write_text("Requested by user\n", encoding="utf-8")
            print("Stop requested. Keep the training window open until it saves and exits.")
        else:
            print("No StyleGAN2-ADA writer lock; no stop request needed.")
    elif cli.command == "train":
        train_model(cfg, cli)
    elif cli.command == "generate":
        generate(cfg, cli)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        sys.exit(1)
