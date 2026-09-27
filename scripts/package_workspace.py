"""Create a complete software deliverable, excluding private images and trained state."""
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = []
for pattern in ("NeoHuman*.ipynb", "README.md", "VALIDATION.md", "requirements*.txt", "upstream-lock.json", "pytest.ini", "neo_r3gan/*.py", "configs/*.json", "scripts/*.py", "scripts/*.ps1", "scripts/*.sh", "tests/*.py", "docs/*.md", "validation/*.json", "validation/*.txt", "validation/*.xml"):
    files.extend(root.glob(pattern))
files = sorted(set(files))
inventory = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
output = root / "dist" / "NeoHuman_R3GAN_Workspace.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
    for path in files:
        z.write(path, path.relative_to(root).as_posix())
    z.writestr("workspace-package.json", json.dumps({"schema": 1, "files": inventory}, indent=2))
with zipfile.ZipFile(output) as z:
    assert z.testzip() is None
    for name, expected in inventory.items():
        assert hashlib.sha256(z.read(name)).hexdigest() == expected
checksum = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix(".sha256").write_text(checksum + "  " + output.name + "\n")
print(f"{output}\n{len(files)} files | {output.stat().st_size:,} bytes | SHA256 {checksum}")
