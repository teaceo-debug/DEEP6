#Requires -Version 5.1
<#
.SYNOPSIS
    Deploys DEEP6.cs to NinjaTrader 8's Custom Indicators folder.

.DESCRIPTION
    Copies Indicators\DEEP6.cs to the NT8 Custom folder and optionally
    triggers NT8 to recompile via its automation interface.

.PARAMETER NT8CustomPath
    Path to NinjaTrader 8 bin\Custom folder.
    Defaults to: $env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom

.PARAMETER SkipCompile
    Skip triggering NT8 recompile (just file copy).

.EXAMPLE
    .\scripts\Deploy-ToNT8.ps1
    .\scripts\Deploy-ToNT8.ps1 -NT8CustomPath "D:\NT8\Custom"
    .\scripts\Deploy-ToNT8.ps1 -SkipCompile
#>

param(
    [string] $NT8CustomPath = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom",
    [switch] $SkipCompile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Config ──────────────────────────────────────────────────────────────────
$ScriptDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot    = Split-Path -Parent $ScriptDir
$SourceFile     = Join-Path $ProjectRoot "Indicators\DEEP6.cs"
$DestFolder     = Join-Path $NT8CustomPath "Indicators"
$DestFile       = Join-Path $DestFolder   "DEEP6.cs"
$TimeStamp      = Get-Date -Format "HH:mm:ss"

# ── Banner ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ██████╗ ███████╗███████╗██████╗  ██████╗ " -ForegroundColor Cyan
Write-Host "  ██╔══██╗██╔════╝██╔════╝██╔══██╗██╔════╝ " -ForegroundColor Cyan
Write-Host "  ██║  ██║█████╗  █████╗  ██████╔╝███████╗ " -ForegroundColor Cyan
Write-Host "  ██║  ██║██╔══╝  ██╔══╝  ██╔═══╝ ╚════██║ " -ForegroundColor Cyan
Write-Host "  ██████╔╝███████╗███████╗██║     ██████╔╝ " -ForegroundColor Cyan
Write-Host "  ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═════╝  " -ForegroundColor Cyan
Write-Host "  v1.0.0  Deploy Script  [$TimeStamp]" -ForegroundColor DarkCyan
Write-Host ""

# ── Validate source ──────────────────────────────────────────────────────────
if (-not (Test-Path $SourceFile)) {
    Write-Host "  [ERROR] Source not found: $SourceFile" -ForegroundColor Red
    exit 1
}

$SourceLines = (Get-Content $SourceFile | Measure-Object -Line).Lines
$SourceSize  = (Get-Item $SourceFile).Length
Write-Host "  Source  : $SourceFile" -ForegroundColor Gray
Write-Host "  Lines   : $SourceLines  |  Size: $([math]::Round($SourceSize/1024,1)) KB" -ForegroundColor Gray
Write-Host ""

# ── Validate / create destination ────────────────────────────────────────────
if (-not (Test-Path $NT8CustomPath)) {
    Write-Host "  [WARN] NT8 Custom path not found: $NT8CustomPath" -ForegroundColor Yellow
    Write-Host "  Is NinjaTrader 8 installed?" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $DestFolder)) {
    Write-Host "  Creating destination folder..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path $DestFolder -Force | Out-Null
}

# ── Backup existing file ─────────────────────────────────────────────────────
if (Test-Path $DestFile) {
    $BackupDir  = Join-Path $ProjectRoot "backups"
    $BackupFile = Join-Path $BackupDir "DEEP6_$(Get-Date -Format 'yyyyMMdd_HHmmss').cs"
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Copy-Item $DestFile $BackupFile
    Write-Host "  Backup  : $BackupFile" -ForegroundColor DarkGray
}

# ── Deploy ───────────────────────────────────────────────────────────────────
Write-Host "  Copying DEEP6.cs..." -ForegroundColor White
Copy-Item -Path $SourceFile -Destination $DestFile -Force
Write-Host "  Dest    : $DestFile" -ForegroundColor Gray

# Verify copy
$CopiedSize = (Get-Item $DestFile).Length
if ($CopiedSize -ne $SourceSize) {
    Write-Host "  [ERROR] File size mismatch after copy!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  ✓ DEPLOYED SUCCESSFULLY" -ForegroundColor Green
Write-Host ""

# ── Trigger NT8 compile ──────────────────────────────────────────────────────
if (-not $SkipCompile) {
    $NT8Process = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
    if ($NT8Process) {
        Write-Host "  NinjaTrader 8 is running. Triggering recompile..." -ForegroundColor Cyan
        & "$ScriptDir\Trigger-NT8Compile.ps1" -ErrorAction SilentlyContinue
        Write-Host "  → In NT8: Tools > Edit NinjaScript > Indicator > DEEP6 > Compile (F5)" -ForegroundColor DarkGray
    } else {
        Write-Host "  NT8 not running. Start NT8 and compile DEEP6 manually:" -ForegroundColor Yellow
        Write-Host "  → Tools > Edit NinjaScript > Indicator > DEEP6 > Compile (F5)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "  ════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host "  Next steps in NT8:" -ForegroundColor White
Write-Host "  1. Tools > Edit NinjaScript > Indicator > DEEP6" -ForegroundColor Gray
Write-Host "  2. Press F5 to compile" -ForegroundColor Gray
Write-Host "  3. Add DEEP6 to a Volumetric Bars chart" -ForegroundColor Gray
Write-Host "  4. Ensure Rithmic Level 2 feed is active" -ForegroundColor Gray
Write-Host "  ════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""
