$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $ProjectRoot "backend"
$Frontend = Join-Path $ProjectRoot "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Backend virtual environment not found at $Python"
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    throw "Frontend dependencies are missing. Run 'npm install' inside frontend first."
}

$LanAddress = Get-NetIPConfiguration |
    Where-Object {
        $_.NetAdapter.Status -eq "Up" -and
        $_.IPv4DefaultGateway -and
        $_.IPv4Address
    } |
    ForEach-Object { $_.IPv4Address.IPAddress } |
    Select-Object -First 1

Start-Process powershell -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Backend'; & '$Python' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
)

Start-Process powershell -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Frontend'; npm run dev"
)

Write-Host ""
Write-Host "BOOKPILE is starting." -ForegroundColor Green
Write-Host "On this computer: http://localhost:5173"
if ($LanAddress) {
    Write-Host "On your phone:     http://${LanAddress}:5173" -ForegroundColor Cyan
    Write-Host "Both devices must be connected to the same Wi-Fi."
} else {
    Write-Warning "No active LAN address was detected. Run 'ipconfig' to find the computer's IPv4 address."
}
Write-Host ""
Write-Host "Keep both server windows open while using BOOKPILE."
