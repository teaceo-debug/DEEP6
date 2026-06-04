Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8Conn {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@
$proc = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$main = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
[NT8Conn]::ShowWindow($proc.MainWindowHandle,9)|Out-Null
Start-Sleep -Milliseconds 200
[NT8Conn]::SetForegroundWindow($proc.MainWindowHandle)|Out-Null
Start-Sleep -Milliseconds 300
$cc = $main
$cond = New-Object System.Windows.Automation.AndCondition(
 (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
 (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Connections'))
)
$conn = $cc.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
$conn.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Start-Sleep -Milliseconds 400
$pcond = New-Object System.Windows.Automation.AndCondition(
 (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
 (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Playback'))
)
$play = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$pcond)
$play.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
'PLAYBACK_TOGGLED'
