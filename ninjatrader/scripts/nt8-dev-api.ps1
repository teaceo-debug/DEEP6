# nt8-dev-api.ps1 - Client for DEEP6DevAddon HTTP API (localhost:19206)
#
# Usage:
#   nt8-dev-api.ps1 -Action health
#   nt8-dev-api.ps1 -Action status
#   nt8-dev-api.ps1 -Action errors [-Format Text|Json]
#   nt8-dev-api.ps1 -Action compile [-Wait] [-TimeoutSeconds 45]
#   nt8-dev-api.ps1 -Action log [-Lines 50]

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("health","status","errors","compile","log")]
    [string]$Action,

    [ValidateSet("Text","Json")]
    [string]$Format = "Text",

    [int]$Lines = 50,
    [switch]$Wait,
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:19206"

function Invoke-Api {
    param(
        [string]$Method = "GET",
        [string]$Path,
        [string]$Body = $null
    )

    $url = "$BaseUrl$Path"
    try {
        if ($Method -eq "POST") {
            $postBody = if ($Body -ne $null) { $Body } else { "{}" }
            $response = Invoke-WebRequest -Uri $url -Method POST -ContentType "application/json" -Body $postBody -UseBasicParsing -TimeoutSec 10
        }
        else {
            $response = Invoke-WebRequest -Uri $url -Method GET -UseBasicParsing -TimeoutSec 10
        }
        return ($response.Content | ConvertFrom-Json)
    }
    catch {
        Write-Host ""
        Write-Host "  Cannot reach DEEP6DevAddon on $BaseUrl" -ForegroundColor Red
        Write-Host "  Is NT8 running with DEEP6DevAddon loaded?" -ForegroundColor Yellow
        Write-Host "  Deploy: nt8-deploy.ps1 -Target AddOns" -ForegroundColor Yellow
        Write-Host "  Compile: nt8-compile.ps1" -ForegroundColor Yellow
        exit 1
    }
}

function Format-Json-Pretty {
    param($obj)
    $obj | ConvertTo-Json -Depth 10
}

function Print-Header {
    param([string]$title)
    Write-Host ""
    Write-Host "DEEP6 NT8 Dev API -- $title -- $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host ("-" * 60) -ForegroundColor DarkGray
}

