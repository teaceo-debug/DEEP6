Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$proc=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$main=[System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
Write-Output ('MAIN title=' + $proc.MainWindowTitle + ' handle=' + $proc.MainWindowHandle)
Write-Output ('UIA main name=[' + $main.Current.Name + '] class=[' + $main.Current.ClassName + ']')
$menus=$main.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)))
for($i=0;$i -lt $menus.Count;$i++){ $m=$menus.Item($i); if($m.Current.Name){ Write-Output ('MENU '+$m.Current.Name) } }
