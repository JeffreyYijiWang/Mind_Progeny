"""Fetch and verify the exact official source; never reset user modifications."""
import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lock = json.loads((root / "upstream-lock.json").read_text())
target = Path(os.environ.get("NEOHUMAN_R3GAN_SOURCE", root / "vendor" / "R3GAN"))
git = ["git"] + (["-c", "http.sslBackend=schannel"] if os.name == "nt" else [])
if not target.exists():
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(git + ["clone", "--no-checkout", lock["url"], str(target)], check=True)
    subprocess.run(git + ["-C", str(target), "checkout", "--detach", lock["commit"]], check=True)
head = subprocess.check_output(git + ["-C", str(target), "rev-parse", "HEAD"], text=True).strip()
dirty = subprocess.check_output(git + ["-C", str(target), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
if head != lock["commit"] or dirty:
    raise SystemExit(f"Refusing modified or wrong checkout: {target}; expected {lock['commit']}")
print(f"Verified official R3GAN {head} at {target}")
