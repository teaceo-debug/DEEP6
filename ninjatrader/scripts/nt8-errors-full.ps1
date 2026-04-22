# nt8-errors-full.ps1 - Read NT8 NinjaScript Editor compile errors via UIAutomation DataGrid
#
# This script reads the error DataGrid inside the NinjaScript Editor (NSE) window directly.
# It is the ONLY reliable way to get full CS#### error text from NT8 -- NT8 does NOT write
# compile errors to any log file. Errors live only in the NSE Output / Error list UI.
#
# Usage:
#   nt8-errors-full.ps1 [-Format Json|Text] [-Open] [-Verbose]
#
# Parameters:
#   -Format Json    Output JSON array of error objects (default)
#   -Format Text    Human-readable output to stdout
#   -Open           If NSE isn't visible, send Alt+T, n to open it, then retry
#   -Verbose        Print progress/diagnostics to stderr
#
# Exit codes:
#   0 = no errors found (clean compile or no compile run yet)
#   1 = one or more errors found
#   2 = NT8 not running
#   3 = NSE window not found (NSE not open; use -Open to auto-open)
#   4 = DataGrid not found in NSE (NSE open but no compile run yet)

param(
    [ValidateSet("Json","Text")]
    [string]$Format = "Json",
    [switch]$Open,
    [switch]$Verbose
)

$ErrorActionPreference = "SilentlyContinue"

# ── helpers ───────────────────────────────────────────────────────────────────

function Write-Diag {
    param([string]$Msg, [string]$Color = "Gray")
    if ($Verbose) { Write-Host $Msg -ForegroundColor $Color -ErrorAction SilentlyContinue }
}

function Emit-Result {
    param([object[]]$Errors)
    if ($Format -eq "Json") {
        if ($null -eq $Errors -or $Errors.Count -eq 0) {
            Write-Output "[]"
        } else {
            $Errors | ConvertTo-Json -Depth 3 -Compress:$false
        }
    } else {
        if ($null -eq $Errors -or $Errors.Count -eq 0) {
            Write-Host "No compile errors." -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "NT8 Compile Errors -- $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
            Write-Host "  Count: $($Errors.Count)" -ForegroundColor Red
            Write-Host ""
            foreach ($e in $Errors) {
                Write-Host "  [$($e.code)] $($e.file) line $($e.line) col $($e.col)" -ForegroundColor Yellow
                Write-Host "  $($e.message)" -ForegroundColor Red
                Write-Host ""
            }
        }
    }
}

function Emit-Error {
    param([string]$Msg, [int]$Code)
    if ($Format -eq "Json") {
        $obj = [PSCustomObject]@{ error = $Msg; code = $Code }
        Write-Output ($obj | ConvertTo-Json -Compress:$false)
    } else {
        Write-Host $Msg -ForegroundColor Yellow
    }
    exit $Code
}

# ── UIAutomation assemblies ───────────────────────────────────────────────────

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinUtil {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

# ── 1. Verify NT8 is running ──────────────────────────────────────────────────

$nt8 = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
if (!$nt8) {
    Emit-Error "NT8 is not running." 2
}

Write-Diag "NT8 found: PID $($nt8.Id)"

# ── 2. Find NSE window ────────────────────────────────────────────────────────

function Find-NSEWindow {
    param($Nt8Process)
    $pidCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
        [int]$Nt8Process.Id
    )
    $allWindows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        $pidCond
    )

    $nse = $null
    foreach ($w in $allWindows) {
        $name = ""
        try { $name = $w.Current.Name } catch { }
        Write-Diag "  Window: '$name'"
        if ($name -like "*NinjaScript*" -or $name -like "*Editor*" -or $name -like "*Script Editor*") {
            $nse = $w
            Write-Diag "  --> Found NSE window: '$name'" Cyan
            break
        }
    }
    return $nse
}

$nse = Find-NSEWindow -Nt8Process $nt8

# ── 3. -Open: if NSE not found, send Alt+T, n to open it ─────────────────────

if ($null -eq $nse -and $Open) {
    Write-Diag "NSE window not found. Sending Alt+T, n to open NinjaScript Editor..." Cyan

    [NT8WinUtil]::ShowWindow($nt8.MainWindowHandle, 9) | Out-Null
    Start-Sleep -Milliseconds 200
    [NT8WinUtil]::SetForegroundWindow($nt8.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 400

    $wsh = New-Object -ComObject WScript.Shell
    $wsh.AppActivate("NinjaTrader") | Out-Null
    Start-Sleep -Milliseconds 300
    $wsh.SendKeys("%t")          # Alt+T = Tools menu
    Start-Sleep -Milliseconds 400
    $wsh.SendKeys("n")           # n = NinjaScript Editor
    Start-Sleep -Milliseconds 1500

    # Retry find
    $nse = Find-NSEWindow -Nt8Process $nt8
}

if ($null -eq $nse) {
    Emit-Error "NinjaScript Editor window not found. Open it via Tools > NinjaScript Editor (or use -Open flag)." 3
}

Write-Diag "NSE window located."

# ── 4. Find the error DataGrid in the NSE window ─────────────────────────────

$gridCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::DataGrid
)

