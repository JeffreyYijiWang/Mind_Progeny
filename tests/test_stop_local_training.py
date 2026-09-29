from pathlib import Path
import pytest
from neo_r3gan.config import default_config
from neo_r3gan.io_utils import write_json, read_json
from scripts import stop_local_training as stop


def session_at(tmp_path, monkeypatch):
    monkeypatch.setattr(stop, "ROOT", tmp_path)
    project = tmp_path / "workspace"
    session = project / "sessions" / "test-session"
    config = default_config("test-stop")
    run = project / "experiments" / config["experiment_id"]
    write_json(session / "launch-config.json", config)
    write_json(session / "status.json", {"run": str(run), "status": "running"})
    write_json(project / "current-local-session.json", {"session_dir": str(session)})
    return session, run


def test_stop_uses_recorded_session_and_preserves_training_files(tmp_path, monkeypatch):
    session, run = session_at(tmp_path, monkeypatch)
    write_json(run / "manifest.json", {"sentinel": "unchanged"})
    write_json(run / "writer.lock" / "owner.json", {"token": "do-not-remove"})
    before = (run / "manifest.json").read_bytes()
    assert stop.request_stop() == (session.resolve(), run.resolve())
    assert (run / "STOP").is_file()
    assert (run / "manifest.json").read_bytes() == before
    assert read_json(run / "writer.lock" / "owner.json")["token"] == "do-not-remove"
    stop.request_stop()  # Repeated request is harmless.


def test_stop_refuses_mismatched_or_external_session(tmp_path, monkeypatch):
    session, run = session_at(tmp_path, monkeypatch)
    write_json(session / "status.json", {"run": str(tmp_path / "other"), "status": "running"})
    with pytest.raises(ValueError, match="different experiments"):
        stop.request_stop()
    assert not (run / "STOP").exists()
    with pytest.raises(ValueError, match="sessions folder"):
        stop.request_stop(tmp_path.parent)
