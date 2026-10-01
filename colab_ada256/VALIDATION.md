# Colab notebook preparation validation

2026-09-29 installer update: regenerated the notebook with streamed pip stdout and
stderr, an installation log, pip refresh and no-cache package installs. All eight
offline tests still pass, including compilation of every updated notebook cell.
The reported Colab failure is not reproduced or diagnosed yet: its traceback
omitted pip's actual error. Verified the official index lists the pinned Python
3.13/Linux x86_64 Torch wheel. No cloud installation success is claimed.

Prepared locally on 2026-09-28. No cloud account was accessed, no Google Drive
mount was performed, and no GPU/model training or generation was started.

Command:

```powershell
& stylegan2_ada/.venv/Scripts/python.exe -m unittest discover -s colab_ada256 -p test_colab.py -v
```

**8 tests passed.**

- Compiled every notebook code cell; outputs are empty and execution counts null.
- Verified training, generation, stale-lock release and STOP-clearing switches
  default to false.
- Extracted the embedded payload in memory; confirmed helper source matches the
  saved files and the embedded archive checksum matches the approved 45-image
  256px dataset.
- Resolved NVIDIA's actual pinned upstream 256px configuration on CPU: 45 images,
  256px, microbatch 4/effective batch 8, half-channel paper256 architecture, TF32,
  safe path-regularization batch and disabled metrics. CUDA initialization was
  explicitly blocked. Source-commit subprocess output was mocked for the temporary
  fixture; the separate existing pinned checkout supplies the imported code.
- Exercised copy/checksum/receipt round trips, corruption rejection and simulated
  Drive-copy failure using temporary local files. Failed copies preserved local
  candidates and published no verified receipt.
- Verified latest-four plus 10-kimg retention, lock exclusion/cleanup, explicit
  stale-lock confirmation, live-PID rejection and execution opt-in guards.

These are offline tests, not Google Drive integration tests. Linux/Colab Python
environment creation, package downloads there, GPU forward/backward execution,
memory fit, throughput, actual Colab interruption handling, GPU/CPU image
generation and snapshot recovery under real Drive failures remain untested.
Weights-only continuation does not restore optimizers, RNG, ADA adaptation or
cumulative counters. Runtime termination can lose work since the last verified
Drive snapshot.

NVIDIA source commit: `d72cc7d041b42ec8e806021a205ed9349f87c6a4`.

Embedded dataset SHA256:
`94e0779302dc87b9e6a1b4dab009ab7a5f091cb584896b1527d791b08f76ec96`.

Expected FFHQ256 download SHA256 (verified from the earlier local download):
`7aa4ddeee38e007ce92a1a0bccd386fc6abba6b5c8692bdbe813d3f1987c0722`.