function Action-Health {
    Print-Header "health"
    $r = Invoke-Api -Path "/health"
    if ($r.ok -eq $true) {
        Write-Host "  DEEP6DevAddon is reachable - ok: true" -ForegroundColor Green
    }
    else {
        Write-Host "  Unexpected response: $(Format-Json-Pretty $r)" -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""
}

function Action-Status {
    Print-Header "status"
    $r = Invoke-Api -Path "/status"

    if ($Format -eq "Json") {
        Format-Json-Pretty $r
        return
    }

    if ($r.nt8_running) { $nt8Color = "Green" } else { $nt8Color = "Red" }
    Write-Host "  NT8 running:      $($r.nt8_running)" -ForegroundColor $nt8Color
    Write-Host "  Last compile:     $($r.last_compile)" -ForegroundColor Cyan
    Write-Host "  DLL mtime:        $($r.dll_mtime)" -ForegroundColor Gray

    $insts = $r.instruments
    if ($insts -and $insts.Count -gt 0) {
        Write-Host "  Instruments ($($insts.Count)):" -ForegroundColor White
        foreach ($inst in $insts) {
            Write-Host "    $inst" -ForegroundColor Gray
        }
    }
    else {
        Write-Host "  Instruments:      (none loaded)" -ForegroundColor DarkGray
    }
    Write-Host ""
}

function Action-Errors {
    Print-Header "errors"
    $errors = @(Invoke-Api -Path "/errors")

    if ($Format -eq "Json") {
        $errors | ConvertTo-Json -Depth 5
        return
    }

    if ($errors.Count -eq 0) {
        Write-Host "  No compile errors found." -ForegroundColor Green
        Write-Host ""
        exit 0
    }

    $errLines = @($errors | Where-Object { ($_ -match "(?i)CS\d{4}|compile.*fail|failed.*compile|Unhandled exception|Exception:") -and ($_ -notmatch "(?i)no error") })
    $warnLines = @($errors | Where-Object { $_ -match "(?i)\bwarning\b" })

    Write-Host "  Lines: $($errors.Count)   Errors(est): $($errLines.Count)   Warnings(est): $($warnLines.Count)" -ForegroundColor White
    Write-Host ""

    foreach ($line in $errors) {
        if (($line -match "(?i)CS\d{4}|compile.*fail|failed.*compile|Unhandled exception|Exception:") -and ($line -notmatch "(?i)no error")) { $color = "Red" }
        elseif ($line -match "(?i)\bwarning\b") { $color = "Yellow" }
        else { $color = "Gray" }
        Write-Host "  $line" -ForegroundColor $color
    }

    Write-Host ""
    if ($errLines.Count -gt 0) { exit 1 }
    exit 0
}

function Action-Compile {
    Print-Header "compile"
    Write-Host "  Triggering compile via DEEP6DevAddon..." -ForegroundColor Cyan

    $r = Invoke-Api -Method "POST" -Path "/compile"
    if ($r.triggered -eq $true) {
        Write-Host "  Compile triggered: true" -ForegroundColor Green
        Write-Host "  Reason: $($r.reason)" -ForegroundColor Gray
        Write-Host "  Telemetry: $($r.telemetry)" -ForegroundColor DarkGray
    }
    else {
        if ($r.error) { $errMsg = " ($($r.error))" } else { $errMsg = "" }
        Write-Host "  Compile triggered: false$errMsg" -ForegroundColor Yellow
        Write-Host "  Reason: $($r.reason)" -ForegroundColor Yellow
        Write-Host "  Telemetry: $($r.telemetry)" -ForegroundColor DarkGray
        Write-Host "  Tip: open NinjaScript Editor in NT8 first (Tools > NinjaScript Editor)" -ForegroundColor Gray
    }

    if (-not $Wait) {
        Write-Host "  Use -Wait to poll for errors after compile." -ForegroundColor DarkGray
        Write-Host ""
        return
    }

    if ($r.triggered -ne $true) {
        Write-Host ""
        exit 1
    }

    Write-Host "  Waiting up to ${TimeoutSeconds}s for compile to finish..." -ForegroundColor Cyan
    $statusBefore = Invoke-Api -Path "/status"
    $mtimeBefore = $statusBefore.dll_mtime
    $compileBefore = $statusBefore.last_compile
    $elapsed = 0
    $pollMs = 1000
    $compileReady = $false

    while ($elapsed -lt ($TimeoutSeconds * 1000)) {
        Start-Sleep -Milliseconds $pollMs
        $elapsed += $pollMs
        $statusNow = Invoke-Api -Path "/status"
        $mtimeNow = $statusNow.dll_mtime
        $compileNow = $statusNow.last_compile

        if (($mtimeNow -ne $mtimeBefore -and -not [string]::IsNullOrEmpty($mtimeNow)) -or
            ($compileNow -ne $compileBefore -and -not [string]::IsNullOrEmpty($compileNow))) {
            if ($mtimeNow -ne $mtimeBefore -and -not [string]::IsNullOrEmpty($mtimeNow)) {
                Write-Host "  DLL updated at: $mtimeNow" -ForegroundColor Green
            }
            if ($compileNow -ne $compileBefore -and -not [string]::IsNullOrEmpty($compileNow)) {
                Write-Host "  Install.xml compile stamp advanced to: $compileNow" -ForegroundColor Green
            }
            $compileReady = $true
            break
        }

        $dots = "." * [math]::Floor($elapsed / 1000)
        Write-Host "`r  Polling${dots}   " -NoNewline
    }

    Write-Host ""

    if (-not $compileReady) {
        Write-Host "  Timeout - DLL mtime unchanged after ${TimeoutSeconds}s." -ForegroundColor Red
        Write-Host "  Check NT8 Output Window for details." -ForegroundColor Yellow
        exit 1
    }

    Start-Sleep -Milliseconds 800
    Write-Host ""
    Write-Host "-- Compile Errors ------------------------------------------" -ForegroundColor DarkGray
    $errors = @(Invoke-Api -Path "/errors")

    if ($errors.Count -eq 0) {
        Write-Host "  No compile errors found. Compile succeeded." -ForegroundColor Green
    }
    else {
        foreach ($line in $errors) {
            if (($line -match "(?i)CS\d{4}|compile.*fail|failed.*compile|Unhandled exception|Exception:") -and ($line -notmatch "(?i)no error")) { $color = "Red" }
            elseif ($line -match "(?i)\bwarning\b") { $color = "Yellow" }
            else { $color = "Gray" }
            Write-Host "  $line" -ForegroundColor $color
        }
        $hasErrors = (@($errors | Where-Object { ($_ -match "(?i)CS\d{4}|compile.*fail|failed.*compile|Unhandled exception|Exception:") -and ($_ -notmatch "(?i)no error") })).Count -gt 0
        if ($hasErrors) { exit 1 }
    }

    Write-Host ""
}

function Action-Log {
    Print-Header "log (last $Lines lines)"
    $linesOut = @(Invoke-Api -Path "/log?lines=$Lines")

    if ($linesOut.Count -eq 0) {
        Write-Host "  No log lines returned." -ForegroundColor Yellow
        Write-Host ""
        return
    }

    foreach ($line in $linesOut) {
        if ($line -match "(?i)\berror\b|CS\d{4}") { $color = "Red" }
        elseif ($line -match "(?i)\bwarning\b") { $color = "Yellow" }
        elseif ($line -match "DEEP6-Addon") { $color = "Cyan" }
        else { $color = "Gray" }
        Write-Host "  $line" -ForegroundColor $color
    }

    Write-Host ""
}

switch ($Action) {
    "health"  { Action-Health }
    "status"  { Action-Status }
    "errors"  { Action-Errors }
    "compile" { Action-Compile }
    "log"     { Action-Log }
}
