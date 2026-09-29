# NeoHuman: separate StyleGAN2-ADA, native 1024 x 1024

## Choose 256 or 1024

Two independent resolution profiles are now prepared. Both use all 45 originals,
their own resolution-matched NVIDIA starting weights and datasets, and the same
85%/1-GiB-headroom allocator policy. **Neither starts automatically.**

| Profile | Notebook | Manual launcher | Microbatch / effective batch |
| --- | --- | --- | --- |
| 256 x 256 | `StyleGAN2_ADA_256_Local.ipynb` | `Start-StyleGAN2-ADA-256.cmd` | 4 / 8 |
| 1024 x 1024 | `StyleGAN2_ADA_1024_Local.ipynb` | `Start-StyleGAN2-ADA.cmd` | 1 / 4 |

The 256 profile uses NVIDIA's `paper256` architecture and FFHQ256 transfer
weights, gamma 1, minibatch-statistics group 4 and path batch shrink 2. It produces
native 256px output. Its lower pixel count permits a larger configured microbatch
and is expected to reduce memory demand; actual speed, utilization and GPU fit
remain untested. TF32 and channels-last FP16 are enabled in both profiles. CUDA
uses available NVIDIA cores without a manually selected core count.

Use `config-256.json` to change the new 256 run's duration. Its 100-kimg budget
means 12,500 batch updates at effective batch 8, not hours. The original 1024
configuration remains in `config.json`. Choose the matching profile when resuming
or generating; snapshots cannot be exchanged between resolutions. Run folders
include the resolution. A shared writer lock prevents both profiles from training
or generating simultaneously. Both retain the original 24-hour completion guard.

```powershell
& .venv/Scripts/python.exe manage.py --profile 256 plan
# Only later, after the current 24-hour run completes:
& .venv/Scripts/python.exe -u manage.py --profile 256 train --execute
& .venv/Scripts/python.exe manage.py --profile 256 generate --execute --snapshot "runs/YOUR-256-RUN/network-snapshot-000010.pkl" --seeds 0,1,2,3
```

`--profile` goes **before** the command; omitting it keeps the 1024 default.
`Stop-StyleGAN2-ADA.cmd` works for either profile. Prepared plans are
`data/prepared-plan-256.json` and `data/prepared-plan-1024.json`; contact sheets
likewise include their resolution in the filename. The following original
configuration description refers to 1024 unless otherwise specified.

### Intel and NVIDIA roles

NVIDIA performs GAN computation; Intel can handle selected desktop applications.
Their cores and VRAM are not pooled. See **[GPU-SPLIT.md](GPU-SPLIT.md)** and
`Open-GPU-Preferences.cmd` for Windows app preferences. No Windows preference,
driver or active training process was changed. You choose which desktop apps to
assign to Intel, and changes may require restarting those apps later.

This experiment prepares NVIDIA's **Training Generative Adversarial Networks with
Limited Data** (StyleGAN2-ADA) for the existing 45 original images. It has its own
environment, data, configuration, pretrained weights and output folders. It does
not use or change the R3GAN model or environment. **No training or generation is
automatically started.** The launchers refuse model execution until the original
`neohuman-local-002-24h` has finished its 24-hour budget, saved a checksum-verified
checkpoint, and released its writer lock. A stopped or crashed early run does not
count as completion. Nothing is scheduled to run when that job ends.

## Start later

Open `StyleGAN2_ADA_1024_Local.ipynb` for the guided workflow, or double-click
**Start-StyleGAN2-ADA.cmd** after the original 24-hour job finishes. Keep the charger
connected and plugged-in sleep set to Never. The launcher checks the predecessor,
source, dataset and weights before loading the new model. Its window stays open
to display progress and any error. Do not launch the upstream vendor scripts
directly: they do not include this project's guard or memory adaptations.

To stop the new run, double-click **Stop-StyleGAN2-ADA.cmd** from another window.
Leave the training window open until it prints `Exiting...`. The stop is checked
at the next maintenance tick, approximately every 1,000 image presentations, so
it is not immediate. Ctrl+C in the training terminal also requests this graceful
stop. Closing the terminal or forcing an interrupt may lose work since the last
completed snapshot. This stop launcher does not stop the original R3GAN.

