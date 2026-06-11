Add-Type -AssemblyName UIAutomationClient
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NtWin {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr extra);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
$dll="C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll"
$before=(Get-Item $dll).LastWriteTime
$target=[IntPtr]::Zero
[NtWin]::EnumWindows({
  param($h,$l)
  $procId=[uint32]0
  [NtWin]::GetWindowThreadProcessId($h,[ref]$procId)|Out-Null
  if($procId -eq 17680){
    $sb=New-Object System.Text.StringBuilder 512
    [NtWin]::GetWindowText($h,$sb,512)|Out-Null
    $title=$sb.ToString()
    if($title -match "NinjaScript Editor") { $script:target=$h }
  }
  $true
}, [IntPtr]::Zero) | Out-Null
if($target -eq [IntPtr]::Zero){ throw "NinjaScript Editor window not found; open editor needed for F5 compile" }
[NtWin]::ShowWindow($target,9)|Out-Null
[NtWin]::SetForegroundWindow($target)|Out-Null
Start-Sleep -Milliseconds 500
$ws=New-Object -ComObject WScript.Shell
$ws.SendKeys("{F5}")
Start-Sleep -Seconds 12
$after=(Get-Item $dll).LastWriteTime
$root=[System.Windows.Automation.AutomationElement]::RootElement
$errorRows=0
try {
  $rows=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  foreach($e in $rows){
    $n=$e.Current.Name
    if($n -match "CS\d{4}|Error") { $errorRows++ }
  }
} catch {}
"before=$($before.ToString("o")) after=$($after.ToString("o")) changed=$($after -gt $before) errorRows=$errorRows"
