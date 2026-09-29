# NeoHuman R3GAN workspace

Two runnable notebooks use **one shared training implementation**:

- `NeoHuman_R3GAN_Colab.ipynb`: GPU runtime, persistent `MyDrive/NeoHuman_R3GAN/` storage.
- `NeoHuman_R3GAN_Local.ipynb`: Windows/Linux NVIDIA GPU, configurable local storage.

Start with the editable settings near the top of either notebook. Follow its numbered cells. The supplied local notebook points to your 45-image ZIP in Downloads. The package does not publish or upload your images anywhere automatically. Training from scratch on 45 images can memorize the dataset; eight hours does not guarantee useful diversity or quality.

## Local setup

Install **Python 3.11**, **Git**, and an NVIDIA driver that supports the CUDA 12.8 PyTorch wheel. Extract the whole workspace package; keep the notebooks beside `neo_r3gan/`, `scripts/`, requirements, and `upstream-lock.json`.

Windows PowerShell, from the extracted folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_local.ps1
.\.venv\Scripts\python.exe -m jupyterlab NeoHuman_R3GAN_Local.ipynb
```

Linux with NVIDIA GPU:

```bash
bash scripts/setup_local.sh
.venv/bin/python -m jupyterlab NeoHuman_R3GAN_Local.ipynb
```

VS Code: open the workspace folder, install Microsoft's Python and Jupyter extensions, open the local notebook, and select the `.venv` Python environment as its notebook kernel. The setup scripts register `NeoHuman R3GAN (.venv)` inside that environment. No activation is needed when using the explicit Python paths above.

The scripts create an isolated environment and install PyTorch 2.7.1 CUDA 12.8 plus pinned application dependencies. Both notebooks check training-critical versions before running. `requirements.txt` pins the shared runtime; `requirements-notebook.txt` adds local JupyterLab. Python 3.11 is the tested local target; the notebooks accept 3.11–3.13. The validation folder records the resolved Windows environment, including transitive dependencies. Other platforms resolve platform-specific dependencies; this is not a universal fully hashed dependency lock. See [PyTorch's official version install commands](https://pytorch.org/get-started/previous-versions/#v271).

The GPU preflight reports OS, GPU, VRAM, CUDA availability, and a CUDA kernel check. Long runs require a working NVIDIA GPU on Windows/Linux. CPU is only an explicit developer diagnostic mode; Apple MPS, AMD and Intel accelerators are unsupported here. The small default 128×128 network and microbatch 2 are intended to fit a laptop GPU; the actual smoke test is the compatibility/memory check. On OOM, reduce microbatch to 1 before starting a new experiment. Match that configuration on both machines for a continuation.

Use the OS power settings to prevent sleep while plugged in, and select the desired lid-close behavior. Sleep interrupts training. No script changes power settings or circumvents runtime limits. If Windows reports `WinError 1455` while importing PyTorch, close unnecessary apps and check Windows virtual-memory settings; training has not started at that point. Never disable TLS certificate validation to fix download errors. On this machine, the Windows certificate store was needed (`pip --use-feature=truststore` with the preexisting pip 24; the setup's pip 25 uses system trust by default).

## Colab setup

1. Open/upload `NeoHuman_R3GAN_Colab.ipynb` in [Google Colab](https://colab.research.google.com/).
2. Select a GPU runtime. Run settings, runtime check, and Drive mount cells.
3. When prompted, upload **`dist/NeoHuman_R3GAN_Workspace.zip`**, the delivered software package. Cell 3 persists it under `MyDrive/NeoHuman_R3GAN/software/`, validates its file checksums, installs pinned dependencies, and fetches the pinned official source. If prompted to restart after changing an imported dependency, restart and rerun settings/cells 1–3.
4. Upload the **45-image ZIP** when cell 4 asks, or set `DATA_ZIP` to an existing Drive file. These are two different ZIPs: software and images.
5. Inspect the full preprocessing contact sheet, configure the experiment, and run the save/recovery smoke test. Only then enable a start or resume cell.

On later sessions the software is already on Drive. The unchanged original image ZIP is stored under `datasets/original/<sha256>.zip`; you can select it without uploading again. The runtime uses `/content/NeoHuman_R3GAN_work` for dataset copies and checkpoint staging. Neither recovery nor the cumulative time budget depends on retaining `/content`.

Colab GPU availability, session length and limits vary. No uninterrupted availability is promised. This workspace uses ordinary execution and Drive mounting; it includes no keep-alive or restriction-bypass scripts. See the [official Colab FAQ](https://research.google.com/colaboratory/faq.html).

## Extend an existing model to 13 total training hours

Use `NeoHuman_R3GAN_Extend_13h.ipynb` in a GPU Colab runtime. Stop the original training call, then run sections 1–5 in order. Section 4 creates a continuation named `neohuman-colab-001-13h` from the latest verified checkpoint of `neohuman-colab-001`; edit the IDs in section 1 if yours differ. It reuses the prepared dataset already on Drive. Set `RESUME_RUN = True` in section 6 to continue training. Do not use Run all.

The continuation carries the same G, D, EMA, Adam states, step/image counters, elapsed time, random states, sampler, preview noise and event thresholds. Only the experiment ID, total budget and config checksum change. The original experiment remains a backup. **Train only the continuation afterward.** The total is 13 hours: a checkpoint with eight saved hours has about five left. Re-running section 4 reopens the continuation without resetting progress. It rejects active/stale writer locks, unrelated destinations, and incomplete attempts rather than overwriting recovery data. Existing source checkpoint files and training configuration are unchanged.

This additive notebook embeds `scripts/extend_training_budget.py` and uses the original software ZIP on Drive. It does not change shared training-code identity or require replacing that ZIP. Future sessions can rerun the continuation notebook with the same settings. To use the ordinary training or CPU generation notebook afterward, select `neohuman-colab-001-13h` and its saved configuration where applicable. The time limit does not guarantee Colab will provide enough GPU quota in one session.

## Generate images in a CPU-only Colab session

Open `NeoHuman_R3GAN_CPU_Generate.ipynb` in Colab and run its four sections in order. It mounts Drive, loads the original software ZIP already stored there, installs the pinned dependencies using the CPU PyTorch index, and generates from the latest verified checkpoint for `neohuman-colab-001` (editable). If installation requests a restart, restart the runtime and rerun this CPU notebook from the top. No image ZIP, GPU preflight, training smoke test, or training resume is needed.

The helper loads the saved EMA generator onto CPU and writes PNGs, a preview grid and provenance under `experiments/<ID>/generated/cpu-step-<step>-<unique-id>/`. Start with four images; edit `NUM_IMAGES` and `START_SEED` in its last cell for another set. It does not alter training configuration, checkpoint state, counters or writer locks. Existing stale training locks do not need release for this read-only checkpoint access. The helper lives in `scripts/generate_cpu.py` and is embedded in the standalone notebook, so the existing Drive software ZIP need not be replaced and the shared training-code digest remains unchanged. CPU inference does not enable CPU training or promise bitwise CPU/GPU image equality.

## Dataset and experiment settings

`configs/example.json` is the same JSON format in both notebooks. It has no machine-specific paths. Edit notebook `PROJECT`, `SCRATCH`, and `DATA_ZIP` separately. All config fields are printed before training. Use a new ID for changed hyperparameters; the runner rejects mismatched configs on resume.

Preprocessing validates the exact expected count (45), rejects corrupt/animated/unsupported files and unsafe ZIP paths, applies EXIF orientation, composites transparency onto white, converts to RGB, resizes with Lanczos and pads to preserve the full composition (center cropping is also configurable). The contact sheet shows original versus training image for every image. SHA-256 records cover the original ZIP, every original/prepared image and the prepared ZIP. Exact duplicates are reported and retained. Prepared data is content-addressed, copied onto scratch disk, verified, then loaded into host RAM. Its checkpointed sampler uses no asynchronous workers or prefetching.

The default is a **compact custom R3GAN configuration**, not the paper's FFHQ preset or pretrained FFHQ model. It imports unmodified upstream Generator, Discriminator and `AdversarialTraining` loss at the locked commit. Upstream's own reference operators avoid a separate CUDA/compiler toolchain. Shared training uses FP32, Adam, EMA, mirroring and simple differentiable brightness/contrast augmentation. The learning rate, regularization and EMA timescale are fixed config values. There is no AMP/scaler, adaptive augmentation or hidden scheduler state. See [the official repository](https://github.com/brownvc/R3GAN) and the detailed [checkpoint audit](docs/CHECKPOINT_AUDIT.md).

```text
NeoHuman_R3GAN/                  # Drive or configurable local project
  software/                     # Colab's persisted workspace package
  datasets/
    original/                   # unchanged ZIP + original metadata
    prepared/<dataset_id>/      # images.zip, manifest.json, preprocessing.png
  configs/                      # experiment JSON and editable drafts
  smoke_reports/                # measured checkpoint/storage/recovery results
  experiments/<experiment_id>/
    config.json, dataset_manifest.json, code_version.json, environment.json
    run.json                    # active or sealed-for-transfer status
    writer.lock/                # present only while writing; stale after hard death
    checkpoints/recovery/       # rolling recovery files
    checkpoints/milestones/     # hourly files, no duplicate recovery copy
    manifest.json, manifests/   # latest verified location + checksummed journals
    samples/, generated/, logs/, exports/
