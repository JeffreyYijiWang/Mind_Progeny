"""Run the requested smoke test; never starts the eight-hour production run."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neo_r3gan.config import default_config
from neo_r3gan.data import prepare_dataset
from neo_r3gan.io_utils import read_json, write_json

parser = argparse.ArgumentParser()
parser.add_argument("zip", type=Path)
parser.add_argument("--project", type=Path, default=Path("workspace"))
parser.add_argument("--scratch", type=Path, default=Path("workspace/.scratch"))
args = parser.parse_args()
config = default_config("neohuman-local-001")
prepared = prepare_dataset(args.zip, args.project, args.scratch, config["dataset"])
manifest = read_json(prepared / "manifest.json")
write_json(Path("validation") / "dataset-report.json", {"count": manifest["count"], "duplicates": manifest["exact_duplicate_count"], "dataset_id": manifest["dataset_id"], "source_sha256": manifest["source_sha256"], "prepared_zip_sha256": manifest["prepared_zip_sha256"], "recipe": manifest["recipe"], "prepared_path": str(prepared)})
from neo_r3gan.workflow import smoke_test
report = smoke_test(config, args.project, args.scratch, prepared)
write_json(Path("validation") / "gpu-smoke-report.json", report)
print(json.dumps({"prepared": str(prepared), "report": "validation/gpu-smoke-report.json"}))
