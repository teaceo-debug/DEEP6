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
    $procs = @(Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue)
    if (!$procs -or $procs.Count -eq 0) { Write-Error "NinjaTrader is not running. Start NT8 first."; exit 1 }

    $main = $procs | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($main) { return $main }
    return ($procs | Select-Object -First 1)
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

    # ── Open NinjaScript Editor via UIAutomation (New > NinjaScript Editor) ──────
    # VERIFIED: NSE is under New menu, NOT Tools menu on this machine.
    Write-Verbose-Host "  Opening NinjaScript Editor (New > NinjaScript Editor via UIAutomation)..."
    Add-Type -AssemblyName UIAutomationClient  -ErrorAction SilentlyContinue
    Add-Type -AssemblyName UIAutomationTypes   -ErrorAction SilentlyContinue

    $uiaRoot    = [System.Windows.Automation.AutomationElement]::RootElement
    $uiaPidCond = New-Object System.Windows.Automation.PropertyCondition `
        ([System.Windows.Automation.AutomationElement]::ProcessIdProperty), ($nt8.Id)
    $uiaAllWin  = $uiaRoot.FindAll([System.Windows.Automation.TreeScope]::Children, $uiaPidCond)

    $uiaCcWin = $null
    foreach ($uiaW in $uiaAllWin) {
        $uiaCls = $null
        try { $uiaCls = $uiaW.Current.ClassName } catch { }
        if ($uiaCls -eq "ControlCenter") { $uiaCcWin = $uiaW; break }
    }

    $uiaMiCond = New-Object System.Windows.Automation.PropertyCondition `
        ([System.Windows.Automation.AutomationElement]::ControlTypeProperty), `
        ([System.Windows.Automation.ControlType]::MenuItem)

    # Expand "New" submenu then invoke "NinjaScript Editor"
    $uiaNewItem = $null
    if ($null -ne $uiaCcWin) {
        $uiaItems = $uiaCcWin.FindAll([System.Windows.Automation.TreeScope]::Descendants, $uiaMiCond)
        foreach ($uiaIt in $uiaItems) {
            $uiaN = $null
            try { $uiaN = $uiaIt.Current.Name } catch { }
            if ($uiaN -eq "New") { $uiaNewItem = $uiaIt; break }
        }
    }

    if ($null -ne $uiaNewItem) {
        $uiaEpOk = $false
        try {
            $uiaEp = $uiaNewItem.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            $uiaEp.Expand()
            $uiaEpOk = $true
        }
        catch { Write-Verbose-Host "  Warning: ExpandCollapse on New failed." Yellow }

        if ($uiaEpOk) {
            Start-Sleep -Milliseconds 600
            $uiaNseItem = $null
            $uiaItems2 = $uiaCcWin.FindAll([System.Windows.Automation.TreeScope]::Descendants, $uiaMiCond)
            foreach ($uiaIt2 in $uiaItems2) {
                $uiaN2 = $null
                try { $uiaN2 = $uiaIt2.Current.Name } catch { }
                if ($uiaN2 -eq "NinjaScript Editor") { $uiaNseItem = $uiaIt2; break }
            }

            if ($null -ne $uiaNseItem) {
                try {
                    $uiaIp = $uiaNseItem.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                    $uiaIp.Invoke()
                    Write-Verbose-Host "  NinjaScript Editor opened via UIAutomation." Cyan
                }
                catch { Write-Verbose-Host "  Warning: Invoke on NinjaScript Editor failed." Yellow }
            }
            else {
                Write-Verbose-Host "  NinjaScript Editor item not found -- NSE may already be open." Yellow
            }
        }
    }
    else {
        Write-Verbose-Host "  New menu item not found in ControlCenter." Yellow
    }
    Start-Sleep -Milliseconds 1500

    # ── Focus NSE window and send F5 ─────────────────────────────────────────────
    Write-Verbose-Host "  Sending F5 (Compile)..."
    $uiaAllWin2 = $uiaRoot.FindAll([System.Windows.Automation.TreeScope]::Children, $uiaPidCond)
    $uiaNseWin  = $null
    foreach ($uiaW2 in $uiaAllWin2) {
        $uiaN3 = $null
        try { $uiaN3 = $uiaW2.Current.Name } catch { }
        if ($uiaN3 -like "*NinjaScript*") { $uiaNseWin = $uiaW2; break }
    }

    $wsh = New-Object -ComObject WScript.Shell
    if ($null -ne $uiaNseWin) {
        $nseHandle = New-Object IntPtr($uiaNseWin.Current.NativeWindowHandle)
        [NT8Win]::ShowWindow($nseHandle, 9)       | Out-Null
        [NT8Win]::SetForegroundWindow($nseHandle) | Out-Null
        Start-Sleep -Milliseconds 500
        $wsh.AppActivate("NinjaScript Editor") | Out-Null
        Start-Sleep -Milliseconds 300
        $wsh.SendKeys("{F5}")
    }
    else {
        Write-Verbose-Host "  NSE window not found -- sending F5 to active NT8 window." Yellow
        $wsh.AppActivate($nt8.Id) | Out-Null
        Start-Sleep -Milliseconds 300
        $wsh.SendKeys("{F5}")
    }
    Start-Sleep -Milliseconds 300
}

# ── 4. Poll for DLL change (success detection) ───────────────────────────────
Write-Verbose-Host "  Polling for DLL change (timeout: ${TimeoutSeconds}s)..." Cyan

$pollInterval = 500   # ms
$elapsed      = 0
$succeeded    = $false
$newMtime     = $null
$postInstallTs = $preInstallTs

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

    $curInstallTs = Get-InstallXmlTimestamp
    if ($curInstallTs -and $curInstallTs -ne $preInstallTs) {
        $postInstallTs = $curInstallTs
        $succeeded = $true
        break
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
    if ($newMtime) {
        Write-Verbose-Host "  COMPILE SUCCEEDED  (DLL updated at $($newMtime.ToString('HH:mm:ss.fff')))" Green
        Write-Output "[COMPILE-RESULT] SUCCESS $($newMtime.ToString('yyyy-MM-dd HH:mm:ss.fff'))"
    } elseif ($postInstallTs -and $postInstallTs -ne $preInstallTs) {
        Write-Verbose-Host "  COMPILE SUCCEEDED  (Install.xml advanced to $postInstallTs)" Green
        Write-Output "[COMPILE-RESULT] SUCCESS $postInstallTs"
    }

    # 7. Read Install.xml on success to confirm official compile timestamp
    if ($postInstallTs) {
        Write-Verbose-Host "  Install.xml <CompiledCustomAssembly>: $postInstallTs" Green
    }
} else {
    # ── 5a. Failure — DLL mtime unchanged after timeout ──────────────────────
    Write-Host ""
    Write-Host "  COMPILE FAILED (DLL unchanged after ${TimeoutSeconds} seconds)" -ForegroundColor Red
    Write-Output "[COMPILE-RESULT] FAILED timeout"
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
                  Where-Object { $_ -notmatch "(?i)no error" } |
                  Select-String -Pattern "CS\d{4}|compile.*fail|failed.*compile|Unhandled exception|Exception:|strategy.*failed|indicator.*failed" -CaseSensitive:$false
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
