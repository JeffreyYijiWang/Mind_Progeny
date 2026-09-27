# Validation record — September 26, 2026

The package was built and tested in this workspace. **The eight-hour production run has not been started.**

## Actual user dataset

- Input: `C:\Users\Jeffr\Downloads\DATA SET-20260926T223837Z-1-001.zip`.
- All **45 PNG images** decoded and passed validation; **0 exact duplicates**.
- Original ZIP SHA-256: `08d993120444b535192ce871c236196618db2e99c28c166a04d4687a3e33460e`.
- Final preprocessing: EXIF orientation, RGB/white alpha composition, Lanczos resize and white padding to **128×128**, preserving the complete image. Center cropping remains an option. The full 45-image contact sheet was visually inspected; padding avoids cutting off tall and wide drawings/diagrams. Small text and fine lines still lose detail at this resolution.
- Prepared dataset ID: `3b086ec44583738d88b35edb`. The prepared images and preview are under `workspace/datasets/prepared/<ID>/` locally. The software ZIP excludes image data.
- Machine-readable evidence: `validation/dataset-report.json`.

## Real GPU training and recovery

Windows build 26200; NVIDIA GeForce RTX 4070 Laptop GPU, 8 GiB VRAM, driver 596.08; Python 3.11.9; PyTorch 2.7.1+cu128; NumPy 2.2.6; Pillow 11.2.1.

The actual final configuration and all 45 images were used. Two complete D/G/EMA iterations ran, then a full checkpoint was saved to the persistent project directory and read back. An uninterrupted third step was compared against a fresh trainer restored from that checkpoint and run for one step. **G, D, EMA, both Adam states, data sampler and all stored random states matched bit for bit.** Counters, saved cumulative training time, event thresholds and fixed preview noise were also checked. The data ordering crosses an epoch boundary during this test.

- Full checkpoint: **16,711,887 bytes / 15.94 MiB**.
- Conservative checkpoint-only storage estimate for eight hours: **0.202 GiB**, or **0.233 GiB with two staging files**. This assumes 13 retained files as an upper bound; tags can reduce duplicates. Add original/prepared data, smoke runs, samples, exports and manual keeps.
- Peak PyTorch allocated GPU memory during this smoke test: **0.597 GiB**. This excludes CUDA context overhead and other applications; it is not total device usage or a long-run memory guarantee.
- Evidence: `validation/gpu-smoke-report.json` and the saved smoke run referenced there.

The first attempts hit Windows `WinError 1455` / memory-allocation errors. After the user closed other apps, GPU testing succeeded. The read-only diagnostic reported a 31.68 GiB system commit limit; long runs still need adequate system memory and ordinary laptop power/thermal management.

## Automated checks

**13 tests passed** in 20.57 seconds. One nonfatal PyTorch warning initialized a cuBLAS context during the integration test. Evidence: `validation/pytest.xml`.

Tests exercised:

- Four rolling recoveries, permanent hourly/manual entries, rolling stop saves, and no duplicate combined recovery/milestone/final file.
- Injected copy and manifest-publication failures preserving previous recovery files.
- Corrupted latest checkpoint plus corrupted manifest pointer recovering an earlier verified checkpoint.
- Writer conflict rejection and explicit stale-lock release.
- Deterministic dataset preparation, expected counts, unsafe ZIP/corrupt image rejection, padding behavior and invalid config rejection.
- Both notebook schemas and every code cell's Python syntax.
- Exact full-state continuation using a small CPU diagnostic model, accelerated event intervals, final budget stop, and no extra training after resuming an exhausted budget.
- A real CUDA handoff between separate local project roots: source sealing, import, refusal to overwrite/import twice, one resumed training step with increasing cumulative time, seeded EMA PNG generation, results export, and tampered bundle rejection.

## Local notebook execution

**All 18 code cells of the delivered local notebook executed successfully**, including real-image preparation, configured GPU smoke test, new training, resume, progress display, image generation and results export. The execution took 36.11 seconds. Test-only overrides used a separate output root/ID, limited training to two steps plus one resumed step, and enabled results export. The delivered notebook retains safe, explicit start/resume/export flags.

Evidence: `validation/notebook-report.json`; the executed notebook with outputs is available locally at `validation/NeoHuman_R3GAN_Local.executed.ipynb`. That executed copy contains image previews and is intentionally excluded from the software ZIP. `validation/environment-windows-py311-cu128.txt` records the resolved environment.

## Still untested

- An actual Google Colab session, Google Drive mounting, remote quota/disconnection behavior and Google's backend durability. Colab cells were syntax/schema checked; equivalent persistence logic was tested locally with fault injection.
- Cross-machine/cross-GPU floating-point continuation. The handoff test used separate roots on the same machine. Full-state portability is implemented; numerical identity across different hardware/software is not promised.
- Real abrupt power loss, a hard runtime kill, laptop sleep or an actual eight-hour session. Unit tests exercised failure paths and time-based events with short intervals.
- Long-run convergence, image quality, diversity and memorization. Samples after a few iterations only verify the pipeline. Forty-five heterogeneous images are a small dataset, and this compact model is not the paper's full FFHQ configuration.

The notebooks require a fresh smoke test on each runtime before a long run. Check Drive quota and keep the laptop awake through your normal OS settings.
