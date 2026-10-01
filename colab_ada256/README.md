# Google Colab: NeoHuman StyleGAN2-ADA at 256×256

Installation troubleshooting (2026-09-29): step 3 now streams all pip output,
records `/content/NeoHuman_ADA256_code/installation.log`, refreshes pip inside the
isolated environment and disables download caching. If an older notebook shows
only `CalledProcessError`, paste `Repair-Colab-Install.py` into a new Colab cell
and run it, then rerun step 3. It does not load a model or alter Drive snapshots.
The generic traceback alone does not establish the cause; inspect the printed
pip error if installation still fails. Python 3.13 wheels exist for pinned Torch
2.7.1+cu128 on Linux x86_64 in the official PyTorch index.

Upload **NeoHuman_ADA256_Colab.ipynb** at https://colab.research.google.com/ using
File > Upload notebook. This single notebook includes the 45 prepared images and
helper code. No companion ZIP or local Python environment is needed. Because the
images are embedded, sharing the notebook also shares that dataset.

1. Select Runtime > Change runtime type > GPU (T4 if offered).
2. Run steps 1–4 to unpack, mount Drive, install and validate.
3. Leave step 5's recovery switches off on your first run.
4. In step 6, set `START_TRAINING = True` only when ready and run that cell.
5. Use the notebook's interrupt button once for a graceful stop; wait for the
   completed snapshot to be verified on Drive before disconnecting.
6. Step 8 generates images after training stops. Select `DEVICE = 'cpu'` there
   if only CPU runtime is available.

Default: native 256×256 StyleGAN2-ADA, official FFHQ256 transfer weights, 45 RGB
inputs, microbatch 4/effective batch 8, 100 kimg (12,500 batch updates) per segment,
and a 2-hour wall-time stop request. The stop is checked at maintenance ticks,
so saving may occur later than the exact time limit. GPU memory uses the existing
85%/1-GiB-headroom policy. This caps PyTorch-managed allocations only, not the
driver or other processes; GPU fit and maximum utilization are not guaranteed.
Reference operations avoid compiling CUDA extensions; they may be slower than
NVIDIA's fused implementations. TF32 applies only to GPUs supporting it.

Snapshots go to `MyDrive/NeoHuman_ADA256_Colab/runs/`. Each segment retains four
recent snapshots plus 10-kimg milestones. Budget roughly 5 GB of Drive quota per
100-kimg segment; older segments remain. Dataset reads/training happen in local
Colab scratch, and completed snapshots are copied to Drive with checksum
verification before a receipt is published. Unverified `.pkl` files are not valid
recovery points. Colab termination or Drive failures can lose the work since the
last verified snapshot. Drive mounting/copying cannot promise transactional
behavior across multiple runtimes; use only one writer for this project.

On reconnection, rerun setup, inspect verified snapshots, explicitly clear a stale
lock only after stopping the old runtime, and set `RESUME_SNAPSHOT`. These restore
weights, **not** optimizer/RNG/ADA state. Counters and budgets restart in a new
segment. R3GAN `.pt` checkpoints cannot be resumed by StyleGAN2-ADA.

This separate cloud workflow uses Google's GPU. It does not interact with your
local 24-hour run or remove its launch guard. Nothing is scheduled or started by
creating this file. CPU and static tests are recorded in VALIDATION.md; an actual
Colab GPU run has not been performed.

Sources: [NVIDIA implementation](https://github.com/NVlabs/stylegan2-ada-pytorch),
[paper](https://arxiv.org/abs/2006.06676),
[Google Colab runtime and Drive limits](https://research.google.com/colaboratory/faq.html).
