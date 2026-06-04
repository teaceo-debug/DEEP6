Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id))
)
for($i=0; $i -lt $wins.Count; $i++) {
  $w = $wins.Item($i)
  $name = ''
  try { $name = $w.Current.Name } catch {}
  $id = ''
  try { $id = $w.Current.AutomationId } catch {}
  $rect = $w.Current.BoundingRectangle
  $hasChartBtn = $false
  try {
    $hit = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
      (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'ChartWindowIndicatorsButton')))
    if($hit){ $hasChartBtn = $true }
  } catch {}
  Write-Output ("IDX={0} NAME=[{1}] AUTOID=[{2}] X={3} Y={4} W={5} H={6} CHART={7}" -f $i,$name,$id,[int]$rect.X,[int]$rect.Y,[int]$rect.Width,[int]$rect.Height,$hasChartBtn)
}
