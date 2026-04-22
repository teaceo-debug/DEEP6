# nt8-compile.ps1 - Trigger NinjaScript recompile via NT8 UI automation
# NT8 must be running with NinjaScript Editor open (or this script opens it).
# Uses DLL timestamp watching to reliably detect compile success or failure.
#
# Usage:
#   nt8-compile.ps1 [-TimeoutSeconds <n>] [-CheckErrors] [-AutoReload] [-Quiet]
#   nt8-compile.ps1 [-WaitSeconds <n>]   # legacy alias for -TimeoutSeconds

param(
    [int]$TimeoutSeconds = 30,
    [Alias("WaitSeconds")]
    [int]$TimeoutSecondsAlias = 0,   # backwards-compat alias; merged below
    [switch]$CheckErrors,
    [switch]$AutoReload,             # skip SendKeys; rely on NSE file-watcher (NSE must be open)
    [switch]$Quiet                   # suppress verbose output; only print [COMPILE-RESULT] line
)

# Merge legacy -WaitSeconds alias into -TimeoutSeconds
if ($TimeoutSecondsAlias -gt 0 -and $TimeoutSeconds -eq 30) {
    $TimeoutSeconds = $TimeoutSecondsAlias
}

$ErrorActionPreference = "Stop"

# ── paths ────────────────────────────────────────────────────────────────────
$dll        = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll"
$installXml = "$env:USERPROFILE\Documents\NinjaTrader 8\log\Install.xml"
$logDir     = "$env:USERPROFILE\Documents\NinjaTrader 8\log"

# ── helpers ──────────────────────────────────────────────────────────────────
function Write-Verbose-Host {
    param([string]$Msg, [string]$Color = "White")
    if (!$Quiet) { Write-Host $Msg -ForegroundColor $Color }
}

function Get-NT8Process {
    $p = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
    if (!$p) { Write-Error "NinjaTrader is not running. Start NT8 first."; exit 1 }
    return $p
}

