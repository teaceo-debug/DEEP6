Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8ReplayFresh {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
function Focus([IntPtr]$h){ [NT8ReplayFresh]::ShowWindow($h,9)|Out-Null; Start-Sleep -Milliseconds 200; [NT8ReplayFresh]::SetForegroundWindow($h)|Out-Null; Start-Sleep -Milliseconds 300 }
function FindCtrl($root,$id,$name,$type){
  $conds = New-Object System.Collections.Generic.List[System.Windows.Automation.Condition]
  if($id){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id))) }
  if($name){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name))) }
  if($type){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type))) }
  if($conds.Count -eq 1){ $cond=$conds[0] } else { $cond = New-Object System.Windows.Automation.AndCondition($conds.ToArray()) }
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
}
function GetWindow($name){
  $proc=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  $ntPid=$proc.Id
  $wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$ntPid)))))
  for($i=0;$i -lt $wins.Count;$i++){ if($wins.Item($i).Current.Name -eq $name){ return $wins.Item($i) } }
}
$existing=GetWindow 'Historical Data'
if($existing){
  $close=FindCtrl $existing 'NTWindowButtonClose' 'Close' ([System.Windows.Automation.ControlType]::Button)
  if($close){ try{$close.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()}catch{}; Start-Sleep -Seconds 1 }
}
$proc=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$main=[System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$tools=FindCtrl $main $null 'Tools' ([System.Windows.Automation.ControlType]::MenuItem)
$tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand(); Start-Sleep -Milliseconds 300
$hist=FindCtrl ([System.Windows.Automation.AutomationElement]::RootElement) $null 'Historical Data' ([System.Windows.Automation.ControlType]::MenuItem)
$hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Seconds 1
$hd=GetWindow 'Historical Data'
if(-not $hd){ throw 'Historical Data not opened' }
Focus([IntPtr]$hd.Current.NativeWindowHandle)
function State($label){
  $hd=GetWindow 'Historical Data'
  $download=FindCtrl $hd 'HistoricalDataWindowMarketReplayDownloadButton' $null $null
  $selector=FindCtrl $hd 'HistoricalDataWindowMarketReplayInstrumentSelector' $null $null
  $date=FindCtrl $hd 'HistoricalDataWindowMarketReplayDateSelector' $null $null
  $txt=FindCtrl $hd 'textBox' $null $null
  "$label|download=$($download.Current.IsEnabled)|selector=$($(if($txt){$txt.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value}else{''}))|date=$($(if($date){$date.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value}else{''}))|selState=$($(if($selector){$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Current.ExpandCollapseState}else{''}))"
}
State 'fresh-open'
$exp=FindCtrl $hd 'HistoricalDataWindowMarketReplayExpander' $null $null
try{$exp.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()}catch{}
Start-Sleep -Milliseconds 300
State 'after-expander'
$treeItems=$hd.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TreeItem)))
if($treeItems.Count -ge 2){ try{$treeItems.Item(1).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()}catch{} }
Start-Sleep -Milliseconds 300
State 'after-tree-select'
$selector=FindCtrl $hd 'HistoricalDataWindowMarketReplayInstrumentSelector' $null $null
$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand(); Start-Sleep -Milliseconds 300
State 'after-selector-expand'
$item=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'MNQ 06-26')),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id)))))
$item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Milliseconds 300
State 'after-contract-select'
$date=FindCtrl $hd 'HistoricalDataWindowMarketReplayDateSelector' $null $null
$date.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('04/25/2026'); Start-Sleep -Milliseconds 300
State 'after-date-set'
