#Requires -Version 5.1
<#
.SYNOPSIS
    Watches DEEP6.cs for changes and auto-deploys to NT8 on every save.

.DESCRIPTION
    Uses FileSystemWatcher to detect changes to Indicators\DEEP6.cs.
    On change, waits 800ms (debounce) then copies to NT8 Custom folder.
    Press Ctrl+C to stop watching.

.PARAMETER NT8CustomPath
    Path to NinjaTrader 8 bin\Custom folder.
#>

param(
    [string] $NT8CustomPath = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"
)

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$SourceFile  = Join-Path $ProjectRoot "Indicators\DEEP6.cs"
$DestFolder  = Join-Path $NT8CustomPath "Indicators"
$DestFile    = Join-Path $DestFolder "DEEP6.cs"

Write-Host ""
Write-Host "  DEEP6 Watch + Auto-Deploy Mode" -ForegroundColor Cyan
Write-Host "  Watching: $SourceFile" -ForegroundColor Gray
Write-Host "  Target  : $DestFile" -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $DestFolder)) {
    New-Item -ItemType Directory -Path $DestFolder -Force | Out-Null
}

# Create FileSystemWatcher
$Watcher = New-Object System.IO.FileSystemWatcher
$Watcher.Path   = Join-Path $ProjectRoot "Indicators"
$Watcher.Filter = "DEEP6.cs"
$Watcher.NotifyFilter = [System.IO.NotifyFilters]::LastWrite
$Watcher.EnableRaisingEvents = $true

$Global:LastDeploy = [DateTime]::MinValue
$DebounceMs = 800

$Action = {
    $Now = [DateTime]::Now
    if (($Now - $Global:LastDeploy).TotalMilliseconds -lt $DebounceMs) { return }
    $Global:LastDeploy = $Now

    Start-Sleep -Milliseconds $DebounceMs

    try {
        Copy-Item -Path $Event.SourceEventArgs.FullPath -Destination $DestFile -Force
        $Lines = (Get-Content $DestFile | Measure-Object -Line).Lines
        Write-Host "  [$(Get-Date -Format 'HH:mm:ss')] Deployed  ($Lines lines)  →  $DestFile" -ForegroundColor Green
        Write-Host "  → Recompile in NT8: Tools > Edit NinjaScript > DEEP6 > F5" -ForegroundColor DarkGray
    } catch {
        Write-Host "  [$(Get-Date -Format 'HH:mm:ss')] Deploy FAILED: $_" -ForegroundColor Red
    }
}

Register-ObjectEvent -InputObject $Watcher -EventName "Changed" -Action $Action | Out-Null

Write-Host "  Watching DEEP6.cs... (hot-deploy active)" -ForegroundColor Green
Write-Host ""

# Keep the script alive
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    $Watcher.EnableRaisingEvents = $false
    $Watcher.Dispose()
    Write-Host "`n  Watcher stopped." -ForegroundColor Gray
}
