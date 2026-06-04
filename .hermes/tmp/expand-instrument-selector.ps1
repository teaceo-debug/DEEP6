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
$selector = $target.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'HistoricalDataWindowMarketReplayInstrumentSelector')))
$ec = $selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$ec.Expand()
Start-Sleep -Seconds 1
$all = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
for($i=0;$i -lt $all.Count;$i++){
  $el=$all.Item($i)
  $c=$el.Current
  if($c.ProcessId -eq $proc.Id -and $c.Name){
    if($c.Name -match 'MNQ|NQ|Micro|Select|Jun|06-26'){
      Write-Output ($c.ControlType.ProgrammaticName + ' :: ' + $c.Name + ' :: ' + $c.AutomationId + ' :: ' + $c.ClassName)
    }
  }
}
