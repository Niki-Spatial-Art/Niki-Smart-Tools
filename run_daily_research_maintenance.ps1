param(
    [switch]$NoNetwork,
    [switch]$NoPreview
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "daily_research_maintenance_$stamp.log"

function Write-Log {
    param([string]$Message)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" | Tee-Object -FilePath $logFile -Append
}

function Invoke-PythonStep {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $python = (Get-Command python -ErrorAction Stop).Source
    Write-Log "python $($Arguments -join ' ')"
    & $python @Arguments 2>&1 | ForEach-Object { $_.ToString() | Tee-Object -FilePath $logFile -Append }
    if ($LASTEXITCODE -ne 0) {
        throw "python step failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

Write-Log "Daily research maintenance started"

Invoke-PythonStep -Arguments @("tools/ifind_weekly_budget.py", "--mode", "postclose")
Invoke-PythonStep -Arguments @("tools/ifind_clean_radar.py")
Invoke-PythonStep -Arguments @("tools/ifind_position_backtest.py", "--days", "120")
Invoke-PythonStep -Arguments @("tools/ifind_smart_pick_batch.py", "--limit", "30")
Invoke-PythonStep -Arguments @("tools/ifind_announcement_gate.py")

$learningArgs = @("tools/learning_intake.py")
if ($NoNetwork) {
    $learningArgs += "--no-network"
}
Invoke-PythonStep -Arguments $learningArgs

Invoke-PythonStep -Arguments @("tools/action_audit.py", "export-plan", "--report", "reports/latest.json", "--journal", "data/paper_trade_journal.csv")
Invoke-PythonStep -Arguments @("tools/action_audit.py", "summarize", "--journal", "data/paper_trade_journal.csv")

if (-not $NoPreview) {
    Invoke-PythonStep -Arguments @("tools/local_dashboard.py", "--write-preview", "data/local_dashboard_preview.html")
}

Write-Log "Daily research maintenance finished"
