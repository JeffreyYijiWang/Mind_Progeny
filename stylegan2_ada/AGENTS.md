# Separate StyleGAN2-ADA experiment

Use only this folder's `.venv`. Preserve the root R3GAN environment and its running
24-hour job. Preparation and CPU validation are authorized; model execution or GPU
training is not authorized until the user explicitly starts it later. Never bypass
the predecessor completion guard. No automatic scheduling or background launch.
Keep NVIDIA's pinned vendor checkout unmodified. Compatibility changes belong in
`compat.py`. Never load an untrusted pickle. Read README.md before changing training.
