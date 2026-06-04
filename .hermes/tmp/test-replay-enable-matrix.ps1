Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8ReplayTest {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
$wsh = New-Object -ComObject WScript.Shell
function Focus([IntPtr]$h){ [NT8ReplayTest]::ShowWindow($h,9)|Out-Null; Start-Sleep -Milliseconds 200; [NT8ReplayTest]::SetForegroundWindow($h)|Out-Null; Start-Sleep -Milliseconds 300 }
function FindCtrl($root,$id,$name,$type){
  $conds = @()
  if($id){ $conds += New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id) }
  if($name){ $conds += New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name) }
  if($type){ $conds += New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type) }
  if($conds.Count -eq 1){ $cond=$conds[0] } else { $cond = New-Object System.Windows.Automation.AndCondition($conds) }
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
$hd=GetHD
if(-not $hd){ throw 'Historical Data not found' }
Focus([IntPtr]$hd.Current.NativeWindowHandle)
$exp=FindCtrl $hd 'HistoricalDataWindowMarketReplayExpander' $null $null
try{$exp.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()}catch{}
Start-Sleep -Milliseconds 300
$treeItems = $hd.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TreeItem)))
if($treeItems.Count -ge 2){ try{$treeItems.Item(1).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()}catch{} }
$selector=FindCtrl $hd 'HistoricalDataWindowMarketReplayInstrumentSelector' $null $null
$text=FindCtrl $hd 'textBox' $null $null
$date=FindCtrl $hd 'HistoricalDataWindowMarketReplayDateSelector' $null $null
$download=FindCtrl $hd 'HistoricalDataWindowMarketReplayDownloadButton' $null $null
$continue=FindCtrl $hd 'btnContinue' $null $null
$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Start-Sleep -Milliseconds 400
$item=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'MNQ 06-26')),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,(Get-Process NinjaTrader | Select-Object -First 1).Id)))))
$item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Milliseconds 300
$date.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('04/25/2026')
Start-Sleep -Milliseconds 300
function Snap($label){
  $selPat=$selector.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
  $datePat=$date.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
  "$label|selector=$($selPat.Current.Value)|date=$($datePat.Current.Value)|download=$($download.Current.IsEnabled)|continue=$($continue.Current.IsEnabled)|selState=$((($selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)).Current.ExpandCollapseState))|dateState=$((($date.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)).Current.ExpandCollapseState))"
}
Snap 'initial'
try{$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse()}catch{}
Start-Sleep -Milliseconds 300
Snap 'selector-collapsed'
try{$date.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()}catch{}
Start-Sleep -Milliseconds 300
Snap 'date-expanded'
try{$date.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse()}catch{}
Start-Sleep -Milliseconds 300
Snap 'date-collapsed'
$text.SetFocus(); Start-Sleep -Milliseconds 100; $wsh.SendKeys('{TAB}'); Start-Sleep -Milliseconds 300
Snap 'after-tab'
$wsh.SendKeys('{ENTER}'); Start-Sleep -Milliseconds 300
Snap 'after-enter'
$continue.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Milliseconds 500
Snap 'after-continue'
