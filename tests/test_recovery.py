import copy
import io
import json
import zipfile
from pathlib import Path
import pytest
import torch
from PIL import Image
from neo_r3gan.checkpoints import Checkpoints, RunLock, release_stale_lock
from neo_r3gan.config import config_hash, default_config, validate
from neo_r3gan.data import prepare_dataset, preprocess, verify_prepared
from neo_r3gan.io_utils import digest, read_json, write_json
from neo_r3gan.upstream import code_version


def dummy_state(step):
    c = default_config("test-run")
    return {"schema": 1, "config": c, "config_sha256": config_hash(c), "code": code_version(), "events": {}, "tensor": torch.tensor([step]),
            "counters": {"step": step, "training_seconds": float(step), "nimg": 8 * step}}


def synthetic_zip(path, count=4):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(count):
            im = Image.new("RGBA", (31 + i, 19 + i), (i * 47, 80, 120, 190))
            b = io.BytesIO()
            im.save(b, format="PNG")
            z.writestr(f"folder/image-{i}.png", b.getvalue())
    return path


def tiny_config():
    c = default_config("tiny-test")
    c["dataset"].update(expected_images=4, resolution=16)
    c["model"].update(widths=[8, 8, 8], cardinalities=[2, 2, 2], blocks=[1, 1, 1], noise_dim=8)
    c["training"].update(batch_size=2, microbatch=1)
    c["preview"]["count"] = 4
    return c


def test_retention_and_no_duplicate_milestones(tmp_path):
    cp = Checkpoints(tmp_path / "run", tmp_path / "local")
    for i in range(1, 10):
        cp.save(dummy_state(i), ["recovery"] + (["milestone"] if i in (2, 4) else []))
        if i == 3:
            cp.mark_keep()
    entries = cp.manifest()["entries"]
    assert [e["step"] for e in entries if "recovery" in e["tags"]] == [6, 7, 8, 9]
    assert [e["step"] for e in entries if "milestone" in e["tags"]] == [2, 4]
    assert [e["step"] for e in entries if "manual" in e["tags"]] == [3]
    cp.save(dummy_state(9), ("recovery", "milestone", "final"))
    assert len(cp.manifest()["entries"]) == len(entries)
    assert len(list((tmp_path / "run").rglob("*.pt"))) == len(entries)


def test_stop_saves_are_rolling(tmp_path):
    cp = Checkpoints(tmp_path / "run", tmp_path / "local")
    for i in range(8):
        cp.save(dummy_state(i), ("stop",))
    assert len(cp.manifest()["entries"]) == 4


def test_failed_copy_keeps_previous_manifest_and_checkpoint(tmp_path, monkeypatch):
    import neo_r3gan.checkpoints as module
    cp = Checkpoints(tmp_path / "run", tmp_path / "local")
    for i in range(4):
        cp.save(dummy_state(i))
    before = cp.manifest()
    def fail(*_):
        raise IOError("simulated Drive disconnection")
    monkeypatch.setattr(module, "verified_copy", fail)
    with pytest.raises(IOError, match="disconnection"):
        cp.save(dummy_state(4))
    assert cp.manifest() == before
    assert cp.latest()[1]["step"] == 3
    assert len(list((tmp_path / "run").rglob("*.pt"))) == 4


def test_failed_manifest_publication_does_not_prune(tmp_path, monkeypatch):
    cp = Checkpoints(tmp_path / "run", tmp_path / "local")
    for i in range(4):
        cp.save(dummy_state(i))
    def fail(_):
        raise IOError("manifest failure")
    monkeypatch.setattr(cp, "_publish", fail)
    with pytest.raises(IOError):
        cp.save(dummy_state(4))
    assert cp.latest()[1]["step"] == 3
    assert all((tmp_path / "run" / e["path"]).exists() for e in cp.manifest()["entries"])


def test_corrupt_latest_and_manifest_recover_previous(tmp_path):
    cp = Checkpoints(tmp_path / "run", tmp_path / "local")
    cp.save(dummy_state(1))
    cp.save(dummy_state(2))
    cp.latest()[0].write_bytes(b"truncated")
    (tmp_path / "run" / "manifest.json").write_bytes(b"partial json")
    state, entry = cp.load_latest()
    assert entry["step"] == 1
    assert state["tensor"].item() == 1


