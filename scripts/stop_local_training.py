"""Request a completed-iteration checkpoint and stop without killing any process."""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from neo_r3gan.checkpoints import Checkpoints
from neo_r3gan.config import load_config
from neo_r3gan.io_utils import read_json, write_json


def request_stop(session=None):
    project = ROOT / "workspace"
    if session is None:
        pointer = project / "current-local-session.json"
        if not pointer.is_file():
            raise FileNotFoundError("No launched local session is recorded yet")
        session = read_json(pointer)["session_dir"]
    session = Path(session).resolve()
    if not session.is_relative_to((project / "sessions").resolve()):
        raise ValueError("Session must be inside this workspace's sessions folder")
    config = load_config(session / "launch-config.json")
    run = (project / "experiments" / config["experiment_id"]).resolve()
    if run.parent != (project / "experiments").resolve():
        raise ValueError("Experiment path escapes this workspace")
    status = read_json(session / "status.json")
    if Path(status["run"]).resolve() != run:
        raise ValueError("Session status and saved configuration name different experiments")
    run.mkdir(parents=True, exist_ok=True)
    (run / "STOP").touch()
    write_json(session / "manual_stop.json", {"requested_at": time.time(), "run": str(run)})
    return session, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=180)
    args = parser.parse_args()
    session, run = request_stop(args.session_dir)
    print("Stop requested for:", run.name, flush=True)
    print("Waiting for the current iteration, checkpoint save and notebook shutdown. No process is being killed.", flush=True)
    deadline = time.monotonic() + max(0, args.wait_seconds)
    while True:
        status = read_json(session / "status.json")
        if status["status"] in ("stopped", "stopped_low_memory", "completed", "failed", "interrupted"):
            print("Session status:", status["status"], flush=True)
            try:
                checkpoint, entry = Checkpoints(run, run).latest()
                print(f"Latest verified checkpoint: step {entry['step']}, {entry['training_seconds']/3600:.4f} saved hours\n{checkpoint}", flush=True)
            except (FileNotFoundError, OSError, ValueError) as exc:
                print("No checkpoint could be verified:", exc, flush=True)
            if (run / "writer.lock").exists() or status["status"] in ("failed", "interrupted"):
                print("Inspect the session logs before resuming; this does not confirm a fresh final save.", flush=True)
                return 1
            return 0
        if time.monotonic() >= deadline:
            print("Stop flag remains in place. Still waiting, or the old process has exited without updating status.", flush=True)
            print("Inspect:", session / "training.stdout.log", flush=True)
            return 2
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