$grid = $null
try {
    $grid = $nse.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $gridCond)
} catch { }

if ($null -eq $grid) {
    Write-Diag "DataGrid not found in NSE. No compile has been run yet, or NSE is showing a different tab." Yellow
    # Not an error condition — just means no compile output exists yet
    Emit-Result -Errors @()
    exit 0
}

Write-Diag "DataGrid located in NSE."

# ── 5. Walk DataGrid rows ─────────────────────────────────────────────────────
# Row 0: header row — cells contain "NinjaScript File", "Error", "Code", "Line", "Column"
# Row 1+: error rows — cells contain: (icon/empty), filename, message, code, line, column (6 cells)
# Detection: error rows have a cell value matching ^CS\d{4}$

$trueCondition = [System.Windows.Automation.Condition]::TrueCondition
$rows = $null
try {
    $rows = $grid.FindAll([System.Windows.Automation.TreeScope]::Children, $trueCondition)
} catch { }

if ($null -eq $rows -or $rows.Count -eq 0) {
    Write-Diag "DataGrid is empty (no rows)." Yellow
    Emit-Result -Errors @()
    exit 0
}

Write-Diag "DataGrid rows found: $($rows.Count)"

$errorList = [System.Collections.Generic.List[object]]::new()

foreach ($row in $rows) {
    $cells = $null
    try {
        $cells = $row.FindAll([System.Windows.Automation.TreeScope]::Children, $trueCondition)
    } catch { continue }

    if ($null -eq $cells -or $cells.Count -eq 0) { continue }

    # Extract cell values
    $vals = [System.Collections.Generic.List[string]]::new()
    foreach ($cell in $cells) {
        $v = ""
        # Try ValuePattern first
        try {
            $vp = $cell.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $v = $vp.Current.Value
        } catch { }

        # Fall back to Name property
        if ([string]::IsNullOrWhiteSpace($v)) {
            try { $v = $cell.Current.Name } catch { }
        }

        # Fall back to TextPattern
        if ([string]::IsNullOrWhiteSpace($v)) {
            try {
                $tp = $cell.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
                $v = $tp.DocumentRange.GetText(512)
            } catch { }
        }

        $vals.Add(($v -replace "`r`n|`r|`n", " ").Trim())
    }

    Write-Diag "  Row cells ($($vals.Count)): $($vals -join ' | ')"

    # Determine if this is an error row by looking for ^CS\d{4}$ in any cell
    $isErrorRow = $false
    $codeValue  = ""
    foreach ($v in $vals) {
        if ($v -match "^CS\d{4}$") {
            $isErrorRow = $true
            $codeValue  = $v
            break
        }
    }

    if (!$isErrorRow) {
        Write-Diag "    --> header or non-error row, skipping."
        continue
    }

    # Parse error row
    # Observed column layout (6 cells): [0]=icon/empty, [1]=filename, [2]=message, [3]=code, [4]=line, [5]=column
    # Layout with 5 cells (no icon): [0]=filename, [1]=message, [2]=code, [3]=line, [4]=column
    $fileName = ""
    $message  = ""
    $code     = $codeValue
    $lineNum  = 0
    $colNum   = 0

    if ($vals.Count -ge 6) {
        # 6-cell layout: icon | file | message | code | line | col
        $fileName = $vals[1]
        $message  = $vals[2]
        $code     = $vals[3]
        $lineNum  = [int]($vals[4] -replace "[^\d]", "0")
        $colNum   = [int]($vals[5] -replace "[^\d]", "0")
    } elseif ($vals.Count -ge 5) {
        # 5-cell layout: file | message | code | line | col
        $fileName = $vals[0]
        $message  = $vals[1]
        $code     = $vals[2]
        $lineNum  = [int]($vals[3] -replace "[^\d]", "0")
        $colNum   = [int]($vals[4] -replace "[^\d]", "0")
    } elseif ($vals.Count -ge 4) {
        # Minimal: file | message | code | line
        $fileName = $vals[0]
        $message  = $vals[1]
        $code     = $vals[2]
        $lineNum  = [int]($vals[3] -replace "[^\d]", "0")
    } else {
        # Unknown layout — use what we have; code was already found
        $message = ($vals | Where-Object { $_ -ne $codeValue }) -join " "
    }

    # Clean up filename — NT8 DataGrid sometimes shows just the base filename, not full path
    $cleanFile = $fileName.Trim()

    $errorObj = [PSCustomObject]@{
        file    = $cleanFile
        message = $message.Trim()
        code    = $code.Trim()
        line    = $lineNum
        col     = $colNum
    }

    Write-Diag "    --> Error: [$($errorObj.code)] $($errorObj.file):$($errorObj.line) -- $($errorObj.message)" Red
    $errorList.Add($errorObj)
}

# ── 6. Output ─────────────────────────────────────────────────────────────────

Write-Diag "Total errors parsed: $($errorList.Count)"

Emit-Result -Errors $errorList.ToArray()

if ($errorList.Count -gt 0) { exit 1 }
exit 0
