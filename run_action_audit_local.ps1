param(
    [switch]$NoEmail,
    [switch]$RequireEmail
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not $env:XINGYAO_QUOTE_PRIORITY) {
    $env:XINGYAO_QUOTE_PRIORITY = "true"
}
if (-not $env:XINGYAO_KLINE_PROBE_ENABLED) {
    $env:XINGYAO_KLINE_PROBE_ENABLED = "true"
}

$logDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "action_audit_$stamp.log"
$report = Join-Path $projectRoot "reports\latest.json"
$journal = Join-Path $projectRoot "data\paper_trade_journal.csv"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Action audit local run started" | Out-File -FilePath $logFile -Encoding utf8

if (-not (Test-Path -LiteralPath $report)) {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Missing report: $report" | Out-File -FilePath $logFile -Encoding utf8 -Append
    throw "Missing report: $report"
}

try {
    $python = (Get-Command python -ErrorAction Stop).Source
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Python: $python" | Out-File -FilePath $logFile -Encoding utf8 -Append

    function Invoke-OptionalPython {
        param(
            [Parameter(Mandatory = $true)]
            [string[]]$Arguments,
            [Parameter(Mandatory = $true)]
            [string]$StepName
        )

        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Optional step started: $StepName" | Out-File -FilePath $logFile -Encoding utf8 -Append
            & $python @Arguments 2>&1 | ForEach-Object {
                $_.ToString() | Out-File -FilePath $logFile -Encoding utf8 -Append
            }
            if ($LASTEXITCODE -ne 0) {
                "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Optional step failed: $StepName exit=$LASTEXITCODE" | Out-File -FilePath $logFile -Encoding utf8 -Append
            }
            else {
                "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Optional step finished: $StepName" | Out-File -FilePath $logFile -Encoding utf8 -Append
            }
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }

    function Invoke-AuditPython {
        param(
            [Parameter(Mandatory = $true)]
            [string[]]$Arguments
        )

        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $python @Arguments 2>&1 | ForEach-Object {
                $_.ToString() | Out-File -FilePath $logFile -Encoding utf8 -Append
            }
            return $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }

    Invoke-OptionalPython -StepName "xingyao-data-probe" -Arguments @("tools/xingyao_data_probe.py")
    Invoke-OptionalPython -StepName "clean-radar-xingyao-ifind-fallback" -Arguments @("tools/ifind_clean_radar.py")
    Invoke-OptionalPython -StepName "ifind-position-backtest" -Arguments @("tools/ifind_position_backtest.py")
    Invoke-OptionalPython -StepName "learning-intake" -Arguments @("tools/learning_intake.py", "--sources", "examples/learning_sources.json", "--output", "reports/learning_intake.md")

    $exitCode = Invoke-AuditPython -Arguments @("tools/action_audit.py", "export-plan", "--report", $report, "--journal", $journal)
    if ($exitCode -ne 0) {
        throw "action_audit export-plan failed with exit code $exitCode"
    }

    $exitCode = Invoke-AuditPython -Arguments @("tools/action_audit.py", "summarize", "--journal", $journal)
    if ($exitCode -ne 0) {
        throw "action_audit summarize failed with exit code $exitCode"
    }

    if (-not $NoEmail) {
        if (-not $env:SMTP_PORT) {
            $env:SMTP_PORT = "465"
        }
        $exitCode = Invoke-AuditPython -Arguments @("tools/action_audit.py", "notify-plan", "--report", $report, "--journal", $journal)
        if ($exitCode -ne 0) {
            $message = "action_audit notify-plan failed with exit code $exitCode; audit export still completed"
            "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] WARNING: $message" | Out-File -FilePath $logFile -Encoding utf8 -Append
            if ($env:ACTION_AUDIT_CLOUD_FALLBACK -ne "false") {
                try {
                    $gh = (Get-Command gh -ErrorAction Stop).Source
                    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Trying GitHub Actions fallback: action-audit.yml" | Out-File -FilePath $logFile -Encoding utf8 -Append
                    & $gh workflow run action-audit.yml --ref main 2>&1 | ForEach-Object {
                        $_.ToString() | Out-File -FilePath $logFile -Encoding utf8 -Append
                    }
                    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GitHub fallback exit code: $LASTEXITCODE" | Out-File -FilePath $logFile -Encoding utf8 -Append
                }
                catch {
                    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GitHub fallback unavailable: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding utf8 -Append
                }
            }
            if ($RequireEmail) {
                throw $message
            }
        }
    }
}
catch {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding utf8 -Append
    throw
}

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Action audit local run finished" | Out-File -FilePath $logFile -Encoding utf8 -Append
