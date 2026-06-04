Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id))
)
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  $hit = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
  $name=''; $class=''; try{$name=$w.Current.Name}catch{}; try{$class=$w.Current.ClassName}catch{}
  Write-Output ("WIN[$i] name=[$name] class=[$class] hasIndicatorsButton=" + [bool]$hit)
}
