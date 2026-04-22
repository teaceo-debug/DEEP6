# nt8-dev-api.ps1 - Client for DEEP6DevAddon HTTP API (localhost:19206)
#
# The DEEP6DevAddon runs inside NT8's process and exposes a lightweight
# HTTP server so you can check status, read compile errors, trigger compiles,
# and tail logs without any UI automation or SendKeys.
#
# Usage:
#   nt8-dev-api.ps1 -Action health
#   nt8-dev-api.ps1 -Action status
#   nt8-dev-api.ps1 -Action errors [-Format Text|Json]
#   nt8-dev-api.ps1 -Action compile [-Wait] [-TimeoutSeconds 45]
#   nt8-dev-api.ps1 -Action log [-Lines 50]
#
# Requires: DEEP6DevAddon compiled and loaded in NT8 (nt8-deploy.ps1 -Target AddOns)
# Port:     19206  (DEEP6)

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("health","status","errors","compile","log")]
    [string]$Action,

    [ValidateSet("Text","Json")]
    [string]$Format = "Text",

    [int]$Lines = 50,

    # For -Action compile: poll /errors after triggering and wait up to N seconds
    [switch]$Wait,
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

$BaseUrl = "http://localhost:19206"

# ── helpers ───────────────────────────────────────────────────────────────────

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
            $response = Invoke-WebRequest -Uri $url -Method POST `
                -ContentType "application/json" `
                -Body $postBody `
                -UseBasicParsing `
                -TimeoutSec 10
        } else {
            $response = Invoke-WebRequest -Uri $url -Method GET `
                -UseBasicParsing `
                -TimeoutSec 10
        }
        return $response.Content | ConvertFrom-Json
    } catch [System.Net.WebException] {
        $status = $null
        if ($_.Exception.Response -ne $null) { $status = $_.Exception.Response.StatusCode }
        if ($null -eq $status) {
            Write-Host "" -ForegroundColor Red
            Write-Host "  Cannot reach DEEP6DevAddon on $BaseUrl" -ForegroundColor Red
            Write-Host "  Is NT8 running with DEEP6DevAddon loaded?" -ForegroundColor Yellow
            Write-Host "  Deploy: nt8-deploy.ps1 -Target AddOns" -ForegroundColor Yellow
            Write-Host "  Compile: nt8-compile.ps1" -ForegroundColor Yellow
        } else {
            Write-Host "  API error: HTTP $status" -ForegroundColor Red
        }
        exit 1
    }
}

function Format-Json-Pretty {
    param($obj)
    # PowerShell 5.1 ConvertTo-Json depth default is 2 — use depth 10 to be safe
    $obj | ConvertTo-Json -Depth 10
}

function Print-Header {
    param([string]$title)
    Write-Host ""
    Write-Host "DEEP6 NT8 Dev API -- $title -- $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host ("-" * 60) -ForegroundColor DarkGray
}

# ── /health ───────────────────────────────────────────────────────────────────

