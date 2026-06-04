Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8ReplayGo {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
function Focus([IntPtr]$h){ [NT8ReplayGo]::ShowWindow($h,9)|Out-Null; Start-Sleep -Milliseconds 200; [NT8ReplayGo]::SetForegroundWindow($h)|Out-Null; Start-Sleep -Milliseconds 300 }
function FindCtrl($root,$id,$name,$type){
  $conds = New-Object System.Collections.Generic.List[System.Windows.Automation.Condition]
  if($id){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id))) }
  if($name){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name))) }
  if($type){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type))) }
  if($conds.Count -eq 1){ $cond=$conds[0] } else { $cond = New-Object System.Windows.Automation.AndCondition($conds.ToArray()) }
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
}
function GetHD(){
  $proc=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  $main=[System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
  if($main){
    $tools=FindCtrl $main $null 'Tools' ([System.Windows.Automation.ControlType]::MenuItem)
    if($tools){
      try{$tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()}catch{}
      Start-Sleep -Milliseconds 300
      $hist=FindCtrl ([System.Windows.Automation.AutomationElement]::RootElement) $null 'Historical Data' ([System.Windows.Automation.ControlType]::MenuItem)
      if($hist){ try{$hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()}catch{}; Start-Sleep -Seconds 1 }
    }
  }
  $ntPid=$proc.Id
  $wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$ntPid)))))
  for($i=0;$i -lt $wins.Count;$i++){ if($wins.Item($i).Current.Name -eq 'Historical Data'){ return $wins.Item($i) } }
}
$path='C:\Users\Tea\Documents\NinjaTrader 8\db\replay\MNQ 06-26\20260425.nrd'
if(Test-Path $path){ Remove-Item $path -Force }
$hd=GetHD
if(-not $hd){ throw 'Historical Data not found' }
Focus([IntPtr]$hd.Current.NativeWindowHandle)
$exp=FindCtrl $hd 'HistoricalDataWindowMarketReplayExpander' $null $null
try{$exp.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()}catch{}
Start-Sleep -Milliseconds 300
$treeItems = $hd.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TreeItem)))
if($treeItems.Count -ge 2){ try{$treeItems.Item(1).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()}catch{} }
$selector=FindCtrl $hd 'HistoricalDataWindowMarketReplayInstrumentSelector' $null $null
$date=FindCtrl $hd 'HistoricalDataWindowMarketReplayDateSelector' $null $null
$download=FindCtrl $hd 'HistoricalDataWindowMarketReplayDownloadButton' $null $null
$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Start-Sleep -Milliseconds 400
$item=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'MNQ 06-26')),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,(Get-Process NinjaTrader | Select-Object -First 1).Id)))))
$item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Milliseconds 300
$date.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('04/25/2026')
Start-Sleep -Milliseconds 400
'EnabledBefore=' + $download.Current.IsEnabled
$download.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
for($i=0;$i -lt 30;$i++){
 Start-Sleep -Seconds 1
 if(Test-Path $path){ 'FOUND size=' + (Get-Item $path).Length; exit 0 }
}
'NOT_FOUND'
