"""The single training implementation used by both notebook front ends."""
import copy
import gc
import math
import os
import platform
import random
import signal
import sys
import time
import warnings
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from .config import config_hash, validate
from .data import ImageStream, grid
from .io_utils import atomic_write, digest, read_json, verified_copy
from .upstream import code_version, environment, networks_and_loss, require_pins


def hardware_report(require_gpu=False):
    report = {"os": platform.platform(), "python": platform.python_version(), "torch": str(torch.__version__), "cuda_build": torch.version.cuda,
              "cuda_available": torch.cuda.is_available(), "mps_available": bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available())}
    if report["cuda_available"]:
        p = torch.cuda.get_device_properties(0)
        report.update(gpu=p.name, vram_gib=round(p.total_memory / 2**30, 2), compute_capability=f"{p.major}.{p.minor}", compiled_architectures=torch.cuda.get_arch_list())
        try:
            (torch.ones(8, device="cuda") * 2).sum().item()
            report["cuda_kernel_check"] = "passed"
        except RuntimeError as exc:
            raise RuntimeError(f"GPU detected but this pinned PyTorch cannot execute CUDA kernels: {exc}") from exc
        if p.total_memory < 4 * 2**30:
            warnings.warn("Less than 4 GiB VRAM: reduce model widths and microbatch before the smoke test")
    print(report)
    if require_gpu and (not report["cuda_available"] or sys.platform not in ("win32", "linux")):
        raise RuntimeError("Long runs require an NVIDIA CUDA GPU on Windows/Linux. Apple MPS, AMD/Intel GPUs, and CPU are unsupported for this training package; use a Colab GPU.")
    return report


