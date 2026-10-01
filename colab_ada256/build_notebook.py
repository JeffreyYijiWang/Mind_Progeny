"""Build a self-contained Colab notebook, including the user's prepared dataset."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT.parent / "stylegan2_ada"
cfg = {"total_kimg": 100, "microbatch": 4, "session_hours": 2,
       "gpu": {"max_allocator_fraction": 0.85, "reserve_mib": 1024,
               "allow_tf32": True, "fp16_channels_last": True}}
files = {
    "cloud_runner.py": (ROOT / "cloud_runner.py").read_bytes(),
    "compat.py": (LOCAL / "compat.py").read_bytes(),
    "gpu_policy.py": (LOCAL / "gpu_policy.py").read_bytes(),
    "neohuman45-256.zip": (LOCAL / "data/neohuman45-256.zip").read_bytes(),
    "dataset-manifest.json": (LOCAL / "data/neohuman45-256.json").read_bytes(),
    "contact-sheet.jpg": (LOCAL / "data/contact-sheet-256.jpg").read_bytes(),
    "config.json": json.dumps(cfg, indent=2).encode(),
}
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for name, data in files.items():
        z.writestr(name, data)
payload = buffer.getvalue()
encoded = base64.b64encode(payload).decode()
payload_sha = hashlib.sha256(payload).hexdigest()
cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)})


def code(text, hidden=False):
    cells.append({"cell_type": "code", "execution_count": None, "outputs": [],
                  "metadata": {"cellView": "form"} if hidden else {}, "source": text.splitlines(keepends=True)})


md("""# NeoHuman — StyleGAN2-ADA 256×256 for Google Colab

**This notebook contains your 45 prepared images and its helper code.** Upload
this single `.ipynb` through **File → Upload notebook** in Google Colab.
Select **Runtime → Change runtime type → GPU** (T4 if offered). It uses Google's
hosted NVIDIA GPU, not your laptop's NVIDIA or Intel graphics. Your local 24-hour
GAN is independent and is not accessed or changed by this notebook.

Training and generation default to **OFF**, including when you choose Run all.
GPU availability and uninterrupted runtime are not guaranteed by Colab.

