from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import re

EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".svg"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def natural_key(value):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r"(\d+)", str(value))]


@dataclass(frozen=True)
class Asset:
    path: Path
    asset_id: str
    sha256: str

    def metadata(self):
        return {"asset_id": self.asset_id, "original_name": self.path.name,
                "source_path": str(self.path.resolve()), "sha256": self.sha256}


def discover(folder, recursive=False, order=None):
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError(f"Input folder does not exist: {root}")
    files = sorted((p for p in (root.rglob("*") if recursive else root.iterdir())
                    if p.is_file() and p.suffix.lower() in EXTENSIONS),
                   key=lambda p: (natural_key(p.relative_to(root)), str(p)))
    if order is not None:
        by_name = {p.relative_to(root).as_posix(): p for p in files}
        unknown = set(order) - by_name.keys()
        if unknown:
            raise ValueError(f"Order contains missing/unsupported inputs: {sorted(unknown)}")
        files = [by_name[name] for name in order]
    if not files:
        raise ValueError("No supported images or SVGs; use PNG/JPEG/TIFF/BMP/SVG")
    assets = []
    for path in files:
        digest = sha256(path)
        name_id = hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest()[:6]
        assets.append(Asset(path, digest[:12] + "-" + name_id, digest))
    return assets
