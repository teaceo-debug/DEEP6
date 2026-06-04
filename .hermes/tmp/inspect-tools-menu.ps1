Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$menuCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Tools'))
)
$tools = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$menuCond)
if(-not $tools){ throw 'Tools not found' }
$exp = $tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$exp.Expand()
Start-Sleep -Milliseconds 500
$all = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem))
)
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $name=$el.Current.Name
  if($name -and ($name -match 'Historical|Import|Export|Database|Options|Replay|Download')){
    Write-Output ($name + ' | pid=' + $el.Current.ProcessId)
  }
}
$exp.Collapse()