[NVIDIA paper](https://arxiv.org/abs/2006.06676) ·
[NVIDIA implementation](https://github.com/NVlabs/stylegan2-ada-pytorch) ·
[Colab runtime limits](https://research.google.com/colaboratory/faq.html)

This is an adapted, unexecuted cloud workflow. CPU checks were performed locally;
no Colab GPU training, Drive mount, or cloud checkpoint transfer has been tested.
""")
md("""## 1. Unpack the included code and 45 images

Run this once per new runtime. No model is loaded. The data is fitted and
white-padded to 256×256, preserving the full compositions. Images are unchanged
from the prepared local 256 dataset; no contrast edits have been applied.
""")
code("""#@title Unpack the included dataset and helpers
from pathlib import Path
import base64, hashlib, io, json, os, shutil, signal, subprocess, sys, zipfile
assert Path('/content').is_dir(), 'Open this in a Google Colab hosted runtime.'
WORK = Path('/content/NeoHuman_ADA256_code')
WORK.mkdir(parents=True, exist_ok=True)
PAYLOAD = '""" + encoded + """'
raw = base64.b64decode(PAYLOAD)
assert hashlib.sha256(raw).hexdigest() == '""" + payload_sha + """', 'Embedded payload checksum failed.'
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for member in z.infolist():
        target = (WORK / member.filename).resolve()
        assert target.is_relative_to(WORK.resolve()) and not member.is_dir()
        target.write_bytes(z.read(member))
del PAYLOAD, raw
print('Unpacked 45 images and helpers; no model started.')
""", hidden=True)
md("## 2. Mount Google Drive and choose the separate project folder")
code("""from google.colab import drive
drive.mount('/content/drive')
PROJECT = Path('/content/drive/MyDrive/NeoHuman_ADA256_Colab')
PROJECT.mkdir(parents=True, exist_ok=True)
print('All durable snapshots will be saved under:', PROJECT)
print('Use this same Google account and project folder when reconnecting.')
""")
md("""## 3. Install the isolated runtime and fetch NVIDIA source/starting weights

This can take several minutes and downloads several GB of Python/CUDA packages.
It uses a separate Python environment; it does not replace Colab's notebook kernel.
The NVIDIA FFHQ256 starting weights are trained on faces, which is a domain
mismatch for this mixed drawing dataset. They are a starting point, not a promise
of image quality. Downloading does not run the model.
""")
code((ROOT / 'Repair-Colab-Install.py').read_text(encoding='utf-8') + """
VENDOR = WORK / 'vendor'
COMMIT = 'd72cc7d041b42ec8e806021a205ed9349f87c6a4'
if not VENDOR.exists():
    subprocess.run(['git', 'clone', 'https://github.com/NVlabs/stylegan2-ada-pytorch.git', str(VENDOR)], check=True)
    subprocess.run(['git', '-C', str(VENDOR), 'checkout', '--detach', COMMIT], check=True)
assert subprocess.check_output(['git', '-C', str(VENDOR), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
import urllib.request
def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024**2), b''):
            h.update(chunk)
    return h.hexdigest()
WEIGHTS_SHA = '7aa4ddeee38e007ce92a1a0bccd386fc6abba6b5c8692bdbe813d3f1987c0722'
WEIGHTS = WORK / 'ffhq256.pkl'
if not WEIGHTS.exists():
    url = 'https://nvlabs-fi-cdn.nvidia.com/stylegan2-ada-pytorch/pretrained/transfer-learning-source-nets/ffhq-res256-mirror-paper256-noaug.pkl'
    temporary = WORK / 'ffhq256.partial'
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as f:
        shutil.copyfileobj(response, f)
    assert file_sha(temporary) == WEIGHTS_SHA, 'Starting-weight checksum mismatch.'
    temporary.replace(WEIGHTS)
assert file_sha(WEIGHTS) == WEIGHTS_SHA
print('Source and starting weights ready; no model loaded.')
""")
md("""## 4. Review settings and validate the plan on CPU

Default: **100 kimg** (100,000 image presentations, 12,500 batch updates), with a
**2-hour wall-time stop request per session**. These are separate limits; whichever
is reached first ends the segment. Time limits and manual stops are checked at the
next maintenance tick, so they can overshoot by a tick plus saving time.

Microbatch 4 processes four images together; effective batch 8 uses accumulation.
If a later GPU run runs out of memory, stop it, set microbatch to 2 or 1, then start
a new segment from a verified snapshot. There is no automatic retry. TF32 (where
supported), mixed precision and channels-last are enabled. The allocator budget
is at most 85% of VRAM, with at least 1 GiB launch-time headroom. Other apps/driver
allocations are outside that cap. Neither maximum utilization nor fitting is guaranteed.
""")
code("""TOTAL_KIMG = 100
MAX_SESSION_HOURS = 2.0
MICROBATCH = 4
CFG = json.loads((WORK / 'config.json').read_text())
CFG.update(total_kimg=TOTAL_KIMG, session_hours=MAX_SESSION_HOURS, microbatch=MICROBATCH)
(WORK / 'config.json').write_text(json.dumps(CFG, indent=2))

def run_command(command, *args):
    argv = [str(PYTHON), '-u', str(WORK / 'cloud_runner.py'), command, '--project', str(PROJECT), *args]
    with subprocess.Popen(argv, cwd=WORK, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1, start_new_session=True) as process:
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
        except KeyboardInterrupt:
            if command == 'train':
                (PROJECT / 'STOP').write_text('Manual notebook interrupt requested a graceful stop.\\n')
                process.send_signal(signal.SIGINT)
                print('Stop requested. Keep this cell/runtime open while it saves to Drive.', flush=True)
                for line in process.stdout:
                    print(line, end='', flush=True)
            else:
                process.terminate()
                process.wait()
                raise
        code = process.wait()
    if code:
        raise RuntimeError(f'Command exited with code {code}; read the error above. No automatic retry.')

run_command('plan')
from IPython.display import Image, display
display(Image(filename=str(WORK / 'contact-sheet.jpg')))
print(CFG)
""")
md("""## 5. Inspect saved snapshots and recover a stale lock only if necessary

On a new runtime, rerun steps 1–4. The helper code/dataset live in temporary
`/content`; completed snapshots live in Drive. Do not use two notebooks to write
to this project at the same time. A disconnect can leave `writer.lock` behind.
Before releasing it, stop/delete the **old runtime**; never release a live writer.
This step is off by default and does not restart training.
""")
code("""snapshots = sorted((PROJECT / 'runs').glob('*/*.verified.json'), key=lambda p: json.loads(p.read_text())['created'])
for receipt in snapshots:
    print(str(receipt).replace('.verified.json', '.pkl'))
if not snapshots:
    print('No verified training snapshots yet.')

CONFIRM_OLD_RUNTIME_STOPPED = False
CLEAR_PREVIOUS_STOP_REQUEST = False
owner_path = PROJECT / 'writer.lock/owner.json'
if owner_path.exists():
    owner = json.loads(owner_path.read_text())
    print('Existing writer lock:', owner)
    if CONFIRM_OLD_RUNTIME_STOPPED:
        run_command('release-lock', '--token', owner['token'], '--confirmation', 'I stopped the old Colab runtime')
if CLEAR_PREVIOUS_STOP_REQUEST:
    assert not (PROJECT / 'writer.lock').exists(), 'Stop the previous writer before clearing STOP.'
    (PROJECT / 'STOP').unlink(missing_ok=True)
""")
md("""## 6. Start training only when ready

Change `START_TRAINING` to True. For continuation, paste a verified Drive `.pkl`
path from step 5 into `RESUME_SNAPSHOT`; otherwise the first run uses FFHQ256.

**Continuation restores network weights only.** Optimizers, random state, ADA
adaptation and kimg counters restart. The kimg/time budgets apply to each new
segment, not the accumulated lifetime of the model. R3GAN `.pt` files are incompatible.

To stop: use **Interrupt execution once** (the cell's stop button) and wait for
`Verified on Drive` and `Exiting...`. Interrupting requests a save at the next
maintenance tick; it is not instantaneous. Do not disconnect/delete the runtime
to request a save. A second interrupt or forced termination may lose unsaved work.
If Colab kills the runtime unexpectedly, use the last verified Drive snapshot.

Snapshots are published after roughly each 1,000 image presentations and graceful
exit. Each segment retains its latest four and 10-kimg milestones. At 100 kimg,
allow roughly 5 GB of free Drive quota per segment; older segments remain saved.
Drive quota cannot be reliably inferred from the mount's free-disk report.
""")
code("""START_TRAINING = False
RESUME_SNAPSHOT = None  # e.g. '/content/drive/MyDrive/NeoHuman_ADA256_Colab/runs/.../network-snapshot-....pkl'
if START_TRAINING:
    args = ['--execute']
    if RESUME_SNAPSHOT:
        args += ['--resume', RESUME_SNAPSHOT]
    run_command('train', *args)
else:
    print('Training is OFF. Change START_TRAINING only when ready.')
""")
md("## 7. Inspect saved previews")
code("""for folder in sorted((PROJECT / 'runs').glob('*')):
    print(folder)
    previews = sorted(folder.glob('fakes*.png'))
    if previews:
        display(Image(filename=str(previews[-1]), width=512))
    if (folder / 'result.json').exists():
        print((folder / 'result.json').read_text())
""")
md("""## 8. Generate native 256×256 images from a verified snapshot

Stop training first. Choose a `.pkl` from step 5, set `GENERATE = True`, and run
this cell. Use `DEVICE = 'cpu'` for slow generation on a CPU runtime when GPU time
is unavailable. Training itself does not fall back to CPU. Keep the same seeds
when comparing checkpoints. Images and their generation metadata are saved to Drive.
""")
code("""GENERATE = False
SNAPSHOT = None
DEVICE = 'cuda'  # Change to 'cpu' for CPU generation.
SEEDS = '0,1,2,3'
if GENERATE:
    assert SNAPSHOT, 'Paste a verified snapshot path from step 5.'
    run_command('generate', '--execute', '--snapshot', SNAPSHOT, '--device', DEVICE, '--seeds', SEEDS)
else:
    print('Generation is OFF.')
""")
for i, cell in enumerate(cells):
    cell["id"] = f"colab-ada256-{i:02d}"
notebook = {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"colab": {"name": "NeoHuman_ADA256_Colab.ipynb", "provenance": []},
                         "accelerator": "GPU", "kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "language_info": {"name": "python"}}}
target = ROOT / "NeoHuman_ADA256_Colab.ipynb"
target.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Built {target.name}: {target.stat().st_size:,} bytes; includes 45 images. Nothing executed.")
