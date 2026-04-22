# nt8-ui.ps1 - NT8 UI interaction primitives
# Usage: nt8-ui.ps1 -Action <action> [options]
#
# Actions: Status | BringToFront | OpenEditor | Compile | OpenOutputWindow |
#          AddIndicator | AddStrategy | Screenshot

param(
    [Parameter(Mandatory)]
    [ValidateSet("Status","BringToFront","OpenEditor","Compile",
                 "OpenOutputWindow","AddIndicator","AddStrategy","Screenshot")]
    [string]$Action,

    [string]$Name,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8Win2 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@

function Get-NT8 {
    $p = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
    if (!$p) { Write-Error "NinjaTrader is not running."; exit 1 }
    return $p
}

function Focus-NT8 {
    $p = Get-NT8
    [NT8Win2]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
    Start-Sleep -Milliseconds 250
    [NT8Win2]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 300
    return $p
}

function Send-Keys {
    param([string]$Keys, [int]$DelayMs = 250)
    $wsh = New-Object -ComObject WScript.Shell
    $wsh.AppActivate("NinjaTrader") | Out-Null
    Start-Sleep -Milliseconds 150
    $wsh.SendKeys($Keys)
    Start-Sleep -Milliseconds $DelayMs
}

switch ($Action) {

    "Status" {
        $p = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
        if ($p) {
            Write-Host "NT8 is RUNNING -- PID $($p.Id), started $($p.StartTime.ToString('HH:mm:ss'))" -ForegroundColor Green
            $nt8 = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"
            $ind = (Get-ChildItem "$nt8\Indicators\DEEP6" -Filter "*.cs" -ErrorAction SilentlyContinue).Count
            $str = (Get-ChildItem "$nt8\Strategies\DEEP6" -Filter "*.cs" -ErrorAction SilentlyContinue).Count
            $add = (Get-ChildItem "$nt8\AddOns\DEEP6"     -Filter "*.cs" -ErrorAction SilentlyContinue).Count
            Write-Host "Deployed: $ind indicators, $str strategies, $add add-ons" -ForegroundColor Cyan
        } else {
            Write-Host "NT8 is NOT running." -ForegroundColor Yellow
        }
    }

    "BringToFront" {
        Focus-NT8 | Out-Null
        Write-Host "NT8 brought to foreground." -ForegroundColor Green
    }

    "OpenEditor" {
        Focus-NT8 | Out-Null
        Write-Host "Opening NinjaScript Editor..."
        Send-Keys "%t" 400
        Send-Keys "n"  1200
        Write-Host "NinjaScript Editor opened." -ForegroundColor Green
    }

    "Compile" {
        Focus-NT8 | Out-Null
        Send-Keys "%t" 400
        Send-Keys "n"  1000
        Write-Host "Sending F5 (Compile)..."
        Send-Keys "{F5}" 500
        Write-Host "Compile triggered -- check NT8 Output Window for results." -ForegroundColor Green
    }

    "OpenOutputWindow" {
        Focus-NT8 | Out-Null
        Write-Host "Opening Output Window..."
        Send-Keys "%v" 400
        Send-Keys "o"  800
        Write-Host "Output Window opened." -ForegroundColor Green
    }

    "AddIndicator" {
        if (!$Name) { $Name = Read-Host "Enter indicator name (e.g. DEEP6Footprint)" }
        Focus-NT8 | Out-Null
        Write-Host "Manual steps to add '$Name' to chart:"
        Write-Host "  1. Click the chart in NT8"
        Write-Host "  2. Right-click the chart"
        Write-Host "  3. Click Indicators..."
        Write-Host "  4. Find '$Name' under the DEEP6 category"
        Write-Host "  5. Double-click to add, configure params, click OK"
        Write-Host ""
        Write-Host "Attempting Shift+F10 (context menu on focused control)..."
        $wsh = New-Object -ComObject WScript.Shell
        $wsh.AppActivate("NinjaTrader") | Out-Null
        Start-Sleep -Milliseconds 400
        $wsh.SendKeys("+{F10}")
        Write-Host "Context menu triggered. Select Indicators... from the menu." -ForegroundColor Cyan
    }

    "AddStrategy" {
        if (!$Name) { $Name = Read-Host "Enter strategy name (e.g. DEEP6Strategy)" }
        Focus-NT8 | Out-Null
        Write-Host "To add strategy '$Name' to a chart:"
        Write-Host "  1. Right-click chart -> Strategies..."
        Write-Host "  2. Find '$Name' under DEEP6 category"
        Write-Host "  3. Double-click -> configure instrument, account, quantity"
        Write-Host "  4. Check Enabled -> OK"
        Write-Host ""
        Write-Host "For Strategy Analyzer (backtesting):"
        Write-Host "  Control Center -> New -> Strategy Analyzer"
        Write-Host "  Select '$Name' -> configure -> Run"
    }

    "Screenshot" {
        if (!$OutputPath) {
            $ts = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
            $OutputPath = "$PSScriptRoot\..\..\captures\nt8-$ts.png"
        }
        $dir = Split-Path $OutputPath
        if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }

        Focus-NT8 | Out-Null
        Start-Sleep -Milliseconds 500

        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen
        $bmp    = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
        $g      = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
        $bmp.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()

        Write-Host "Screenshot saved: $OutputPath" -ForegroundColor Green
    }
}
