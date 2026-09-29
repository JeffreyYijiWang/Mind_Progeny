"""Real CUDA-checkpoint -> CPU inference check; never runs training."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import nbformat
import torch
from scripts.generate_cpu import generate_cpu
from neo_r3gan.io_utils import sha256
from neo_r3gan.upstream import code_version

project = ROOT / "workspace"
experiment = "neohuman-local-002"
run = project / "experiments" / experiment
protected = [p for p in run.rglob("*") if p.is_file() and "generated" not in p.relative_to(run).parts]
before = {str(p): sha256(p) for p in protected}
torch.set_num_threads(2)
rng = torch.get_rng_state().clone()
started = time.perf_counter()
with patch.object(torch.cuda, "is_available", return_value=False), patch.object(torch.cuda, "_lazy_init", side_effect=AssertionError("CPU generation must not initialize CUDA")):
    result = generate_cpu(project, experiment, seeds=range(4))
    repeated = generate_cpu(project, experiment, seeds=[0])
assert torch.equal(rng, torch.get_rng_state()), "Inference changed CPU RNG state"
assert sha256(result["paths"][0]) == sha256(repeated["paths"][0]), "Same seed did not reproduce the image"
after = {str(p): sha256(p) for p in protected}
assert before == after, "Existing training files changed"
new_protected = {str(p) for p in run.rglob("*") if p.is_file() and "generated" not in p.relative_to(run).parts}
assert new_protected == set(before), "Inference added or removed training files"
for path in result["paths"]:
    from PIL import Image
    with Image.open(path) as im:
        assert im.size == (128, 128) and im.mode == "RGB"
nb = nbformat.read(ROOT / "NeoHuman_R3GAN_CPU_Generate.ipynb", as_version=4)
nbformat.validate(nb)
for cell in nb.cells:
    if cell.cell_type == "code":
        compile(cell.source, cell.id, "exec")
report = {"passed": True, "seconds": time.perf_counter() - started, "platform": sys.platform, "torch": str(torch.__version__), "code": code_version(), "source_checkpoint_step": result["checkpoint"]["step"], "source_checkpoint_sha256": result["checkpoint"]["sha256"], "generated_images": 4, "repeated_seed_identical": True, "cpu_rng_preserved": True, "training_files_unchanged": True, "cuda_unavailable_and_initialization_blocked": True, "notebook_schema_and_syntax_valid": True, "live_colab_tested": False, "output": str(result["output"])}
(ROOT / "validation" / "cpu-generation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
