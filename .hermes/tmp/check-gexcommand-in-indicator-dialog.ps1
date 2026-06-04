Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinX {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@

function Find-First($root, $conds) {
  if ($conds.Count -eq 1) { $cond = $conds[0] } else { $cond = New-Object System.Windows.Automation.AndCondition($conds) }
  return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id))
)
$chart = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  $class=''; try{$class=$w.Current.ClassName}catch{}
  $name=''; try{$name=$w.Current.Name}catch{}
  if($class -eq 'ChartWindow' -or $name -like 'Chart*') { $chart=$w; break }
}
if(-not $chart){ throw 'Chart window not found' }
[NT8WinX]::ShowWindow([IntPtr]$chart.Current.NativeWindowHandle,9) | Out-Null
Start-Sleep -Milliseconds 200
[NT8WinX]::SetForegroundWindow([IntPtr]$chart.Current.NativeWindowHandle) | Out-Null
Start-Sleep -Milliseconds 400
$btn = Find-First $chart @(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
)
if(-not $btn){ throw 'Indicators button not found' }
$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
$wins2 = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id))
)
$dialog = $null
for($i=0;$i -lt $wins2.Count;$i++){
  $w=$wins2.Item($i)
  $name=''; try{$name=$w.Current.Name}catch{}
  if($name -match 'Indicators'){ $dialog=$w; break }
}
if(-not $dialog){
  for($i=0;$i -lt $wins2.Count;$i++){
    $w=$wins2.Item($i)
    $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
    for($j=0;$j -lt $all.Count;$j++){
      $el=$all.Item($j)
      $n=''; try{$n=$el.Current.Name}catch{}
      if($n -match 'Indicators'){ $dialog=$w; break }
    }
    if($dialog){ break }
  }
}
if(-not $dialog){ throw 'Indicators dialog not found' }
Write-Output ('DIALOG=' + $dialog.Current.Name)
$all = $dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$hits = @()
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $n=''; try{$n=$el.Current.Name}catch{}
  if($n -and ($n -match 'GEXCommand|DEEP6|GEX')){
    $hits += ($el.Current.ControlType.ProgrammaticName + ' | ' + $n + ' | ' + $el.Current.AutomationId)
  }
}
if($hits.Count -eq 0){ Write-Output 'NO_HITS' } else { $hits | ForEach-Object { Write-Output $_ } }
