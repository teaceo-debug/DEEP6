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
  $tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
  Start-Sleep -Milliseconds 300
  $histCond = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Historical Data'))
  )
  $hist = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$histCond)
  $hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  Start-Sleep -Seconds 2
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
}
function Find-ById($root,$id){
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)))
}
Open-HistoricalData
$target = Get-HistoricalWindow
$expander = Find-ById $target 'HistoricalDataWindowMarketReplayExpander'
$expander.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Start-Sleep -Milliseconds 300
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
Start-Sleep -Milliseconds 300
$dateBox = Find-ById $target 'HistoricalDataWindowMarketReplayDateSelector'
$dateBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('04/25/2026')
Start-Sleep -Milliseconds 300
$continue = Find-ById $target 'btnContinue'
$continue.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
for($i=0;$i -lt 20;$i++){
  Start-Sleep -Seconds 1
  $target = Get-HistoricalWindow
  $msg = Find-ById $target 'txtMessage'
  $elapsed = Find-ById $target 'txtElapsedRemaining'
  $iters = Find-ById $target 'txtIterations'
  $download = Find-ById $target 'HistoricalDataWindowMarketReplayDownloadButton'
  Write-Output ('tick=' + $i + ' msg=' + ($(if($msg){$msg.Current.Name}else{''})) + ' elapsed=' + ($(if($elapsed){$elapsed.Current.Name}else{''})) + ' iters=' + ($(if($iters){$iters.Current.Name}else{''})) + ' downloadEnabled=' + ($(if($download){$download.Current.IsEnabled}else{'NA'})))
}
