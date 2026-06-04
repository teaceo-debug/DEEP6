Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$main = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$ok = $main.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.AndCondition((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'NTMessageBoxOKButton')),(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)))))
if($ok){ $ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); 'OK_CLICKED' } else { 'OK_NOT_FOUND' }
