"""Build an additive Colab notebook for a full-state 13-hour continuation."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
original = json.loads((root / "NeoHuman_R3GAN_Colab.ipynb").read_text(encoding="utf-8"))
source_cells = {c["id"]: "".join(c["source"]) for c in original["cells"]}
cells = []


def add(kind, source):
    cell = {"cell_type": kind, "id": f"extend-{len(cells):03d}", "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
        compile(source, cell["id"], "exec")
    cells.append(cell)


add("markdown", """# Continue your saved R3GAN model to 13 total training hours

Connect a GPU runtime. Stop the original training run before continuing. Run sections in order, **not Run all**. This notebook reuses the original software ZIP and prepared dataset on Drive. No image ZIP upload is needed when that dataset is still present.

The latest verified full checkpoint is copied into `neohuman-colab-001-13h` with a larger budget. The learned weights, EMA, optimizers, random states, sampler, event timers and elapsed training time are preserved. **13 hours is the total, not 13 extra hours.** The original experiment remains a backup; continue training only the `-13h` experiment afterward. A checkpoint with 8 saved hours has about 5 hours remaining.

An interrupted runtime may leave a writer lock. This notebook does not delete locks automatically. If the extension cell reports a stale lock, use the original notebook's explicit lock-inspection/release procedure only after confirming every old writer has stopped, then retry. Re-running the extension cell reuses a completed continuation and never resets its progress. An incomplete failed extension is refused; preserve it and select another destination ID.

Test evidence and limits are recorded in VALIDATION.md. Live Colab execution and a real 13-hour session have not been tested.
""")
add("markdown", "## 1 · Settings and GPU check\nKeep `SOURCE_ID` as the original run. On later sessions keep all these settings the same.\n")
add("code", '''from pathlib import Path
PROJECT = Path("/content/drive/MyDrive/NeoHuman_R3GAN")
SCRATCH = Path("/content/NeoHuman_R3GAN_extend_work")
CODE_ROOT = Path("/content/NeoHuman_R3GAN_extend_code")
CODE_BUNDLE = PROJECT / "software" / "NeoHuman_R3GAN_Workspace.zip"
SOURCE_ID = "neohuman-colab-001"
CONTINUATION_ID = "neohuman-colab-001-13h"
TOTAL_HOURS = 13
''')
add("code", source_cells["colab-004"])
add("markdown", "## 2 · Mount Drive and load the original pinned software\nIf installation requests a restart, restart and rerun from section 1.\n")
add("code", source_cells["colab-006"])
setup = source_cells["colab-008"].replace("then rerun settings and cells 1–3.", "then rerun this continuation notebook from section 1.")
add("code", setup)
add("markdown", "## 3 · Define the full-state extension helper\nThis keeps the shared training code unchanged so the old checkpoint remains compatible.\n")
add("code", (root / "scripts" / "extend_training_budget.py").read_text(encoding="utf-8"))
add("markdown", "## 4 · Create or reopen the 13-hour continuation\nThe source training run must be stopped. This verifies the copied checkpoint before making the continuation resumable. A second run of this cell reuses the continuation's current checkpoint.\n")
add("code", '''CFG, PREPARED = extend_training_budget(PROJECT, SCRATCH, SOURCE_ID, CONTINUATION_ID, TOTAL_HOURS)
print("Continue this experiment:", CFG["experiment_id"])
print("Total training-hour limit:", CFG["schedule"]["budget_seconds"] / 3600)
''')
add("markdown", "## 5 · Run the GPU save/resume test\nRequired after each runtime restart. This uses a separate smoke-test experiment.\n")
add("code", '''from neo_r3gan.workflow import smoke_test, train, latest_verified, clear_stop, show_progress, generate_images
from IPython.display import display
from PIL import Image
SMOKE_REPORT = smoke_test(CFG, PROJECT, SCRATCH, PREPARED)
display(Image.open(SMOKE_REPORT["preview"]))
''')
add("markdown", "## 6 · Resume latest verified checkpoint\nSet `RESUME_RUN = True`, then run this cell. It restores the saved elapsed time and stops when the cumulative total reaches 13 hours. Keep the saved configuration unchanged. GPU quota and session limits still apply; saved progress can resume in a later GPU session.\n")
add("code", '''RESUME_RUN = False  # Change to True when ready to continue.
if RESUME_RUN:
    latest_verified(PROJECT, CFG)
    clear_stop(PROJECT, CFG)
    RESULT = train(CFG, PROJECT, SCRATCH, PREPARED, resume=True)
else:
    print("Set RESUME_RUN=True to continue the saved model to 13 total hours.")
''')
add("markdown", "## 7 · View results after training stops\nThe extension run writes new samples and checkpoints under its `-13h` folder. The original run's older samples remain in its original folder.\n")
add("code", 'RUN_FOLDER = show_progress(PROJECT, CFG)\nprint(RUN_FOLDER)\n')
add("markdown", "### Generate individual images on GPU\nFor CPU inference later, use the CPU notebook with `EXPERIMENT_ID = \"neohuman-colab-001-13h\"`.\n")
add("code", '''from neo_r3gan.data import grid
GENERATED = generate_images(PROJECT, SCRATCH, CFG, PREPARED, seeds=range(16))
display(grid([Image.open(path) for path in GENERATED], columns=4))
print("Saved:", GENERATED[0].parent)
''')
notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}, "accelerator": "GPU"}, "nbformat": 4, "nbformat_minor": 5}
output = root / "NeoHuman_R3GAN_Extend_13h.ipynb"
output.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
print(output)
