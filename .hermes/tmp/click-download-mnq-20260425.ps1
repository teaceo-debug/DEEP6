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
function Find-ById($root,$id){
  $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)))
}
$instrumentText = Find-ById $target 'textBox'
$dateBox = Find-ById $target 'HistoricalDataWindowMarketReplayDateSelector'
$downloadButton = Find-ById $target 'HistoricalDataWindowMarketReplayDownloadButton'
$vp1 = $instrumentText.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$vp2 = $dateBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$vp1.SetValue('MNQ 06-26')
$vp2.SetValue('04/25/2026')
Start-Sleep -Milliseconds 500
$downloadButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Output 'DOWNLOAD_CLICKED'
