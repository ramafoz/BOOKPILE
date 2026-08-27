param(
    [string]$Version = "1.0.0",
    [string]$Ref = "HEAD",
    [string]$OutputDirectory = "release-artifacts"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Git = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $Git) {
    throw "Git was not found. Install Git for Windows before building a release."
}
if ($Version -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$') {
    throw "Version must use a semantic form such as 1.0.0 or 1.0.0-rc.1."
}

Push-Location $ProjectRoot
try {
    $RepositoryRoot = (& $Git.Source rev-parse --show-toplevel 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $RepositoryRoot -ne $ProjectRoot) {
        throw "Run this script from the BOOKPILE repository checkout."
    }

    $Dirty = & $Git.Source status --porcelain
    if ($Dirty) {
        throw "The working tree is not clean. Commit or discard changes before building the release artifact."
    }

    & $Git.Source rev-parse --verify "$Ref^{commit}" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Git reference '$Ref' does not identify a commit."
    }

    $Output = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
        $OutputDirectory
    } else {
        Join-Path $ProjectRoot $OutputDirectory
    }
    New-Item -ItemType Directory -Force $Output | Out-Null

    $BaseName = "BOOKPILE-Local-v$Version"
    $Archive = Join-Path $Output "$BaseName.zip"
    $Checksum = Join-Path $Output "$BaseName.sha256"
    Remove-Item -LiteralPath $Archive -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Checksum -Force -ErrorAction SilentlyContinue

    & $Git.Source archive `
        --format=zip `
        "--prefix=$BaseName/" `
        "--output=$Archive" `
        $Ref
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Archive)) {
        throw "Git could not create the release archive."
    }

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    "$Hash  $BaseName.zip" | Set-Content -LiteralPath $Checksum -Encoding ascii

    Write-Host "Release artifact created:" -ForegroundColor Green
    Write-Host "  $Archive"
    Write-Host "  $Checksum"
    Write-Host "SHA-256: $Hash"
}
finally {
    Pop-Location
}
