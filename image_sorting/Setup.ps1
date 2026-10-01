$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
}
& .venv/Scripts/python.exe -m pip install --use-feature=truststore -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Sorting dependencies could not be installed.' }