def cpu_tree(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {k: cpu_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [cpu_tree(v) for v in value]
    if isinstance(value, tuple):
        return tuple(cpu_tree(v) for v in value)
    return copy.deepcopy(value)


def rng_state(device):
    np_state = np.random.get_state()
    return {"python": random.getstate(), "numpy": [np_state[0], np_state[1].tolist(), int(np_state[2]), int(np_state[3]), float(np_state[4])],
            "torch_cpu": torch.get_rng_state(), "torch_cuda": torch.cuda.get_rng_state(0) if device.type == "cuda" else None}


def restore_rng(state, device):
    random.setstate(state["python"])
    n = state["numpy"]
    np.random.set_state((n[0], np.asarray(n[1], dtype=np.uint32), n[2], n[3], n[4]))
    torch.set_rng_state(state["torch_cpu"].cpu())
    if device.type == "cuda":
        if state["torch_cuda"] is None:
            raise ValueError("A CPU diagnostic checkpoint cannot resume a CUDA experiment")
        torch.cuda.set_rng_state(state["torch_cuda"].cpu(), 0)


class Trainer:
    def __init__(self, config, prepared, device="cuda", allow_cpu=False):
        require_pins()
        self.config = copy.deepcopy(validate(config))
        self.device = torch.device(device)
        if self.device.type != "cuda" and not allow_cpu:
            raise RuntimeError("CPU is only allowed for explicit diagnostic tests")
        if self.device.type == "cuda" and self.device.index not in (None, 0):
            raise ValueError("Only one GPU (cuda:0) is supported")
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        random.seed(config["seed"])
        np.random.seed(config["seed"])
        torch.manual_seed(config["seed"])
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.use_deterministic_algorithms(config["training"]["deterministic"])
        Generator, Discriminator, Loss = networks_and_loss()
        m = config["model"]
        kw = dict(WidthPerStage=m["widths"], BlocksPerStage=m["blocks"], CardinalityPerStage=m["cardinalities"], ExpansionFactor=m["expansion"])
        self.G = Generator(NoiseDimension=m["noise_dim"], **kw).to(self.device).train().requires_grad_(False)
        reverse = {k: list(reversed(v)) if isinstance(v, list) else v for k, v in kw.items()}
        self.D = Discriminator(**reverse).to(self.device).train().requires_grad_(False)
        self.ema = copy.deepcopy(self.G).eval().requires_grad_(False)
        self.loss = Loss(self.G, self.D)
        t = config["training"]
        self.g_opt = torch.optim.Adam(self.G.parameters(), lr=t["lr"], betas=(0.0, t["beta2"]), eps=1e-8, foreach=False)
        self.d_opt = torch.optim.Adam(self.D.parameters(), lr=t["lr"], betas=(0.0, t["beta2"]), eps=1e-8, foreach=False)
        self.dataset_manifest = read_json(Path(prepared) / "manifest.json")
        if any(self.dataset_manifest["recipe"].get(k) != v for k, v in config["dataset"].items()):
            raise ValueError("Dataset preprocessing differs from experiment configuration")
        self.stream = ImageStream(prepared, config["seed"] + 1)
        self.counters = {"step": 0, "nimg": 0, "training_seconds": 0.0}
        self.events = {name: float(config["schedule"][name + "_seconds"]) for name in ("sample", "recovery", "milestone", "log")}
        self.preview_z = torch.randn(config["preview"]["count"], m["noise_dim"], generator=torch.Generator().manual_seed(config["preview"]["seed"]))
        self.dirty = False

    def augment(self, x):
        p = self.config["training"]["augment_probability"]
        if not p:
            return x
        shape = (len(x), 1, 1, 1)
        mask = (torch.rand(shape, device=x.device) < p).to(x.dtype)
        brightness = (torch.rand(shape, device=x.device) - 0.5) * 0.2 * mask
        contrast = 1 + (torch.rand(shape, device=x.device) - 0.5) * 0.4 * mask
        return x * contrast + brightness

    def step(self):
        self.dirty = True
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        t = self.config["training"]
        batch, micro = t["batch_size"], t["microbatch"]
        metrics = {}
        for phase, model, opt in (("D", self.D, self.d_opt), ("G", self.G, self.g_opt)):
            model.requires_grad_(True)
            opt.zero_grad(set_to_none=True)
            real = self.stream.next(batch, self.device, t["mirror"])
            noise = torch.randn(batch, self.config["model"]["noise_dim"], device=self.device)
            losses = []
            for r, z in zip(real.split(micro), noise.split(micro)):
                if phase == "D":
                    values = self.loss.AccumulateDiscriminatorGradients(z, r, None, Gamma=t["gamma"], Scale=micro / batch, Preprocessor=self.augment)
                else:
                    values = self.loss.AccumulateGeneratorGradients(z, r, None, Scale=micro / batch, Preprocessor=self.augment)
                losses.append(torch.stack([v.mean() for v in values]))
            if any(p.grad is not None and not bool(torch.isfinite(p.grad).all()) for p in model.parameters()):
                raise FloatingPointError("Non-finite gradients; step incomplete. Resume the last persisted checkpoint.")
            opt.step()
            model.requires_grad_(False)
            means = torch.stack(losses).mean(0).cpu().tolist()
            metrics[phase + "_loss"] = means[0]
            if phase == "D":
                metrics.update(R1=means[2], R2=means[3])
        beta = 0.5 ** (batch / max(t["ema_nimg"], 1e-8))
        with torch.no_grad():
            for ema, current in zip(self.ema.parameters(), self.G.parameters()):
                ema.copy_(current.lerp(ema, beta))
            for ema, current in zip(self.ema.buffers(), self.G.buffers()):
                ema.copy_(current)
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        self.counters["training_seconds"] += time.perf_counter() - start
        self.counters["step"] += 1
        self.counters["nimg"] += batch
        self.dirty = False
        return dict(metrics, **self.counters)

    def state_dict(self):
        if self.dirty:
            raise RuntimeError("Cannot checkpoint a partially completed D/G iteration")
        return cpu_tree({"schema": 1, "config": self.config, "config_sha256": config_hash(self.config), "code": code_version(), "environment": environment(),
                         "dataset_sha256": digest(self.dataset_manifest), "G": self.G.state_dict(), "D": self.D.state_dict(), "G_ema": self.ema.state_dict(),
                         "G_optimizer": self.g_opt.state_dict(), "D_optimizer": self.d_opt.state_dict(), "counters": self.counters, "events": self.events,
                         "sampler": self.stream.state_dict(), "random": rng_state(self.device), "preview_z": self.preview_z,
                         "implementation": {"precision": "float32", "scheduler": "constant-config", "grad_scaler": None, "workers": 0, "device_type": self.device.type}})

    def load_state_dict(self, state):
        if state["schema"] != 1 or state["config_sha256"] != config_hash(self.config) or state["code"] != code_version():
            raise ValueError("Checkpoint schema, shared code, upstream revision, or configuration mismatch")
        if state["dataset_sha256"] != digest(self.dataset_manifest):
            raise ValueError("Dataset manifest mismatch")
        if state["implementation"]["device_type"] != self.device.type:
            raise ValueError("Cannot mix a CPU diagnostic run and a CUDA experiment")
        current = environment()
        for key in ("torch", "numpy", "Pillow"):
            if state["environment"][key].split("+")[0] != current[key].split("+")[0]:
                raise ValueError(f"Checkpoint dependency mismatch: {key}")
        if state["environment"] != current:
            warnings.warn("Runtime/hardware differs: full training state will resume, but bitwise continuation across machines is not guaranteed.")
        self.G.load_state_dict(state["G"], strict=True)
        self.D.load_state_dict(state["D"], strict=True)
        self.ema.load_state_dict(state["G_ema"], strict=True)
        self.g_opt.load_state_dict(state["G_optimizer"])
        self.d_opt.load_state_dict(state["D_optimizer"])
        self.counters, self.events = copy.deepcopy(state["counters"]), copy.deepcopy(state["events"])
        self.stream.load_state_dict(state["sampler"])
        self.preview_z = state["preview_z"].cpu()
        restore_rng(state["random"], self.device)  # Last: constructors and loading must not perturb recovery RNG.
        self.dirty = False

    def due(self, name):
        return self.counters["training_seconds"] >= self.events[name]

    def advance_event(self, name):
        interval = self.config["schedule"][name + "_seconds"]
        while self.events[name] <= self.counters["training_seconds"]:
            self.events[name] += interval

    @torch.no_grad()
    def generate(self, noise):
        images = []
        for z in noise.split(self.config["training"]["microbatch"]):
            values = ((self.ema(z.to(self.device)).cpu().float() + 1) * 127.5).round().clamp(0, 255).byte()
            images.extend(Image.fromarray(x.permute(1, 2, 0).numpy()) for x in values)
        return images

    def preview(self, local, persistent):
        name = f"{self.config['experiment_id']}_step-{self.counters['step']:09d}_train-{int(self.counters['training_seconds']):08d}s.png"
        path = Path(local) / "samples" / name
        canvas = grid(self.generate(self.preview_z), columns=math.ceil(math.sqrt(len(self.preview_z))))
        atomic_write(path, lambda f: canvas.save(f, format="PNG"))
        verified_copy(path, Path(persistent) / "samples" / name)
        return Path(persistent) / "samples" / name


class GracefulStop:
    """SIGINT/SIGTERM request a stop at the next completed optimizer boundary."""
    def __init__(self):
        self.requested, self.previous = False, {}

    def __enter__(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.previous[sig] = signal.getsignal(sig)
            signal.signal(sig, self._request)
        return self

    def _request(self, *_):
        self.requested = True
        print("Graceful stop requested. Finishing this iteration and persisting recovery...", flush=True)

    def __exit__(self, *_):
        for sig, handler in self.previous.items():
            signal.signal(sig, handler)


def release_gpu():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
