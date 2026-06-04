Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'MNQ 06-26')),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
)
$items = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
for($i=0;$i -lt $items.Count;$i++){
  $el=$items.Item($i)
  Write-Output ('ITEM ' + $i + ' TYPE=' + $el.Current.ControlType.ProgrammaticName + ' NAME=' + $el.Current.Name + ' CLASS=' + $el.Current.ClassName)
  foreach($p in @(
    [System.Windows.Automation.InvokePattern]::Pattern,
    [System.Windows.Automation.SelectionItemPattern]::Pattern,
    [System.Windows.Automation.ExpandCollapsePattern]::Pattern,
    [System.Windows.Automation.ValuePattern]::Pattern,
    [System.Windows.Automation.TogglePattern]::Pattern
  )){
    $obj=$null
    if($el.TryGetCurrentPattern($p,[ref]$obj)){ Write-Output ('  pattern=' + $p.ProgrammaticName) }
  }
}
