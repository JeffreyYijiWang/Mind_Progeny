"""Execute the delivered local notebook on real data, with bounded test runs."""
import json
import sys
import time
from pathlib import Path
import nbformat
from nbclient import NotebookClient

root = Path(__file__).resolve().parents[1]
nb = nbformat.read(root / "NeoHuman_R3GAN_Local.ipynb", as_version=4)
project = root / "test-output" / ("notebook-" + time.strftime("%Y%m%d-%H%M%S"))
for cell in nb.cells:
    if cell.cell_type != "code":
        continue
    text = cell.source
    if "PROJECT = CODE_ROOT" in text:
        text = text.replace('PROJECT = CODE_ROOT / "workspace"', "PROJECT = Path(" + repr(str(project)) + ")")
        text = text.replace('EXPERIMENT_ID = "neohuman-local-001"', 'EXPERIMENT_ID = "notebook-validation"')
    if "START_NEW_RUN = False" in text:
        text = text.replace("START_NEW_RUN = False", "START_NEW_RUN = True")
        text = text.replace("resume=False)", "resume=False, max_steps=2)")
    if "RESUME_RUN = False" in text:
        text = text.replace("RESUME_RUN = False", "RESUME_RUN = True")
        text = text.replace("resume=True)", "resume=True, max_steps=1)")
    if "EXPORT_RESULTS = False" in text:
        text = text.replace("EXPORT_RESULTS = False", "EXPORT_RESULTS = True")
    cell.source = text
client = NotebookClient(nb, timeout=300, kernel_name="neohuman-r3gan", resources={"metadata": {"path": str(root)}})
start = time.monotonic()
try:
    client.execute()
finally:
    output = root / "validation" / "NeoHuman_R3GAN_Local.executed.ipynb"
    output.parent.mkdir(exist_ok=True)
    nbformat.write(nb, output)
errors = [o for c in nb.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"]
report = {"passed": not errors, "code_cells": sum(c.cell_type == "code" for c in nb.cells), "elapsed_seconds": time.monotonic() - start,
          "production_steps_in_test_run": 3, "smoke_iterations": "2 + 1 uninterrupted + 1 resumed", "project": str(project), "executed_notebook": str(output),
          "test_overrides": "Isolated output root/ID; start and resume enabled with max_steps 2 and 1; results export enabled. Original delivered notebook remains unmodified."}
(root / "validation" / "notebook-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
