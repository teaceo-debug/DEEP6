Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinCtl3 {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}
"@
$cc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*Control Center*' } | Select-Object -First 1
if (-not $cc) { $cc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Select-Object -First 1 }
if (-not $cc) { Write-Host 'NO-NT8'; exit 1 }
[WinCtl3]::ShowWindow($cc.MainWindowHandle, 9) | Out-Null
Start-Sleep -Milliseconds 200
[WinCtl3]::MoveWindow($cc.MainWindowHandle, 100, 100, 1400, 900, $true) | Out-Null
Start-Sleep -Milliseconds 200
[WinCtl3]::SetForegroundWindow($cc.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500
$wsh = New-Object -ComObject WScript.Shell
$wsh.AppActivate('Control Center') | Out-Null
Start-Sleep -Milliseconds 300
$wsh.SendKeys('%n')
Start-Sleep -Milliseconds 300
$wsh.SendKeys('{DOWN}')
Start-Sleep -Milliseconds 1200
Write-Host 'MENU-DOWN'
