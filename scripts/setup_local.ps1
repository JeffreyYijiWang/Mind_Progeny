param([switch]$Dev)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 and retry.' }
}
& .\.venv\Scripts\python.exe -m pip install pip==25.1.1
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& .\.venv\Scripts\python.exe -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch install failed; check the NVIDIA driver and network.' }
$requirementsFile = if ($Dev) { 'requirements-dev.txt' } else { 'requirements-notebook.txt' }
& .\.venv\Scripts\python.exe -m pip install -r $requirementsFile
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe scripts/fetch_upstream.py
if ($LASTEXITCODE -ne 0) { throw 'Pinned source retrieval failed.' }
& .\.venv\Scripts\python.exe -m ipykernel install --sys-prefix --name neohuman-r3gan --display-name 'NeoHuman R3GAN (.venv)'
if ($LASTEXITCODE -ne 0) { throw 'Kernel registration failed.' }
Write-Host 'Ready: .\.venv\Scripts\python.exe -m jupyterlab NeoHuman_R3GAN_Local.ipynb'
