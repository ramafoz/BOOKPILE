$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Shell = New-Object -ComObject WScript.Shell

function New-BookpileShortcut {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Description,
        [string]$Icon
    )

    $Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "$Name.lnk"))
    $Shortcut.TargetPath = $PowerShell
    $Shortcut.Arguments = (
        "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass " +
        "-File `"$Script`""
    )
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = $Description
    $Shortcut.IconLocation = $Icon
    $Shortcut.Save()
}

New-BookpileShortcut `
    "Start BOOKPILE" `
    (Join-Path $ProjectRoot "start-bookpile-background.ps1") `
    "Start BOOKPILE for this computer and the home network" `
    "$env:SystemRoot\System32\imageres.dll,102"

New-BookpileShortcut `
    "Stop BOOKPILE" `
    (Join-Path $ProjectRoot "stop-bookpile.ps1") `
    "Stop the BOOKPILE background servers" `
    "$env:SystemRoot\System32\imageres.dll,100"

Write-Host "Desktop shortcuts created in $Desktop"
