"""Notebook-facing operations, all shared between Colab and local."""
import copy
import json
import math
import shutil
import sys
import time
import uuid
from pathlib import Path
import torch
from .checkpoints import Checkpoints, RunLock
from .config import config_hash, validate
from .data import stage_dataset, verify_prepared
from .engine import GracefulStop, Trainer, environment, hardware_report, release_gpu
from .io_utils import digest, read_json, verified_copy, write_json
from .upstream import code_version

SESSION = uuid.uuid4().hex


def run_path(project, config):
    validate(config)
    return Path(project) / "experiments" / config["experiment_id"]


def _assert_active(run):
    status = read_json(Path(run) / "run.json")
    if status["status"] != "active":
        raise RuntimeError("This source experiment was sealed for transfer. Resume only on the imported destination.")


def _initialize(config, project, run, local, prepared, resume):
    manifest = verify_prepared(prepared)
    for key, value in config["dataset"].items():
        if manifest["recipe"][key] != value:
            raise ValueError(f"Prepared dataset setting differs from config: {key}")
    if (run / "run.json").exists():
        _assert_active(run)
        if not resume:
            raise FileExistsError("Experiment already exists. Use resume=True or choose a new experiment ID.")
        if read_json(run / "config.json") != config or read_json(run / "dataset_manifest.json") != manifest:
            raise ValueError("Resume requires the saved configuration and identical dataset manifest")
    else:
        if resume:
            raise FileNotFoundError("No experiment to resume. Import a bundle or start a new experiment.")
        if (run / "config.json").exists() or (run / "manifest.json").exists():
            raise RuntimeError("Experiment initialization was interrupted. Inspect its saved files; choose a new ID instead of overwriting it.")
        for folder in ("checkpoints/recovery", "checkpoints/milestones", "samples", "logs", "exports"):
            (run / folder).mkdir(parents=True, exist_ok=True)
        for name, value in (("config.json", config), ("dataset_manifest.json", manifest), ("code_version.json", code_version()), ("environment.json", environment())):
            verified_copy(write_json(local / name, value), run / name)
        verified_copy(local / "config.json", Path(project) / "configs" / (config["experiment_id"] + ".json"))
        write_json(run / "run.json", {"status": "active", "experiment_id": config["experiment_id"], "created": time.time()})


def _smoke_key(config, prepared):
    return digest({"config": config, "dataset": verify_prepared(prepared), "code": code_version()})


