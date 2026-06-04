Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8Check {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
function Open-IndicatorsDialog {
  $p=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  $wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
  $chart=$null
  foreach($w in $wins){
    $hit=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
    if($hit){ $chart=$w; break }
  }
  if(-not $chart){ throw 'Chart not found' }
  [NT8Check]::ShowWindow([IntPtr]$chart.Current.NativeWindowHandle,9)|Out-Null
  Start-Sleep -Milliseconds 200
  [NT8Check]::SetForegroundWindow([IntPtr]$chart.Current.NativeWindowHandle)|Out-Null
  Start-Sleep -Milliseconds 400
  $btn=$chart.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
  $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  Start-Sleep -Seconds 2
  $wins2=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
  foreach($w in $wins2){
    $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
    foreach($el in $all){
      $n=''; try{$n=$el.Current.Name}catch{}
      if($n -eq 'Indicators'){ return $w }
    }
  }
  throw 'Indicators dialog not found'
}
$dialog=Open-IndicatorsDialog
$listItems=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::ListItem)))
$count=0
foreach($li in $listItems){
 $name=''; try{$name=$li.Current.Name}catch{}
 if($name -like 'GEXCommand*'){ Write-Output ('GEXITEM=' + $name); $count++ }
}
Write-Output ('GEXITEM_COUNT=' + $count)
$ok=$dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'btnOk')))
if($ok){ try{$ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()}catch{} }
