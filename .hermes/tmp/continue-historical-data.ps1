Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$pid = $p.Id
$winCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$pid))
)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
$hist = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  if($w.Current.Name -eq 'Historical Data'){ $hist=$w; break }
}
if(-not $hist){ throw 'Historical Data window not found' }
$btnCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Continue'))
)
$btn = $hist.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$btnCond)
if(-not $btn){ throw 'Continue button not found' }
$inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$inv.Invoke()
Start-Sleep -Seconds 2
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  Write-Output ('WINDOW: ' + $w.Current.Name)
  $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  for($j=0;$j -lt $all.Count;$j++){
    $el = $all.Item($j)
    $name = $el.Current.Name
    $type = $el.Current.ControlType.ProgrammaticName
    if($name){ Write-Output ('  ' + $type + ' :: ' + $name) }
  }
}