PowerShell commands, **from this folder**, using this environment:

```powershell
& .venv/Scripts/python.exe manage.py status
& .venv/Scripts/python.exe -u manage.py train --execute
# In a second terminal, when needed:
& .venv/Scripts/python.exe manage.py stop
```

## What is configured

| Setting | Prepared value |
| --- | --- |
| Architecture | NVIDIA StyleGAN2, full 1024px synthesis network; paper1024 base |
| Transfer source | NVIDIA FFHQ 1024px StyleGAN2 checkpoint |
| Dataset | All 45 original images, fitted and white-padded to 1024px; no crop |
| GPU profile | One GPU; microbatch 1; effective batch 4 through accumulation |
| Precision | Upstream FP16 at high-resolution blocks; FP32 elsewhere |
| Throughput | TF32 permitted for eligible FP32 operations; channels-last FP16 convolutions |
| Memory budget | PyTorch allocator capped at 85% of VRAM or launch-time free VRAM minus 1 GiB, whichever is smaller |
| ADA | Target 0.6; translations and isotropic scale; upright orientation preserved |
| R1 regularization | Gamma 2.0, upstream lazy regularization |
| Path regularization | Batch shrink 1, preventing an empty batch at microbatch 1 |
| Minibatch statistics | Group size 1; reduces cross-image statistics versus the paper |
| Data loader | Zero worker processes, no pinned-memory queue |
| Preview and snapshots | Four fixed preview images; every 1 kimg, and on graceful exit |
| Initial budget | 100 kimg = 100,000 real-image presentations = 25,000 batch updates |
| Metrics | Automatic FID disabled; 45 training images do not provide a useful reference population |

`config.json` sets the **new** experiment's budget with `total_kimg`. Its default
100 kimg is a bounded first experiment, not a prediction of quality or a time
limit. It is unrelated to the old model's 24-hour budget. Review the saved images
as training progresses; do not assume the final snapshot is the best one.

The 45 inputs are a very small, varied collection. ADA mitigates discriminator
overfitting; it cannot guarantee varied, detailed results with only 45 images.
The FFHQ starting weights depict faces, so they are a domain mismatch for drawings
and diagrams. This is an explicit transfer-learning starting point, not a model
already trained on these images. Text accuracy is not guaranteed. The network
generates 1024px images directly; this is not output upscaling. Inputs smaller
than 1024px are enlarged during preparation without adding source detail.

## Memory and compatibility

NVIDIA's published setup recommends at least 12 GB of GPU memory. This laptop has
an RTX 4070 Laptop GPU with 8 GB. The prepared settings reduce memory demand, but
**a successful 1024px GPU training step and peak memory fit have not been tested**
while the original model is running. Training may still run out of memory,
especially during regularization or snapshot creation. The launcher reports the
failure and exits; it does not silently lower resolution, restart, or fall back
to CPU. A free-memory check alone cannot establish that the run will fit.

Training and generation both apply the allocator cap **before loading models onto
the GPU**. On an otherwise free 8 GiB GPU, the maximum PyTorch allocation budget
is approximately 6.8 GiB. Other applications using VRAM at startup reduce it.
This makes an out-of-memory error possible sooner, deliberately preserving
headroom. It is not a system-wide cap: CUDA context/driver allocations and other
programs are outside PyTorch's control, and free memory can change after startup.
An allocation that exceeds the PyTorch cap fails; no retry or automatic batch
increase is performed. The previous verified snapshots remain available, but an
out-of-memory failure does not guarantee a new checkpoint.

CUDA schedules work across available cores; there is no useful “use every core”
switch. TF32 enables eligible Tensor Core operations at reduced mantissa precision,
so results may differ from strict FP32. Channels-last FP16 is enabled to improve
convolution throughput where supported. Actual utilization and speed still need
measurement after the original run finishes. Microbatch 1 and accumulation remain
in place. cuDNN benchmark search stays off to avoid its transient workspace peaks.
GPU allocation/free-memory readings are saved to each run's `status.json` at
maintenance ticks. Reference operations may still be a throughput bottleneck.

