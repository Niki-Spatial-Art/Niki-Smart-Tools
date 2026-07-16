$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = if ($env:A_STOCK_PYTHON) { $env:A_STOCK_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
& $python .\tools\a_stock_radar_snapshot.py @args
exit $LASTEXITCODE
