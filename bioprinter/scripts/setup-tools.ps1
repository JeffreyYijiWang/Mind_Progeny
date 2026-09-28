param(
    [ValidateSet('inkscape','prusa-slicer','both')][string]$Tool = 'both',
    [switch]$Install,
    [switch]$Upgrade
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$scriptArgs = @((Join-Path $PSScriptRoot 'setup_external.py'), '--tool', $Tool)
if ($Install) { $scriptArgs += '--install' }
if ($Upgrade) { $scriptArgs += '--upgrade' }
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -X utf8 @scriptArgs
} else {
    py -3.11 -X utf8 @scriptArgs
}
exit $LASTEXITCODE
