$p = 'C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_command.json'
if (Test-Path $p) {
  Get-Item $p | Select-Object FullName,Length,LastWriteTime | Format-List
  Get-Content $p -TotalCount 120
} else {
  'MISSING'
}
