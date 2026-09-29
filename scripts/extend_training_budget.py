"""Create a full-state continuation with a larger total budget; preserve the source.

This lives outside neo_r3gan so existing checkpoint code identities stay valid.
Only the experiment ID, total budget and corresponding config hash change.
"""
import copy
import math
import tempfile
import time
from pathlib import Path

from neo_r3gan.checkpoints import Checkpoints, RunLock
from neo_r3gan.config import config_hash, default_config, load_config, validate
from neo_r3gan.data import verify_prepared
from neo_r3gan.io_utils import digest, read_json, safe_child, write_json
from neo_r3gan.upstream import code_version, require_pins


def extend_training_budget(project, scratch, source_id, destination_id, total_hours=13):
    """Source must be stopped. Repeated calls reuse a verified continuation."""
    for name in (source_id, destination_id):
        validate(default_config(name))
    if source_id == destination_id:
        raise ValueError("Use a different continuation ID to preserve the source")
    if isinstance(total_hours, bool) or not isinstance(total_hours, (int, float)) or not math.isfinite(total_hours) or total_hours <= 0:
        raise ValueError("Total hours must be finite and positive")
    require_pins()
    project, scratch = Path(project), Path(scratch)
    source = project / "experiments" / source_id
    destination = project / "experiments" / destination_id
    if not (source / "run.json").is_file():
        raise FileNotFoundError("Saved source experiment not found; check Drive and source ID")
    scratch.mkdir(parents=True, exist_ok=True)
    with RunLock(source), tempfile.TemporaryDirectory(dir=scratch, prefix="extend-budget-") as temporary:
        local = Path(temporary)
        if read_json(source / "run.json")["status"] != "active":
            raise RuntimeError("Source is sealed for transfer; use the imported active run")
        original = load_config(source / "config.json")
        if original["experiment_id"] != source_id:
            raise ValueError("Source configuration belongs to another experiment")
        target_seconds = total_hours * 3600
        if target_seconds <= original["schedule"]["budget_seconds"]:
            raise ValueError("The new total budget must exceed the source budget")
        version = code_version()
        if read_json(source / "code_version.json") != version:
            raise ValueError("Use the original software package for this checkpoint")
        dataset = read_json(source / "dataset_manifest.json")
        prepared = safe_child(project / "datasets" / "prepared", dataset["dataset_id"])
        if verify_prepared(prepared) != dataset:
            raise ValueError("Prepared dataset differs from the source experiment")
        extended = copy.deepcopy(original)
        extended["experiment_id"] = destination_id
        extended["schedule"]["budget_seconds"] = target_seconds
        validate(extended)
        identity = {"source_id": source_id, "source_config_sha256": config_hash(original),
                    "destination_id": destination_id, "total_budget_seconds": target_seconds}
        if destination.exists():
            # Never overwrite a previous attempt, another experiment or a
            # continuation that has already advanced beyond the fork point.
            with RunLock(destination):
                if not (destination / "run.json").is_file() or not (destination / "extension.json").is_file():
                    raise RuntimeError("Destination exists but extension is incomplete; preserve it and use a new destination ID")
                if read_json(destination / "run.json")["status"] != "active":
                    raise RuntimeError("Continuation is sealed for transfer")
                provenance = read_json(destination / "extension.json")
                if any(provenance.get(k) != v for k, v in identity.items()) or read_json(destination / "config.json") != extended:
                    raise ValueError("Destination belongs to a different extension; refusing to overwrite it")
                if read_json(destination / "dataset_manifest.json") != dataset or read_json(destination / "code_version.json") != version:
                    raise ValueError("Continuation dataset/code metadata mismatch")
                state, entry = Checkpoints(destination, local).load_latest()
                if state["config"] != extended or state["config_sha256"] != config_hash(extended) or state["code"] != version or state["dataset_sha256"] != digest(dataset):
                    raise ValueError("Continuation checkpoint identity mismatch")
                del state
                print(f"Using existing continuation at {entry['training_seconds']/3600:.4f} h; remaining {max(0, target_seconds-entry['training_seconds'])/3600:.4f} h.")
            return extended, prepared
        state, entry = Checkpoints(source, local).load_latest()
        if state["schema"] != 1 or state["code"] != version or state["config"] != original or state["config_sha256"] != config_hash(original) or state["dataset_sha256"] != digest(dataset):
            raise ValueError("Source checkpoint configuration/dataset/code mismatch")
        if any(state["counters"][key] != entry[key] for key in ("step", "training_seconds")):
            raise ValueError("Checkpoint counters differ from its manifest")
        if target_seconds <= entry["training_seconds"]:
            raise ValueError("New total budget is already exhausted by the saved checkpoint")
        # The models, EMA, optimizers, counters, RNGs, sampler and event timers
        # are intentionally untouched. No trainer or new weights are created.
        state["config"] = extended
        state["config_sha256"] = config_hash(extended)
        destination.mkdir(parents=True, exist_ok=False)
        with RunLock(destination) as lock:
            for name, value in (("config.json", extended), ("dataset_manifest.json", dataset),
                                ("code_version.json", version), ("environment.json", state["environment"])):
                write_json(destination / name, value)
            manager = Checkpoints(destination, local / "destination", extended["schedule"]["keep_recovery"], lock)
            saved = manager.save(state, ("recovery", "manual"))
            checked, _ = manager.load_latest()
            from neo_r3gan.workflow import _compare
            _compare(state, checked)  # Read back every tensor and saved state field.
            del checked, state
            write_json(destination / "extension.json", dict(identity, source_checkpoint=entry, created=time.time()))
            write_json(project / "configs" / (destination_id + ".json"), extended)
            # Published last: incomplete attempts are never treated as usable.
            write_json(destination / "run.json", {"status": "active", "experiment_id": destination_id, "created": time.time(), "continued_from": source_id})
            print(f"Verified continuation at step {saved['step']}, {saved['training_seconds']/3600:.4f} saved hours; remaining {(target_seconds-saved['training_seconds'])/3600:.4f} h of {total_hours} total.")
    return extended, prepared
