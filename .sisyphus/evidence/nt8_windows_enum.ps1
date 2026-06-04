Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinEnum {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
$ntIds = @(Get-Process NinjaTrader -ErrorAction SilentlyContinue | ForEach-Object { [uint32]$_.Id })
[WinEnum]::EnumWindows({ param($h,$l)
  $procId = [uint32]0
  [void][WinEnum]::GetWindowThreadProcessId($h, [ref]$procId)
  if($ntIds -contains $procId){
    $len=[WinEnum]::GetWindowTextLength($h)
    $sb=New-Object System.Text.StringBuilder ([Math]::Max(256,$len+1))
    [void][WinEnum]::GetWindowText($h,$sb,$sb.Capacity)
    $vis=[WinEnum]::IsWindowVisible($h)
    Write-Host "hwnd=$h pid=$pid visible=$vis title='$($sb.ToString())'"
  }
  return $true
}, [IntPtr]::Zero) | Out-Null
