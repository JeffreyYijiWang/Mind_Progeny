import copy
import io
import json
import zipfile
from pathlib import Path
import pytest
import torch
from PIL import Image
from neo_r3gan.config import default_config
from neo_r3gan.data import prepare_dataset
from neo_r3gan.io_utils import read_json
from neo_r3gan.transfer import export_recovery_bundle, export_results, import_recovery_bundle
from neo_r3gan.workflow import train, generate_images


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA GPU required for portable handoff integration")
def test_gpu_handoff_resume_generation_and_results(tmp_path):
    c = default_config("transfer-test")
    c["dataset"].update(expected_images=4, resolution=16)
    c["model"].update(widths=[8, 8, 8], blocks=[1, 1, 1], cardinalities=[2, 2, 2], noise_dim=8)
    c["training"].update(batch_size=2, microbatch=1)
    c["preview"]["count"] = 4
    source_zip = tmp_path / "data.zip"
    with zipfile.ZipFile(source_zip, "w") as z:
        for i in range(4):
            out = io.BytesIO()
            Image.new("RGB", (20, 30), (50 * i, 100, 140)).save(out, format="PNG")
            z.writestr(str(i) + ".png", out.getvalue())
    source, scratch, destination = tmp_path / "source", tmp_path / "scratch", tmp_path / "destination"
    prepared = prepare_dataset(source_zip, source, scratch, c["dataset"])
    original = train(c, source, scratch, prepared, max_steps=2, require_smoke=False)
    bundle = export_recovery_bundle(source, scratch, c)
    assert read_json(Path(original["run"]) / "run.json")["status"] == "transferred"
    with pytest.raises(RuntimeError, match="sealed"):
        train(c, source, scratch, prepared, resume=True, max_steps=1, require_smoke=False)
    imported, imported_data = import_recovery_bundle(bundle, destination, scratch / "destination")
    assert imported == c
    with pytest.raises(FileExistsError):
        import_recovery_bundle(bundle, destination, scratch / "destination")
    resumed = train(imported, destination, scratch / "destination", imported_data, resume=True, max_steps=1, require_smoke=False)
    assert resumed["step"] == original["step"] + 1
    assert resumed["training_seconds"] > original["training_seconds"]
    generated = generate_images(destination, scratch, imported, imported_data, seeds=[7, 13])
    assert len(generated) == 2 and all(p.exists() for p in generated)
    results = export_results(destination, scratch, imported)
    with zipfile.ZipFile(results) as z:
        assert z.testzip() is None
        assert any(name.startswith("checkpoints/") for name in z.namelist())
        assert any(name.startswith("generated/") for name in z.namelist())
        assert any(name.startswith("logs/") for name in z.namelist())
    # Tampering is detected before an experiment can be created.
    corrupt = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(bundle) as z, zipfile.ZipFile(corrupt, "w") as out:
        for name in z.namelist():
            out.writestr(name, b"bad" if name == "config.json" else z.read(name))
    with pytest.raises(ValueError, match="Corrupt bundle"):
        import_recovery_bundle(corrupt, tmp_path / "bad-target", scratch)
    assert not (tmp_path / "bad-target" / "experiments").exists()
