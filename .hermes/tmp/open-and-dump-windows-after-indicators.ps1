Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8WinA {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
$p=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
$chart=$null
for($i=0;$i -lt $wins.Count;$i++){
 $w=$wins.Item($i)
 $hit=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
 if($hit){ $chart=$w; break }
}
if(-not $chart){ throw 'chart not found' }
[NT8WinA]::ShowWindow([IntPtr]$chart.Current.NativeWindowHandle,9)|Out-Null
Start-Sleep -Milliseconds 200
[NT8WinA]::SetForegroundWindow([IntPtr]$chart.Current.NativeWindowHandle)|Out-Null
Start-Sleep -Milliseconds 500
$btn=$chart.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 3
$wins2=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
for($i=0;$i -lt $wins2.Count;$i++){
 $w=$wins2.Item($i)
 $name=''; $class=''; $handle=''; try{$name=$w.Current.Name}catch{}; try{$class=$w.Current.ClassName}catch{}; try{$handle=$w.Current.NativeWindowHandle}catch{}
 Write-Output ("WIN[$i] name=[$name] class=[$class] handle=$handle")
 $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
 $hits=0
 for($j=0;$j -lt $all.Count;$j++){
   $n=''; try{$n=$all.Item($j).Current.Name}catch{}
   if($n -match 'Indicators|GEXCommand|Add|OK|Cancel'){ Write-Output ('  ' + $all.Item($j).Current.ControlType.ProgrammaticName + ' | ' + $n + ' | ' + $all.Item($j).Current.AutomationId); $hits++ }
 }
 if($hits -eq 0){ Write-Output '  no interesting descendants' }
}
