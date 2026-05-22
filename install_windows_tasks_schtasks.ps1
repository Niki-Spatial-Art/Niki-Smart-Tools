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

$slots = @(
    @{ Name = "ETF Strategy Monitor 0910"; Time = "09:10"; Label = "盘前预案" },
    @{ Name = "ETF Strategy Monitor 0945"; Time = "09:45"; Label = "早盘确认" },
    @{ Name = "ETF Strategy Monitor 1045"; Time = "10:45"; Label = "二次确认" },
    @{ Name = "ETF Strategy Monitor 1345"; Time = "13:45"; Label = "午后延续" },
    @{ Name = "ETF Strategy Monitor 1440"; Time = "14:40"; Label = "尾盘处理" },
    @{ Name = "ETF Strategy Monitor 2130"; Time = "21:30"; Label = "收盘复盘" }
)

foreach ($slot in $slots) {
    $powershellPath = Join-Path $PSHOME "powershell.exe"
    $taskCommand = "`"$powershellPath`" -NoProfile -ExecutionPolicy Bypass -File `"$runner`""
    & schtasks.exe /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /TN $slot.Name /TR $taskCommand /ST $slot.Time | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install scheduled task: $($slot.Name)"
    }
    Write-Host "Installed: $($slot.Name) at $($slot.Time) $($slot.Label)"
}

$powershellPath = Join-Path $PSHOME "powershell.exe"
$catchupCommand = "`"$powershellPath`" -NoProfile -ExecutionPolicy Bypass -File `"$catchupRunner`""

& schtasks.exe /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /TN "ETF Strategy Monitor Catchup 0925" /TR $catchupCommand /ST 09:25 | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install scheduled task: ETF Strategy Monitor Catchup 0925"
}
Write-Host "Installed: ETF Strategy Monitor Catchup 0925"

& schtasks.exe /Create /F /SC ONLOGON /TN "ETF Strategy Monitor Catchup Logon" /TR $catchupCommand | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not install logon catchup task. The 09:25 catchup task is already installed; run this script as Administrator if you also want logon catchup."
}
else {
    Write-Host "Installed: ETF Strategy Monitor Catchup Logon"
}

Write-Host "Runner: $runner"
Write-Host "Catchup runner: $catchupRunner"
Write-Host "Logs: $(Join-Path $projectRoot 'logs')"
