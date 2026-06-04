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
function Get-HistoricalWindow {
  $proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
  $winCond = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
  )
  $wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
  for($i=0;$i -lt $wins.Count;$i++){
    $w=$wins.Item($i)
    if($w.Current.Name -eq 'Historical Data'){ return $w }
  }
  return $null
}
function Find-ById($root,$id){
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)))
}
Open-HistoricalData
$target = Get-HistoricalWindow
if(-not $target){ throw 'Historical Data window not found' }
$expander = Find-ById $target 'HistoricalDataWindowMarketReplayExpander'
$expander.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Start-Sleep -Milliseconds 500
$selector = Find-ById $target 'HistoricalDataWindowMarketReplayInstrumentSelector'
$selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Start-Sleep -Milliseconds 500
$proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$itemCond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'MNQ 06-26')),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
)
$item = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$itemCond)
$item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Milliseconds 500
$target = Get-HistoricalWindow
$selector = Find-ById $target 'HistoricalDataWindowMarketReplayInstrumentSelector'
$textBox = Find-ById $target 'textBox'
$download = Find-ById $target 'HistoricalDataWindowMarketReplayDownloadButton'
'DropSelectorValue=' + $selector.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
'TextBoxValue=' + $textBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
'DownloadEnabled=' + $download.Current.IsEnabled
