$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "monitor_$stamp.log"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run started" | Out-File -FilePath $logFile -Encoding utf8

$triggeredCloudFallback = $false

function Invoke-GitHubMonitorFallback {
    param(
        [string]$Reason
    )

    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Local monitor failed; trying GitHub Actions fallback. Reason: $Reason" | Out-File -FilePath $logFile -Encoding utf8 -Append

    try {
        $gh = (Get-Command gh -ErrorAction Stop).Source
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GitHub CLI: $gh" | Out-File -FilePath $logFile -Encoding utf8 -Append
        & $gh workflow run monitor.yml --ref main *>> $logFile
        $ghExitCode = $LASTEXITCODE
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GitHub fallback exit code: $ghExitCode" | Out-File -FilePath $logFile -Encoding utf8 -Append

        if ($ghExitCode -eq 0) {
            "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GitHub fallback accepted. Cloud email should arrive after the workflow finishes." | Out-File -FilePath $logFile -Encoding utf8 -Append
            return $true
        }
    }
    catch {
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GitHub fallback failed: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding utf8 -Append
    }

    return $false
}

try {
    $python = (Get-Command python -ErrorAction Stop).Source
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Python: $python" | Out-File -FilePath $logFile -Encoding utf8 -Append

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $python monitor.py 2>&1 | ForEach-Object {
        $_.ToString() | Out-File -FilePath $logFile -Encoding utf8 -Append
    }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference

    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Python exit code: $exitCode" | Out-File -FilePath $logFile -Encoding utf8 -Append
    if ($exitCode -ne 0) {
        $triggeredCloudFallback = Invoke-GitHubMonitorFallback -Reason "monitor.py exit code $exitCode"
        if ($triggeredCloudFallback) {
            "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run finished via GitHub fallback" | Out-File -FilePath $logFile -Encoding utf8 -Append
            exit 0
        }
        throw "monitor.py failed with exit code $exitCode"
    }
}
catch {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding utf8 -Append
    if (-not $triggeredCloudFallback) {
        $triggeredCloudFallback = Invoke-GitHubMonitorFallback -Reason $_.Exception.Message
        if ($triggeredCloudFallback) {
            "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run finished via GitHub fallback" | Out-File -FilePath $logFile -Encoding utf8 -Append
            exit 0
        }
    }
    throw
}

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run finished" | Out-File -FilePath $logFile -Encoding utf8 -Append
