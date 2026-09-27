"""Generate two real notebooks around one shared workflow API."""
import json
import sys
import textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neo_r3gan.config import default_config

ROOT = Path(__file__).resolve().parents[1]


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": textwrap.dedent(text).strip() + "\n"}


def code(text):
    return {"cell_type": "code", "execution_count": None, "outputs": [], "metadata": {}, "source": textwrap.dedent(text).strip() + "\n"}


def notebook(colab):
    label = "Colab" if colab else "Local"
    cells = [md(f"""
    # NeoHuman · R3GAN · {label}
    Train on your 45-image ZIP, with verified recovery and the same portable state on both machines.
    **Start with the editable settings below. Run cells in order, one at a time.** Do not use Run All: start, resume, and import are alternative actions.

    The supplied small 128×128 model trains from scratch. It uses the official R3GAN networks and RpGAN + R1/R2 loss with reference PyTorch operators, FP32, and a custom single-GPU loop. It is not the paper's large FFHQ preset. With 45 images, memorization and weak diversity are serious possibilities; eight hours is a time budget, not a quality guarantee.

    Defaults: previews every 10 training minutes, recovery every 15 minutes, milestones every hour, stop after 8 cumulative training hours. Save/sample overhead and time offline do not count. Abrupt termination can lose work since the last verified persisted checkpoint.
    """)]
    if colab:
        cells += [md("""
        ## Editable settings — keep these together
        Set **Runtime → Change runtime type → GPU**. Upload the delivered `NeoHuman_R3GAN_Workspace.zip` when cell 3 asks; this is the software package, not your image ZIP. It is cached on Drive for later sessions.
        Upload the 45-image ZIP in cell 4, or point `DATA_ZIP` to a file already on Drive. For recovery on a new runtime, select the same ZIP again (its original is also stored by hash under `datasets/original`).
        """), code('''
        from pathlib import Path
        PROJECT = Path("/content/drive/MyDrive/NeoHuman_R3GAN")
        SCRATCH = Path("/content/NeoHuman_R3GAN_work")
        CODE_ROOT = Path("/content/NeoHuman_R3GAN_code")
        CODE_BUNDLE = PROJECT / "software" / "NeoHuman_R3GAN_Workspace.zip"
        DATA_ZIP = ""  # Existing Drive path, or leave empty to upload the 45-image ZIP.
        CONFIG_FILE = ""  # Optional existing shared config JSON. Required values must match when resuming.
        EXPERIMENT_ID = "neohuman-colab-001"  # Different from the laptop experiment for parallel runs.
        IMPORT_BUNDLE = ""  # Optional existing Drive path to a handoff ZIP; see import cell below.
        ''')]
    else:
        cells += [md("""
        ## First launch — isolated environment
        Extract the complete workspace ZIP and open a terminal in that folder. Install Python 3.11 and Git first.

        **Windows PowerShell:** `powershell -ExecutionPolicy Bypass -File scripts/setup_local.ps1`

        **Linux with NVIDIA GPU:** `bash scripts/setup_local.sh`

        **JupyterLab:** Windows: `.\\.venv\\Scripts\\python.exe -m jupyterlab NeoHuman_R3GAN_Local.ipynb`; Linux: `.venv/bin/python -m jupyterlab NeoHuman_R3GAN_Local.ipynb`.

        **VS Code:** open this folder, install the Microsoft Python and Jupyter extensions, open this notebook, and choose **Select Kernel → Python Environments → .venv**. All cells must use that environment.

        Use normal OS power settings to keep the laptop awake while plugged in. Sleep, closing the lid, or powering down interrupts training. This notebook does not alter power settings. CPU, Apple MPS, and AMD/Intel GPUs are unsupported for long runs here; use Colab instead.

        ## Editable settings
        The provided image ZIP is prefilled for your laptop. Change it when moving the workspace. You may place `PROJECT` on a larger local disk; avoid a sync folder for live training if possible.
        """), code(r'''
        from pathlib import Path
        CODE_ROOT = Path.cwd()  # Folder containing this notebook and neo_r3gan/.
        PROJECT = CODE_ROOT / "workspace"
        SCRATCH = PROJECT / ".scratch"
        DATA_ZIP = r"C:\Users\Jeffr\Downloads\DATA SET-20260926T223837Z-1-001.zip"
        CONFIG_FILE = ""  # Optional saved shared configuration JSON.
        EXPERIMENT_ID = "neohuman-local-001"
        IMPORT_BUNDLE = ""  # Optional local path to a handoff ZIP.
        ''')]
    cells += [md("## 1 · Check GPU and runtime"), code('''
    import platform, shutil, subprocess, sys
    print("OS:", platform.platform(), "Python:", sys.version)
    if shutil.which("nvidia-smi"):
        subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv"], check=True)
    else:
        raise RuntimeError("No NVIDIA runtime found. Select a Colab GPU or install/check the laptop NVIDIA driver before continuing.")
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError("Use Python 3.11–3.13 for these pins. Local instructions use Python 3.11.")
    ''')]
    if colab:
        cells += [md("## 2 · Mount Google Drive"), code('''
        from google.colab import drive
        drive.mount("/content/drive")
        PROJECT.mkdir(parents=True, exist_ok=True)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        print("Persistent project:", PROJECT)
        ''')]
        cells += [md("""
        ## 3 · Install pinned dependencies and retrieve pinned R3GAN code
        The software package contains shared modules and both notebooks; upstream is fetched at commit `19a7ddf463fbac2bd39b4c1c73d63f1c441c7403`.
        If asked to restart the session after installation, do so, then rerun cells 1–3. The package remains on Drive. This setup uses normal Colab resources and makes no availability promise; see the [Colab FAQ](https://research.google.com/colaboratory/faq.html).
        """), code('''
        import hashlib, importlib, json, os, zipfile
        from pathlib import PurePosixPath
        if not CODE_BUNDLE.exists():
            from google.colab import files
            print("Upload NeoHuman_R3GAN_Workspace.zip (the SOFTWARE package)")
            uploaded = files.upload()
            if len(uploaded) != 1:
                raise ValueError("Upload exactly one workspace ZIP")
            payload = next(iter(uploaded.values()))
            CODE_BUNDLE.parent.mkdir(parents=True, exist_ok=True)
            temporary = CODE_BUNDLE.with_suffix(".partial")
            temporary.write_bytes(payload)
            os.replace(temporary, CODE_BUNDLE)
        with zipfile.ZipFile(CODE_BUNDLE) as package:
            inventory = json.loads(package.read("workspace-package.json"))["files"]
            if set(package.namelist()) != set(inventory) | {"workspace-package.json"}:
                raise ValueError("Workspace ZIP inventory mismatch")
            for name, expected in inventory.items():
                p = PurePosixPath(name)
                if p.is_absolute() or ".." in p.parts or "\\\\" in name or ":" in name:
                    raise ValueError("Unsafe package path")
                data = package.read(name)
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("Workspace ZIP checksum mismatch")
                target = CODE_ROOT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        os.chdir(CODE_ROOT)
        sys.path.insert(0, str(CODE_ROOT))
        loaded = {name: str(getattr(sys.modules[name], "__version__", "")) for name in ("torch", "numpy", "PIL") if name in sys.modules}
        subprocess.run([sys.executable, "-m", "pip", "install", "pip==25.1.1"], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "torch==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu128"], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "matplotlib==3.10.3"], check=True)
        subprocess.run([sys.executable, "scripts/fetch_upstream.py"], check=True)
        for name, pin in {"torch": "2.7.1", "numpy": "2.2.6", "PIL": "11.2.1"}.items():
            if name in loaded and loaded[name].split("+")[0] != pin:
                raise RuntimeError("Dependencies changed. Restart the Colab session, then rerun settings and cells 1–3.")
        importlib.invalidate_caches()
        ''')]
    else:
        cells += [md("## 2 · Create local project folders"), code('''
        PROJECT.mkdir(parents=True, exist_ok=True)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        print("Persistent project:", PROJECT.resolve())
        print("Dataset working copies:", SCRATCH.resolve())
        '''), md("## 3 · Verify isolated environment and pinned R3GAN code"), code('''
        if sys.prefix == sys.base_prefix:
            raise RuntimeError("Select the project's .venv kernel; run scripts/setup_local.ps1 or .sh first.")
        sys.path.insert(0, str(CODE_ROOT))
        subprocess.run([sys.executable, "scripts/fetch_upstream.py"], cwd=CODE_ROOT, check=True)
        ''')]
    cells += [code('''
    from neo_r3gan.config import default_config, load_config, validate
    from neo_r3gan.data import prepare_dataset
    from neo_r3gan.engine import hardware_report
    from neo_r3gan.upstream import require_pins
    from neo_r3gan.workflow import smoke_test, train, latest_verified, show_progress, generate_images, mark_keep, clear_stop
    from neo_r3gan.transfer import export_results, export_recovery_bundle, import_recovery_bundle
    from neo_r3gan.io_utils import read_json, write_json
    require_pins()
    HARDWARE = hardware_report(require_gpu=True)
    CFG = load_config(CONFIG_FILE) if CONFIG_FILE else default_config(EXPERIMENT_ID)
    print("Experiment:", CFG["experiment_id"])
    ''')]
    cells += [md("## 4 · Upload or select the 45-image ZIP")]
    if colab:
        cells += [code('''
        if not DATA_ZIP:
            from google.colab import files
            print("Upload the ZIP containing your 45 IMAGES")
            uploaded = files.upload()
            if len(uploaded) != 1:
                raise ValueError("Upload exactly one image ZIP")
            filename, payload = next(iter(uploaded.items()))
            selected = SCRATCH / "uploads" / Path(filename).name
            selected.parent.mkdir(parents=True, exist_ok=True)
            selected.write_bytes(payload)
            DATA_ZIP = str(selected)
        assert Path(DATA_ZIP).is_file(), DATA_ZIP
        print("Selected:", DATA_ZIP)
        ''')]
    else:
        cells += [code('''
        if not Path(DATA_ZIP).is_file():
            raise FileNotFoundError("Edit DATA_ZIP in the settings cell to your 45-image ZIP")
        print("Selected:", DATA_ZIP)
        ''')]
    cells += [md("""
    ## 5 · Validate images and preview preprocessing
    Validation requires exactly 45 decodable images by default. EXIF orientation is applied, transparency is composited on white, then resized with Lanczos and padded to 128×128 to preserve the full image. Every pair below is **original (left), exact training image enlarged (right)**. Inspect whether the full composition and important details are preserved.
    Original ZIPs are copied unchanged to persistent storage, with SHA-256 metadata. Training uses a verified copy on runtime/local scratch disk, loaded into RAM. Change `CFG['dataset']` here before preparation if needed; model stage counts must match resolution.
    """), code('''
    from IPython.display import display
    from PIL import Image
    PREPARED = prepare_dataset(DATA_ZIP, PROJECT, SCRATCH, CFG["dataset"])
    DATASET_MANIFEST = read_json(PREPARED / "manifest.json")
    print("Images:", DATASET_MANIFEST["count"], "Exact duplicates:", DATASET_MANIFEST["exact_duplicate_count"])
    display(Image.open(PREPARED / "preprocessing.png"))
    '''), md("""
    ## 6 · Configure the experiment
    Edit the JSON file named by `CONFIG_FILE` or the values below **before the first run**. A resume always requires the saved config unchanged. To try different training hyperparameters, use a new experiment ID.
    `batch_size` is the effective batch; `microbatch` controls VRAM use and must divide it. Reduce `microbatch` to 1 on OOM; then use a new ID and rerun the smoke test. Widths/blocks/cardinalities define the compact model, and must have 6 stages for 128×128.

    For independent parallel training keep different IDs (defaults: `neohuman-colab-001` and `neohuman-local-001`). These are separate models. Never point both writers at the same experiment folder.
    """), code('''
    # These defaults already appear in CFG; uncomment only for a NEW experiment:
    # CFG["training"]["microbatch"] = 1
    # CFG["schedule"]["sample_seconds"] = 600
    # CFG["schedule"]["recovery_seconds"] = 900
    # CFG["schedule"]["milestone_seconds"] = 3600
    # CFG["schedule"]["budget_seconds"] = 8 * 3600
    # CFG["schedule"]["keep_recovery"] = 4
    validate(CFG)
    import json
    print(json.dumps(CFG, indent=2))
    # A draft is not a running experiment; the runner saves immutable run metadata.
    DRAFT_CONFIG = PROJECT / "configs" / (CFG["experiment_id"] + ".draft.json")
    write_json(DRAFT_CONFIG, CFG)
    '''), md("""
    ## Optional · Import and resume an experiment from another machine
    **Skip this cell for a new independent experiment.** First stop training on the source and use its handoff export cell. A handoff seals the source run, and includes the prepared images so preprocessing cannot silently differ. Import a given bundle on **one destination only**. Existing destination experiment folders are refused; use an empty project root when moving back.

    Set `IMPORT_BUNDLE` above, then run this cell instead of cells 4–6. It supplies the saved `CFG` and `PREPARED`. Next run cell 7, then **Resume latest verified checkpoint**. Offline copied bundles cannot enforce a global distributed lock; do not run a copied experiment in two locations. A local lock refuses concurrent writers to one coherent storage root; stale locks never expire automatically.
    """), code('''
    if IMPORT_BUNDLE:
        CFG, PREPARED = import_recovery_bundle(IMPORT_BUNDLE, PROJECT, SCRATCH)
        EXPERIMENT_ID = CFG["experiment_id"]
        DATASET_MANIFEST = read_json(PREPARED / "manifest.json")
    else:
        print("Import skipped. Set IMPORT_BUNDLE only when moving a stopped experiment.")
    '''), md("""
    ## 7 · Short training and checkpoint-recovery test
    This uses your real dataset and the actual configured model. It trains two iterations, persists a full checkpoint, and compares the next iteration against a fresh trainer restored from disk. It checks G, D, EMA, optimizers, sampler and random states exactly on this runtime. Smoke work uses a separate ID and does not consume the production run's eight-hour budget.
    It also measures checkpoint size and estimates retained storage. Ensure you have extra space for originals, prepared data, smoke runs, samples, manual keeps, and export ZIPs. Drive account quota must be checked in Drive; filesystem free-space figures can be misleading. Rerun this smoke test after every kernel/runtime restart before a long run.
    """), code('''
    SMOKE_REPORT = smoke_test(CFG, PROJECT, SCRATCH, PREPARED)
    display(Image.open(SMOKE_REPORT["preview"]))
    '''), md("""
    ## 8 · Start training — NEW experiment only
    Set `START_NEW_RUN = True` only when ready, then run this cell. It refuses an existing experiment. The smoke test is mandatory. The call occupies this kernel until the budget is reached or you interrupt it.
    """), code('''
    START_NEW_RUN = False  # Change to True to start the full run.
    if START_NEW_RUN:
        RESULT = train(CFG, PROJECT, SCRATCH, PREPARED, resume=False)
    else:
        print("Ready. Set START_NEW_RUN=True to begin, or use the resume cell below.")
    '''), md("""
    ## Resume latest verified checkpoint
    Run setup/preparation and the smoke test after reconnecting. Set `RESUME_RUN = True` here. This verifies the persisted checkpoint checksum and restores models, optimizers, EMA, counters, cumulative time, event timers, random states, and the data sampler position.
    After three saved training hours, about five hours remain. CUDA/OS/driver/hardware changes may change floating point results even with full state restoration; cross-machine bitwise equality is not promised. This is a full-state resume of this shared runner, not an importer for upstream `.pkl` weight snapshots.
    """), code('''
    RESUME_RUN = False  # Change to True to resume; leave START_NEW_RUN=False.
    if RESUME_RUN:
        latest_verified(PROJECT, CFG)
        clear_stop(PROJECT, CFG)
        RESULT = train(CFG, PROJECT, SCRATCH, PREPARED, resume=True)
    else:
        print("Set RESUME_RUN=True to resume the latest verified persisted checkpoint.")
    '''), md("""
    ### Stop, interrupt, and stale-lock recovery
    Use the notebook's stop/interrupt button once and wait: SIGINT/SIGTERM normally request a checkpoint at the next complete D/G iteration. If the runtime injects an exception mid-iteration, partially updated optimizers are not saved; the last verified checkpoint remains usable. A kill, crash, sleep, or lost Colab runtime can prevent a final save.
    You can also create an empty `STOP` file inside `experiments/<ID>/` from another terminal/file browser. A busy kernel cannot execute a second stop cell. Wait for the save-complete output before shutting down or exporting.

    If an abruptly terminated writer leaves a lock, first confirm that every old writer is stopped. Then inspect its token and explicitly release it below. **Never release a lock just because training looks slow.**
    """), code('''
    RELEASE_STALE_LOCK = False
    if RELEASE_STALE_LOCK:
        from neo_r3gan.checkpoints import release_stale_lock
        run = PROJECT / "experiments" / CFG["experiment_id"]
        owner_path = run / "writer.lock" / "owner.json"
        owner = read_json(owner_path) if owner_path.exists() else {"token": "missing-owner"}
        print(owner)
        # Paste the inspected token, and the literal confirmation only after stopping every old writer.
        EXPECTED_TOKEN = ""
        CONFIRMATION = ""  # I stopped every writer for this experiment
        release_stale_lock(run, EXPECTED_TOKEN, CONFIRMATION)
    '''), md("""
    ## 9 · View progress and generated samples
    Run after a training call returns. During training, the cell prints live progress and you can inspect saved PNGs in Drive/local file browser. G/D losses are diagnostics, not proof of image quality or originality.
    """), code('''
    RUN_FOLDER = show_progress(PROJECT, CFG)
    print(RUN_FOLDER)
    '''), md("### Generate individual PNGs using EMA and reproducible seeds"), code('''
    GENERATED = generate_images(PROJECT, SCRATCH, CFG, PREPARED, seeds=range(16))
    from neo_r3gan.data import grid
    display(grid([Image.open(path) for path in GENERATED], columns=4))
    print("Saved:", GENERATED[0].parent)
    '''), md("### Manually keep a checkpoint"), code('''
    KEEP_LATEST = False
    if KEEP_LATEST:
        print(mark_keep(PROJECT, CFG))  # Adds a manifest tag; does not duplicate the checkpoint.
    '''), md("""
    ## 10 · Export checkpoints, generated images, and logs
    Results export includes every retained checkpoint, configuration/version/dataset metadata, logs, previews and individual generated PNGs. It leaves this run active for future resume. It can require substantial additional storage.
    """), code('''
    EXPORT_RESULTS = False
    if EXPORT_RESULTS:
        RESULTS_ZIP = export_results(PROJECT, SCRATCH, CFG)
        print("Results ZIP:", RESULTS_ZIP)
    '''), md("""
    ### Move this experiment to the other machine — seal source and export recovery bundle
    Use only after training has stopped. This operation seals the source run so it cannot train again in this folder. The bundle carries the latest verified full checkpoint, config, dataset manifest, exact prepared image ZIP, environment and code identity. Copy/download it to one destination and use **Import and resume** there. Keep the original source as an archive. Exporting results above is sufficient if you only want a backup.
    """), code('''
    MOVE_EXPERIMENT = False
    if MOVE_EXPERIMENT:
        HANDOFF_ZIP = export_recovery_bundle(PROJECT, SCRATCH, CFG)
        print("Import on one destination:", HANDOFF_ZIP)
    '''), md("""
    The latest four recovery entries, all hourly milestones, the final budget checkpoint, and manual keeps survive retention. A single file can carry several tags. On Colab each checkpoint is written atomically to scratch, copied under a temporary Drive filename, SHA-256 checked, renamed, and read back before the manifest advances. Old valid files are removed only after the replacement and manifest persist. Drive's mount is the storage interface: a completed read-back is verified, but cannot prove Google's backend replication or protect against account deletion/quota failures. Failures are printed and stop the training call.

    Shared implementation details, upstream checkpoint audit, exact launch commands, and the validation record are in `README.md`, `docs/CHECKPOINT_AUDIT.md`, and `VALIDATION.md` in the workspace package.
    """)]
    for i, cell in enumerate(cells):
        cell["id"] = f"{label.lower()}-{i:03d}"
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3" if colab else "NeoHuman R3GAN (.venv)", "language": "python", "name": "python3" if colab else "neohuman-r3gan"}, "language_info": {"name": "python", "version": "3.11"}, "colab": {"name": f"NeoHuman_R3GAN_{label}.ipynb", "provenance": []}}, "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    for is_colab in (True, False):
        label = "Colab" if is_colab else "Local"
        path = ROOT / f"NeoHuman_R3GAN_{label}.ipynb"
        path.write_text(json.dumps(notebook(is_colab), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(path)
    (ROOT / "configs").mkdir(exist_ok=True)
    (ROOT / "configs" / "example.json").write_text(json.dumps(default_config(), indent=2) + "\n")