def train(config, project, scratch, prepared, resume=False, max_steps=None, require_smoke=True, device="cuda", allow_cpu=False):
    """Count only completed training iterations; saving, downtime and previews are excluded."""
    validate(config)
    if not allow_cpu:
        hardware_report(require_gpu=True)
    if require_smoke:
        path = Path(project) / "smoke_reports" / (_smoke_key(config, prepared) + ".json")
        report = read_json(path) if path.exists() else {}
        if not report.get("passed") or report.get("session") != SESSION:
            raise RuntimeError("Run the smoke test for this configuration in this kernel before training/resuming")
    run = run_path(project, config)
    local = Path(scratch) / "experiments" / config["experiment_id"]
    working = stage_dataset(prepared, scratch)
    with RunLock(run) as lock:
        _initialize(config, project, run, local, prepared, resume)
        manager = Checkpoints(run, local, config["schedule"]["keep_recovery"], lock)
        trainer = Trainer(config, working, device=device, allow_cpu=allow_cpu)
        if resume:
            state, entry = manager.load_latest()
            trainer.load_state_dict(state)
            del state
            print(f"Restored step {entry['step']}, {entry['training_seconds']/3600:.4f} cumulative training hours", flush=True)
        else:
            manager.save(trainer.state_dict(), ("recovery",))
        remaining = max(0, config["schedule"]["budget_seconds"] - trainer.counters["training_seconds"])
        print(f"Budget remaining: {remaining/3600:.4f} training hours. Run: {run}", flush=True)
        start_step = trainer.counters["step"]
        log_name = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.jsonl"
        local_log = local / "logs" / log_name
        local_log.parent.mkdir(parents=True, exist_ok=True)
        metrics = dict(trainer.counters)
        error = None
        try:
            with GracefulStop() as stop:
                while trainer.counters["training_seconds"] < config["schedule"]["budget_seconds"]:
                    if stop.requested or (run / "STOP").exists():
                        break
                    if max_steps is not None and trainer.counters["step"] - start_step >= max_steps:
                        break
                    metrics = trainer.step()
                    if trainer.due("log") or trainer.counters["step"] == start_step + 1:
                        trainer.advance_event("log")
                        with local_log.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(dict(metrics, wall_time=time.time())) + "\n")
                        verified_copy(local_log, run / "logs" / log_name)
                        print(f"step {metrics['step']} | {metrics['training_seconds']/3600:.4f} h | D {metrics['D_loss']:.4f} | G {metrics['G_loss']:.4f}", flush=True)
                    if trainer.due("sample"):
                        trainer.preview(local, run)
                        trainer.advance_event("sample")
                    milestone, recovery = trainer.due("milestone"), trainer.due("recovery")
                    if milestone or recovery:
                        if milestone:
                            trainer.advance_event("milestone")
                        if recovery:
                            trainer.advance_event("recovery")
                        tags = ["recovery"] + (["milestone"] if milestone else [])
                        manager.save(trainer.state_dict(), tags)
                        print(f"Persisted verified checkpoint at step {trainer.counters['step']}", flush=True)
        except BaseException as exc:
            error = exc
            print(f"Training stopped: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        finally:
            try:
                if not trainer.dirty:
                    completed = trainer.counters["training_seconds"] >= config["schedule"]["budget_seconds"]
                    tags = ["recovery", "final" if completed else "stop"]
                    if trainer.due("milestone"):
                        tags.append("milestone")
                        trainer.advance_event("milestone")
                    # Save before preview: a preview failure must not prevent recovery.
                    manager.save(trainer.state_dict(), tags)
                    trainer.preview(local, run)
                    if local_log.exists():
                        verified_copy(local_log, run / "logs" / log_name)
                else:
                    print("Interrupted during an incomplete step. Keeping the last verified checkpoint; partial optimizer state is not saved.", file=sys.stderr)
            except BaseException as save_error:
                print(f"FINAL SAVE/PREVIEW FAILED: {save_error}", file=sys.stderr, flush=True)
                if error is None:
                    error = save_error
            counters = dict(trainer.counters)
            del trainer
            release_gpu()
        if error is not None:
            raise error
        return dict(counters, run=str(run), latest=manager.latest()[1])


def latest_verified(project, config):
    run = run_path(project, config)
    path, entry = Checkpoints(run, run / ".read-cache").latest()
    print(f"Verified: {path}\nStep {entry['step']} | cumulative {entry['training_seconds']/3600:.4f} h | remaining {max(0, config['schedule']['budget_seconds']-entry['training_seconds'])/3600:.4f} h")
    return path, entry


def mark_keep(project, config, checkpoint_path=None):
    run = run_path(project, config)
    with RunLock(run) as lock:
        return Checkpoints(run, run / ".metadata-cache", config["schedule"]["keep_recovery"], lock).mark_keep(checkpoint_path)


def request_stop(project, config):
    path = run_path(project, config) / "STOP"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def clear_stop(project, config):
    run = run_path(project, config)
    with RunLock(run):
        (run / "STOP").unlink(missing_ok=True)


def _compare(a, b, path="state"):
    if isinstance(a, torch.Tensor):
        if not torch.equal(a, b):
            diff = (a.double() - b.double()).abs().max().item()
            raise AssertionError(f"Save/resume diverged at {path}; max abs difference {diff}")
    elif isinstance(a, dict):
        if a.keys() != b.keys():
            raise AssertionError(path + " keys differ")
        for k in a:
            _compare(a[k], b[k], path + "." + str(k))
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            raise AssertionError(path + " lengths differ")
        for i, (x, y) in enumerate(zip(a, b)):
            _compare(x, y, path + f"[{i}]")
    elif a != b:
        raise AssertionError(path + " differs")


def smoke_test(config, project, scratch, prepared, device="cuda", allow_cpu=False):
    """Actual configured model/data: two steps, persist, then compare the third step."""
    if not allow_cpu:
        hardware_report(require_gpu=True)
    test_config = copy.deepcopy(config)
    test_config["experiment_id"] = config["experiment_id"][:45] + "-smoke-" + uuid.uuid4().hex[:8]
    run = run_path(project, test_config)
    local = Path(scratch) / "experiments" / test_config["experiment_id"]
    working = stage_dataset(prepared, scratch)
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    with RunLock(run) as lock:
        _initialize(test_config, project, run, local, prepared, resume=False)
        manager = Checkpoints(run, local, lock=lock)
        a = Trainer(test_config, working, device, allow_cpu)
        a.step()
        a.step()
        saved = a.state_dict()
        entry = manager.save(saved)
        a.step()
        expected = a.state_dict()
        del a, saved
        release_gpu()
        # Fresh object, then reload only from successfully persisted storage.
        restored, _ = manager.load_latest()
        b = Trainer(test_config, working, device, allow_cpu)
        b.load_state_dict(restored)
        if b.counters["training_seconds"] != entry["training_seconds"]:
            raise AssertionError("Cumulative budget did not restore")
        b.step()
        actual = b.state_dict()
        for key in ("G", "D", "G_ema", "G_optimizer", "D_optimizer", "sampler", "random", "preview_z"):
            _compare(expected[key], actual[key], key)
        for key in ("step", "nimg"):
            _compare(expected["counters"][key], actual["counters"][key], key)
        _compare(restored["events"], actual["events"], "events")
        preview = b.preview(local, run)
        manager.save(actual, ("recovery", "manual"))
        peak = torch.cuda.max_memory_allocated() / 2**30 if device.startswith("cuda") else None
        del b, restored, actual, expected
        release_gpu()
    # Conservative upper bound: rolling + hourly milestones + final, plus two staging files.
    s = config["schedule"]
    retained = s["keep_recovery"] + math.ceil(s["budget_seconds"] / s["milestone_seconds"]) + 1
    report = {"passed": True, "session": SESSION, "device": device, "environment": environment(), "code": code_version(), "config_sha256": config_hash(config),
              "dataset_sha256": digest(verify_prepared(prepared)), "checkpoint_bytes": entry["bytes"], "checkpoint_mib": round(entry["bytes"] / 2**20, 2),
              "estimated_retained_checkpoints_max": retained, "estimated_checkpoint_storage_gib": round(retained * entry["bytes"] / 2**30, 3),
              "recommended_checkpoint_space_with_staging_gib": round((retained + 2) * entry["bytes"] / 2**30, 3),
              "peak_gpu_allocated_gib": peak, "saved_training_seconds": entry["training_seconds"], "next_step_tensor_comparison": "bitwise_equal",
              "smoke_experiment": str(run), "preview": str(preview), "notes": "Add original/prepared data, samples, exports, manual keeps, and smoke runs. Drive mount free space is not account quota. Timings exclude save/sample downtime."}
    write_json(Path(project) / "smoke_reports" / (_smoke_key(config, prepared) + ".json"), report)
    write_json(run / "smoke_report.json", report)
    print(json.dumps(report, indent=2))
    return report


def generate_images(project, scratch, config, prepared, seeds=range(16)):
    """EMA inference from the latest verified recovery checkpoint, separate sample RNG."""
    run = run_path(project, config)
    local = Path(scratch) / "experiments" / config["experiment_id"]
    working = stage_dataset(prepared, scratch)
    with RunLock(run):
        manager = Checkpoints(run, local)
        state, entry = manager.load_latest()
        trainer = Trainer(config, working)
        trainer.load_state_dict(state)
        del state
        target = run / "generated" / f"step-{entry['step']:09d}"
        seeds = list(seeds)
        if not seeds or len(seeds) > 10000 or any(type(s) is not int or s < 0 for s in seeds):
            raise ValueError("Provide 1..10000 nonnegative integer seeds")
        paths = []
        for seed in seeds:
            noise = torch.randn(1, config["model"]["noise_dim"], generator=torch.Generator().manual_seed(seed))
            image = trainer.generate(noise)[0]
            source = local / "generated" / f"seed-{seed:06d}.png"
            source.parent.mkdir(parents=True, exist_ok=True)
            image.save(source)
            verified_copy(source, target / source.name)
            paths.append(target / source.name)
        write_json(target / "generation.json", {"seeds": seeds, "checkpoint": entry, "code": code_version(), "environment": environment()})
        del trainer
        release_gpu()
    return paths


def show_progress(project, config):
    from IPython.display import display
    import matplotlib.pyplot as plt
    run = run_path(project, config)
    latest_verified(project, config)
    samples = sorted((run / "samples").glob("*.png"))
    if samples:
        from PIL import Image
        display(Image.open(samples[-1]))
    records = []
    for path in sorted((run / "logs").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                if "G_loss" in record:
                    records.append(record)
            except ValueError:
                pass
    if records:
        fig, ax = plt.subplots(figsize=(9, 3))
        for name in ("G_loss", "D_loss"):
            ax.plot([r["training_seconds"] / 3600 for r in records], [r[name] for r in records], label=name)
        ax.set(xlabel="Cumulative training hours", ylabel="Loss (not an image-quality score)")
        ax.legend()
        display(fig)
        plt.close(fig)
    return run
