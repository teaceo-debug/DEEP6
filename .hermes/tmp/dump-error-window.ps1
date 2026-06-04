Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$main = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$all = $main.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $c=$el.Current
  if($c.Name){ Write-Output ($c.ControlType.ProgrammaticName + ' | ' + $c.Name + ' | ' + $c.AutomationId) }
}
