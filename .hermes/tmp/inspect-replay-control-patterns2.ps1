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
$ids = 'HistoricalDataWindowMarketReplayInstrumentSelector','textBox','instruments','HistoricalDataWindowMarketReplayDateSelector','HistoricalDataWindowMarketReplayDownloadButton'
$patterns = @(
  [System.Windows.Automation.ValuePattern]::Pattern,
  [System.Windows.Automation.InvokePattern]::Pattern,
  [System.Windows.Automation.ExpandCollapsePattern]::Pattern,
  [System.Windows.Automation.SelectionItemPattern]::Pattern,
  [System.Windows.Automation.SelectionPattern]::Pattern,
  [System.Windows.Automation.TogglePattern]::Pattern,
  [System.Windows.Automation.TextPattern]::Pattern,
  [System.Windows.Automation.ScrollItemPattern]::Pattern,
  [System.Windows.Automation.RangeValuePattern]::Pattern,
  [System.Windows.Automation.TransformPattern]::Pattern
)
foreach($id in $ids){
  $el = $target.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)))
  if($el){
    Write-Output ('ID=' + $id + ' TYPE=' + $el.Current.ControlType.ProgrammaticName + ' NAME=' + $el.Current.Name + ' CLASS=' + $el.Current.ClassName)
    foreach($p in $patterns){
      $obj = $null
      if($el.TryGetCurrentPattern($p,[ref]$obj)){ Write-Output ('  pattern=' + $p.ProgrammaticName) }
    }
  }
}
