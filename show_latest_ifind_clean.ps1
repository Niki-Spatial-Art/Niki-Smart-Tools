$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$reportDir = Join-Path $root "reports\ifind_clean"

if (-not (Test-Path -LiteralPath $reportDir)) {
    Write-Host "No iFind clean report directory found. Run: python .\tools\ifind_clean_radar.py"
    exit 1
}

$latest = Get-ChildItem -LiteralPath $reportDir -Filter "*_ifind_clean_radar.md" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $latest) {
    Write-Host "No iFind clean report found. Run: python .\tools\ifind_clean_radar.py"
    exit 1
}

Write-Host "Opening latest iFind clean report:"
Write-Host $latest.FullName
notepad $latest.FullName
