Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
$dialog=$null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  for($j=0;$j -lt $all.Count;$j++){
    $n=''; try{$n=$all.Item($j).Current.Name}catch{}
    if($n -eq 'Indicators'){ $dialog=$w; break }
  }
  if($dialog){ break }
}
if(-not $dialog){ throw 'Indicators dialog not open' }
$btns=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)))
for($i=0;$i -lt $btns.Count;$i++){
 $b=$btns.Item($i)
 Write-Output ($b.Current.Name + ' | ' + $b.Current.AutomationId)
}
