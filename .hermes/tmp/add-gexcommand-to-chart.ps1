Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinB {
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
 [NT8WinB]::ShowWindow([IntPtr]$chart.Current.NativeWindowHandle,9)|Out-Null
 Start-Sleep -Milliseconds 200
 [NT8WinB]::SetForegroundWindow([IntPtr]$chart.Current.NativeWindowHandle)|Out-Null
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
$dialog = Open-IndicatorsDialog
# If already configured, just OK out
$existing = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'GEXCommand(C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_command.json,85,5,true,true,true,true,true)')))
if(-not $existing){
  $item = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::ListItem)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'GEXCommand(C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_command.json,85,5,true,true,true,true,true)')))))
  if(-not $item){ throw 'GEXCommand available item not found' }
  try{ $item.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() } catch {}
  Start-Sleep -Milliseconds 300
  $add = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'add')))))
  if(-not $add){ throw 'Add button not found' }
  $add.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  Start-Sleep -Seconds 1
}
$ok = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'btnOk')))
if(-not $ok){ throw 'OK button not found' }
$ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
'GEXCOMMAND_ADDED_OR_CONFIRMED'
