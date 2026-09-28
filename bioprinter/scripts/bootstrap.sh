#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
echo 'Requires Python 3.11. Install optional external executables separately; see docs/setup.md.'
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m bioprinter doctor
