param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$now = Get-Date
$todayStamp = $now.ToString("yyyyMMdd")
$catchupLog = Join-Path $logDir ("monitor_catchup_{0}.log" -f $todayStamp)

function Write-CatchupLog {
    param([string]$Message)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" | Out-File -FilePath $catchupLog -Encoding utf8 -Append
}

Write-CatchupLog "Catchup check started"

if (-not $Force -and $now.TimeOfDay -lt ([TimeSpan]::Parse("09:12"))) {
    Write-CatchupLog "Skipped: before the first morning decision window"
    exit 0
}

$successPattern = "ETF strategy email sent|GitHub fallback accepted|SMTP email accepted"
$todayLogs = Get-ChildItem -Path $logDir -Filter ("monitor_{0}_*.log" -f $todayStamp) -File -ErrorAction SilentlyContinue

foreach ($log in $todayLogs) {
    if (Select-String -Path $log.FullName -Pattern $successPattern -Quiet -ErrorAction SilentlyContinue) {
        Write-CatchupLog "Skipped: successful monitor log already exists: $($log.Name)"
        exit 0
    }
}

Write-CatchupLog "No successful monitor email found for today; starting local monitor"

$runner = Join-Path $projectRoot "run_monitor_local.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing local runner: $runner"
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner
$exitCode = $LASTEXITCODE
Write-CatchupLog "Local monitor exit code: $exitCode"

if ($exitCode -ne 0) {
    exit $exitCode
}
