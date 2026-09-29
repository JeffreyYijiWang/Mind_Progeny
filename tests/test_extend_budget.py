import copy
from pathlib import Path
import pytest
import torch
from neo_r3gan.checkpoints import Checkpoints, RunLock
from neo_r3gan.config import config_hash
from neo_r3gan.data import prepare_dataset
from neo_r3gan.engine import Trainer
from neo_r3gan.io_utils import sha256, write_json
from neo_r3gan.workflow import _compare, train
from scripts.extend_training_budget import extend_training_budget
from test_recovery import tiny_config, synthetic_zip


def files_under(folder):
    return {str(p.relative_to(folder)): sha256(p) for p in folder.rglob("*") if p.is_file()}


@pytest.fixture
def saved_run(tmp_path, request):
    torch.set_num_threads(2)
    device = getattr(request, "param", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA GPU required for the GPU extension integration check")
    config = tiny_config()
    project, scratch = tmp_path / "project", tmp_path / "scratch"
    prepared = prepare_dataset(synthetic_zip(tmp_path / "images.zip"), project, scratch, config["dataset"])
    result = train(config, project, scratch, prepared, max_steps=2, require_smoke=False, device=device, allow_cpu=(device == "cpu"))
    run = Path(result["run"])
    manager = Checkpoints(run, scratch / "fixture")
    state, _ = manager.load_latest()
    # Test-only clock fixture representing an exhausted eight-hour budget.
    # No real eight-hour training is claimed by this test.
    state["counters"]["training_seconds"] = 8 * 3600
    state["events"] = {name: 8 * 3600 + config["schedule"][name + "_seconds"] for name in state["events"]}
    manager.save(state, ("recovery", "final"))
    return config, project, scratch, prepared, run, state


@pytest.mark.parametrize("saved_run", ["cpu", "cuda"], indirect=True)
def test_extension_preserves_full_state_and_resumes_past_old_budget(saved_run):
    config, project, scratch, prepared, source, before_state = saved_run
    before = files_under(source)
    extended, data = extend_training_budget(project, scratch, config["experiment_id"], "continued-13h", 13)
    assert files_under(source) == before
    assert extended["schedule"]["budget_seconds"] == 46800
    target = project / "experiments" / extended["experiment_id"]
    manager = Checkpoints(target, scratch / "inspect")
    after_state, entry = manager.load_latest()
    expected = copy.deepcopy(before_state)
    expected["config"] = extended
    expected["config_sha256"] = config_hash(extended)
    _compare(expected, after_state)
    assert "final" not in entry["tags"]
    # Same-next-step comparison: only ID/budget changed, not learned behavior.
    device = before_state["implementation"]["device_type"]
    baseline = Trainer(config, prepared, device=device, allow_cpu=(device == "cpu"))
    baseline.load_state_dict(before_state)
    baseline.step()
    expected_next = baseline.state_dict()
    del baseline
    result = train(extended, project, scratch, data, resume=True, max_steps=1, require_smoke=False, device=device, allow_cpu=(device == "cpu"))
    assert result["step"] == before_state["counters"]["step"] + 1
    assert 8 * 3600 < result["training_seconds"] < 13 * 3600
    continued, _ = manager.load_latest()
    for key in ("G", "D", "G_ema", "G_optimizer", "D_optimizer", "sampler", "random", "preview_z", "events"):
        _compare(expected_next[key], continued[key], key)
    target_before_retry = files_under(target)
    again, _ = extend_training_budget(project, scratch, config["experiment_id"], "continued-13h", 13)
    assert again == extended
    assert files_under(target) == target_before_retry  # No progress reset.
    assert files_under(source) == before


def test_source_lock_and_budget_changes_refused(saved_run):
    config, project, scratch, _, source, _ = saved_run
    with RunLock(source):
        with pytest.raises(RuntimeError, match="writer lock"):
            extend_training_budget(project, scratch, config["experiment_id"], "continued-13h", 13)
    assert not (project / "experiments" / "continued-13h").exists()
    for hours in (8, 7, float("inf")):
        with pytest.raises(ValueError):
            extend_training_budget(project, scratch, config["experiment_id"], "continued-13h", hours)


def test_failed_extension_preserves_source_and_refuses_partial_destination(saved_run, monkeypatch):
    config, project, scratch, _, source, _ = saved_run
    before = files_under(source)
    def fail(*args, **kwargs):
        raise IOError("simulated Drive checkpoint failure")
    with monkeypatch.context() as patch:
        patch.setattr(Checkpoints, "save", fail)
        with pytest.raises(IOError, match="Drive checkpoint"):
            extend_training_budget(project, scratch, config["experiment_id"], "continued-13h", 13)
    assert files_under(source) == before
    target = project / "experiments" / "continued-13h"
    assert not (target / "run.json").exists()
    with pytest.raises(RuntimeError, match="incomplete"):
        extend_training_budget(project, scratch, config["experiment_id"], "continued-13h", 13)
    assert files_under(source) == before


def test_existing_unrelated_destination_is_never_overwritten(saved_run):
    config, project, scratch, _, _, _ = saved_run
    target = project / "experiments" / "unrelated"
    write_json(target / "run.json", {"status": "active"})
    before = files_under(target)
    with pytest.raises(RuntimeError, match="incomplete"):
        extend_training_budget(project, scratch, config["experiment_id"], "unrelated", 13)
    assert files_under(target) == before
