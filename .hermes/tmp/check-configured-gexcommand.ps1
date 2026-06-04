Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
foreach($w in $wins){
  $hit=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'GEXCommand(C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_command.json,85,5,true,true,true,true,true)')))
  if($hit){ 'FOUND_CONFIGURED_GEXCOMMAND'; exit 0 }
}
'NOT_FOUND'
