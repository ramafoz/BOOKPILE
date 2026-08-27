param(
    [switch]$SkipDesktopShortcuts
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $ProjectRoot "backend"
$Frontend = Join-Path $ProjectRoot "frontend"
$VirtualEnvironment = Join-Path $Backend ".venv"
$VirtualPython = Join-Path $VirtualEnvironment "Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-MajorVersion {
    param(
        [string]$VersionText,
        [string]$ToolName
    )
    if ($VersionText -notmatch '(\d+)\.(\d+)') {
        throw "Could not determine the installed $ToolName version from '$VersionText'."
    }
    return [int]$Matches[1]
}

if ($env:OS -ne "Windows_NT") {
    throw "BOOKPILE Local v1 is currently packaged and supported for Windows only."
}

Write-Host "BOOKPILE Local v1 installer" -ForegroundColor Green
Write-Host "Project folder: $ProjectRoot"
Write-Host "Existing catalogue data and covers will not be overwritten."

$PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw "Python was not found. Install 64-bit Python 3.11 or newer, then run this installer again."
}
$PythonVersion = & $PythonCommand.Source --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Python could not be started. Install 64-bit Python 3.11 or newer and enable 'Add Python to PATH'."
}
if ((Get-MajorVersion $PythonVersion "Python") -lt 3) {
    throw "BOOKPILE requires Python 3.11 or newer. Detected: $PythonVersion"
}
if ($PythonVersion -notmatch 'Python 3\.(\d+)') {
    throw "BOOKPILE requires Python 3.11 or newer. Detected: $PythonVersion"
}
if ([int]$Matches[1] -lt 11) {
    throw "BOOKPILE requires Python 3.11 or newer. Detected: $PythonVersion"
}

$NodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $NodeCommand -or -not $NpmCommand) {
    throw "Node.js and npm were not found. Install Node.js 20 LTS or newer, then run this installer again."
}
$NodeVersion = & $NodeCommand.Source --version 2>&1
if ($LASTEXITCODE -ne 0 -or (Get-MajorVersion $NodeVersion "Node.js") -lt 20) {
    throw "BOOKPILE requires Node.js 20 or newer. Detected: $NodeVersion"
}

Write-Host "Python: $PythonVersion"
Write-Host "Node.js: $NodeVersion"

if (-not (Test-Path $VirtualPython)) {
    Write-Step "Creating the private Python environment"
    & $PythonCommand.Source -m venv $VirtualEnvironment
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VirtualPython)) {
        throw "The Python virtual environment could not be created."
    }
} else {
    Write-Step "Using the existing private Python environment"
}

Write-Step "Installing backend dependencies"
& $VirtualPython -m pip install --disable-pip-version-check -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Backend dependency installation failed."
}

Write-Step "Installing exact frontend dependencies"
Push-Location $Frontend
try {
    & $NpmCommand.Source ci
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend dependency installation failed."
    }

    Write-Step "Building the optimized frontend"
    & $NpmCommand.Source run build
    if ($LASTEXITCODE -ne 0) {
        throw "The optimized frontend build failed."
    }
}
finally {
    Pop-Location
}

Write-Step "Preparing the local catalogue"
Push-Location $Backend
try {
    & $VirtualPython -c "from app.database import init_database; init_database()"
    if ($LASTEXITCODE -ne 0) {
        throw "The local catalogue could not be initialized."
    }
}
finally {
    Pop-Location
}

if (-not $SkipDesktopShortcuts) {
    Write-Step "Creating Start and Stop desktop shortcuts"
    & (Join-Path $ProjectRoot "install-desktop-shortcuts.ps1")
}

Write-Host "`nBOOKPILE Local v1 is installed." -ForegroundColor Green
Write-Host "Start it with the 'Start BOOKPILE' desktop shortcut or run:"
Write-Host "  .\start-bookpile-background.ps1" -ForegroundColor Yellow
Write-Host "Before importing or entering a large catalogue, read BACKUP_AND_RECOVERY.md."
