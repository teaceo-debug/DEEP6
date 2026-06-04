Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-NtRoot {
  $p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
}

$root = Get-NtRoot
$menuCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Tools'))
)
$tools = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$menuCond)
$exp = $tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$exp.Expand()
Start-Sleep -Milliseconds 300
$histCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Historical Data'))
)
$hist = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$histCond)
if(-not $hist){ throw 'Historical Data menu item not found' }
$invoke = $hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$invoke.Invoke()
Start-Sleep -Seconds 2
$winCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,(Get-Process NinjaTrader | Select-Object -First 1).Id))
)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  Write-Output ('WINDOW: ' + $w.Current.Name)
}
$target = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  if($w.Current.Name -match 'Historical Data'){ $target=$w; break }
}
if(-not $target){ throw 'Historical Data window not found' }
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $name=$el.Current.Name
  $type=$el.Current.ControlType.ProgrammaticName
  if($name){ Write-Output ($type + ' :: ' + $name) }
}
