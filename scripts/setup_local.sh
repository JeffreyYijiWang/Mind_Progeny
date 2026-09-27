#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3.11 -m venv .venv
.venv/bin/python -m pip install pip==25.1.1
.venv/bin/python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
.venv/bin/python -m pip install -r requirements-notebook.txt
.venv/bin/python scripts/fetch_upstream.py
.venv/bin/python -m ipykernel install --sys-prefix --name neohuman-r3gan --display-name 'NeoHuman R3GAN (.venv)'
echo 'Ready: .venv/bin/python -m jupyterlab NeoHuman_R3GAN_Local.ipynb'
