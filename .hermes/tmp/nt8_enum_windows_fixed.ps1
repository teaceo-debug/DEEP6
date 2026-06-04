Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class EnumWin2 {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint procIdOut);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

$nt8Proc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $nt8Proc) { Write-Host 'NO-NT8'; exit 1 }
$targetProcId = [uint32]$nt8Proc.Id

$cb = [EnumWin2+EnumWindowsProc]{
  param([IntPtr]$hWnd,[IntPtr]$lParam)
  $ownerProcId = [uint32]0
  [void][EnumWin2]::GetWindowThreadProcessId($hWnd, [ref]$ownerProcId)
  if ($ownerProcId -eq $targetProcId) {
    $sb = New-Object System.Text.StringBuilder 1024
    [void][EnumWin2]::GetWindowText($hWnd, $sb, $sb.Capacity)
    $title = $sb.ToString()
    $rect = New-Object EnumWin2+RECT
    [void][EnumWin2]::GetWindowRect($hWnd, [ref]$rect)
    $vis = [EnumWin2]::IsWindowVisible($hWnd)
    Write-Host (("HANDLE={0} VISIBLE={1} TITLE=[{2}] RECT={3},{4},{5},{6}") -f $hWnd, $vis, $title, $rect.Left, $rect.Top, $rect.Right, $rect.Bottom)
  }
  return $true
}

[EnumWin2]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
