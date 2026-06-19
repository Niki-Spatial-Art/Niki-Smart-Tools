$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$Python = "python"
$BundledPython = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $BundledPython) {
    $Python = $BundledPython
}

$Source = if ($env:MASON_LIBRARY_SOURCE) { $env:MASON_LIBRARY_SOURCE } else { "D:\梅森" }
$Output = if ($env:MASON_LIBRARY_OUTPUT) { $env:MASON_LIBRARY_OUTPUT } else { "data\mason_library" }

& $Python "tools\index_mason_library.py" --source $Source --output $Output
