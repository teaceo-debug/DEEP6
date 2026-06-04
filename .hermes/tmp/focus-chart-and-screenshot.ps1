Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinC {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@

param(
  [string]$OutputPath = "C:\Users\Tea\DEEP6\captures\nt8-chart-focused.png"
)

$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id))
)
$chart = $null
for($i=0; $i -lt $wins.Count; $i++){
  $w = $wins.Item($i)
  $hit = $w.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'ChartWindowIndicatorsButton'))
  )
  if($hit){ $chart = $w; break }
}
if(-not $chart){ throw 'Chart window not found' }

$handle = [IntPtr]$chart.Current.NativeWindowHandle
[NT8WinC]::ShowWindow($handle, 9) | Out-Null
Start-Sleep -Milliseconds 300
[NT8WinC]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Seconds 1

$rect = $chart.Current.BoundingRectangle
$width = [int][Math]::Ceiling($rect.Width)
$height = [int][Math]::Ceiling($rect.Height)
$x = [int][Math]::Floor($rect.X)
$y = [int][Math]::Floor($rect.Y)

$dir = Split-Path $OutputPath
if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }

$bmp = New-Object System.Drawing.Bitmap($width, $height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
$bmp.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()

Write-Output "CHART_SCREENSHOT $OutputPath"