```

## Train, stop and recover

The smoke cell runs two iterations of the actual configured model on the selected data, persists a checkpoint, then compares the third iteration with a new trainer restored from persistent storage. It checks tensor equality for both models, EMA, optimizer state, sampler and random states. Smoke experiments use separate IDs and do not consume the production time budget. Run it after every kernel restart. It reports actual checkpoint size, peak CUDA allocation and conservative retained storage estimates; add room for data, PNGs, smoke runs, manually kept checkpoints, and exports. Check Drive account quota separately.

Set `START_NEW_RUN=True` to start a new run. Its call occupies the notebook kernel. The defaults are:

| Event | Cumulative active training time |
|---|---:|
| Log status | 1 minute |
| Sample preview | 10 minutes |
| Full recovery checkpoint | 15 minutes |
| Retained milestone | 1 hour |
| Budget-complete checkpoint | approximately 8 hours |

Intervals are configurable in `schedule` before creating the run. Timing includes completed data fetch/augmentation/D/G/EMA iterations and synchronization, and excludes setup, maintenance, checkpoint transfers, samples and downtime. An iteration can cross a boundary, so a save or final stop may be slightly late. If several boundaries are crossed by one iteration, one checkpoint represents the current state; skipped intermediate model states cannot be reconstructed.

Interrupt once and wait for the cell to return. SIGINT/SIGTERM normally defer stopping until the D/G iteration completes; some notebook interrupts can instead abort mid-step, in which case no partially updated state is saved. Alternatively create `experiments/<ID>/STOP` from a separate terminal/file browser. A busy kernel cannot execute a second notebook stop cell. Abrupt runtime termination may prevent any final save. Recovery always relies on the last successfully persisted checkpoint.

On reconnect use the clearly labeled **Resume latest verified checkpoint** cell after setup, data preparation (or import), and smoke test. It verifies the checkpoint again before loading and restores cumulative training time. A saved three-hour run has about five hours remaining. It restores G, D, EMA, both Adam states, step/nimg counters, event thresholds, Python/NumPy/Torch CPU and selected CUDA RNG state, permutation/cursor/epoch/sampler RNG, and fixed preview noise. This is full state for this single-GPU implementation. It does not claim bitwise equality across different GPU models, drivers, OS, CUDA/PyTorch builds, or Python runtimes.

### Running the local notebook from a terminal

After local setup, this launcher executes a separate copy of the actual notebook, including its GPU smoke test. It chooses start or resume from the saved experiment state and records progress under the specified session directory:

```powershell
.\.venv\Scripts\python.exe -u scripts/run_local_notebook.py --config configs/local-recovery.json --session-dir workspace/sessions/my-training-session
```

`configs/local-recovery.json` uses experiment `neohuman-local-002` and recovery saves every **two active training minutes**; the eight-hour budget, ten-minute previews and hourly milestones are unchanged. Reuse the exact saved configuration when resuming. Use a fresh session directory for each launch. Do not start a second writer for the same experiment.

Read `training.stdout.log` when output is redirected there, or the launcher's terminal output, for increasing steps. The session's `status.json` records the current cell and `memory.json` records Windows memory headroom. The executed notebook snapshot updates between cells; during the long training cell, use the log and experiment checkpoint manifest for current progress.

On Windows, the launcher checks available committed memory before loading the kernel. A background check requests the trainer's existing safe stop when headroom falls below 2 GiB. This is a best-effort precaution, not a guarantee against a sudden allocation failure. Display-save failures are reported without terminating the training kernel. If `memory_stop.json` appears, inspect the latest checkpoint and free memory before resuming. A `STOP` file deliberately blocks automatic restart; remove that specific file only after verifying the previous writer has exited and intending to resume. No launcher changes Windows virtual-memory or power settings.

## Persistence and retention

Each filename includes experiment ID, step and cumulative seconds. Atomic local writes use a temporary file, flush/fsync and rename. Completed checkpoints are copied to a temporary destination, hashed, renamed and read back. Only after that succeeds is an immutable checksummed manifest journal published, then the current pointer. Resume can recover from an interrupted pointer update and skips damaged checkpoints with a visible warning. SHA-256 verifies integrity, not authenticity; import only bundles you trust.

The latest **four recovery entries**, **all hourly milestones**, **the final checkpoint**, and **manual keeps** remain. Checkpoints can have multiple tags; the same iteration serving recovery/milestone/final is stored once. The manual-keep cell adds a tag without copying weights. Stop checkpoints participate in rolling retention. New data and manifests persist before old unneeded files are deleted. Interrupted writes may leave unreferenced `.partial-*` files/orphans; they are ignored rather than risking deletion of useful state. Read-back through a Drive mount is the strongest check available here, not proof of remote backend replication. Save failures are printed and stop the training call; no hours of silent unsaved continuation.

## Parallel experiments and machine handoff

Independent parallel experiments use different IDs and folders; defaults distinguish Colab and local. They are separate models, not a combined training run. There is no automatic averaging or merging.

One experiment on another machine: stop the source, use **Move this experiment** to export a recovery bundle, copy it, and use **Import and resume** on the destination. It includes the latest full checkpoint, exact config, manifest, prepared image ZIP, dependency information and code fingerprints. The source is sealed after successful bundle staging and cannot resume from that folder. Import refuses an existing destination run and checks every file hash, schema, code identity, dataset identity and dependency versions. Re-run the smoke test there, then resume. To move back use an empty destination project root. Results-only export is available separately and does not seal a run; it includes all retained checkpoints, generated images, samples and logs.

Import a handoff on **one destination only**. Offline copies cannot provide a global distributed lease, and a Drive filesystem mount is not a reliable cross-host lock service. The fail-closed local directory lock prevents ordinary concurrent writers to one coherent storage root, and never expires automatically. Distinct IDs for parallel work and source sealing for transfer are required. Do not copy an active experiment folder and train both copies. To release a stale lock, first establish all previous writers stopped; the notebook requires its exact token and explicit confirmation. If a crash leaves a sealed source and `.zip.pending` export, inspect the source's `bundle_sha256` and pending file checksum before manually restoring the bundle's `.zip` name; never unseal a source that may already be imported elsewhere.

## Validation and rebuilding

See `VALIDATION.md` for what actually ran and what still requires Colab/Drive or long-run testing. To run checks in the isolated environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_dataset_gpu.py "C:\Users\Jeffr\Downloads\DATA SET-20260926T223837Z-1-001.zip"
```

`scripts/build_notebooks.py` regenerates both notebooks from shared templates. `scripts/package_workspace.py` creates the software ZIP with a checksummed inventory; no data, weights, environment, or upstream source is bundled. The upstream repository is fetched directly at the locked commit; its terms apply separately. Nothing here grants additional rights to upstream code or models.
