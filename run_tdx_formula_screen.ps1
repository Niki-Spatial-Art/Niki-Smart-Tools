param(
    [string]$InputPath = "$PSScriptRoot\work\tdx_exports",
    [string]$OutputBase = "$PSScriptRoot\reports"
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path -LiteralPath $InputPath)) {
    New-Item -ItemType Directory -Path $InputPath -Force | Out-Null
    Write-Host "Created input folder:" $InputPath -ForegroundColor Yellow
    Write-Host "Put exported TongDaXin formula files here, then rerun this command." -ForegroundColor Yellow
    exit 2
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $OutputBase "tdx_formula_screen_$stamp"
New-Item -ItemType Directory -Path $out -Force | Out-Null

python "$PSScriptRoot\tools\tdx_formula_screen.py" --input "$InputPath" --output "$out"

Write-Host ""
Write-Host "Output:" $out -ForegroundColor Cyan
Write-Host "Report:" (Join-Path $out "tdx_formula_screen.md") -ForegroundColor Cyan
Write-Host "CSV:" (Join-Path $out "tdx_formula_screen.csv") -ForegroundColor Cyan
