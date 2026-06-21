param([switch]$Quiet)

$ErrorActionPreference = "SilentlyContinue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $ProjectRoot ".bookpile-runtime"
$StateFile = Join-Path $Runtime "state.json"

Add-Type -AssemblyName System.Windows.Forms

function Stop-ProcessTree {
    param([int]$ProcessId)
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        & taskkill.exe /PID $ProcessId /T /F *> $null
    }
}

$Stopped = $false
if (Test-Path $StateFile) {
    $State = Get-Content $StateFile -Raw | ConvertFrom-Json
    Stop-ProcessTree ([int]$State.frontend_pid)
    Stop-ProcessTree ([int]$State.backend_pid)
    $Stopped = $true
}

# Stop project-owned listeners even when they came from an older launcher.
foreach ($Port in 5173, 8000) {
    $Listeners = Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        $ListenerProcess = Get-CimInstance Win32_Process `
            -Filter "ProcessId = $($Listener.OwningProcess)"
        if ($ListenerProcess.CommandLine -like "*$ProjectRoot*") {
            Stop-ProcessTree ([int]$Listener.OwningProcess)
            $Stopped = $true
        }
    }
}

$LegacyProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -like "*$ProjectRoot*" -and
        (
            $_.CommandLine -match "uvicorn\s+app\.main:app" -or
            $_.CommandLine -match "vite(\.cmd|\.js)?\s+preview"
        )
    }
foreach ($Process in $LegacyProcesses) {
    Stop-ProcessTree ([int]$Process.ProcessId)
    $Stopped = $true
}

Remove-Item $StateFile -Force -ErrorAction SilentlyContinue

$Message = if ($Stopped) {
    "BOOKPILE has been stopped."
} else {
    "BOOKPILE was not running."
}
if ($Quiet) {
    Write-Output $Message
} else {
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "BOOKPILE",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}
