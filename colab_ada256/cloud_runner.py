"""Separate Google Colab runner. Nothing executes a model without --execute."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
COMMIT = "d72cc7d041b42ec8e806021a205ed9349f87c6a4"
WEIGHTS_URL = "https://nvlabs-fi-cdn.nvidia.com/stylegan2-ada-pytorch/pretrained/transfer-learning-source-nets/ffhq-res256-mirror-paper256-noaug.pkl"
WEIGHTS_SHA = "7aa4ddeee38e007ce92a1a0bccd386fc6abba6b5c8692bdbe813d3f1987c0722"
DATA_SHA = "94e0779302dc87b9e6a1b4dab009ab7a5f091cb584896b1527d791b08f76ec96"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def verified_copy(source, target):
    source, target = Path(source), Path(target)
    digest = sha(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha(target) == digest:
        return digest
    tmp = target.with_name(target.name + "." + uuid.uuid4().hex + ".partial")
    shutil.copyfile(source, tmp)
    if sha(tmp) != digest:
        raise IOError("Copy verification failed; previous files were retained.")
    tmp.replace(target)
    if sha(target) != digest:
        raise IOError("Final copy verification failed.")
    return digest


def verify_inputs():
    from PIL import Image
    archive = HERE / "neohuman45-256.zip"
    if sha(archive) != DATA_SHA:
        raise IOError("The embedded 45-image dataset checksum failed.")
    with zipfile.ZipFile(archive) as z:
        images = [n for n in z.namelist() if n.endswith(".png")]
        if len(images) != 45:
            raise ValueError("Expected 45 images.")
        for name in images:
            with z.open(name) as f, Image.open(f) as im:
                if im.size != (256, 256) or im.mode != "RGB":
                    raise ValueError("Expected 256x256 RGB images.")
                im.verify()
    weights = HERE / "ffhq256.pkl"
    if sha(weights) != WEIGHTS_SHA:
        raise IOError("NVIDIA starting weights checksum failed.")
    vendor = HERE / "vendor"
    if subprocess.check_output(["git", "-C", str(vendor), "rev-parse", "HEAD"], text=True).strip() != COMMIT:
        raise RuntimeError("Incorrect NVIDIA source commit.")
    if subprocess.check_output(["git", "-C", str(vendor), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise RuntimeError("NVIDIA vendor source was modified.")


def options(cfg, resume=None):
    if cfg["total_kimg"] < 1 or not isinstance(cfg["total_kimg"], int):
        raise ValueError("total_kimg must be a positive integer.")
    if cfg["microbatch"] not in (1, 2, 4) or 8 % cfg["microbatch"]:
        raise ValueError("Choose microbatch 1, 2 or 4; effective batch stays 8.")
    if not 0 < cfg["session_hours"] <= 24:
        raise ValueError("session_hours must be greater than zero and at most 24.")
    verify_inputs()
    sys.path.insert(0, str(HERE / "vendor"))
    import train
    from compat import install
    install()
    _, args = train.setup_training_loop_kwargs(
        gpus=1, data=str(HERE / "neohuman45-256.zip"), cfg="paper256", gamma=1.0,
        batch=8, kimg=cfg["total_kimg"], snap=1, metrics=[], seed=2026, mirror=False,
        aug="ada", target=0.6, augpipe="bg", resume=str(resume or HERE / "ffhq256.pkl"),
        fp32=False, nhwc=True, allow_tf32=True, nobench=True, workers=1)
    args.batch_gpu = cfg["microbatch"]
    args.D_kwargs.epilogue_kwargs.mbstd_group_size = cfg["microbatch"]
    args.loss_kwargs.pl_batch_shrink = 1 if cfg["microbatch"] == 1 else 2
    args.data_loader_kwargs = dict(num_workers=0, pin_memory=False)
    args.G_opt_kwargs.foreach = args.D_opt_kwargs.foreach = False
    args.G_opt_kwargs.betas = [0.0, 0.99]
    args.D_opt_kwargs.betas = [0.0, 0.99]
    args.kimg_per_tick = 1
    for name in ("xflip", "rotate90", "rotate", "aniso"):
        args.augment_kwargs[name] = 0
    return args


def require_cloud(project):
    # Keep this separate cloud workflow from becoming a bypass of local launch guards.
    if not Path("/content").is_dir() or not Path("/content/drive/MyDrive").is_dir():
        raise RuntimeError("Use a Google Colab hosted runtime and mount Google Drive first.")
    project = Path(project).resolve()
    if not project.is_relative_to(Path("/content/drive/MyDrive")):
        raise ValueError("Project must be inside mounted MyDrive.")
    return project


@contextlib.contextmanager
def lock(project):
    folder = project / "writer.lock"
    project.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir()
    except FileExistsError:
        raise RuntimeError("An active or stale Colab writer lock exists. Use the notebook's explicit lock recovery cell only after stopping the old runtime.") from None
    token = uuid.uuid4().hex
    write(folder / "owner.json", {"token": token, "host": socket.gethostname(), "pid": os.getpid(), "created": time.time()})
    try:
        yield
    finally:
        if read(folder / "owner.json")["token"] != token:
            raise RuntimeError("Writer lock changed; refusing cleanup.")
        (folder / "owner.json").unlink()
        folder.rmdir()


def release_lock(project, token, confirmation):
    if confirmation != "I stopped the old Colab runtime":
        raise ValueError("Explicit confirmation is required; never release a live writer's lock.")
    owner_path = project / "writer.lock/owner.json"
    owner = read(owner_path)
    if owner["token"] != token:
        raise ValueError("Lock owner changed; inspect again.")
    if owner["host"] == socket.gethostname():
        import psutil
        if psutil.pid_exists(owner["pid"]):
            raise RuntimeError("The old writer PID is still alive in this runtime.")
    owner_path.unlink()
    owner_path.parent.rmdir()


def verified_snapshot(project, value):
    path = Path(value).resolve()
    if not path.is_relative_to(project / "runs") or path.suffix != ".pkl":
        raise ValueError("Choose a snapshot from this separate ADA256 Drive project.")
    receipt = read(path.with_suffix(".verified.json"))
    if receipt["resolution"] != 256 or path.stat().st_size != receipt["bytes"] or sha(path) != receipt["sha256"]:
        raise IOError("Snapshot verification failed. Choose an earlier verified snapshot.")
    return path


def publish_snapshots(local_run, drive_run):
    published = []
    for source in sorted(local_run.glob("network-snapshot-*.pkl")):
        digest = sha(source)
        target = drive_run / (source.stem + "-" + digest[:12] + ".pkl")
        receipt = target.with_suffix(".verified.json")
        if not receipt.exists():
            verified_copy(source, target)
            kimg = int(source.stem.rsplit("-", 1)[1])
            write(receipt, {"sha256": digest, "bytes": target.stat().st_size, "resolution": 256,
                            "kimg_floor": kimg, "created": time.time(), "state": "network weights only"})
        elif not target.exists() or sha(target) != digest or read(receipt)["sha256"] != digest:
            raise IOError("Previously published snapshot no longer verifies; local files were retained.")
        published.append(target)
    # Retain the latest four plus every 10-kimg milestone, separately per segment.
    receipts = sorted(drive_run.glob("*.verified.json"), key=lambda p: read(p)["created"])
    for receipt in receipts[:-4]:
        metadata = read(receipt)
        if metadata["kimg_floor"] > 0 and metadata["kimg_floor"] % 10 == 0:
            continue
        model = receipt.with_name(receipt.name.replace(".verified.json", ".pkl"))
        model.unlink(missing_ok=True)
        receipt.unlink()
    # All candidates above have now been verified on Drive. Keep two locally.
    for old in sorted(local_run.glob("network-snapshot-*.pkl"))[:-2]:
        old.unlink()
    for pattern in ("fakes*.png", "reals.png", "stats.jsonl", "log.txt"):
        for source in local_run.glob(pattern):
            # Logs may be open; they are informational, not recovery checkpoints.
            shutil.copyfile(source, drive_run / source.name)
    return published


def train_model(project, cfg, execute, resume=None):
    if not execute:
        raise RuntimeError("Training is off; --execute is required.")
    project = require_cloud(project)
    with lock(project):
        selected = verified_snapshot(project, resume) if resume else HERE / "ffhq256.pkl"
        local_weights = HERE / "resume.pkl" if resume else selected
        if resume:
            verified_copy(selected, local_weights)
        args = options(cfg, local_weights)
        import torch
        import dnnlib
        from training import training_loop
        from torch_utils import training_stats
        from compat import small_preview
        from gpu_policy import configure, memory_status
        if not torch.cuda.is_available():
            raise RuntimeError("No NVIDIA CUDA GPU. Select a GPU runtime; CPU training fallback is disabled.")
        gpu_budget = configure(torch, cfg["gpu"])
        name = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        local_run = HERE / "runs" / name
        drive_run = project / "runs" / name
        local_run.mkdir(parents=True)
        drive_run.mkdir(parents=True)
        args.run_dir = str(local_run)
        for folder in (local_run, drive_run):
            write(folder / "config.json", cfg)
            write(folder / "training_options.json", dict(args))
            write(folder / "provenance.json", {"commit": COMMIT, "dataset_sha256": DATA_SHA,
                  "source_weights": str(selected), "source_weights_sha256": sha(local_weights),
                  "gpu": torch.cuda.get_device_name(0), "gpu_budget": gpu_budget,
                  "torch": torch.__version__, "snapshot_semantics": "weights only; optimizer, ADA and counters restart"})
        stop = project / "STOP"
        if stop.exists():
            raise RuntimeError("STOP is present. Remove it with the notebook's explicit clear-stop option before starting.")
        started = time.monotonic()
        stopped_for = []

        def request_stop(*_):
            stop.write_text("Manual stop requested\n", encoding="utf-8")
            print("Stop requested. Waiting for the next tick and verified Drive snapshot.", flush=True)

        def abort():
            if stop.exists():
                stopped_for[:] = ["manual"]
            elif time.monotonic() - started >= cfg["session_hours"] * 3600:
                stopped_for[:] = ["session time limit"]
            return bool(stopped_for)

        def progress(kimg, total_kimg):
            published = publish_snapshots(local_run, drive_run)
            write(drive_run / "status.json", {"kimg_floor": kimg, "total_kimg": total_kimg,
                  "elapsed_wall_hours": (time.monotonic() - started) / 3600,
                  "gpu_memory": memory_status(torch), "updated": time.time()})
            if published:
                print("Verified on Drive:", published[-1], flush=True)

        previous = signal.signal(signal.SIGINT, request_stop)
        training_loop.setup_snapshot_image_grid = small_preview
        training_stats.init_multiprocessing(rank=0, sync_device=None)
        try:
            with dnnlib.util.Logger(file_name=str(local_run / "log.txt"), file_mode="a", should_flush=True):
                print("Drive output:", drive_run, flush=True)
                training_loop.training_loop(**args, abort_fn=abort, progress_fn=progress)
            write(drive_run / "result.json", {"status": "stopped" if stopped_for else "completed", "reason": stopped_for})
        except BaseException as exc:
            write(drive_run / "result.json", {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            raise
        finally:
            signal.signal(signal.SIGINT, previous)


def generate(project, cfg, execute, snapshot, seeds, device):
    if not execute:
        raise RuntimeError("Generation is off; --execute is required.")
    project = require_cloud(project)
    with lock(project):
        source = verified_snapshot(project, snapshot)
        verify_inputs()
        verified_copy(source, HERE / "generate.pkl")
        sys.path.insert(0, str(HERE / "vendor"))
        import legacy
        import numpy as np
        import torch
        from PIL import Image
        from compat import install
        from gpu_policy import configure
        install()
        if device == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("No CUDA GPU; select CPU generation explicitly if needed.")
            configure(torch, cfg["gpu"])
        with (HERE / "generate.pkl").open("rb") as f:
            model = legacy.load_network_pkl(f)["G_ema"].eval().requires_grad_(False).to(device)
        if model.img_resolution != 256:
            raise ValueError("Expected a 256px generator.")
        out = project / "generated" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        out.mkdir(parents=True)
        with torch.no_grad():
            for seed in seeds:
                z = torch.from_numpy(np.random.RandomState(seed).randn(1, model.z_dim)).to(device)
                label = torch.zeros((1, model.c_dim), device=device)
                pixels = model(z, label, truncation_psi=0.7, noise_mode="const", force_fp32=(device == "cpu"))
                pixels = (pixels.permute(0, 2, 3, 1) * 127.5 + 128).clamp(0, 255).to(torch.uint8)[0].cpu().numpy()
                Image.fromarray(pixels).save(out / f"seed-{seed:06d}.png")
        write(out / "generation.json", {"snapshot": str(source), "sha256": sha(source), "seeds": seeds, "device": device})
        print("Generated 256x256 images:", out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "train", "generate", "release-lock"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume")
    parser.add_argument("--snapshot")
    parser.add_argument("--seeds", default="0,1,2,3")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--token", default="")
    parser.add_argument("--confirmation", default="")
    cli = parser.parse_args()
    cfg = read(HERE / "config.json")
    project = Path(cli.project).resolve()
    if cli.command == "plan":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        args = options(cfg)
        import torch
        assert not torch.cuda.is_initialized()
        print(json.dumps({"mode": "prepared-not-started", "cuda_initialized": False, "training_options": dict(args)}, indent=2))
    elif cli.command == "train":
        train_model(project, cfg, cli.execute, cli.resume)
    elif cli.command == "generate":
        if not cli.snapshot:
            raise ValueError("Select a verified snapshot first.")
        generate(project, cfg, cli.execute, cli.snapshot, [int(x) for x in cli.seeds.split(",")], cli.device)
    elif cli.command == "release-lock":
        release_lock(require_cloud(project), cli.token, cli.confirmation)


if __name__ == "__main__":
    main()
