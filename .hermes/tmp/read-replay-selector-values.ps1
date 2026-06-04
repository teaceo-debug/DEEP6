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
$sections = Find-ById $target 'SectionsList'
foreach($el in @($instrumentText,$dateBox,$sections)){
  if($el){
    $c = $el.Current
    Write-Output ('AutoId=' + $c.AutomationId + ' Class=' + $c.ClassName)
    try {
      $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
      Write-Output ('Value=' + $vp.Current.Value)
    } catch {
      Write-Output 'ValuePattern=NO'
    }
    try {
      $tp = $el.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
      Write-Output ('Text=' + $tp.DocumentRange.GetText(-1))
    } catch {
      Write-Output 'TextPattern=NO'
    }
  }
}
