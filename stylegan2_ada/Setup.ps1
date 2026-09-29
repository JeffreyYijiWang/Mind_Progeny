$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 environment creation failed.' }
}
& .venv/Scripts/python.exe -m pip install --use-feature=truststore torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'Isolated PyTorch installation failed.' }
& .venv/Scripts/python.exe -m pip install --use-feature=truststore -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .venv/Scripts/python.exe manage.py fetch
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA source/weights preparation failed.' }
& .venv/Scripts/python.exe manage.py prepare
if ($LASTEXITCODE -ne 0) { throw 'Dataset preparation failed.' }
& .venv/Scripts/python.exe manage.py plan
if ($LASTEXITCODE -ne 0) { throw 'CPU-only configuration validation failed.' }
Write-Host 'Prepared. No GPU model or training was started.'
& .venv/Scripts/python.exe manage.py --profile 256 fetch
if ($LASTEXITCODE -ne 0) { throw '256px weight preparation failed.' }
& .venv/Scripts/python.exe manage.py --profile 256 prepare
if ($LASTEXITCODE -ne 0) { throw '256px dataset preparation failed.' }
& .venv/Scripts/python.exe manage.py --profile 256 plan
if ($LASTEXITCODE -ne 0) { throw '256px CPU configuration validation failed.' }
Write-Host 'Both resolutions prepared. Training remains off.'
