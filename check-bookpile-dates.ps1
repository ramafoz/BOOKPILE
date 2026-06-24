$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project "backend\.venv\Scripts\python.exe"

& $python (Join-Path $project "maintenance\check_dates.py")
$exitCode = $LASTEXITCODE

Write-Host ""
Read-Host "Press Enter to close"
exit $exitCode
