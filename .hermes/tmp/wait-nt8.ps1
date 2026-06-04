1..30 | ForEach-Object {
  $p = Get-Process NinjaTrader -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p) {
    Write-Output ($p.MainWindowTitle + '|' + $p.MainWindowHandle)
    exit 0
  }
  Start-Sleep -Seconds 1
}
exit 1
