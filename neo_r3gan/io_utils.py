"""Small, checked filesystem operations; no final filename is written in place."""
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, writer):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial-" + uuid.uuid4().hex)
    try:
        with tmp.open("wb") as f:
            writer(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if os.name != "nt":
            try:
                fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError:
                pass  # Some mounted filesystems do not support directory fsync.
    finally:
        tmp.unlink(missing_ok=True)
    return path


def write_json(path, value):
    return atomic_write(path, lambda f: f.write(canonical(value) + b"\n"))


def verified_copy(source, target):
    source, target = Path(source), Path(target)
    expected = sha256(source)
    if source.resolve() == target.resolve():
        return expected
    def copy(f):
        with source.open("rb") as s:
            shutil.copyfileobj(s, f, 8 * 1024 * 1024)
        f.flush()
        if sha256(f.name) != expected:
            raise IOError(f"Transfer checksum failed: {target}")
    atomic_write(target, copy)
    if sha256(target) != expected:
        raise IOError(f"Read-back checksum failed: {target}")
    return expected


def safe_child(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"Unsafe relative path: {relative}")
    return path

