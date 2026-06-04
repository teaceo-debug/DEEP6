Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinProbe {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@
$p = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Host 'NO-NT8'; exit 1 }
$pid = $p.Id
Get-Process -Name 'NinjaTrader' | ForEach-Object {
  $h = $_.MainWindowHandle
  $title = $_.MainWindowTitle
  $r = New-Object WinProbe+RECT
  [void][WinProbe]::GetWindowRect($h, [ref]$r)
  $vis = [WinProbe]::IsWindowVisible($h)
  Write-Host "PID=$($_.Id) HANDLE=$h VISIBLE=$vis TITLE=[$title] RECT=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)"
}
