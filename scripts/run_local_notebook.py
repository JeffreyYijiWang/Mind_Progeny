"""Execute a production copy of the local notebook and persist live outputs.

The source notebook is untouched. Exactly one of its start/resume branches runs.
The notebook's smoke test and shared trainer retain all recovery safeguards.
"""
import argparse
import asyncio
import json
import io
import os
import shutil
import sys
import time
import threading
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from neo_r3gan.io_utils import atomic_write, read_json, write_json
from neo_r3gan.config import default_config, load_config
from scripts.memory_diagnostic import memory_snapshot


def watch_memory(run, session, stopped, reserve_gib=2.0, interval=1.0):
    """Use the shared trainer's existing STOP mechanism; never kill its process."""
    last_record = 0.0
    while not stopped.wait(interval):
        try:
            memory = memory_snapshot()
            if memory is None:
                return
            if time.monotonic() - last_record >= 15:
                write_json(session / "memory.json", dict(memory, checked_at=time.time()))
                last_record = time.monotonic()
            if memory["available_commit_GiB"] < reserve_gib:
                # STOP is honored before the next iteration. This also blocks a
                # new production run when pressure begins during its smoke test.
                run.mkdir(parents=True, exist_ok=True)
                (run / "STOP").touch()
                write_json(session / "memory_stop.json", dict(memory, requested_at=time.time(), reserve_gib=reserve_gib))
                print(f"MEMORY GUARD: {memory['available_commit_GiB']:.2f} GiB commit available. Requested a safe checkpoint and stop.", flush=True)
                return
        except (OSError, MemoryError) as exc:
            print(f"Memory watcher could not record status: {type(exc).__name__}", file=sys.stderr, flush=True)


class LiveNotebookClient(NotebookClient):
    def process_message(self, msg, cell, cell_index):
        result = super().process_message(msg, cell, cell_index)
        if msg["msg_type"] == "stream":
            message = msg["content"]["text"]
            print(message, end="", flush=True)
            self.live_status["latest_output"] = message[-4000:]
            self.save_live()  # Small status only; do not reserialize embedded PNGs.
        elif msg["msg_type"] == "error":
            self.save_live()
        return result

    def save_live(self, notebook_snapshot=False):
        """Display persistence must never terminate a healthy training kernel."""
        self.live_status["updated_at"] = time.time()
        if notebook_snapshot:
            try:
                def write_notebook(f):
                    # Stream JSON; avoid nbformat's deep copy + full JSON string
                    # + encoded byte string on every progress message.
                    stream = io.TextIOWrapper(f, encoding="utf-8", write_through=True)
                    try:
                        json.dump(self.nb, stream, ensure_ascii=False, indent=1)
                        stream.flush()
                    finally:
                        stream.detach()
                atomic_write(self.output_path, write_notebook)
            except (MemoryError, OSError) as exc:
                self.live_status["notebook_snapshot_warning"] = type(exc).__name__
                print(f"Notebook display save skipped ({type(exc).__name__}); training checkpoints are independent.", file=sys.stderr, flush=True)
        try:
            write_json(self.status_path, self.live_status)
        except (MemoryError, OSError) as exc:
            print(f"Live status save skipped: {type(exc).__name__}", file=sys.stderr, flush=True)


