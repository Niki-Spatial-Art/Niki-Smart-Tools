$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "monitor_$stamp.log"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run started" | Out-File -FilePath $logFile -Encoding utf8

try {
    $python = (Get-Command python -ErrorAction Stop).Source
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Python: $python" | Out-File -FilePath $logFile -Encoding utf8 -Append

    & $python monitor.py *>> $logFile
    $exitCode = $LASTEXITCODE

    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Python exit code: $exitCode" | Out-File -FilePath $logFile -Encoding utf8 -Append
    if ($exitCode -ne 0) {
        throw "monitor.py failed with exit code $exitCode"
    }
}
catch {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding utf8 -Append
    throw
}

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run finished" | Out-File -FilePath $logFile -Encoding utf8 -Append
