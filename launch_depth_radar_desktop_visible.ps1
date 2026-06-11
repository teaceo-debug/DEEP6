$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Tea\DEEP6'
$py = 'C:\Users\Tea\AppData\Local\Programs\Python\Python311\python.exe'
$logDir = 'C:\Users\Tea\DEEP6\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdout = Join-Path $logDir 'depth_radar_desktop.out.log'
$stderr = Join-Path $logDir 'depth_radar_desktop.err.log'
Start-Process -FilePath $py -WorkingDirectory 'C:\Users\Tea\DEEP6' -ArgumentList @('-m','depth_radar_desktop','--source','rithmic','--show-console') -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Start-Sleep -Seconds 2
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'depth_radar_desktop|launch.pyw' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 4
