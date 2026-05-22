$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $projectRoot "run_monitor_local.ps1"
$catchupRunner = Join-Path $projectRoot "run_monitor_catchup.ps1"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing local runner: $runner"
}

if (-not (Test-Path -LiteralPath $catchupRunner)) {
    throw "Missing catchup runner: $catchupRunner"
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$times = @(
    @{ Suffix = "0910"; Time = "09:10"; Label = "盘前预案" },
    @{ Suffix = "0945"; Time = "09:45"; Label = "早盘确认" },
    @{ Suffix = "1045"; Time = "10:45"; Label = "二次确认" },
    @{ Suffix = "1345"; Time = "13:45"; Label = "午后延续" },
    @{ Suffix = "1440"; Time = "14:40"; Label = "尾盘处理" },
    @{ Suffix = "2130"; Time = "21:30"; Label = "收盘复盘" }
)

foreach ($slot in $times) {
    $taskName = "ETF Strategy Monitor $($slot.Suffix)"
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""

    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
        -At $slot.Time

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Run ETF Strategy Monitor locally at $($slot.Time) Beijing time on weekdays for $($slot.Label)." `
        -Force | Out-Null

    Write-Host "Installed Windows scheduled task: $taskName ($($slot.Time) $($slot.Label))"
}

$catchupAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$catchupRunner`""

$catchupTriggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "09:25"),
    (New-ScheduledTaskTrigger -AtLogOn)
)

Register-ScheduledTask `
    -TaskName "ETF Strategy Monitor Catchup" `
    -Action $catchupAction `
    -Trigger $catchupTriggers `
    -Settings $settings `
    -Description "Check whether today's ETF Strategy Monitor email was sent; if not, run it once." `
    -Force | Out-Null

Write-Host "Installed Windows scheduled task: ETF Strategy Monitor Catchup"

Write-Host "Runner: $runner"
Write-Host "Catchup runner: $catchupRunner"
Write-Host "Schedule: Monday-Friday 09:10, 09:45, 10:45, 13:45, 14:40, 21:30"
Write-Host "Logs will be saved in: $(Join-Path $projectRoot 'logs')"
