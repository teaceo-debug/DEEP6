Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p=Get-Process NinjaTrader -ErrorAction Stop | Select-Object -First 1
$wins=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$p.Id)))
$idx=0
foreach($w in $wins){
 $hit=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'ChartWindowIndicatorsButton')))
 if($hit){
   Write-Output ('CHART['+$idx+'] handle='+$w.Current.NativeWindowHandle)
   $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
   $matches=0
   foreach($el in $all){
     $n=''; try{$n=$el.Current.Name}catch{}
     if($n -and ($n -match 'GEXCommand|GAMMA FLIP|CALL WALL|PUT WALL|VANNA|DEX PEAK|CHARM DRIFT|Massive timestamp|0DTE EXPIRY DAY')){
       Write-Output ('  ' + $el.Current.ControlType.ProgrammaticName + ' | ' + $n + ' | ' + $el.Current.AutomationId)
       $matches++
     }
   }
   if($matches -eq 0){ Write-Output '  NO_GEX_TEXT_MATCHES' }
   $idx++
 }
}
