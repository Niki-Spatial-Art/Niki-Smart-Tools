$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$sdkRoot = "C:\Users\Niki_Spatial\Documents\Codex\2026-05-20\codex-github-2\tmp"
$amazingDataSdk = Join-Path $sdkRoot "amazingdata_sdk"
$xingyaoSdk = Join-Path $sdkRoot "xingyao_sdk"

if (-not (Test-Path $amazingDataSdk) -or -not (Test-Path $xingyaoSdk)) {
    throw "Xingyao SDK paths were not found. Please check: $sdkRoot"
}

$user = "10500164719"
$secure = Read-Host "Enter Xingyao password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)

try {
    $pwd = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)

    $env:XINGYAO_ENABLED = "true"
    $env:XINGYAO_USER = $user
    $env:XINGYAO_PASSWORD = $pwd
    $env:XINGYAO_HOST = "101.230.159.234"
    $env:XINGYAO_PORT = "8600"
    $env:XINGYAO_SDK_PATHS = "$amazingDataSdk;$xingyaoSdk"

    & powershell -NoProfile -ExecutionPolicy Bypass -File .\run_monitor_local.ps1
}
finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    Remove-Variable secure,pwd,ptr,user -ErrorAction SilentlyContinue
    Remove-Item Env:XINGYAO_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:XINGYAO_USER -ErrorAction SilentlyContinue
    Remove-Item Env:XINGYAO_ENABLED -ErrorAction SilentlyContinue
}
