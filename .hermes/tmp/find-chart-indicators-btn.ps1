Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')
$el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
if($el){
  Write-Output ('FOUND name=' + $el.Current.Name + ' pid=' + $el.Current.ProcessId + ' class=' + $el.Current.ClassName)
} else {
  Write-Output 'NOT_FOUND'
}
