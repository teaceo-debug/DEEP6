# nt8-status.ps1 - NT8 health check: running state, deployed files, recent errors
# Usage: nt8-status.ps1 [-ShowErrors] [-ShowLog <n>]

param(
    [switch]$ShowErrors,
    [int]$ShowLog = 0
)

$NT8Custom = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"
$NT8Log    = "$env:USERPROFILE\Documents\NinjaTrader 8\log"
$RepoSrc   = "$PSScriptRoot\..\Custom"

Write-Host ""
Write-Host "NT8 Status -- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "=============================================="

# 1. Process
$proc = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
if ($proc) {
    $uptime = (Get-Date) - $proc.StartTime
    Write-Host "NT8:  RUNNING  PID=$($proc.Id)  uptime=$([math]::Round($uptime.TotalMinutes,1))m  mem=$([math]::Round($proc.WorkingSet64/1MB,0))MB" -ForegroundColor Green
} else {
    Write-Host "NT8:  NOT RUNNING" -ForegroundColor Yellow
}

# 2. Deployed files
Write-Host ""
Write-Host "-- Deployed Files -------------------------------------"

foreach ($type in "Indicators","Strategies","AddOns") {
    $dst = "$NT8Custom\$type\DEEP6"
    $src = "$RepoSrc\$type\DEEP6"

    if (!(Test-Path $dst)) {
        Write-Host "  [$type\DEEP6] NOT DEPLOYED" -ForegroundColor Red
        continue
    }

    $dstFiles = Get-ChildItem $dst -Filter "*.cs" -Recurse -ErrorAction SilentlyContinue
    Write-Host "  [$type\DEEP6]  $($dstFiles.Count) file(s)" -ForegroundColor Cyan

    foreach ($f in $dstFiles) {
        $srcFile = Join-Path "$src" $f.Name
        $sync = "no-src"
        if (Test-Path $srcFile) {
            $h1 = (Get-FileHash $f.FullName).Hash
            $h2 = (Get-FileHash $srcFile).Hash
            if ($h1 -eq $h2) { $sync = "in-sync" } else { $sync = "DRIFT" }
        }
        $color = if ($sync -eq "in-sync") { "Gray" } else { "Yellow" }
        Write-Host "    $($f.Name)  [$sync]" -ForegroundColor $color
    }
}

# 3. DLL build timestamp + Install.xml confirmed compile
$dll        = "$NT8Custom\NinjaTrader.Custom.dll"
$installXml = "$env:USERPROFILE\Documents\NinjaTrader 8\log\Install.xml"

Write-Host ""
Write-Host "-- Last Compile ----------------------------------------"

if (Test-Path $dll) {
    $built = (Get-Item $dll).LastWriteTime
    $age   = (Get-Date) - $built
    $color = if ($age.TotalMinutes -lt 5) { "Green" } elseif ($age.TotalHours -lt 1) { "Cyan" } else { "Gray" }
    Write-Host "  NinjaTrader.Custom.dll  built $($built.ToString('HH:mm:ss'))  ($([math]::Round($age.TotalMinutes,0))m ago)" -ForegroundColor $color
} else {
    Write-Host "  NinjaTrader.Custom.dll  NOT FOUND" -ForegroundColor Red
}

# Install.xml — NT8 writes <CompiledCustomAssembly> after each successful compile.
# This is the official NT8-confirmed last good compile timestamp (not just DLL mtime).
if (Test-Path $installXml) {
    try {
        [xml]$xml  = Get-Content $installXml -Raw
        $node = $xml.SelectSingleNode("//CompiledCustomAssembly")
        if ($node -and $node.InnerText.Trim() -ne "") {
            Write-Host "  NT8 confirmed last good compile: $($node.InnerText.Trim())" -ForegroundColor Cyan
        } else {
            Write-Host "  Install.xml: <CompiledCustomAssembly> element empty or missing" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Install.xml: parse error -- $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  Install.xml: not found ($installXml)" -ForegroundColor Yellow
}

# 4. Log errors
if ($ShowErrors -or $ShowLog -gt 0) {
    Write-Host ""
    Write-Host "-- Log -------------------------------------------------"
    $logFile = Join-Path $NT8Log "$(Get-Date -Format 'yyyy-MM-dd').txt"

    if (!(Test-Path $logFile)) {
        $logFile = Get-ChildItem $NT8Log -Filter "*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
    }

    if ($logFile -and (Test-Path $logFile)) {
        Write-Host "  File: $logFile"
        $lines = Get-Content $logFile

        if ($ShowLog -gt 0) {
            Write-Host "  Last $ShowLog lines:"
            $lines | Select-Object -Last $ShowLog | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
        }

        if ($ShowErrors) {
            $errors = $lines | Select-String -Pattern "\berror\b|CS\d{4}|compile.*fail|failed.*compile" -CaseSensitive:$false
            if ($errors) {
                Write-Host "  Errors found ($($errors.Count)):" -ForegroundColor Red
                $errors | Select-Object -Last 30 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
            } else {
                Write-Host "  No errors found in log." -ForegroundColor Green
            }
        }
    } else {
        Write-Host "  No log file found." -ForegroundColor Yellow
    }
}

Write-Host ""
