"""Verified offline handoff and results bundles. No automatic model merging."""
import os
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
import torch
from .checkpoints import Checkpoints, RunLock
from .config import config_hash, validate
from .data import verify_prepared
from .io_utils import atomic_write, canonical, digest, read_json, safe_child, sha256, verified_copy, write_json
from .upstream import code_version, environment, require_pins
from .workflow import _assert_active, run_path


def _bundle(path, files, metadata):
    inventory = {name: {"sha256": sha256(source), "bytes": source.stat().st_size} for name, source in files.items()}
    def writer(f):
        with zipfile.ZipFile(f, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for name, source in files.items():
                z.write(source, name)
            z.writestr("bundle.json", canonical(dict(metadata, files=inventory)))
    atomic_write(path, writer)
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise IOError("Bundle ZIP validation failed")
    return path


def export_recovery_bundle(project, scratch, config):
    """Seal a stopped source run and hand off to one destination; fails if a writer is live."""
    run = run_path(project, config)
    local = Path(scratch) / "exports"
    local.mkdir(parents=True, exist_ok=True)
    with RunLock(run) as lock:
        _assert_active(run)
        cp, entry = Checkpoints(run, local).latest()
        dataset = read_json(run / "dataset_manifest.json")
        prepared = Path(project) / "datasets" / "prepared" / dataset["dataset_id"]
        verify_prepared(prepared, dataset)
        if config != read_json(run / "config.json"):
            raise ValueError("Export must use the saved experiment configuration")
        ticket = uuid.uuid4().hex
        files = {"checkpoint.pt": cp, "config.json": run / "config.json", "dataset_manifest.json": run / "dataset_manifest.json",
                 "code_version.json": run / "code_version.json", "environment.json": run / "environment.json", "prepared/images.zip": prepared / "images.zip"}
        if (prepared / "preprocessing.png").exists():
            files["prepared/preprocessing.png"] = prepared / "preprocessing.png"
        name = f"{config['experiment_id']}_step-{entry['step']:09d}_train-{int(entry['training_seconds']):08d}s_handoff-{ticket[:8]}.zip"
        bundle = _bundle(local / name, files, {"schema": 1, "kind": "handoff", "ticket": ticket, "experiment_id": config["experiment_id"], "code": code_version(), "checkpoint": entry})
        # Publish under a pending name first. Only a sealed source produces a usable final bundle.
        pending = run / "exports" / (name + ".pending")
        checksum = verified_copy(bundle, pending)
        lock.check()
        write_json(run / "run.json", {"status": "transferred", "experiment_id": config["experiment_id"], "ticket": ticket, "sealed": time.time(), "bundle_sha256": checksum})
        final = pending.with_name(name)
        os.replace(pending, final)
        if sha256(final) != checksum:
            raise IOError("Handoff bundle read-back failed; source remains sealed")
        write_json(final.with_suffix(".sha256.json"), {"file": name, "sha256": checksum})
        print(f"Source sealed. Import this handoff bundle on exactly one destination: {final}")
        return final


def import_recovery_bundle(bundle_path, project, scratch):
    """Validate every member before deserializing. Refuse existing destination runs."""
    require_pins()
    project, scratch = Path(project), Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="import-") as tmp:
        temp = Path(tmp)
        with zipfile.ZipFile(bundle_path) as z:
            names = z.namelist()
            if len(set(names)) != len(names) or len(names) > 1000:
                raise ValueError("Duplicate or too many bundle members")
            if sum(i.file_size for i in z.infolist()) > 100 * 1024**3:
                raise ValueError("Bundle exceeds the 100 GiB safety limit")
            for name in names:
                p = PurePosixPath(name)
                if p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
                    raise ValueError("Unsafe bundle member")
            meta = __import__("json").loads(z.read("bundle.json"))
            if meta["schema"] != 1 or meta["kind"] != "handoff" or meta["code"] != code_version():
                raise ValueError("Bundle type, schema, or code version mismatch")
            if set(names) != set(meta["files"]) | {"bundle.json"}:
                raise ValueError("Bundle inventory mismatch")
            for name, info in meta["files"].items():
                target = safe_child(temp, name)
                def extract(f, member=name):
                    with z.open(member) as source:
                        __import__("shutil").copyfileobj(source, f, 8 * 1024 * 1024)
                atomic_write(target, extract)
                if target.stat().st_size != info["bytes"] or sha256(target) != info["sha256"]:
                    raise ValueError(f"Corrupt bundle member: {name}")
        config = validate(read_json(temp / "config.json"))
        dataset = read_json(temp / "dataset_manifest.json")
        if config["experiment_id"] != meta["experiment_id"] or read_json(temp / "code_version.json") != code_version():
            raise ValueError("Bundle identity/version mismatch")
        write_json(temp / "prepared" / "manifest.json", dataset)
        verify_prepared(temp / "prepared", dataset)
        state = torch.load(temp / "checkpoint.pt", map_location="cpu", weights_only=True)
        if state["schema"] != 1 or state["code"] != code_version() or state["config"] != config or state["config_sha256"] != config_hash(config) or state["dataset_sha256"] != digest(dataset):
            raise ValueError("Checkpoint does not match bundled configuration/dataset/code")
        if state["implementation"]["device_type"] != "cuda":
            raise ValueError("CPU diagnostic checkpoints cannot be imported as GPU experiments")
        current = environment()
        for key in ("torch", "numpy", "Pillow"):
            if state["environment"][key].split("+")[0] != current[key].split("+")[0]:
                raise ValueError(f"Dependency mismatch: {key}")
        run = run_path(project, config)
        if run.exists():
            raise FileExistsError("Destination experiment already exists. Choose an empty project root; never overwrite a run.")
        with RunLock(run) as lock:
            if (run / "run.json").exists() or (run / "manifest.json").exists():
                raise FileExistsError("Destination was created by another importer; refusing to overwrite it")
            prepared = project / "datasets" / "prepared" / dataset["dataset_id"]
            for source in (temp / "prepared").iterdir():
                verified_copy(source, prepared / source.name)
            for name in ("config.json", "dataset_manifest.json", "code_version.json", "environment.json"):
                verified_copy(temp / name, run / name)
            manager = Checkpoints(run, scratch / "imports" / meta["ticket"], config["schedule"]["keep_recovery"], lock)
            manager.save(state, ("recovery", "manual"))
            write_json(run / "run.json", {"status": "active", "experiment_id": config["experiment_id"], "import_ticket": meta["ticket"], "imported": time.time()})
            verified_copy(temp / "config.json", project / "configs" / (config["experiment_id"] + ".json"))
        print(f"Imported {config['experiment_id']} at {state['counters']['training_seconds']/3600:.4f} h. Run the smoke cell, then Resume latest verified checkpoint.")
        return config, prepared


def export_results(project, scratch, config):
    """Archive all retained checkpoints, samples, generated images and logs; no ownership change."""
    run = run_path(project, config)
    with RunLock(run):
        manager = Checkpoints(run, Path(scratch) / "exports")
        manager.latest()
        files = {}
        for entry in manager.manifest()["entries"]:
            source = safe_child(run, entry["path"])
            if sha256(source) != entry["sha256"]:
                raise IOError(f"Cannot export corrupt checkpoint: {source}")
            files[entry["path"]] = source
        for folder in ("samples", "generated", "logs"):
            for file in (run / folder).rglob("*"):
                if file.is_file() and ".partial-" not in file.name:
                    files[file.relative_to(run).as_posix()] = file
        for name in ("config.json", "dataset_manifest.json", "code_version.json", "environment.json", "manifest.json"):
            files[name] = run / name
        name = config["experiment_id"] + "_results_" + time.strftime("%Y%m%d-%H%M%S") + ".zip"
        local = _bundle(Path(scratch) / "exports" / name, files, {"schema": 1, "kind": "results", "code": code_version()})
        target = run / "exports" / name
        checksum = verified_copy(local, target)
        write_json(target.with_suffix(".sha256.json"), {"sha256": checksum})
        return target
