Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$wsh = New-Object -ComObject WScript.Shell
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
$target.SetFocus()
Start-Sleep -Milliseconds 200
$instrumentText.SetFocus()
Start-Sleep -Milliseconds 300
$wsh.SendKeys('^a')
Start-Sleep -Milliseconds 100
$wsh.SendKeys('{BACKSPACE}')
Start-Sleep -Milliseconds 100
$wsh.SendKeys('MNQ 06-26')
Start-Sleep -Milliseconds 200
$wsh.SendKeys('{TAB}')
Start-Sleep -Milliseconds 300
$dateBox.SetFocus()
Start-Sleep -Milliseconds 200
$wsh.SendKeys('^a')
Start-Sleep -Milliseconds 100
$wsh.SendKeys('04/25/2026')
Start-Sleep -Milliseconds 200
$wsh.SendKeys('{TAB}')
Start-Sleep -Seconds 1
$vp1 = $instrumentText.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$vp2 = $dateBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
'Instrument=' + $vp1.Current.Value
'Date=' + $vp2.Current.Value
'DownloadEnabled=' + $downloadButton.Current.IsEnabled