function Get-InstallXmlTimestamp {
    # Parse <CompiledCustomAssembly> from Install.xml; returns string or $null
    if (!(Test-Path $installXml)) { return $null }
    try {
        [xml]$xml = Get-Content $installXml -Raw
        $node = $xml.SelectSingleNode("//CompiledCustomAssembly")
        if ($node) { return $node.InnerText.Trim() }
    } catch { }
    return $null
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8Win {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@

function Bring-NT8ToFront {
    param($Process)
    [NT8Win]::ShowWindow($Process.MainWindowHandle, 9) | Out-Null
    Start-Sleep -Milliseconds 200
    [NT8Win]::SetForegroundWindow($Process.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 300
}

# ── banner ───────────────────────────────────────────────────────────────────
Write-Verbose-Host ""
Write-Verbose-Host "NT8 Compile -- $(Get-Date -Format 'HH:mm:ss')"
Write-Verbose-Host "---------------------------------------------"

# ── 1. Record pre-compile DLL mtime ─────────────────────────────────────────
$preMtime = $null
if (Test-Path $dll) {
    $preMtime = (Get-Item $dll).LastWriteTime
    Write-Verbose-Host "  DLL pre-mtime : $($preMtime.ToString('HH:mm:ss.fff'))" Gray
} else {
    Write-Verbose-Host "  DLL not found (first compile?): $dll" Yellow
}

# ── 2. Record Install.xml timestamp BEFORE compile ──────────────────────────
$preInstallTs = Get-InstallXmlTimestamp
if ($preInstallTs) {
    Write-Verbose-Host "  Install.xml pre: $preInstallTs" Gray
} else {
    Write-Verbose-Host "  Install.xml: not found or no <CompiledCustomAssembly> element" Gray
}

# ── 3. Trigger compile ───────────────────────────────────────────────────────
$nt8 = Get-NT8Process
Write-Verbose-Host "  NT8 found: PID $($nt8.Id)"

if ($AutoReload) {
    # -AutoReload: skip SendKeys; NinjaScript Editor's file-watcher picks up saved files automatically.
    # NOTE: NSE must be open for auto-detection to work. This mode is useful when
    # nt8-deploy.ps1 has already written the .cs file and NSE is watching the folder.
    Write-Verbose-Host "  -AutoReload mode: skipping SendKeys. NSE file-watcher will detect changes." Cyan
    Write-Verbose-Host "  (Ensure NinjaScript Editor is open in NT8.)" Cyan
} else {
    Write-Verbose-Host "  Bringing NT8 to foreground..."
    Bring-NT8ToFront -Process $nt8

    $wsh = New-Object -ComObject WScript.Shell

    Write-Verbose-Host "  Opening NinjaScript Editor (Tools > NinjaScript Editor)..."
    $wsh.AppActivate("NinjaTrader") | Out-Null
    Start-Sleep -Milliseconds 400
    $wsh.SendKeys("%t")
    Start-Sleep -Milliseconds 350
    $wsh.SendKeys("n")
    Start-Sleep -Milliseconds 1200

    Write-Verbose-Host "  Sending F5 (Compile)..."
    $wsh.AppActivate("NinjaTrader") | Out-Null
    Start-Sleep -Milliseconds 200
    $wsh.SendKeys("{F5}")
    Start-Sleep -Milliseconds 300
}

# ── 4. Poll for DLL change (success detection) ───────────────────────────────
Write-Verbose-Host "  Polling for DLL change (timeout: ${TimeoutSeconds}s)..." Cyan

$pollInterval = 500   # ms
$elapsed      = 0
$succeeded    = $false
$newMtime     = $null

while ($elapsed -lt ($TimeoutSeconds * 1000)) {
    Start-Sleep -Milliseconds $pollInterval
    $elapsed += $pollInterval

    if (Test-Path $dll) {
        $cur = (Get-Item $dll).LastWriteTime
        if ($null -eq $preMtime -or $cur -gt $preMtime) {
            $newMtime  = $cur
            $succeeded = $true
            break
        }
    }

    if (!$Quiet) {
        $dots = "." * ([math]::Floor($elapsed / 1000))
        Write-Host "`r  Waiting${dots}   " -NoNewline
    }
}

if (!$Quiet) { Write-Host "" }   # newline after dot progress

# ── 5. Emit result ────────────────────────────────────────────────────────────
if ($succeeded) {
    Write-Verbose-Host ""
    Write-Verbose-Host "  COMPILE SUCCEEDED  (DLL updated at $($newMtime.ToString('HH:mm:ss.fff')))" Green

    # 7. Read Install.xml on success to confirm official compile timestamp
    $postInstallTs = Get-InstallXmlTimestamp
    if ($postInstallTs) {
        Write-Verbose-Host "  Install.xml <CompiledCustomAssembly>: $postInstallTs" Green
    }

    Write-Host "[COMPILE-RESULT] SUCCESS $($newMtime.ToString('yyyy-MM-dd HH:mm:ss.fff'))"
} else {
    # ── 5a. Failure — DLL mtime unchanged after timeout ──────────────────────
    Write-Host ""
    Write-Host "  COMPILE FAILED (DLL unchanged after ${TimeoutSeconds} seconds)" -ForegroundColor Red
    Write-Host "[COMPILE-RESULT] FAILED timeout" -ForegroundColor Red
}

# ── 8. -CheckErrors: grep NT8 log for runtime errors ─────────────────────────
# NOTE: CS#### compile errors appear ONLY in the NT8 Output Window (View > Output Window),
# not in the daily log file. This log grep catches runtime errors (e.g. NullReference,
# strategy/indicator load failures) that NT8 writes after compile+load, not build errors.
if ($CheckErrors) {
    Write-Verbose-Host ""
    Write-Verbose-Host "  Checking NT8 log for runtime errors..." Cyan
    $logFile = Join-Path $logDir "$(Get-Date -Format 'yyyy-MM-dd').txt"

    if (!(Test-Path $logFile)) {
        $logFile = Get-ChildItem $logDir -Filter "*.txt" |
                   Sort-Object LastWriteTime -Descending |
                   Select-Object -First 1 -ExpandProperty FullName
    }

    if ($logFile -and (Test-Path $logFile)) {
        $errors = Get-Content $logFile |
                  Select-String -Pattern "\berror\b|\bERROR\b|CS\d{4}" -CaseSensitive:$false
        if ($errors) {
            Write-Host "  ERRORS FOUND:" -ForegroundColor Red
            $errors | Select-Object -Last 20 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        } else {
            Write-Verbose-Host "  No errors found in log -- runtime log appears clean." Green
        }
    } else {
        Write-Verbose-Host "  Log file not found." Yellow
    }
}

Write-Verbose-Host ""
Write-Verbose-Host "Check NT8 Output Window (View > Output Window) for CS#### compiler details." Cyan
