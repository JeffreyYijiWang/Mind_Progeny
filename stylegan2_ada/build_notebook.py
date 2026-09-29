"""Rebuild the safe, output-free local notebook using only the standard library."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)})


def code(text):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                  "source": text.splitlines(keepends=True)})


md("""# NeoHuman — NVIDIA StyleGAN2-ADA, 1024 × 1024

Separate local experiment using all 45 images. **Prepared only: training is OFF.**
Wait for the existing 24-hour R3GAN to finish. No scheduled or automatic launch.

[NVIDIA paper](https://arxiv.org/abs/2006.06676) · [Official code](https://github.com/NVlabs/stylegan2-ada-pytorch)

The 8 GB laptop profile uses one-image microbatches, accumulation, mixed precision,
TF32/channels-last acceleration, and reference operations. Both training and
generation cap PyTorch-managed allocations at 85% of VRAM or free VRAM minus
1 GiB at startup, whichever is smaller. This excludes driver/other-app allocations;
exceeding the cap stops the run with an error. GPU fit is not yet verified. Native 1024px output and
good results from 45 inputs are different questions; detail/diversity are not guaranteed.
See `README.md` and `VALIDATION.md` in this folder.
""")
code("""from pathlib import Path
import json, subprocess, sys

HERE = Path.cwd().resolve()
PROJECT = HERE if (HERE / 'manage.py').exists() and (HERE / 'upstream-lock.json').exists() else HERE / 'stylegan2_ada'
assert (PROJECT / 'manage.py').exists(), 'Open the notebook from Mind_Progeny or its stylegan2_ada folder.'
PYTHON = PROJECT / '.venv' / 'Scripts' / 'python.exe'
PROFILE = '1024'
assert PYTHON.exists(), 'Run Setup.ps1 in the stylegan2_ada folder first.'

def command(*args):
    # Each command uses the isolated environment, regardless of notebook kernel.
    with subprocess.Popen([str(PYTHON), '-u', str(PROJECT / 'manage.py'), '--profile', PROFILE, *args], cwd=PROJECT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
        except KeyboardInterrupt:
            if args and args[0] == 'train':
                subprocess.run([str(PYTHON), str(PROJECT / 'manage.py'), 'stop'], cwd=PROJECT, check=True)
                print('Stop requested. Waiting for the next maintenance tick and snapshot...', flush=True)
                for line in process.stdout:
                    print(line, end='', flush=True)
            else:
                raise
        result = process.wait()
    if result:
        raise RuntimeError(f'Command stopped with exit code {result}; read its message above.')

print('Separate project:', PROJECT)
print('Separate Python:', PYTHON)
""")
md("## 1. Check readiness (no GPU or model execution)")
code("command('status')\ncommand('plan')\n")
md("## 2. Inspect the 45 prepared inputs")
code("""from IPython.display import display, Image
display(Image(filename=str(PROJECT / 'data' / 'contact-sheet.jpg')))
manifest = json.loads((PROJECT / 'data' / 'neohuman45-1024.json').read_text())
print('Images:', manifest['count'], '| resolution:', manifest['resolution'], '| enlarged inputs:', manifest['upscaled_count'])
""")
md("""## 3. Review the NEW run's budget

`total_kimg = 100` means 100,000 image presentations (25,000 batch updates at batch 4).
It is **not 100 hours or the previous model's 24-hour limit**. This is an initial
experiment budget, not a quality guarantee. If changing it before a run, edit
`config.json` in this folder and rerun the plan cell. Review previews while training.
""")
code("print((PROJECT / 'config.json').read_text())\n")
md("""## 4. Start manually AFTER the original 24-hour run finishes

Change `START_TRAINING` to `True` only when ready to run this new model. The launcher
still checks the original run's completion. The cell remains busy during training.
If GPU memory is insufficient, it exits; no automatic lower-resolution fallback.
Keep the charger connected and sleep set to Never.

To stop while this cell is busy, double-click `Stop-StyleGAN2-ADA.cmd` in this folder.
Keep the notebook/kernel/window open until the run saves and exits. The stop is
checked at the next maintenance tick (roughly every 1,000 image presentations).
Do not use kernel shutdown as a save command.
""")
code("""START_TRAINING = False
RESUME_SNAPSHOT = None  # Optional absolute path to a verified snapshot from THIS project.
if START_TRAINING:
    args = ['train', '--execute']
    if RESUME_SNAPSHOT:
        args += ['--resume', str(Path(RESUME_SNAPSHOT).resolve())]
    command(*args)
else:
    print('Training stays OFF. Change START_TRAINING only when you are ready.')
""")
md("""## 5. Inspect saved previews and snapshots

Network snapshots restore weights only. A later `--resume` starts fresh optimizers,
ADA adaptation and counters in a separate run folder; the budget applies again.
Choose snapshots by visual quality, not merely by the highest step number.
""")
code("""runs = sorted((PROJECT / 'runs').glob('*')) if (PROJECT / 'runs').exists() else []
for run in runs:
    print(run)
    verified = sorted(run.glob('network-snapshot-*.verified.json'))
    print('  Verified snapshots:', len(verified))
    if verified:
        print('  Latest:', str(verified[-1]).replace('.verified.json', '.pkl'))
    previews = sorted(run.glob('fakes*.png'))
    if previews:
        display(Image(filename=str(previews[-1]), width=640))
if not runs:
    print('No new training run has started yet.')
""")
md("""## 6. Generate native 1024px PNGs after training has stopped

Set `SNAPSHOT` to the full `.pkl` path you selected above. Change `GENERATE` to
`True` only when ready. This loads the new model on the GPU and generates one image
at a time; it cannot run alongside this project's training. Nothing generates on
Run All with the defaults. Results go to a new `generated/` subfolder.
""")
code("""GENERATE = False
SNAPSHOT = None  # Paste the full verified .pkl path here as a quoted string.
SEEDS = '0,1,2,3'
if GENERATE:
    assert SNAPSHOT, 'Choose a verified snapshot first.'
    command('generate', '--execute', '--snapshot', str(Path(SNAPSHOT).resolve()), '--seeds', SEEDS, '--truncation', '0.7')
else:
    print('Generation stays OFF.')
""")

notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3 (local)", "language": "python", "name": "python3"},
             "language_info": {"name": "python", "version": "3.11"}}, "nbformat": 4, "nbformat_minor": 5}
for i, cell in enumerate(cells):
    cell["id"] = f"ada-{i:02d}"
for resolution in ('1024', '256'):
    import copy
    output = copy.deepcopy(notebook)
    for cell in output['cells']:
        text = ''.join(cell['source'])
        text = text.replace("data' / 'contact-sheet.jpg", "data' / 'contact-sheet-1024.jpg")
        if resolution == '256':
            text = text.replace('1024', '256').replace('25,000', '12,500').replace('batch 4', 'batch 8')
            text = text.replace('one-image microbatches', 'four-image microbatches')
            text = text.replace("PROJECT / 'config.json'", "PROJECT / 'config-256.json'").replace('`config.json`', '`config-256.json`')
        cell['source'] = text.splitlines(keepends=True)
    (ROOT / f"StyleGAN2_ADA_{resolution}_Local.ipynb").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("Created safe local notebook; no cells executed.")