function Action-Health {
    Print-Header "health"
    $r = Invoke-Api -Path "/health"
    if ($r.ok -eq $true) {
        Write-Host "  DEEP6DevAddon is reachable — ok: true" -ForegroundColor Green
    } else {
        Write-Host "  Unexpected response: $(Format-Json-Pretty $r)" -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""
}

# ── /status ───────────────────────────────────────────────────────────────────

function Action-Status {
    Print-Header "status"
    $r = Invoke-Api -Path "/status"

    if ($Format -eq "Json") {
        Format-Json-Pretty $r
        return
    }

    $nt8Color = if ($r.nt8_running) { "Green" } else { "Red" }
    Write-Host "  NT8 running:      $($r.nt8_running)" -ForegroundColor $nt8Color
    Write-Host "  Last compile:     $($r.last_compile)"  -ForegroundColor Cyan
    Write-Host "  DLL mtime:        $($r.compile_dll_mtime)" -ForegroundColor Gray

    $insts = $r.instruments
    if ($insts -and $insts.Count -gt 0) {
        Write-Host "  Instruments ($($insts.Count)):" -ForegroundColor White
        foreach ($inst in $insts) {
            Write-Host "    $inst" -ForegroundColor Gray
        }
    } else {
        Write-Host "  Instruments:      (none loaded)" -ForegroundColor DarkGray
    }
    Write-Host ""
}

# ── /errors ───────────────────────────────────────────────────────────────────

function Action-Errors {
    Print-Header "errors"
    $errors = Invoke-Api -Path "/errors"

    if ($Format -eq "Json") {
        $errors | ConvertTo-Json -Depth 5
        return
    }

    if ($errors.Count -eq 0) {
        Write-Host "  No compile errors found." -ForegroundColor Green
        Write-Host ""
        exit 0
    }

    # Separate errors vs warnings
    $errLines  = @($errors | Where-Object { $_ -match "(?i)\berror\b|CS\d{4}" })
    $warnLines = @($errors | Where-Object { $_ -match "(?i)\bwarning\b" })
    $otherLines= @($errors | Where-Object { $_ -notin $errLines -and $_ -notin $warnLines })

    Write-Host "  Lines: $($errors.Count)   Errors(est): $($errLines.Count)   Warnings(est): $($warnLines.Count)" -ForegroundColor White
    Write-Host ""

    foreach ($line in $errors) {
        $color = if     ($line -match "(?i)\berror\b|CS\d{4}.*error") { "Red" }
                 elseif ($line -match "(?i)\bwarning\b")               { "Yellow" }
                 else                                                   { "Gray" }
        Write-Host "  $line" -ForegroundColor $color
    }

    Write-Host ""
    if ($errLines.Count -gt 0) { exit 1 }
    exit 0
}

# ── /compile ──────────────────────────────────────────────────────────────────

function Action-Compile {
    Print-Header "compile"
    Write-Host "  Triggering compile via DEEP6DevAddon..." -ForegroundColor Cyan

    $r = Invoke-Api -Method "POST" -Path "/compile"
    if ($r.triggered -eq $true) {
        Write-Host "  Compile triggered: true" -ForegroundColor Green
    } else {
        $errMsg = if ($r.error) { " ($($r.error))" } else { "" }
        Write-Host "  Compile triggered: false$errMsg" -ForegroundColor Yellow
        Write-Host "  Tip: open NinjaScript Editor in NT8 first (Tools > NinjaScript Editor)" -ForegroundColor Gray
    }

    if (!$Wait) {
        Write-Host "  Use -Wait to poll for errors after compile." -ForegroundColor DarkGray
        Write-Host ""
        return
    }

    # Poll DLL mtime change via /status, then read /errors
    Write-Host "  Waiting up to ${TimeoutSeconds}s for compile to finish..." -ForegroundColor Cyan

    # Record DLL mtime before
    $statusBefore = Invoke-Api -Path "/status"
    $mtimeBefore  = $statusBefore.compile_dll_mtime

    $elapsed     = 0
    $pollMs      = 1000
    $compileReady = $false

    while ($elapsed -lt ($TimeoutSeconds * 1000)) {
        Start-Sleep -Milliseconds $pollMs
        $elapsed += $pollMs

        $statusNow = Invoke-Api -Path "/status"
        $mtimeNow  = $statusNow.compile_dll_mtime

        if ($mtimeNow -ne $mtimeBefore -and ![string]::IsNullOrEmpty($mtimeNow)) {
            Write-Host "  DLL updated at: $mtimeNow" -ForegroundColor Green
            $compileReady = $true
            break
        }

        $dots = "." * [math]::Floor($elapsed / 1000)
        Write-Host "`r  Polling${dots}   " -NoNewline
    }

    Write-Host ""  # newline after dot progress

    if (!$compileReady) {
        Write-Host "  Timeout — DLL mtime unchanged after ${TimeoutSeconds}s." -ForegroundColor Red
        Write-Host "  Check NT8 Output Window for details." -ForegroundColor Yellow
        exit 1
    }

    # Give NT8 a moment to finish writing error output
    Start-Sleep -Milliseconds 800

    Write-Host ""
    Write-Host "-- Compile Errors ------------------------------------------" -ForegroundColor DarkGray
    $errors = Invoke-Api -Path "/errors"

    if ($errors.Count -eq 0) {
        Write-Host "  No compile errors found. Compile succeeded." -ForegroundColor Green
    } else {
        foreach ($line in $errors) {
            $color = if     ($line -match "(?i)\berror\b|CS\d{4}") { "Red" }
                     elseif ($line -match "(?i)\bwarning\b")        { "Yellow" }
                     else                                            { "Gray" }
            Write-Host "  $line" -ForegroundColor $color
        }
        $hasErrors = ($errors | Where-Object { $_ -match "(?i)\berror\b|CS\d{4}" }).Count -gt 0
        if ($hasErrors) { exit 1 }
    }

    Write-Host ""
}

# ── /log ─────────────────────────────────────────────────────────────────────

function Action-Log {
    Print-Header "log (last $Lines lines)"
    $lines = Invoke-Api -Path "/log?lines=$Lines"

    if ($lines.Count -eq 0) {
        Write-Host "  No log lines returned." -ForegroundColor Yellow
        Write-Host ""
        return
    }

    foreach ($line in $lines) {
        $color = if     ($line -match "(?i)\berror\b|CS\d{4}") { "Red" }
                 elseif ($line -match "(?i)\bwarning\b")        { "Yellow" }
                 elseif ($line -match "DEEP6-Addon")            { "Cyan" }
                 else                                            { "Gray" }
        Write-Host "  $line" -ForegroundColor $color
    }

    Write-Host ""
}

# ── dispatch ──────────────────────────────────────────────────────────────────

switch ($Action) {
    "health"  { Action-Health  }
    "status"  { Action-Status  }
    "errors"  { Action-Errors  }
    "compile" { Action-Compile }
    "log"     { Action-Log     }
}
