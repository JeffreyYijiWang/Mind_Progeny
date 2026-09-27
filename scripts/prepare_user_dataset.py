"""Validate and preview data without loading CUDA/PyTorch libraries."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neo_r3gan.config import default_config
from neo_r3gan.data import prepare_dataset
from neo_r3gan.io_utils import read_json, write_json

prepared = prepare_dataset(sys.argv[1], Path("workspace"), Path("workspace/.scratch"), default_config()["dataset"])
manifest = read_json(prepared / "manifest.json")
write_json(Path("validation") / "dataset-report.json", {"count": manifest["count"], "duplicates": manifest["exact_duplicate_count"], "dataset_id": manifest["dataset_id"], "source_sha256": manifest["source_sha256"], "prepared_zip_sha256": manifest["prepared_zip_sha256"], "recipe": manifest["recipe"], "prepared_path": str(prepared)})
print(prepared)
