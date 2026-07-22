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
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

# The dashboard reads the private broker snapshot locally. This refresh only
# fetches public market prices and K-lines; it does not call iFind, Xingyao,
# option services, or a broker.
& $python .\tools\a_stock_radar_snapshot.py
if ($LASTEXITCODE -ne 0) {
    Write-Warning "行情快照未完整生成。工作台仍可打开，但会把新开仓降级为观察。"
}

& $python .\tools\local_dashboard.py --host 127.0.0.1 --port 8501
