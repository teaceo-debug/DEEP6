$ErrorActionPreference = 'Stop'
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$dst = "C:\Users\Tea\Documents\NinjaTrader 8\backups\replay-db-fix-$ts"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Get-Process NinjaTrader -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Copy-Item 'C:\Users\Tea\Documents\NinjaTrader 8\db\NinjaTrader.sqlite' -Destination (Join-Path $dst 'NinjaTrader.sqlite') -Force
if (Test-Path 'C:\Users\Tea\Documents\NinjaTrader 8\db\NinjaTrader.sqlite-wal') { Copy-Item 'C:\Users\Tea\Documents\NinjaTrader 8\db\NinjaTrader.sqlite-wal' -Destination (Join-Path $dst 'NinjaTrader.sqlite-wal') -Force }
if (Test-Path 'C:\Users\Tea\Documents\NinjaTrader 8\db\NinjaTrader.sqlite-shm') { Copy-Item 'C:\Users\Tea\Documents\NinjaTrader 8\db\NinjaTrader.sqlite-shm' -Destination (Join-Path $dst 'NinjaTrader.sqlite-shm') -Force }
if (Test-Path 'C:\Users\Tea\Documents\NinjaTrader 8\Config.xml') { Copy-Item 'C:\Users\Tea\Documents\NinjaTrader 8\Config.xml' -Destination (Join-Path $dst 'Config.xml') -Force }
Write-Output $dst
