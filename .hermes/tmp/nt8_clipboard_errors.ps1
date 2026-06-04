Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8ClipWin {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$p = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Host 'NT8 not running'; exit 1 }
[NT8ClipWin]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
Start-Sleep -Milliseconds 250
[NT8ClipWin]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 400
$wsh = New-Object -ComObject WScript.Shell
$wsh.AppActivate('NinjaTrader') | Out-Null
Start-Sleep -Milliseconds 250
# Open editor then output window
$wsh.SendKeys('%t')
Start-Sleep -Milliseconds 400
$wsh.SendKeys('n')
Start-Sleep -Milliseconds 1200
$wsh.SendKeys('%v')
Start-Sleep -Milliseconds 350
$wsh.SendKeys('o')
Start-Sleep -Milliseconds 1000
# Try select all and copy
$wsh.SendKeys('^a')
Start-Sleep -Milliseconds 300
$wsh.SendKeys('^c')
Start-Sleep -Milliseconds 600
try {
  $text = [System.Windows.Forms.Clipboard]::GetText()
  if ([string]::IsNullOrWhiteSpace($text)) { Write-Host '[EMPTY-CLIPBOARD]' }
  else { Write-Output $text }
} catch {
  Write-Host '[CLIPBOARD-READ-FAILED]'
  Write-Host $_.Exception.Message
  exit 2
}
