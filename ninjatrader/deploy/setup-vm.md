# DEEP6 Windows VM Setup Guide

## 1. Create the VM

### Recommended: Azure Windows VM
```
Region:        East US 2 (closest to CME Aurora IL datacenter)
Size:          B2s (2 vCPU, 4 GB RAM) — $40/mo
               B4ms if running Strategy Analyzer backtests — $70/mo
OS:            Windows 11 Pro (includes RDP)
Disk:          128 GB Premium SSD
Networking:    Allow RDP (3389), outbound HTTPS (443)
```

### Alternative: AWS
```
Region:        us-east-2 (Ohio) or us-east-1 (Virginia)
Instance:      t3.medium (2 vCPU, 4 GB) — ~$50/mo with Windows
```

### Budget: Vultr/Hetzner
```
Vultr Cloud Compute: 2 vCPU / 4 GB — $24/mo + $16/mo Windows = ~$40/mo
Hetzner Cloud: CX22 — $12/mo + Windows license (~$15/mo)
```

## 2. Initial VM Setup

RDP into the VM, then run in PowerShell (as Admin):

```powershell
# Install Git
winget install Git.Git

# Install NinjaTrader 8
# Download from https://ninjatrader.com/Download
# Run installer, complete setup wizard
# Login with your NT8 license key

# Connect Rithmic
# In NT8: Tools > Account Connection > Add > Rithmic
# Server: use your Apex or Lucid credentials
# Test connection

# Clone DEEP6
cd $env:USERPROFILE
git clone https://github.com/teaceo-debug/DEEP6.git

# First deploy
cd DEEP6\ninjatrader\deploy
.\auto-deploy.ps1 -Force

# Open NT8, press F5 to compile
```

## 3. Automate Deployments

### Option A: Scheduled Task (simplest)
Poll GitHub every 5 minutes:

```powershell
# Create scheduled task (run in Admin PowerShell)
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File $env:USERPROFILE\DEEP6\ninjatrader\deploy\auto-deploy.ps1"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "DEEP6-AutoDeploy" -Action $action -Trigger $trigger `
    -Description "Auto-deploy DEEP6 from GitHub every 5 min" -RunLevel Highest
```

### Option B: GitHub Actions Self-Hosted Runner (best)
The VM runs a GitHub Actions runner. On push to main, it auto-deploys:

```powershell
# Install GitHub Actions runner on the VM
mkdir C:\actions-runner && cd C:\actions-runner
# Download from: https://github.com/teaceo-debug/DEEP6/settings/actions/runners/new
# Follow the configure steps shown on that page
```

Then add `.github/workflows/deploy-nt8.yml` to the repo:

```yaml
name: Deploy to NT8 VM
on:
  push:
    branches: [main]
    paths: ['ninjatrader/Custom/**']

jobs:
  deploy:
    runs-on: self-hosted  # your Windows VM
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to NT8
        run: .\ninjatrader\deploy\auto-deploy.ps1 -Force
```

### Option C: Webhook + listener (advanced)
GitHub webhook → lightweight HTTP listener on VM → triggers deploy.
More complex, faster than polling, but scheduled task is good enough.

## 4. Keep NT8 Running 24/7

NT8 needs an active desktop session (it's a WPF app). Two approaches:

### Auto-login + auto-start
```powershell
# Enable auto-login (run as Admin)
$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty $RegPath "AutoAdminLogon" -Value "1"
Set-ItemProperty $RegPath "DefaultUsername" -Value "your-username"
Set-ItemProperty $RegPath "DefaultPassword" -Value "your-password"

# Add NT8 to startup
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\NinjaTrader.lnk")
$Shortcut.TargetPath = "C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe"
$Shortcut.Save()
```

### Keep RDP session alive
Azure/AWS VMs disconnect RDP after idle timeout. To prevent:
```
# Group Policy: Computer Config > Admin Templates > Windows Components > Remote Desktop Services
# > Session Time Limits > Set time limit for disconnected sessions = Never
```

Or use a keep-alive script:
```powershell
# Prevent screen lock (moves mouse 1px every 4 min)
while ($true) {
    $Pos = [System.Windows.Forms.Cursor]::Position
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(($Pos.X + 1), $Pos.Y)
    Start-Sleep -Seconds 1
    [System.Windows.Forms.Cursor]::Position = $Pos
    Start-Sleep -Seconds 240
}
```

## 5. Monitoring

### Daily health check script
```powershell
# Add to Task Scheduler — runs at 9:00 AM ET daily
$nt8Process = Get-Process NinjaTrader -ErrorAction SilentlyContinue
if (!$nt8Process) {
    Write-Host "NT8 NOT RUNNING — restarting..."
    Start-Process "C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe"
    # TODO: send alert (email/Slack/Discord webhook)
}

# Check last deploy
$lastDeploy = Get-Content "$env:USERPROFILE\DEEP6\ninjatrader\deploy\logs\deploy-log.jsonl" | 
    Select-Object -Last 1 | ConvertFrom-Json
Write-Host "Last deploy: $($lastDeploy.timestamp) | Commit: $($lastDeploy.commit)"
```

## 6. The Full Workflow

```
You (Mac, Claude Code)
  ↓ code changes
  ↓ git push origin main
  
GitHub (teaceo-debug/DEEP6)
  ↓ webhook or 5-min poll
  
Windows VM (Azure East US 2)
  ↓ auto-deploy.ps1
  ↓ git pull → xcopy → compile
  
NinjaTrader 8 (running 24/7)
  ↓ auto-recompiles on file change
  ↓ DEEP6Strategy restarts with new code
  ↓ Rithmic feed → signals → paper/live orders
  
You (monitoring)
  ← Output window via RDP
  ← Daily health check alerts
  ← .ndjson capture files pulled back to Mac for analysis
```

## Cost Summary

| Item | Monthly |
|------|---------|
| Azure B2s VM | $40 |
| NT8 license | $0 (lifetime, already owned) |
| Rithmic data | $0 (included with Apex/Lucid) |
| Total | **~$40/mo** |

## Why Chicago-Region VM?

Your Rithmic data feed connects to CME's matching engine in Aurora, IL. A VM in Azure East US 2 (Virginia) or AWS us-east-2 (Ohio) gets ~5-15ms to Aurora. Your home Mac gets 30-80ms depending on ISP. For 1-minute bar strategies the latency difference doesn't matter much, but for the capture harness (recording tick-by-tick) and eventual sub-bar entry optimization, lower latency = cleaner data.
