"""Build a self-contained Colab CPU inference notebook using the saved software ZIP."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
original = json.loads((root / "NeoHuman_R3GAN_Colab.ipynb").read_text(encoding="utf-8"))
setup = next("".join(c["source"]) for c in original["cells"] if c["cell_type"] == "code" and "workspace-package.json" in "".join(c["source"]))
setup = setup.replace("https://download.pytorch.org/whl/cu128", "https://download.pytorch.org/whl/cpu")
setup = setup.replace(', "matplotlib==3.10.3"', "")
setup = setup.replace("then rerun settings and cells 1–3.", "then rerun this CPU notebook from the top.")
cells = []


def cell(kind, source):
    item = {"cell_type": kind, "id": f"cpu-{len(cells):03d}", "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        item.update(execution_count=None, outputs=[])
        compile(source, item["id"], "exec")
    cells.append(item)


cell("markdown", """# NeoHuman R3GAN — Generate images on CPU

Use this notebook in a **CPU Colab runtime** to generate images from your saved GPU training checkpoint. Run the cells in order. No training or GPU is needed, and the original 45-image ZIP is not needed.

The existing software ZIP and experiment must be in your Google Drive. This notebook reads the original pinned software, verifies the latest checkpoint, and loads only the EMA generator for CPU inference. It writes new images in a separate output subfolder without changing training checkpoints, timers, configuration or writer locks. You do not need to release a stale training lock for this notebook.

If installation asks for a runtime restart, restart and rerun this notebook from the top. CPU inference has been tested locally on Windows using a real CUDA-trained checkpoint; this Colab notebook's cells were syntax/schema checked, but its live Colab installation has not been tested.
""")
cell("markdown", "## 1 · Connect Drive and select the saved experiment\nKeep the ID of the existing experiment. Leave your original training notebook closed while using this separate CPU notebook.\n")
cell("code", '''from pathlib import Path
import sys, subprocess
from google.colab import drive
drive.mount("/content/drive")
PROJECT = Path("/content/drive/MyDrive/NeoHuman_R3GAN")
EXPERIMENT_ID = "neohuman-colab-001"
CODE_ROOT = Path("/content/NeoHuman_R3GAN_cpu_code")
CODE_BUNDLE = PROJECT / "software" / "NeoHuman_R3GAN_Workspace.zip"
if not (PROJECT / "experiments" / EXPERIMENT_ID / "config.json").is_file():
    raise FileNotFoundError("Saved experiment not found. Check your Google account, project path and experiment ID.")
if not (3, 11) <= sys.version_info[:2] <= (3, 13):
    raise RuntimeError("The pinned software requires Python 3.11–3.13.")
''')
cell("markdown", "## 2 · Load the original software and CPU dependencies\nUses the software ZIP already stored on Drive. If missing, upload the original software ZIP when prompted. This does not alter that ZIP or your training notebook.\n")
cell("code", setup)
cell("markdown", "## 3 · Load the CPU image-generation helper\nThis cell defines the function; the next cell creates your images.\n")
cell("code", (root / "scripts" / "generate_cpu.py").read_text(encoding="utf-8"))
cell("markdown", "## 4 · Generate and save images\nStart with four images. Change `START_SEED` to get another set. The same checkpoint and seeds reproduce the same images on the same CPU/software setup; CPU and GPU outputs need not be bitwise identical. Each run saves to a new folder.\n")
cell("code", '''from IPython.display import display
START_SEED = 0
NUM_IMAGES = 4
torch.set_num_threads(2)
RESULT = generate_cpu(PROJECT, EXPERIMENT_ID, seeds=range(START_SEED, START_SEED + NUM_IMAGES))
display(Image.open(RESULT["preview"]))
print("Open this folder in Google Drive:", RESULT["output"])
''')
notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
output = root / "NeoHuman_R3GAN_CPU_Generate.ipynb"
output.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
print(output)
