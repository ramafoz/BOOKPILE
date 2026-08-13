$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $ProjectRoot "backend"
$Frontend = Join-Path $ProjectRoot "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$Vite = Join-Path $Frontend "node_modules\.bin\vite.cmd"

if (-not (Test-Path $Python)) {
    throw "Backend virtual environment not found at $Python"
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    throw "Frontend dependencies are missing. Run 'npm install' inside frontend first."
}
if (-not (Test-Path $Vite)) {
    throw "Vite was not found at $Vite. Run 'npm install' inside frontend first."
}

$LanAddress = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
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

if (-not $LanAddress) {
    throw "No active LAN address was detected. Connect this computer to the home network and try again."
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Address,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Connection = $Client.BeginConnect($Address, $Port, $null, $null)
        if (-not $Connection.AsyncWaitHandle.WaitOne(300)) {
            return $false
        }
        $Client.EndConnect($Connection)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $Client.Dispose()
    }
}

$OccupiedServices = @()
if (Test-TcpPort -Address "127.0.0.1" -Port 8000) {
    $OccupiedServices += "backend (port 8000)"
}
if (Test-TcpPort -Address $LanAddress -Port 5173) {
    $OccupiedServices += "frontend (port 5173)"
}
if ($OccupiedServices.Count -gt 0) {
    $ServiceList = $OccupiedServices -join " and "
    throw "BOOKPILE is already running or its ports are occupied by $ServiceList. Close the existing BOOKPILE server windows before starting it again."
}

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
    Write-Host "Building the optimized mobile frontend..." -ForegroundColor Yellow
    Push-Location $Frontend
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "The frontend build failed."
        }
    }
    finally {
        Pop-Location
    }
}

Start-Process powershell -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Backend'; & '$Python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
)

Start-Process powershell -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Frontend'; & '$Vite' preview --host=$LanAddress --port=5173"
)

Write-Host ""
Write-Host "BOOKPILE is starting." -ForegroundColor Green
Write-Host "On this computer and phone: http://${LanAddress}:5173" -ForegroundColor Cyan
Write-Host "Both devices must be connected to the same Wi-Fi."
Write-Host ""
Write-Host "Keep both server windows open while using BOOKPILE."
