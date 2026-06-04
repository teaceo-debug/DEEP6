# MAD Levels Service — quick status check
$pidFile  = Join-Path $PSScriptRoot ".mad_levels.pid"
$logFile  = "C:\Users\Tea\DEEP6\logs\mad_levels_service.log"
$jsonFile = "C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\mad_levels.json"

Write-Host "`nMAD Levels Service Status" -ForegroundColor Cyan
Write-Host ("=" * 50) -ForegroundColor Cyan

# Process check
$running = $false
if (Test-Path -LiteralPath $pidFile) {
    $procId = [int](Get-Content $pidFile).Trim()
    try {
        $proc = Get-Process -Id $procId -ErrorAction Stop
        Write-Host "  Process:  RUNNING (PID $procId)" -ForegroundColor Green
        $running = $true
    } catch {
        Write-Host "  Process:  DEAD (stale PID $procId)" -ForegroundColor Red
    }
} else {
    Write-Host "  Process:  NOT RUNNING" -ForegroundColor Red
}

# JSON check
if (Test-Path -LiteralPath $jsonFile) {
    $json = Get-Content $jsonFile -Raw | ConvertFrom-Json
    $age = [math]::Round(((Get-Date).ToUniversalTime() - [datetime]::Parse($json.generated_at_utc)).TotalSeconds)
    Write-Host "  JSON:     $($json.nq_count) NQ + $($json.es_count) ES levels (${age}s ago)" -ForegroundColor Green
    Write-Host "  Session:  $($json.session_date_et)" -ForegroundColor Gray
} else {
    Write-Host "  JSON:     NOT FOUND" -ForegroundColor Red
}

# Last 5 log lines
if (Test-Path -LiteralPath $logFile) {
    Write-Host "`n  Recent log:" -ForegroundColor Gray
    Get-Content $logFile -Tail 5 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}

Write-Host ""
