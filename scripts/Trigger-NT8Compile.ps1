#Requires -Version 5.1
<#
.SYNOPSIS
    Attempts to trigger NinjaTrader 8's NinjaScript compiler for DEEP6.

.DESCRIPTION
    NT8 exposes a limited automation interface. This script tries to:
    1. Find the NT8 window
    2. Use WinAPI SendMessage / UI Automation to trigger compile

    Note: NT8 does not expose a public COM/automation API for compiling.
    The most reliable method is the NT8 CLI approach (if available) or
    manually pressing F5 in the NinjaScript Editor.
    This script serves as a placeholder / hook for future automation.
#>

param()

$NT8 = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue

if (-not $NT8) {
    Write-Host "  [SKIP] NinjaTrader 8 is not running." -ForegroundColor Yellow
    return
}

Write-Host "  NT8 PID: $($NT8.Id)  |  Window: $($NT8.MainWindowTitle)" -ForegroundColor Gray

# Future: use NT8 automation interface or SendKeys
# For now, bring NT8 to foreground as a visual reminder
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

[Win32]::ShowWindow($NT8.MainWindowHandle, 9) | Out-Null   # SW_RESTORE
[Win32]::SetForegroundWindow($NT8.MainWindowHandle) | Out-Null

Write-Host "  NT8 brought to foreground. Press F5 in the NinjaScript Editor to compile." -ForegroundColor Cyan

# TODO: Add UI Automation compile trigger when NT8 exposes a supported interface
