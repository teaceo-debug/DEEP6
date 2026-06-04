Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class EnumWin {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
$p = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Host 'NO-NT8'; exit 1 }
$targetPid = [uint32]$p.Id
$proc = [EnumWin+EnumWindowsProc]{
  param([IntPtr]$hWnd,[IntPtr]$l)
  $pid = 0
  [void][EnumWin]::GetWindowThreadProcessId($hWnd, [ref]$pid)
  if ($pid -eq $targetPid) {
    $sb = New-Object System.Text.StringBuilder 512
    [void][EnumWin]::GetWindowText($hWnd, $sb, $sb.Capacity)
    $title = $sb.ToString()
    $rect = New-Object EnumWin+RECT
    [void][EnumWin]::GetWindowRect($hWnd, [ref]$rect)
    $vis = [EnumWin]::IsWindowVisible($hWnd)
    Write-Host "HANDLE=$hWnd VISIBLE=$vis TITLE=[$title] RECT=$($rect.Left),$($rect.Top),$($rect.Right),$($rect.Bottom)"
  }
  return $true
}
[EnumWin]::EnumWindows($proc, [IntPtr]::Zero) | Out-Null
