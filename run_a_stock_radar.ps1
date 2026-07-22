$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$localPython = Join-Path $projectRoot ".venv-a-stock\\Scripts\\python.exe"
$python = if ($env:A_STOCK_PYTHON) {
    $env:A_STOCK_PYTHON
} elseif (Test-Path -LiteralPath $localPython) {
    $localPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
& $python .\tools\a_stock_radar_snapshot.py @args
exit $LASTEXITCODE
