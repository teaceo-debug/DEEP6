$paths = @(
  'C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6Atlas.cs',
  'C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6AtlasDiag.cs',
  'C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\DEEP6AtlasStrategy.cs'
)
foreach($p in $paths){ if(Test-Path $p){ Remove-Item $p -Force; Write-Output ('REMOVED ' + $p) } else { Write-Output ('MISSING ' + $p) } }
