# Separate StyleGAN2-ADA experiment

Use only this folder's `.venv`. Preserve the root R3GAN environment and its running
24-hour job. The user has now explicitly authorized a separate 256px GPU run for
eight hours. A hidden background launch is authorized for this run. Use the explicit
--allow-stopped-predecessor option only for a user-requested switch; it still requires
a stopped original run, a verified checkpoint and a released writer lock.
Keep NVIDIA's pinned vendor checkout unmodified. Compatibility changes belong in
`compat.py`. Never load an untrusted pickle. Read README.md before changing training.
