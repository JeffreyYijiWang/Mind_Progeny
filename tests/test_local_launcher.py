import json
import threading
from pathlib import Path
import nbformat
import pytest
from scripts import run_local_notebook as launcher
from neo_r3gan.config import default_config


def client_at(tmp_path):
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("print('hello')")])
    client = launcher.LiveNotebookClient(nb)
    client.live_status = {"status": "running"}
    client.output_path = tmp_path / "live.ipynb"
    client.status_path = tmp_path / "status.json"
    return client


def test_display_memory_error_does_not_abort_training(tmp_path, monkeypatch):
    client = client_at(tmp_path)
    def fail(*_):
        raise MemoryError("simulated notebook serializer allocation failure")
    monkeypatch.setattr(launcher, "atomic_write", fail)
    client.save_live(notebook_snapshot=True)
    status = json.loads(client.status_path.read_text())
    assert status["status"] == "running"
    assert status["notebook_snapshot_warning"] == "MemoryError"


def test_status_updates_do_not_rewrite_notebook(tmp_path, monkeypatch):
    client = client_at(tmp_path)
    def unexpected(*_):
        raise AssertionError("Progress messages must not serialize notebook images")
    monkeypatch.setattr(launcher, "atomic_write", unexpected)
    client.save_live()
    assert client.status_path.exists()
    assert not client.output_path.exists()


def test_streaming_notebook_snapshot_is_valid(tmp_path):
    client = client_at(tmp_path)
    client.nb.cells[0].outputs = [nbformat.v4.new_output("stream", name="stdout", text="step 1\n")]
    client.save_live(notebook_snapshot=True)
    loaded = nbformat.read(client.output_path, as_version=4)
    nbformat.validate(loaded)
    assert loaded.cells[0].outputs[0].text == "step 1\n"


def test_memory_watcher_requests_stop_without_killing_process(tmp_path, monkeypatch):
    session = tmp_path / "session"
    session.mkdir()
    run = tmp_path / "run"
    samples = iter([{"available_commit_GiB": 6.0}, {"available_commit_GiB": 1.8}])
    monkeypatch.setattr(launcher, "memory_snapshot", lambda: next(samples))
    launcher.watch_memory(run, session, threading.Event(), interval=0)
    assert (run / "STOP").exists()
    assert json.loads((session / "memory_stop.json").read_text())["available_commit_GiB"] == 1.8


@pytest.mark.parametrize("resume", [False, True])
def test_exactly_one_training_branch_with_stop_checks(tmp_path, resume):
    source = Path(__file__).resolve().parents[1] / "NeoHuman_R3GAN_Local.ipynb"
    config = default_config("neohuman-local-002")
    configured = launcher.configure_notebook(nbformat.read(source, as_version=4), tmp_path / "config.json", config, resume)
    start = next(c.source for c in configured.cells if "START_NEW_RUN = " in c.source and c.cell_type == "code")
    recover = next(c.source for c in configured.cells if "RESUME_RUN = " in c.source and c.cell_type == "code")
    assert f"START_NEW_RUN = {not resume}" in start
    assert f"RESUME_RUN = {resume}" in recover
    assert "clear_stop(PROJECT, CFG)" not in recover
    assert start.startswith('if (PROJECT / "experiments"')
    assert recover.startswith('if (PROJECT / "experiments"')
    for cell in configured.cells:
        if cell.cell_type == "code":
            compile(cell.source, cell.id, "exec")
