$ErrorActionPreference = 'Stop'
$root = 'C:\Users\Tea\Documents\NinjaTrader 8\db'
$orig = Join-Path $root 'NinjaTrader.sqlite'
$rebuilt = Join-Path $root 'NinjaTrader.rebuilt.sqlite'
$corrupt = Join-Path $root 'NinjaTrader.pre-rebuild-corrupt.sqlite'
if (!(Test-Path $rebuilt)) { throw 'Rebuilt database not found.' }
if (Test-Path $corrupt) { Remove-Item $corrupt -Force }
Move-Item $orig $corrupt -Force
Move-Item $rebuilt $orig -Force
Write-Output 'SWAPPED'
Write-Output $orig
Write-Output $corrupt
