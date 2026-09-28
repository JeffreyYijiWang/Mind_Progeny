$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host 'Requires Python 3.11. Inkscape, PrusaSlicer and FFmpeg are optional separate system installs.'
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
& .\.venv\Scripts\python.exe -m pip install --use-feature=truststore --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }
& .\.venv\Scripts\python.exe -m bioprinter doctor
