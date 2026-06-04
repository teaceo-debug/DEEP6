Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Find-ElementByNameAndType([System.Windows.Automation.AutomationElement]$root,[string]$name,[System.Windows.Automation.ControlType]$type,[System.Windows.Automation.TreeScope]$scope=[System.Windows.Automation.TreeScope]::Descendants){
  $cond = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name))
  )
  $root.FindFirst($scope,$cond)
}

$proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$ntPid = $proc.Id
$main = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$tools = Find-ElementByNameAndType $main 'Tools' ([System.Windows.Automation.ControlType]::MenuItem)
$toolsExp = $tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$toolsExp.Expand()
Start-Sleep -Milliseconds 300
$histMenu = Find-ElementByNameAndType ([System.Windows.Automation.AutomationElement]::RootElement) 'Historical Data' ([System.Windows.Automation.ControlType]::MenuItem)
$histMenu.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
$winCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$ntPid))
)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
$hist = $null
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  if($w.Current.Name -eq 'Historical Data'){ $hist=$w; break }
}
if(-not $hist){ throw 'Historical Data window not found after opening' }
$continue = Find-ElementByNameAndType $hist 'Continue' ([System.Windows.Automation.ControlType]::Button)
if($continue){ $continue.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
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
