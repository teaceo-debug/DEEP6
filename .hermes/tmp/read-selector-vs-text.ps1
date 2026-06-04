Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$winCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
$target = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  if($w.Current.Name -eq 'Historical Data'){ $target=$w; break }
}
function Find-ById($root,$id){
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)))
}
$selector = Find-ById $target 'HistoricalDataWindowMarketReplayInstrumentSelector'
$textBox = Find-ById $target 'textBox'
$selectorValue = $selector.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$textValue = $textBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
'SelectorValue=' + $selectorValue.Current.Value
'TextValue=' + $textValue.Current.Value
