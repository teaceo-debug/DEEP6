Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$proc=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id)))))
for($i=0;$i -lt $wins.Count;$i++){
 $w=$wins.Item($i)
 Write-Output ('WINDOW '+$i+' name=['+$w.Current.Name+'] class=['+$w.Current.ClassName+'] handle='+$w.Current.NativeWindowHandle)
 $menus=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)))
 for($j=0;$j -lt $menus.Count;$j++){ $m=$menus.Item($j); if($m.Current.Name){ Write-Output ('  MENU '+$m.Current.Name) } }
}
