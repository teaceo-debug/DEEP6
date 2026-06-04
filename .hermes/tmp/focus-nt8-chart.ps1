param()

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinD {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@

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
[NT8WinD]::ShowWindow($handle, 9) | Out-Null
Start-Sleep -Milliseconds 250
[NT8WinD]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Milliseconds 750

$title = $chart.Current.Name
Write-Output "FOCUSED_CHART $title"