The policy is in `config.json` under `gpu`. See PyTorch's
[allocator limit documentation](https://docs.pytorch.org/docs/2.7/generated/torch.cuda.memory.set_per_process_memory_fraction.html)
and [TF32 documentation](https://docs.pytorch.org/docs/2.7/notes/cuda.html#tensorfloat-32-tf32-on-ampere-and-later-devices).

The separate Python 3.11 / PyTorch 2.7.1+cu128 environment uses NVIDIA's reference
bias activation and resampling implementations. They still execute on the GPU
during training, but do not compile CUDA extensions. `compat.py` updates the
grid-sampling backward call for this PyTorch version and uses native convolution
autograd. This avoids changing the laptop's drivers, CUDA toolkit or root
environment. Reference operations can be substantially slower and can use more
memory than NVIDIA's compiled kernels. These local adaptations are **not an
official NVIDIA-validated combination or an exact reproduction of paper settings**.

## Inspect and generate images later

Each manual launch creates a new `runs/<timestamp>-<id>/` containing `log.txt`,
`stats.jsonl`, `fakes*.png`, `network-snapshot-*.pkl`, metadata and checksum receipts.
The `kimg` column means thousands of training image presentations, not hours.
Open successive previews and look for recognizable structure, variety, and signs
of copying the originals. Compare snapshots using the same generation seeds.

After training has stopped, choose a snapshot that has an adjacent
`.verified.json` receipt. Replace the example path below with your actual run:

```powershell
& .venv/Scripts/python.exe manage.py generate --execute --snapshot "runs/YOUR-RUN/network-snapshot-000010.pkl" --seeds 0,1,2,3 --truncation 0.7
```

Images are generated individually and saved as 1024x1024 PNGs in a new
`generated/` folder. A matching generation manifest records weights, seeds and
truncation. Generation shares the new project's lock, so it cannot run concurrently
with this project's training. Lower truncation often reduces variation.

## Continue from a snapshot

```powershell
& .venv/Scripts/python.exe -u manage.py train --execute --resume "runs/YOUR-RUN/network-snapshot-000010.pkl"
```

These are NVIDIA **network-weight snapshots**, not the root R3GAN's full-state
recovery checkpoints. Continuation restores G, D and G_ema, but starts fresh
optimizers, random state, ADA adaptation and a new kimg counter. `total_kimg`
therefore applies to each new segment; 100 does not mean a cumulative lifetime
limit across resumes. The old run folder remains intact. Only completed,
checksum-verified local snapshots are accepted by these launchers. A process or
machine crash during snapshot writing can leave an incomplete `.pkl` without a
receipt; use an earlier verified snapshot. Keep enough disk space: full-network
snapshots can total tens of GB over a long run. No snapshots are automatically
deleted. The launcher reserves an estimated disk budget before starting (about
44 GiB for the initial 100-kimg segment); actual snapshot sizes can vary.

## Recreate preparation (no model execution)

Run `powershell -ExecutionPolicy Bypass -File .\Setup.ps1` from this folder.
It creates only this folder's `.venv`, downloads the pinned NVIDIA source and
official transfer weights, prepares the original 45 images, and runs a CPU-only
configuration check. It neither loads pretrained pickle objects nor trains.
The original archive's checksum is in `config.json`. If it is moved, update
`original_zip` to its location while retaining the matching checksum.

`data/contact-sheet.jpg` shows the prepared inputs; `data/neohuman45-1024.json`
records source dimensions, per-image hashes and resizing. `data/prepared-plan.json`
records resolved upstream options. Dataset, weights, environment, vendor checkout
and outputs are ignored by Git; the download/setup instructions reproduce them.
Only load trusted model pickle files. Download receipts establish local integrity,
not a publisher-signed model checksum. NVIDIA's source/license remains in the
pinned vendor checkout. This project is a **local Windows notebook**, not a
self-contained Colab notebook.

Research and implementation:

- [NVIDIA paper: Training Generative Adversarial Networks with Limited Data](https://arxiv.org/abs/2006.06676)
- [Official NVIDIA StyleGAN2-ADA PyTorch repository](https://github.com/NVlabs/stylegan2-ada-pytorch)
- Pinned commit: `d72cc7d041b42ec8e806021a205ed9349f87c6a4`.

See `VALIDATION.md` for performed checks and deliberately deferred GPU validation.
