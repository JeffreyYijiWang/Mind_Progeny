"""Verified persistence, fail-closed writer locks, and bounded recovery retention."""
import copy
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from .io_utils import atomic_write, digest, read_json, safe_child, sha256, verified_copy, write_json


class RunLock:
    def __init__(self, run):
        self.run = Path(run)
        self.path = self.run / "writer.lock"
        self.token = uuid.uuid4().hex

    def __enter__(self):
        self.run.mkdir(parents=True, exist_ok=True)
        try:
            self.path.mkdir()
        except FileExistsError:
            raise RuntimeError(f"Run has an active or stale writer lock: {self.path}. Stop the other writer; stale locks require explicit release.") from None
        write_json(self.path / "owner.json", {"token": self.token, "host": socket.gethostname(), "pid": os.getpid(), "created": time.time()})
        return self

    def check(self):
        if read_json(self.path / "owner.json")["token"] != self.token:
            raise RuntimeError("Writer ownership changed; refusing to save")

    def __exit__(self, *_):
        self.check()
        (self.path / "owner.json").unlink()
        self.path.rmdir()


def release_stale_lock(run, token, confirmation):
    """Never inferred from a timeout: the caller must establish the old writer is dead."""
    if confirmation != "I stopped every writer for this experiment":
        raise ValueError("Explicit stale-lock confirmation required")
    path = Path(run) / "writer.lock"
    owner = read_json(path / "owner.json") if (path / "owner.json").exists() else {"token": "missing-owner"}
    if token != owner["token"]:
        raise ValueError("Lock token changed; inspect the current owner before retrying")
    (path / "owner.json").unlink(missing_ok=True)
    path.rmdir()


class Checkpoints:
    def __init__(self, run, local, keep=4, lock=None):
        self.run, self.local, self.keep, self.lock = Path(run), Path(local), keep, lock

    def manifest(self):
        candidates = [self.run / "manifest.json"] + list((self.run / "manifests").glob("*.json"))
        valid = []
        for path in candidates:
            try:
                envelope = read_json(path)
                if digest(envelope["manifest"]) == envelope["sha256"]:
                    valid.append(envelope["manifest"])
            except (OSError, ValueError, KeyError):
                continue
        if not valid:
            if any(path.exists() for path in candidates):
                raise IOError("No valid checkpoint manifest; refusing to overwrite recovery history")
            return {"schema": 1, "generation": 0, "entries": [], "latest": None}
        return max(valid, key=lambda v: v["generation"])

    def _publish(self, manifest):
        if self.lock:
            self.lock.check()
        manifest["generation"] += 1
        envelope = {"manifest": manifest, "sha256": digest(manifest)}
        # Immutable journal is recoverable even if replacing the pointer is interrupted.
        journal = f"manifest-{manifest['generation']:010d}.json"
        local = write_json(self.local / journal, envelope)
        verified_copy(local, self.run / "manifests" / journal)
        verified_copy(local, self.run / "manifest.json")
        for old in sorted((self.run / "manifests").glob("*.json"))[:-8]:
            old.unlink()

    def save(self, state, tags=("recovery",)):
        import torch
        if self.lock:
            self.lock.check()
        manifest = self.manifest()
        reason = "stop" if "stop" in tags else "scheduled"
        tags = sorted((set(tags) - {"stop"}) | {"recovery"})
        seconds, step = state["counters"]["training_seconds"], state["counters"]["step"]
        state_key = digest({"counters": state["counters"], "events": state["events"], "config": state["config_sha256"], "code": state["code"]})
        if manifest["entries"] and manifest["entries"][-1].get("state_key") == state_key:
            entry = manifest["entries"][-1]
            if sha256(safe_child(self.run, entry["path"])) == entry["sha256"]:
                entry["tags"] = sorted(set(entry["tags"]) | set(tags))
                self._publish(manifest)
                return entry
        name = f"{state['config']['experiment_id']}_step-{step:09d}_train-{int(seconds):08d}s_{uuid.uuid4().hex[:8]}.pt"
        folder = "milestones" if "milestone" in tags else "recovery"
        relative = f"checkpoints/{folder}/{name}"
        local = self.local / "checkpoints" / name
        try:
            atomic_write(local, lambda f: torch.save(state, f))
            checksum = verified_copy(local, self.run / relative)
            entry = {"path": relative, "sha256": checksum, "bytes": local.stat().st_size, "step": step, "training_seconds": seconds, "tags": tags, "reason": reason, "state_key": state_key, "created": time.time()}
            updated = copy.deepcopy(manifest)
            updated["entries"].append(entry)
            recoveries = [e for e in updated["entries"] if "recovery" in e["tags"]]
            for old in recoveries[:-self.keep]:
                old["tags"].remove("recovery")
            deletable = [e for e in updated["entries"] if not e["tags"]]
            updated["entries"] = [e for e in updated["entries"] if e["tags"]]
            updated["latest"] = {"path": relative, "sha256": checksum, "location": str((self.run / relative).resolve())}
            self._publish(updated)
            # Only after verified checkpoint AND manifest publication succeeds.
            for old in deletable:
                safe_child(self.run, old["path"]).unlink(missing_ok=True)
            # Local copies are staging, not a second retention store.
            local.unlink(missing_ok=True)
            return entry
        except Exception as exc:
            print(f"CHECKPOINT SAVE FAILED: {exc}. Previous verified checkpoints retained. Local candidate: {local}", file=sys.stderr, flush=True)
            raise

    def latest(self):
        manifest = self.manifest()
        for entry in reversed(manifest["entries"]):
            path = safe_child(self.run, entry["path"])
            try:
                if path.stat().st_size == entry["bytes"] and sha256(path) == entry["sha256"]:
                    return path, entry
            except OSError:
                pass
            print(f"WARNING: invalid checkpoint skipped: {path}", file=sys.stderr)
        raise FileNotFoundError("No successfully persisted, verified checkpoint is available")

    def load_latest(self):
        import torch
        path, entry = self.latest()
        local = self.local / "resume" / path.name
        verified_copy(path, local)
        # The format contains tensors + primitive containers, never pickled model objects.
        state = torch.load(local, map_location="cpu", weights_only=True)
        local.unlink(missing_ok=True)
        return state, entry

    def mark_keep(self, relative=None):
        if self.lock:
            self.lock.check()
        manifest = self.manifest()
        relative = relative or self.latest()[1]["path"]
        entry = next(e for e in manifest["entries"] if e["path"] == relative)
        if sha256(safe_child(self.run, relative)) != entry["sha256"]:
            raise ValueError("Cannot retain an unverified checkpoint")
        entry["tags"] = sorted(set(entry["tags"]) | {"manual"})
        self._publish(manifest)
        return entry
