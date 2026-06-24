$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project "backend\.venv\Scripts\python.exe"

& $python (Join-Path $project "maintenance\check_goodreads_links.py") --interactive
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Manual decisions are saved in the generated CSV report."
Read-Host "Press Enter to close"
exit $exitCode
