$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $projectRoot "scripts\trigger_cloud_email.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing email trigger script: $runner"
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$slots = @(
    # GitHub Actions dispatch and the full-market scan normally consume 1-3 minutes.
    # Run early so delivery is close to the user-facing slot time.
    @{ Name = "Niki Email Intraday 0945"; Time = "09:42"; TargetTime = "09:45"; Mode = "intraday" },
    @{ Name = "Niki Email Intraday 1045"; Time = "10:42"; TargetTime = "10:45"; Mode = "intraday" },
    @{ Name = "Niki Email Intraday 1420"; Time = "14:17"; TargetTime = "14:20"; Mode = "intraday" },
    @{ Name = "Niki Email Post Close 1535"; Time = "15:32"; TargetTime = "15:35"; Mode = "post_close" }
)

foreach ($slot in $slots) {
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Mode $($slot.Mode)"
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
        -At $slot.Time

    Register-ScheduledTask `
        -TaskName $slot.Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Pre-dispatch the $($slot.Mode) Investment Workbench email at $($slot.Time) Beijing time; target delivery $($slot.TargetTime)." `
        -Force | Out-Null
    Write-Host "Installed: $($slot.Name) (trigger $($slot.Time), target $($slot.TargetTime))"
}

Write-Host "Tasks use GitHub Actions SMTP secrets and do not read or upload local broker snapshots."
