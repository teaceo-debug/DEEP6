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
if(-not $target){ throw 'Historical Data window not found' }
$treeItems = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TreeItem)))
for($i=0;$i -lt $treeItems.Count;$i++){
  $el = $treeItems.Item($i)
  $texts = $el.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Text)))
  $names = @()
  for($j=0;$j -lt $texts.Count;$j++){ if($texts.Item($j).Current.Name){ $names += $texts.Item($j).Current.Name } }
  Write-Output ('TreeItem ' + $i + ' labels=' + ($names -join '|'))
  foreach($p in @([System.Windows.Automation.SelectionItemPattern]::Pattern,[System.Windows.Automation.ExpandCollapsePattern]::Pattern,[System.Windows.Automation.InvokePattern]::Pattern)){
    $obj=$null
    if($el.TryGetCurrentPattern($p,[ref]$obj)){ Write-Output ('  pattern=' + $p.ProgrammaticName) }
  }
}
