Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinZ {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
function Open-IndicatorsDialog {
 $p=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
 $wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
 $chart=$null
 for($i=0;$i -lt $wins.Count;$i++){
   $w=$wins.Item($i)
   $hit=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
   if($hit){ $chart=$w; break }
 }
 if(-not $chart){ throw 'Chart not found' }
 [NT8WinZ]::ShowWindow([IntPtr]$chart.Current.NativeWindowHandle,9)|Out-Null
 Start-Sleep -Milliseconds 200
 [NT8WinZ]::SetForegroundWindow([IntPtr]$chart.Current.NativeWindowHandle)|Out-Null
 Start-Sleep -Milliseconds 400
 $btn=$chart.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
 $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
 Start-Sleep -Seconds 2
 $wins2=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
 for($i=0;$i -lt $wins2.Count;$i++){
   $w=$wins2.Item($i)
   $texts=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Text)))
   for($j=0;$j -lt $texts.Count;$j++){
     $n=''; try{$n=$texts.Item($j).Current.Name}catch{}
     if($n -eq 'Indicators'){ return $w }
   }
 }
 throw 'Indicators dialog not found'
}
$dialog=Open-IndicatorsDialog
Write-Output 'DIALOG_OPEN'
$btns=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)))
for($i=0;$i -lt $btns.Count;$i++){
 $b=$btns.Item($i)
 Write-Output (($b.Current.Name) + ' | ' + $b.Current.AutomationId)
}
