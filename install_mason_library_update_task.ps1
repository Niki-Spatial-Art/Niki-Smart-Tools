$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "NikiMasonLibraryUpdate"
$RunScript = Join-Path $RepoRoot "run_mason_library_update.ps1"

if (-not (Test-Path $RunScript)) {
    throw "Update script not found: $RunScript"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""

$Trigger = New-ScheduledTaskTrigger -Daily -At 21:30

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Update local Mason trading knowledge-library index." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: daily 21:30"
Write-Host "Script: $RunScript"
