Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$winCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id))
)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
$target = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  if($w.Current.Name -eq 'Playback'){ $target=$w; break }
}
if(-not $target){ throw 'Playback window not found' }
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $name=$el.Current.Name
  $type=$el.Current.ControlType.ProgrammaticName
  if($name){ Write-Output ($type + ' :: ' + $name) }
}
