# NVIDIA training and Intel desktop graphics

Detected on this laptop: NVIDIA GeForce RTX 4070 Laptop GPU and Intel Iris Xe
Graphics. This CUDA GAN uses NVIDIA for all model computation. Intel cannot add
cores or memory to the NVIDIA CUDA device. No cross-vendor distributed training
or memory pooling is implemented. CPU image preparation remains on the CPU.

Windows can separately assign ordinary desktop apps to Intel, which may leave
more NVIDIA memory available. This is an app preference, not a driver split.
No driver, BIOS/MUX, active app, or Windows graphics preference was changed during
preparation. The following manual steps let you choose which apps to move:

1. Open `Open-GPU-Preferences.cmd`, or Settings > System > Display > Graphics.
2. Select your browser or other desktop app, then its graphics options.
3. Choose the option explicitly showing **Intel Iris Xe** (usually Power saving).
4. Restart that app when convenient for the preference to take effect. Do not
   close the terminal or notebook running your current 24-hour training job.
5. If adding the new training executable, its path is
   `stylegan2_ada\.venv\Scripts\python.exe`; select NVIDIA / High performance.
   The GAN already explicitly uses CUDA, irrespective of display preferences.

Some displays are physically wired to NVIDIA; Windows preferences cannot change
that wiring. GPU numbers in Task Manager need not match CUDA indices. Compare GPU
names and use Task Manager's GPU-engine column/compute graphs when checking usage.
Neither this setup nor Windows preferences can guarantee 100% core occupancy.

[Microsoft's per-app graphics preference instructions](https://support.microsoft.com/en-us/windows/hardware/display-graphics/optimizations-for-windowed-games-in-windows-11)