def test_writer_lock_and_explicit_stale_release(tmp_path):
    with RunLock(tmp_path) as first:
        with pytest.raises(RuntimeError, match="writer lock"):
            with RunLock(tmp_path):
                pass
        with pytest.raises(ValueError):
            release_stale_lock(tmp_path, first.token, "")
    stale = RunLock(tmp_path).__enter__()
    release_stale_lock(tmp_path, stale.token, "I stopped every writer for this experiment")
    assert not (tmp_path / "writer.lock").exists()


def test_dataset_determinism_and_count(tmp_path):
    source = synthetic_zip(tmp_path / "images.zip")
    cfg = tiny_config()
    path = prepare_dataset(source, tmp_path / "project", tmp_path / "scratch", cfg["dataset"])
    manifest = verify_prepared(path)
    assert manifest["count"] == 4
    assert manifest["exact_duplicate_count"] == 0
    assert prepare_dataset(source, tmp_path / "project", tmp_path / "scratch", cfg["dataset"]) == path
    with pytest.raises(ValueError, match="Expected 45"):
        prepare_dataset(source, tmp_path / "p2", tmp_path / "s2", default_config()["dataset"])


def test_zip_traversal_and_invalid_images_rejected(tmp_path):
    source = tmp_path / "bad.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("../bad.png", b"x")
    with pytest.raises(ValueError, match="Unsafe"):
        prepare_dataset(source, tmp_path / "p", tmp_path / "s", tiny_config()["dataset"])
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("bad.png", b"x")
    with pytest.raises(ValueError, match="Invalid image"):
        prepare_dataset(source, tmp_path / "p", tmp_path / "s", tiny_config()["dataset"])


def test_config_rejects_bad_microbatch():
    c = default_config()
    c["training"]["microbatch"] = 3
    with pytest.raises(ValueError):
        validate(c)


def test_padding_preserves_wide_composition():
    settings = tiny_config()["dataset"]
    im = Image.new("RGB", (80, 20), (255, 0, 0))
    padded = preprocess(im, settings)
    assert padded.size == (16, 16)
    assert padded.getpixel((0, 0)) == (255, 255, 255)
    assert padded.getpixel((0, 8)) == (255, 0, 0)
    centered = preprocess(im, dict(settings, crop="center"))
    assert centered.getpixel((0, 0)) == (255, 0, 0)


def test_notebook_syntax_and_schema():
    import nbformat
    for path in Path.cwd().glob("NeoHuman*.ipynb"):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                compile(cell.source, str(path) + ":" + cell.id, "exec")
        assert any("Resume latest verified checkpoint" in c.source for c in notebook.cells)


def test_cpu_full_state_resume_and_budget(tmp_path):
    from neo_r3gan.engine import Trainer
    from neo_r3gan.workflow import _compare, smoke_test, train
    torch.set_num_threads(2)
    c = tiny_config()
    source = synthetic_zip(tmp_path / "images.zip")
    project, scratch = tmp_path / "project", tmp_path / "scratch"
    prepared = prepare_dataset(source, project, scratch, c["dataset"])
    smoke = smoke_test(c, project, scratch, prepared, device="cpu", allow_cpu=True)
    assert smoke["passed"] and smoke["next_step_tensor_comparison"] == "bitwise_equal"
    c["schedule"].update(budget_seconds=0.001, sample_seconds=0.001, recovery_seconds=0.001, milestone_seconds=0.001, log_seconds=0.001)
    result = train(c, project, scratch, prepared, require_smoke=False, device="cpu", allow_cpu=True)
    assert result["step"] == 1
    run = Path(result["run"])
    manager = Checkpoints(run, scratch)
    final = manager.latest()[1]
    assert {"milestone", "final", "recovery"} <= set(final["tags"])
    assert len(list(run.rglob("*.pt"))) == 2  # Initial + combined recovery/milestone/final.
    resumed = train(c, project, scratch, prepared, resume=True, require_smoke=False, device="cpu", allow_cpu=True)
    assert resumed["step"] == result["step"]
    assert resumed["training_seconds"] == result["training_seconds"]
    assert len(list(run.rglob("*.pt"))) == 2
    wrong = copy.deepcopy(c)
    wrong["training"]["gamma"] *= 2
    with pytest.raises(ValueError, match="saved configuration"):
        train(wrong, project, scratch, prepared, resume=True, require_smoke=False, device="cpu", allow_cpu=True)
