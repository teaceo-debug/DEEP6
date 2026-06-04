# GEX Doctor Desktop — One-click launcher
param([switch]$NoBridge)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DesktopDir = Join-Path $ProjectRoot "gex_terminal\desktop"

Write-Host "GEX Doctor v2.0 — Desktop App" -ForegroundColor Green
Write-Host "Starting..." -ForegroundColor Cyan

Set-Location $DesktopDir

# Check node_modules
if (-not (Test-Path "node_modules\electron")) {
  Write-Host "Installing Electron deps..." -ForegroundColor Yellow
  npm install
}

# Launch Electron (which manages Python backend automatically)
$env:DEEP6_PROJECT_ROOT = $ProjectRoot
npx electron .
