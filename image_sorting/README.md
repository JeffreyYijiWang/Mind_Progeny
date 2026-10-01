# ShuffleSnap sorting for generated GAN images

Uses [Kyle McDonald's ShuffleSnap](https://github.com/kylemcdonald/shufflesnap),
pinned to PyPI 0.3.0. Installed in this folder's separate `.venv`; the root training
environment is unchanged. This tool uses CPU only, with two numerical/native
threads. It does not load GANs, touch checkpoints, or require a GPU.

The input is a folder of individual `seed-*.png` files. Appearance features are
computed from 32px grayscale ink, edges and horizontal/vertical profiles. PCA
reduces those features to two dimensions; ShuffleSnap assigns them to distinct
grid cells. Similar patterns tend to group together. This is **not a quality
ranking, semantic classifier, or image enhancement**. The 2D projection loses
information; retained variance is recorded. Pixel colors/content are not edited
in the original files. Rendering uses white padding for non-square inputs.

## Use later

Drag a generated-image folder onto `Sort-Generated-Images.cmd`. This defaults to
10 columns with enough rows for the images (100 images produces 10x10).
Outputs go to a new `workspace/exports/shufflesnap-...` folder.

Or run, from this folder:

```powershell
& .venv/Scripts/python.exe sort_images.py --input "C:/path/to/generated/images" --columns 10 --rows 10
& .venv/Scripts/python.exe sort_images.py --comparison "../workspace/exports/checkpoint-grids-20260929-110205-82cfb6" --columns 10 --rows 10
```

Each sorted set includes `sorted-grid.png`, `cell-map.csv` and `sort.json`. Row and
column numbers start at 1; seeds and source hashes let you identify every tile.
The source files and existing grids are never renamed, deleted or overwritten.

Comparison mode produces two different overviews:

- `sorted-comparison.png`: each checkpoint is sorted independently. Corresponding
  positions do **not** necessarily have the same seed.
- `matched-seed-comparison.png`: every checkpoint uses the last checkpoint's
  sorted seed layout, allowing comparison of the same seed at the same position.

All output grids/maps are bundled in `sorted-grids-and-maps.zip`. The original
images stay in their original directories. A maximum of 4096 inputs keeps this
simple dense PCA implementation bounded; it is not ShuffleSnap's own size limit.

Recreate the environment with `powershell -ExecutionPolicy Bypass -File Setup.ps1`.
The pinned release supports a `margin` argument; we explicitly use zero to match
the normalized [0,1] points. Unreleased upstream main changes this API, so upgrades
require checking the coordinate convention. The package includes its upstream
MIT license. No source code from that package was copied into the training code.
