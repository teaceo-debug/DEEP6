# nt8-deploy.ps1 - Deploy DEEP6 NinjaScript files to NT8 Custom folder
# Usage: nt8-deploy.ps1 [-Target All|Indicators|Strategies|AddOns] [-Force] [-DryRun]

param(
    [ValidateSet("All","Indicators","Strategies","AddOns")]
    [string]$Target = "All",
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoCustom = "$PSScriptRoot\..\Custom"
$NT8Custom  = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"

# Files that exist in the repo for the test project only — never deploy to NT8.
# FootprintBar.cs: types are defined inline in DEEP6Footprint.cs for NT8;
# the standalone file is for the net8.0 NUnit project only (causes CS0101 if deployed).
$NT8_EXCLUDE = @("FootprintBar.cs")

if (!(Test-Path $NT8Custom)) {
    Write-Error "NT8 Custom folder not found: $NT8Custom"
    exit 1
}

function Deploy-Folder {
    param([string]$Type)

    $src = "$RepoCustom\$Type\DEEP6"
    $dst = "$NT8Custom\$Type\DEEP6"

    if (!(Test-Path $src)) {
        Write-Host "  [$Type] Source not found -- skipping: $src" -ForegroundColor Yellow
        return
    }

    $srcFiles = Get-ChildItem $src -Recurse -Filter "*.cs" |
                Where-Object { $NT8_EXCLUDE -notcontains $_.Name }
    $count    = $srcFiles.Count

    if ($DryRun) {
        Write-Host "  [$Type] DRY RUN -- would copy $count file(s) to $dst" -ForegroundColor Cyan
        $srcFiles | ForEach-Object { Write-Host "    $($_.Name)" -ForegroundColor Gray }
        return
    }

    if (!$Force -and (Test-Path $dst)) {
        $changed = $srcFiles | Where-Object {
            $dstFile = Join-Path $dst $_.Name
            !(Test-Path $dstFile) -or
            (Get-FileHash $_.FullName).Hash -ne (Get-FileHash $dstFile).Hash
        }
        if ($changed.Count -eq 0) {
            Write-Host "  [$Type] No changes -- skipping (use -Force to override)" -ForegroundColor Gray
            return
        }
    }

    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    New-Item $dst -ItemType Directory -Force | Out-Null
    $srcFiles | ForEach-Object {
        $rel     = $_.FullName.Substring($src.Length)
        $dstFile = Join-Path $dst $rel
        $dstDir  = Split-Path $dstFile
        if (!(Test-Path $dstDir)) { New-Item $dstDir -ItemType Directory -Force | Out-Null }
        Copy-Item $_.FullName $dstFile -Force
    }

    Write-Host "  [$Type] Deployed $count file(s) to $dst" -ForegroundColor Green
    $srcFiles | ForEach-Object { Write-Host "    $($_.Name)" -ForegroundColor Gray }
}

$dryLabel = if ($DryRun) { "[DRY RUN] " } else { "" }
Write-Host ""
Write-Host "DEEP6 NT8 Deploy $($dryLabel)-- $(Get-Date -Format 'HH:mm:ss')"
Write-Host "Target: $Target | Source: $RepoCustom"
Write-Host "---------------------------------------------"

switch ($Target) {
    "All"        { "Indicators","Strategies","AddOns" | ForEach-Object { Deploy-Folder $_ } }
    "Indicators" { Deploy-Folder "Indicators" }
    "Strategies" { Deploy-Folder "Strategies" }
    "AddOns"     { Deploy-Folder "AddOns" }
}

if (!$DryRun) {
    Write-Host ""
    Write-Host "Deploy complete. Run nt8-compile.ps1 to recompile in NT8." -ForegroundColor Cyan
}
