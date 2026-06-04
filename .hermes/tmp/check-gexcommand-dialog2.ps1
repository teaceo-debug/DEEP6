Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinY {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
function Find-First($root, $conds) {
  if ($conds.Count -eq 1) { $cond = $conds[0] } else { $cond = New-Object System.Windows.Automation.AndCondition($conds) }
  return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id)))
$chart = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  $hit=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
  if($hit){ $chart=$w; break }
}
if(-not $chart){ throw 'Chart window not found' }
[NT8WinY]::ShowWindow([IntPtr]$chart.Current.NativeWindowHandle,9) | Out-Null
Start-Sleep -Milliseconds 200
[NT8WinY]::SetForegroundWindow([IntPtr]$chart.Current.NativeWindowHandle) | Out-Null
Start-Sleep -Milliseconds 400
$btn = Find-First $chart @((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
$wins2 = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id)))
$dialog = $null
for($i=0;$i -lt $wins2.Count;$i++){
  $w=$wins2.Item($i)
  $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  for($j=0;$j -lt $all.Count;$j++){
    $el=$all.Item($j)
    $n=''; try{$n=$el.Current.Name}catch{}
    if($n -eq 'Indicators'){ $dialog=$w; break }
  }
  if($dialog){ break }
}
if(-not $dialog){ throw 'Indicators dialog not found' }
Write-Output 'DIALOG_FOUND'
$all = $dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$hits=@()
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $n=''; $id=''; $type='';
  try{$n=$el.Current.Name}catch{}
  try{$id=$el.Current.AutomationId}catch{}
  try{$type=$el.Current.ControlType.ProgrammaticName}catch{}
  if(($n -and ($n -match 'GEXCommand|DEEP6|GEX')) -or ($id -and ($id -match 'GEXCommand|DEEP6|GEX'))){
    $hits += ("$type | $n | $id")
  }
}
if($hits.Count -eq 0){ 'NO_HITS' } else { $hits | ForEach-Object { $_ } }
