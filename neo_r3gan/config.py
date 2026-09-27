import copy
import math
import re
from .io_utils import digest, read_json


DEFAULT = {
    "schema": 1,
    "experiment_id": "neohuman-local-001",
    "seed": 2026,
    "dataset": {"expected_images": 45, "resolution": 128, "crop": "pad", "alpha_background": [255, 255, 255]},
    "model": {"noise_dim": 64, "widths": [128, 128, 128, 96, 64, 32], "blocks": [1, 1, 1, 1, 1, 1], "cardinalities": [8, 8, 8, 8, 4, 4], "expansion": 2},
    "training": {"batch_size": 8, "microbatch": 2, "lr": 0.0001, "beta2": 0.9, "gamma": 1.0, "ema_nimg": 1000, "mirror": True, "augment_probability": 0.2, "deterministic": True},
    "schedule": {"budget_seconds": 28800, "sample_seconds": 600, "recovery_seconds": 900, "milestone_seconds": 3600, "log_seconds": 60, "keep_recovery": 4},
    "preview": {"count": 16, "seed": 12345}
}


def default_config(experiment_id=None):
    config = copy.deepcopy(DEFAULT)
    if experiment_id:
        config["experiment_id"] = experiment_id
    return config


def validate(config):
    if set(config) != set(DEFAULT) or config["schema"] != 1:
        raise ValueError("Unsupported configuration schema or unknown top-level fields")
    for key in ("dataset", "model", "training", "schedule", "preview"):
        if set(config[key]) != set(DEFAULT[key]):
            raise ValueError(f"Unknown or missing {key} fields")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", config["experiment_id"]):
        raise ValueError("Use an experiment ID containing only letters, digits, '-' and '_'")
    d, m, t, s = (config[k] for k in ("dataset", "model", "training", "schedule"))
    if d["resolution"] not in (16, 32, 64, 128, 256) or d["crop"] not in ("center", "pad"):
        raise ValueError("Resolution must be 16/32/64/128/256; crop must be center or pad")
    n = int(math.log2(d["resolution"])) - 1
    if any(len(m[k]) != n for k in ("widths", "blocks", "cardinalities")):
        raise ValueError(f"Resolution requires {n} stages in widths, blocks and cardinalities")
    counts = [d["expected_images"], m["noise_dim"], m["expansion"], t["batch_size"], t["microbatch"], s["keep_recovery"], config["preview"]["count"]] + m["widths"] + m["blocks"] + m["cardinalities"]
    seeds = [config["seed"], config["preview"]["seed"]]
    if any(type(x) is not int or x <= 0 for x in counts) or any(type(x) is not int or not 0 <= x < 2**32 - 1 for x in seeds):
        raise ValueError("Counts must be positive integers; seeds must be nonnegative integers")
    if not 1 <= config["preview"]["count"] <= 256 or config["seed"] >= 2**32:
        raise ValueError("Preview count must be 1..256; seed must be below 2**32")
    if len(d["alpha_background"]) != 3 or any(type(x) is not int or not 0 <= x <= 255 for x in d["alpha_background"]):
        raise ValueError("alpha_background must contain three byte values")
    if any(w * m["expansion"] % c for w, c in zip(m["widths"], m["cardinalities"])):
        raise ValueError("Expanded stage widths must be divisible by cardinalities")
    if t["batch_size"] % t["microbatch"]:
        raise ValueError("batch_size must be divisible by microbatch")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in s.values()):
        raise ValueError("Schedule intervals and retention must be positive and finite")
    for k in ("lr", "gamma", "ema_nimg"):
        if not math.isfinite(t[k]) or t[k] <= 0:
            raise ValueError(f"{k} must be finite and positive")
    if not 0 <= t["beta2"] < 1 or not 0 <= t["augment_probability"] <= 1:
        raise ValueError("Invalid optimizer or augmentation probability")
    if type(t["mirror"]) is not bool or type(t["deterministic"]) is not bool:
        raise ValueError("mirror and deterministic must be boolean")
    return config


def load_config(path):
    return validate(read_json(path))


def config_hash(config):
    return digest(validate(config))
