$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $projectRoot "run_monitor_local.ps1"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing local runner: $runner"
}

$taskName = "ETF Strategy Monitor 0910"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At 09:10

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Run ETF Strategy Monitor locally at 09:10 Beijing time on weekdays." `
    -Force | Out-Null

Write-Host "Installed Windows scheduled task: $taskName"
Write-Host "Runner: $runner"
Write-Host "Schedule: Monday-Friday 09:10"
Write-Host "Logs will be saved in: $(Join-Path $projectRoot 'logs')"