def configure_notebook(nb, config_path, config, resume):
    replacements = {"start": 0, "resume": 0, "export": 0, "settings": 0}
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source
        if 'CONFIG_FILE = ""' in source:
            replacements["settings"] += 1
            source = source.replace('CONFIG_FILE = ""', "CONFIG_FILE = " + repr(str(config_path)))
            source = source.replace('EXPERIMENT_ID = "neohuman-local-001"', "EXPERIMENT_ID = " + repr(config["experiment_id"]))
        if "START_NEW_RUN = False" in source:
            replacements["start"] += 1
            source = source.replace("START_NEW_RUN = False", "START_NEW_RUN = " + str(not resume))
        if "RESUME_RUN = False" in source:
            replacements["resume"] += 1
            source = source.replace("RESUME_RUN = False", "RESUME_RUN = " + str(resume))
        if "EXPORT_RESULTS = False" in source:
            replacements["export"] += 1
            source = source.replace("EXPORT_RESULTS = False", "EXPORT_RESULTS = True")
        if "RESULT = train(" in source:
            # Do not proceed to generation/export while memory is low, or
            # accidentally clear the watcher's STOP in the resume cell.
            guard = 'if (PROJECT / "experiments" / CFG["experiment_id"] / "STOP").exists():\n    raise RuntimeError("Training stopped safely. Inspect memory_stop.json and the latest checkpoint before resuming.")\n'
            source = guard + source + "\n" + guard
            source = source.replace("    clear_stop(PROJECT, CFG)\n", "")
        cell.source = source
        compile(source, f"local-notebook:{cell.id}", "exec")
    if any(value != 1 for value in replacements.values()):
        raise RuntimeError(f"Notebook layout differs from the expected launch interface: {replacements}")
    nbformat.validate(nb)
    return nb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Config for a new run; an existing run must match its saved config")
    args = parser.parse_args()
    session = args.session_dir.resolve()
    session.mkdir(parents=True, exist_ok=True)
    project = ROOT / "workspace"
    config = load_config(args.config) if args.config else default_config()
    run = project / "experiments" / config["experiment_id"]
    if (run / "writer.lock").exists():
        raise RuntimeError("An active or stale writer lock exists; refusing a second training process")
    resume = (run / "run.json").exists()
    if resume and read_json(run / "run.json")["status"] != "active":
        raise RuntimeError("The experiment is sealed for transfer and cannot train here")
    if (run / "STOP").exists():
        raise RuntimeError("An explicit STOP request exists. Clear it only when resuming is intended.")
    memory = memory_snapshot()
    if memory and memory["available_commit_GiB"] < 4.0:
        raise RuntimeError(f"Only {memory['available_commit_GiB']:.2f} GiB of system commit is available. Free at least 4 GiB before loading CUDA, or configure Windows virtual memory.")
    # Conservative check for checkpoints, samples, smoke test and the final results ZIP.
    free = shutil.disk_usage(ROOT).free
    if free < 700 * 1024**2:
        raise RuntimeError(f"Only {free / 2**20:.0f} MiB free; free at least 700 MiB before starting this default run")
    nb = nbformat.read(ROOT / "NeoHuman_R3GAN_Local.ipynb", as_version=4)
    config_path = session / "launch-config.json"
    if resume and read_json(run / "config.json") != config:
        raise RuntimeError("Requested configuration differs from the saved experiment")
    write_json(config_path, config)
    nb = configure_notebook(nb, config_path, config, resume)
    status = {"status": "starting", "pid": os.getpid(), "started_at": time.time(), "run": str(run),
              "resume": resume, "disk_free_gib_at_start": round(free / 2**30, 3),
              "source_notebook": str(ROOT / "NeoHuman_R3GAN_Local.ipynb")}
    client = LiveNotebookClient(nb, timeout=None, kernel_name="neohuman-r3gan",
                               resources={"metadata": {"path": str(ROOT)}})
    client.live_status = status
    client.output_path = session / "NeoHuman_R3GAN_Local.running.ipynb"
    client.status_path = session / "status.json"

    def starting_cell(cell, cell_index):
        if cell.cell_type == "code":
            status.update(status="running", current_cell=cell.id, cell_index=cell_index)
            print(f"\n--- Executing {cell.id} ---", flush=True)
            client.save_live()

    def finished_cell(cell, cell_index, execute_reply):
        status["last_executed_cell"] = cell.id
        client.save_live(notebook_snapshot=True)

    client.on_cell_start = starting_cell
    client.on_cell_executed = finished_cell
    client.save_live(notebook_snapshot=True)
    write_json(project / "current-local-session.json", {"session_dir": str(session), "run": str(run), "pid": os.getpid(), "started_at": status["started_at"]})
    watcher_stopped = threading.Event()
    watcher = threading.Thread(target=watch_memory, args=(run, session, watcher_stopped), daemon=True)
    watcher.start()
    print(f"Production notebook launched: {'resume' if resume else 'new run'}\nOutputs: {client.output_path}\nRun: {run}", flush=True)
    try:
        client.execute()
    except BaseException as exc:
        state = "stopped_low_memory" if (session / "memory_stop.json").exists() else ("stopped" if (run / "STOP").exists() else "failed")
        status.update(status=state, error=f"{type(exc).__name__}: {exc}", finished_at=time.time())
        raise
    else:
        stopped = (run / "STOP").exists()
        status.update(status="stopped" if stopped else "completed", finished_at=time.time())
        print(f"Notebook {status['status']}. Checkpoints, samples, generated images and results are saved in {run}", flush=True)
    finally:
        watcher_stopped.set()
        watcher.join(timeout=2)
        client.save_live(notebook_snapshot=True)


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
