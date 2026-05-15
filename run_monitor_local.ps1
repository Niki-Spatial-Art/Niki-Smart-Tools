$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "monitor_$stamp.log"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run started" | Out-File -FilePath $logFile -Encoding utf8

python monitor.py *>> $logFile

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ETF Strategy Monitor local run finished" | Out-File -FilePath $logFile -Encoding utf8 -Append
