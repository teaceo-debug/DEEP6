Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
  [System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id))
)
for($i=0;$i -lt $wins.Count;$i++){
  $w=$wins.Item($i)
  $name=''; $class=''; $handle='';
  try{$name=$w.Current.Name}catch{}
  try{$class=$w.Current.ClassName}catch{}
  try{$handle=$w.Current.NativeWindowHandle}catch{}
  Write-Output ("WIN[$i] name=[$name] class=[$class] handle=$handle")
}
