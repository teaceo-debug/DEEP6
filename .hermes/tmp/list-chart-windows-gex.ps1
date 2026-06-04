Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p = Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
$idx=0
foreach($w in $wins){
  $indBtn = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
  if($indBtn){
    $tab=''; try{$tab = ($w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowInstrumentSelectorMenuItem')))).Current.Name}catch{}
    $gex = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'GEXCommand')))
    Write-Output ("CHART[$idx] instrument=[" + $tab + "] hasGEXName=" + [bool]$gex + " handle=" + $w.Current.NativeWindowHandle)
    $idx++
  }
}
