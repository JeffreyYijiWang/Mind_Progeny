"""Load unmodified upstream networks/loss with their own reference operators."""
import hashlib
import importlib.metadata
import os
import platform
import subprocess
import sys
from pathlib import Path
from .io_utils import read_json

ROOT = Path(__file__).resolve().parents[1]
LOCK = read_json(ROOT / "upstream-lock.json")


def checkout():
    path = Path(os.environ.get("NEOHUMAN_R3GAN_SOURCE", ROOT / "vendor" / "R3GAN"))
    if not (path / ".git").exists():
        raise RuntimeError("Run python scripts/fetch_upstream.py before training")
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    if actual != LOCK["commit"] or dirty:
        raise RuntimeError("R3GAN source differs from upstream-lock.json; restore the pinned clean checkout")
    return path


def code_version():
    h = hashlib.sha256()
    for path in sorted((ROOT / "neo_r3gan").glob("*.py")) + [ROOT / "upstream-lock.json"]:
        h.update(path.name.encode())
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return {"shared_sha256": h.hexdigest(), "upstream_commit": LOCK["commit"], "backend": LOCK["backend"], "checkpoint_schema": 1}


def environment():
    import torch
    return {"python": platform.python_version(), "os": platform.platform(), "torch": str(torch.__version__), "cuda": torch.version.cuda,
            "numpy": importlib.metadata.version("numpy"), "Pillow": importlib.metadata.version("Pillow"),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}


def require_pins():
    expected = {"torch": "2.7.1", "numpy": "2.2.6", "Pillow": "11.2.1"}
    for package, version in expected.items():
        if importlib.metadata.version(package).split("+")[0] != version:
            raise RuntimeError(f"{package} must be {version}. Install pinned dependencies and restart the kernel.")


def networks_and_loss():
    path = str(checkout())
    if path not in sys.path:
        sys.path.insert(0, path)
    import R3GAN.FusedOperators as fused
    import R3GAN.Resamplers as resamplers
    fused.BiasedActivation = fused.BiasedActivationReference
    resamplers.InterpolativeUpsampler = resamplers.InterpolativeUpsamplerReference
    resamplers.InterpolativeDownsampler = resamplers.InterpolativeDownsamplerReference
    if "R3GAN.Networks" in sys.modules:
        if sys.modules["R3GAN.Networks"].BiasedActivation is not fused.BiasedActivationReference:
            raise RuntimeError("R3GAN already loaded with a different backend; restart the kernel")
    from R3GAN.Networks import Generator, Discriminator
    from R3GAN.Trainer import AdversarialTraining
    return Generator, Discriminator, AdversarialTraining

