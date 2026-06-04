# GEX Terminal v2.0 — Launch Script
# Usage: .\scripts\start_gex_terminal.ps1

param(
    [int]$Port = 8780,
    [int]$UIPort = 3001,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "GEX Terminal v2.0 — Starting..." -ForegroundColor Green

# Validate config
Write-Host "Validating configuration..." -ForegroundColor Cyan
& python -m gex_terminal --dry-run
if ($LASTEXITCODE -ne 0) {
    Write-Host "Configuration validation failed. Check your .env.gex_terminal file." -ForegroundColor Red
    exit 1
}

if ($DryRun) {
    Write-Host "Dry run complete. Exiting." -ForegroundColor Yellow
    exit 0
}

# Start Python backend
Write-Host "Starting Python backend on port $Port..." -ForegroundColor Cyan
$BackendJob = Start-Job -ScriptBlock {
    param($root, $port)
    Set-Location $root
    python -m gex_terminal --port $port
} -ArgumentList $ProjectRoot, $Port

# Wait for backend to start
Start-Sleep -Seconds 3

# Check backend health
try {
    $health = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 5
    Write-Host "Backend healthy: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "Backend health check failed: $_" -ForegroundColor Red
    Stop-Job $BackendJob
    exit 1
}

# Start Next.js UI
Write-Host "Starting Next.js UI on port $UIPort..." -ForegroundColor Cyan
$UIJob = Start-Job -ScriptBlock {
    param($root, $uiPort)
    Set-Location "$root\gex_terminal\ui"
    npm run dev -- --port $uiPort
} -ArgumentList $ProjectRoot, $UIPort

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "GEX Terminal v2.0 is running!" -ForegroundColor Green
Write-Host "  Backend: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "  UI:      http://localhost:$UIPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

# Wait for jobs
try {
    Wait-Job $BackendJob, $UIJob
} finally {
    Stop-Job $BackendJob, $UIJob -ErrorAction SilentlyContinue
    Remove-Job $BackendJob, $UIJob -ErrorAction SilentlyContinue
}
