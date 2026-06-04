Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8ReplayProbe {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
function Focus([IntPtr]$h){ [NT8ReplayProbe]::ShowWindow($h,9)|Out-Null; Start-Sleep -Milliseconds 200; [NT8ReplayProbe]::SetForegroundWindow($h)|Out-Null; Start-Sleep -Milliseconds 300 }
function FindCtrl($root,$id,$name,$type){
  $conds = New-Object System.Collections.Generic.List[System.Windows.Automation.Condition]
  if($id){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id))) }
  if($name){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name))) }
  if($type){ $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type))) }
  if($conds.Count -eq 1){ $cond=$conds[0] } else { $cond = New-Object System.Windows.Automation.AndCondition($conds.ToArray()) }
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
}
function GetWindow($name){
  $p=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  $wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))))
  for($i=0;$i -lt $wins.Count;$i++){ if($wins.Item($i).Current.Name -eq $name){ return $wins.Item($i) } }
}
$path='C:\Users\Tea\Documents\NinjaTrader 8\db\replay\MNQ 06-26\20260425.nrd'
if(Test-Path $path){ Remove-Item $path -Force }
$cc = [System.Windows.Automation.AutomationElement]::FromHandle((Get-Process NinjaTrader | Select-Object -First 1).MainWindowHandle)
$tools=FindCtrl $cc $null 'Tools' ([System.Windows.Automation.ControlType]::MenuItem)
$tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand(); Start-Sleep -Milliseconds 300
$hist=FindCtrl ([System.Windows.Automation.AutomationElement]::RootElement) $null 'Historical Data' ([System.Windows.Automation.ControlType]::MenuItem)
$hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Seconds 1
$hd=GetWindow 'Historical Data'
Focus([IntPtr]$hd.Current.NativeWindowHandle)
$exp=FindCtrl $hd 'HistoricalDataWindowMarketReplayExpander' $null $null
try{$exp.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()}catch{}
$treeItems=$hd.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TreeItem)))
if($treeItems.Count -ge 2){ try{$treeItems.Item(1).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()}catch{} }
$selector=FindCtrl $hd 'HistoricalDataWindowMarketReplayInstrumentSelector' $null $null
$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand(); Start-Sleep -Milliseconds 300
$p=Get-Process NinjaTrader | Select-Object -First 1
$item=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'MNQ 06-26')),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))))
$item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Milliseconds 300
$date=FindCtrl $hd 'HistoricalDataWindowMarketReplayDateSelector' $null $null
$date.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('04/25/2026'); Start-Sleep -Milliseconds 300
$download=FindCtrl $hd 'HistoricalDataWindowMarketReplayDownloadButton' $null $null
'Enabled=' + $download.Current.IsEnabled
$download.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
for($i=0;$i -lt 20;$i++){
  Start-Sleep -Seconds 2
  $hd=GetWindow 'Historical Data'
  $msg=FindCtrl $hd 'txtMessage' $null $null
  $elapsed=FindCtrl $hd 'txtElapsedRemaining' $null $null
  $iters=FindCtrl $hd 'txtIterations' $null $null
  $cancel=FindCtrl $hd 'btnCancel' $null $null
  $continue=FindCtrl $hd 'btnContinue' $null $null
  $wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
  $named=@()
  for($j=0;$j -lt $wins.Count;$j++){
    $w=$wins.Item($j)
    if($w.Current.ProcessId -eq $p.Id -and $w.Current.Name){ $named += $w.Current.Name }
  }
  Write-Output ("tick=$i file=" + (Test-Path $path) + " msg='" + $(if($msg){$msg.Current.Name}else{''}) + "' elapsed='" + $(if($elapsed){$elapsed.Current.Name}else{''}) + "' iters='" + $(if($iters){$iters.Current.Name}else{''}) + "' cancelVis=" + $(if($cancel){-not $cancel.Current.IsOffscreen}else{'NA'}) + " continueVis=" + $(if($continue){-not $continue.Current.IsOffscreen}else{'NA'}) + " windows=" + ($named -join ','))
}
