param([switch]$Quiet)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $ProjectRoot "backend"
$Frontend = Join-Path $ProjectRoot "frontend"
$Runtime = Join-Path $ProjectRoot ".bookpile-runtime"
$StateFile = Join-Path $Runtime "state.json"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$ViteScript = Join-Path $Frontend "node_modules\vite\bin\vite.js"
$Node = (Get-Command node.exe -ErrorAction Stop).Source

function Show-BookpileMessage {
    param(
        [string]$Text,
        [string]$Title = "BOOKPILE",
        [System.Windows.Forms.MessageBoxIcon]$Icon =
            [System.Windows.Forms.MessageBoxIcon]::Information
    )

    if ($Quiet) {
        Write-Output "$Title`: $Text"
        return
    }
    [System.Windows.Forms.MessageBox]::Show(
        $Text,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        $Icon
    ) | Out-Null
}

function Get-LanAddress {
    return [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        Where-Object {
            $_.OperationalStatus -eq "Up" -and
            $_.NetworkInterfaceType -ne "Loopback"
        } |
        ForEach-Object {
            $properties = $_.GetIPProperties()
            if ($properties.GatewayAddresses.Count -gt 0) {
                $properties.UnicastAddresses |
                    Where-Object {
                        $_.Address.AddressFamily -eq
                            [System.Net.Sockets.AddressFamily]::InterNetwork -and
                        -not $_.Address.ToString().StartsWith("169.254.")
                    } |
                    ForEach-Object { $_.Address.ToString() }
            }
        } |
        Select-Object -First 1
}

function Test-Bookpile {
    param([string]$Url)
    try {
        $response = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

try {
    if (-not (Test-Path $Python)) {
        throw "Backend virtual environment not found."
    }
    if (-not (Test-Path $ViteScript)) {
        throw "Frontend dependencies are missing. Run npm install inside frontend."
    }

    $LanAddress = Get-LanAddress
    if (-not $LanAddress) {
        $LanAddress = "127.0.0.1"
    }
    $Url = "http://${LanAddress}:5173"

    if (Test-Bookpile $Url) {
        Set-Clipboard $Url
        Show-BookpileMessage "BOOKPILE is already running.`n`n$Url`n`nThe address has been copied to the clipboard."
        exit 0
    }

    New-Item -ItemType Directory -Force $Runtime | Out-Null
    $StartupLog = Join-Path $Runtime "startup.log"
    Set-Content $StartupLog "BOOKPILE startup: $(Get-Date -Format o)"

    $DistIndex = Join-Path $Frontend "dist\index.html"
    $SourceFiles = Get-ChildItem -Path @(
        (Join-Path $Frontend "src"),
        (Join-Path $Frontend "index.html"),
        (Join-Path $Frontend "vite.config.ts"),
        (Join-Path $Frontend "package.json")
    ) -Recurse -File
    $NewestSource = $SourceFiles |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1

    if (
        -not (Test-Path $DistIndex) -or
        (Get-Item $DistIndex).LastWriteTimeUtc -lt $NewestSource.LastWriteTimeUtc
    ) {
        Add-Content $StartupLog "Building optimized frontend..."
        Push-Location $Frontend
        try {
            & npm.cmd run build *>> $StartupLog
            if ($LASTEXITCODE -ne 0) {
                throw "The optimized frontend build failed."
            }
        }
        finally {
            Pop-Location
        }
    }

    $BackendProcess = Start-Process `
        -FilePath $Python `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", "8000"
        ) `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Runtime "backend.out.log") `
        -RedirectStandardError (Join-Path $Runtime "backend.err.log") `
        -PassThru

    $FrontendProcess = Start-Process `
        -FilePath $Node `
        -ArgumentList @(
            $ViteScript, "preview",
            "--host=$LanAddress", "--port=5173"
        ) `
        -WorkingDirectory $Frontend `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Runtime "frontend.out.log") `
        -RedirectStandardError (Join-Path $Runtime "frontend.err.log") `
        -PassThru

    @{
        backend_pid = $BackendProcess.Id
        frontend_pid = $FrontendProcess.Id
        url = $Url
        started_at = (Get-Date -Format o)
    } | ConvertTo-Json | Set-Content $StateFile

    $Ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-Bookpile $Url) {
            $Ready = $true
            break
        }
    }
    if (-not $Ready) {
        throw "BOOKPILE did not become ready. Logs are in $Runtime"
    }

    Set-Clipboard $Url
    $NetworkNote = if ($LanAddress -eq "127.0.0.1") {
        "No home network was detected, so this address works on this computer only."
    } else {
        "Open this address on devices connected to the same private Wi-Fi."
    }
    Show-BookpileMessage "BOOKPILE is ready.`n`n$Url`n`n$NetworkNote`n`nThe address has been copied to the clipboard."
}
catch {
    Show-BookpileMessage `
        "BOOKPILE could not start.`n`n$($_.Exception.Message)" `
        "BOOKPILE startup error" `
        ([System.Windows.Forms.MessageBoxIcon]::Error)
    exit 1
}
