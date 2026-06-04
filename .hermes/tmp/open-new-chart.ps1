Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8Focus {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
$wsh = New-Object -ComObject WScript.Shell
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
[NT8Focus]::ShowWindow($p.MainWindowHandle,9)|Out-Null
Start-Sleep -Milliseconds 200
[NT8Focus]::SetForegroundWindow($p.MainWindowHandle)|Out-Null
Start-Sleep -Milliseconds 500
$wsh.AppActivate('NinjaTrader') | Out-Null
Start-Sleep -Milliseconds 200
$wsh.SendKeys('%n')
Start-Sleep -Milliseconds 400
$wsh.SendKeys('c')
Start-Sleep -Seconds 2
'OPENED_NEW_CHART?'
