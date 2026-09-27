"""Content-addressed datasets, explicit preprocessing, and resumable sampling."""
import hashlib
import io
import json
import math
import tempfile
import warnings
import zipfile
from pathlib import Path, PurePosixPath
from PIL import Image, ImageOps, __version__ as pillow_version
from .io_utils import digest, read_json, sha256, verified_copy, write_json

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def grid(images, columns=4):
    images = list(images)
    if not images:
        raise ValueError("No images to preview")
    w, h = images[0].size
    canvas = Image.new("RGB", (columns * w, math.ceil(len(images) / columns) * h), (28, 28, 28))
    for i, im in enumerate(images):
        canvas.paste(im, ((i % columns) * w, (i // columns) * h))
    return canvas


def preprocess(image, settings):
    image = ImageOps.exif_transpose(image)
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, tuple(settings["alpha_background"]) + (255,))
    image = Image.alpha_composite(background, rgba).convert("RGB")
    size = (settings["resolution"], settings["resolution"])
    if settings["crop"] == "pad":
        return ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color=tuple(settings["alpha_background"]), centering=(0.5, 0.5))
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def prepare_dataset(zip_path, project, scratch, settings):
    """Read ZIP members without extraction; persist source + prepared artifact hashes."""
    zip_path, project, scratch = map(Path, (zip_path, project, scratch))
    scratch.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(zip_path)
    recipe = dict(settings, implementation="exif-rgb-alpha-resize-lanczos-v1", pillow=pillow_version)
    dataset_id = digest({"source_sha256": source_hash, "recipe": recipe})[:24]
    target = project / "datasets" / "prepared" / dataset_id
    original = project / "datasets" / "original" / f"{source_hash}.zip"
    if not original.exists() or sha256(original) != source_hash:
        verified_copy(zip_path, original)
    write_json(original.with_suffix(".json"), {"original_filename": zip_path.name, "sha256": source_hash})
    if (target / "manifest.json").exists():
        manifest = read_json(target / "manifest.json")
        verify_prepared(target, manifest)
        return target
    records, previews, ignored = [], [], []
    with tempfile.TemporaryDirectory(dir=scratch, prefix="prepare-") as tmp:
        local = Path(tmp)
        with zipfile.ZipFile(zip_path) as source, zipfile.ZipFile(local / "images.zip", "w", compression=zipfile.ZIP_STORED) as output:
            members = sorted(source.infolist(), key=lambda x: x.filename)
            if len(members) > 10000 or sum(m.file_size for m in members) > 4 * 1024**3:
                raise ValueError("ZIP exceeds 10,000 entries or 4 GiB uncompressed")
            seen = set()
            for member in members:
                name = PurePosixPath(member.filename.replace("\\", "/"))
                if name.is_absolute() or ".." in name.parts or ":" in str(name) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Unsafe ZIP member: {member.filename}")
                if member.is_dir() or "__MACOSX" in name.parts or name.name.startswith("."):
                    ignored.append(member.filename)
                    continue
                if name.suffix.lower() not in EXTENSIONS:
                    raise ValueError(f"Unsupported ZIP member {member.filename}; use only supported image files")
                if member.filename in seen or member.file_size > 256 * 1024**2:
                    raise ValueError(f"Duplicate filename or oversized member: {member.filename}")
                seen.add(member.filename)
                raw = source.read(member)
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", Image.DecompressionBombWarning)
                        with Image.open(io.BytesIO(raw)) as check:
                            check.verify()
                        with Image.open(io.BytesIO(raw)) as im:
                            if getattr(im, "n_frames", 1) != 1:
                                raise ValueError("Animated/multi-page images are unsupported")
                            im.load()
                            size, mode = list(im.size), im.mode
                            prepared = preprocess(im, settings)
                            # Side-by-side letterboxed original and exact training crop.
                            before = ImageOps.pad(ImageOps.exif_transpose(im).convert("RGB"), (128, 128))
                            pair = Image.new("RGB", (256, 128))
                            pair.paste(before, (0, 0))
                            pair.paste(prepared.resize((128, 128), Image.Resampling.NEAREST), (128, 0))
                            previews.append(pair)
                except Exception as exc:
                    raise ValueError(f"Invalid image {member.filename}: {exc}") from exc
                buffer = io.BytesIO()
                prepared.save(buffer, format="PNG")
                png = buffer.getvalue()
                prepared_name = f"{len(records):05d}.png"
                output.writestr(zipfile.ZipInfo(prepared_name, (1980, 1, 1, 0, 0, 0)), png)
                records.append({"source": member.filename, "source_sha256": hashlib.sha256(raw).hexdigest(), "original_size": size, "original_mode": mode,
                                "prepared": prepared_name, "prepared_sha256": hashlib.sha256(png).hexdigest()})
            if len(records) != settings["expected_images"]:
                raise ValueError(f"Expected {settings['expected_images']} images; decoded {len(records)}")
            output.writestr(zipfile.ZipInfo("dataset.json", (1980, 1, 1, 0, 0, 0)), json.dumps({"labels": None}))
        duplicate_count = len(records) - len({r["source_sha256"] for r in records})
        manifest = {"schema": 1, "dataset_id": dataset_id, "source_sha256": source_hash, "recipe": recipe, "count": len(records), "images": records,
                    "ignored": ignored, "exact_duplicate_count": duplicate_count, "prepared_zip_sha256": sha256(local / "images.zip")}
        write_json(local / "manifest.json", manifest)
        grid(previews, columns=3).save(local / "preprocessing.png")
        for filename in ("images.zip", "preprocessing.png", "manifest.json"):
            verified_copy(local / filename, target / filename)
    if duplicate_count:
        print(f"WARNING: {duplicate_count} duplicate image(s) retained and recorded in manifest")
    print(f"Validated {len(records)} images. Prepared dataset: {target}")
    return target


def verify_prepared(path, manifest=None):
    path = Path(path)
    manifest = manifest or read_json(path / "manifest.json")
    if manifest["schema"] != 1 or sha256(path / "images.zip") != manifest["prepared_zip_sha256"]:
        raise ValueError("Prepared dataset checksum/schema mismatch")
    with zipfile.ZipFile(path / "images.zip") as z:
        if len(manifest["images"]) != manifest["count"]:
            raise ValueError("Dataset count mismatch")
        for item in manifest["images"]:
            raw = z.read(item["prepared"])
            if hashlib.sha256(raw).hexdigest() != item["prepared_sha256"]:
                raise ValueError("Prepared image checksum mismatch")
    return manifest


def stage_dataset(prepared, scratch):
    prepared, scratch = Path(prepared), Path(scratch)
    manifest = verify_prepared(prepared)
    working = scratch / "datasets" / manifest["dataset_id"]
    for name in ("images.zip", "manifest.json"):
        verified_copy(prepared / name, working / name)
    verify_prepared(working, manifest)
    return working


class ImageStream:
    """All images in host RAM; exact permutation/cursor, no worker prefetch state."""
    def __init__(self, path, seed):
        import torch
        import numpy as np
        manifest = verify_prepared(path)
        with zipfile.ZipFile(Path(path) / "images.zip") as z:
            arrays = []
            for record in manifest["images"]:
                with Image.open(io.BytesIO(z.read(record["prepared"]))) as im:
                    arrays.append(np.asarray(im.convert("RGB"), dtype=np.uint8).copy())
        self.images = torch.from_numpy(np.stack(arrays)).permute(0, 3, 1, 2).contiguous()
        self.generator = torch.Generator(device="cpu").manual_seed(seed)
        self.order = torch.randperm(len(arrays), generator=self.generator)
        self.position, self.epochs = 0, 0

    def next(self, count, device, mirror):
        import torch
        indices = []
        while len(indices) < count:
            if self.position == len(self.order):
                self.order = torch.randperm(len(self.order), generator=self.generator)
                self.position = 0
                self.epochs += 1
            take = min(count - len(indices), len(self.order) - self.position)
            indices.extend(self.order[self.position:self.position + take].tolist())
            self.position += take
        batch = self.images[indices].to(device=device, dtype=torch.float32) / 127.5 - 1
        if mirror:
            flips = torch.rand((count, 1, 1, 1), device=device) < 0.5
            batch = torch.where(flips, batch.flip(3), batch)
        return batch

    def state_dict(self):
        return {"rng": self.generator.get_state(), "order": self.order.clone(), "position": self.position, "epochs": self.epochs}

    def load_state_dict(self, state):
        import torch
        if sorted(state["order"].tolist()) != list(range(len(self.images))) or not 0 <= state["position"] <= len(self.images):
            raise ValueError("Invalid sampler state")
        self.generator.set_state(state["rng"].cpu())
        self.order = state["order"].cpu().to(torch.int64)
        self.position, self.epochs = state["position"], state["epochs"]
