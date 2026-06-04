# Stop MAD Levels Service
$pidFile = Join-Path $PSScriptRoot ".mad_levels.pid"

if (Test-Path -LiteralPath $pidFile) {
    $procId = [int](Get-Content $pidFile).Trim()
    try {
        $proc = Get-Process -Id $procId -ErrorAction Stop
        Stop-Process -Id $procId -Force
        Remove-Item -LiteralPath $pidFile -Force
        Write-Host "MAD Levels stopped (PID $procId)" -ForegroundColor Yellow
    } catch {
        Remove-Item -LiteralPath $pidFile -Force
        Write-Host "MAD Levels PID $procId already gone" -ForegroundColor Gray
    }
} else {
    Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "MAD Levels stopped (fallback kill)" -ForegroundColor Yellow
}
