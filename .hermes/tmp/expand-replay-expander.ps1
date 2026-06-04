Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Open-HistoricalData {
  $proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
  $toolsCond = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Tools'))
  )
  $tools = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$toolsCond)
  if($tools){
    $tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
    Start-Sleep -Milliseconds 300
    $histCond = New-Object System.Windows.Automation.AndCondition(
      (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
      (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Historical Data'))
    )
    $hist = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$histCond)
    if($hist){ $hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Seconds 2 }
  }
}
function Find-ById($root,$id){
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
}
Open-HistoricalData
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
$expander = Find-ById $target 'HistoricalDataWindowMarketReplayExpander'
if(-not $expander){ throw 'Replay expander not found' }
$exp = $expander.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$exp.Expand()
Start-Sleep -Seconds 1
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $c=$el.Current
  if(-not $c.IsOffscreen){
    $line = [string]::Format('{0} | Name={1} | AutoId={2} | Class={3} | Help={4}',
      $c.ControlType.ProgrammaticName,$c.Name,$c.AutomationId,$c.ClassName,$c.HelpText)
    Write-Output $line
  }
}
