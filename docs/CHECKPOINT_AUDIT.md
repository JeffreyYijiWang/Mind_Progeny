# Upstream checkpoint inspection and recovery contract

Inspected `brownvc/R3GAN` commit `19a7ddf463fbac2bd39b4c1c73d63f1c441c7403`:

- [`training/training_loop.py`](https://github.com/brownvc/R3GAN/blob/19a7ddf463fbac2bd39b4c1c73d63f1c441c7403/training/training_loop.py): snapshots contain G, D, G_ema, training-set kwargs, cur_nimg, D_opt_state and G_opt_state. Restore copies model parameters and optimizer states, and initializes cur_nimg from the snapshot. The claim that these snapshots are weight-only would be incorrect.
- The same loop initializes RNG seeds and the InfiniteSampler anew; it does not serialize Python/NumPy/Torch RNG state or the dataloader sampler cursor/prefetch state. `batch_idx`, tick/event state, preview noise and elapsed timing are initialized afresh. Snapshot writes are ordinary pickle writes, without atomic replacement, verified Drive copy, retention policy or persistent manifest. Cumulative active training hours are not a recovery field.
- [`R3GAN/Trainer.py`](https://github.com/brownvc/R3GAN/blob/19a7ddf463fbac2bd39b4c1c73d63f1c441c7403/R3GAN/Trainer.py): official relativistic paired loss and R1/R2 zero-centered penalties. The shared runner calls these exact gradient-accumulation functions.
- [`R3GAN/Networks.py`](https://github.com/brownvc/R3GAN/blob/19a7ddf463fbac2bd39b4c1c73d63f1c441c7403/R3GAN/Networks.py), `Resamplers.py` and `FusedOperators.py`: official architecture and supplied reference implementations. The loader selects upstream's own reference classes before importing Networks. The checkout is not patched.

The supplied runner replaces the orchestration and serialization layer, using direct state dictionaries loaded with `torch.load(weights_only=True)`. It does not load upstream pickle files as if they were compatible exact-resume files.

| State | Stored/restored by this workspace |
|---|---|
| Generator, discriminator, EMA | Full parameter and buffer state dictionaries |
| Optimizers | Both Adam moments, steps and param groups |
| Training counters | Completed D/G iteration, nimg, cumulative active seconds |
| Timers | Next sample, recovery, milestone and log thresholds |
| Randomness | Python, legacy NumPy, Torch CPU, cuda:0 |
| Data ordering | Permutation, cursor, epochs, separate sampler RNG |
| Preview | Fixed noise tensor |
| Configuration | Complete JSON and checksum |
| Compatibility | Schema, shared-module hash, upstream commit, backend, core versions, dataset manifest hash |

The runner uses FP32 and fixed hyperparameters: no AMP scaler, learning-rate scheduler object, adaptive augmentation controller, distributed ranks or async workers exist to restore. Augmentation draws use the saved Torch RNG; its constant probability is in config. GPU kernels synchronize before timing. Incomplete iterations are never serialized. The primary safe stop path is a signal request serviced at an iteration boundary; unexpected exceptions mid-step leave the previous persisted state intact.

This format is portable between these two notebooks using the same code/config/data. Same-environment deterministic tests check exact next-step tensor equality. Full-state restoration across machines can still yield different floating-point trajectories due to GPU/driver/OS/library differences. Lost unsaved work is replayed after a hard crash and its compute time cannot be known from the previous checkpoint; the budget counts recovered completed training progress, not unknowable work performed after the last save.
