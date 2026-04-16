# DEEP6 Auto-Deploy Script for Windows VM
# Runs as a scheduled task or GitHub Actions self-hosted runner
# Pulls latest code from GitHub → copies to NT8 Custom/ → triggers recompile

param(
    [string]$RepoDir = "$env:USERPROFILE\DEEP6",
    [string]$NT8Custom = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom",
    [string]$Branch = "main",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "============================================"
Write-Host " DEEP6 Auto-Deploy"
Write-Host " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "============================================"

# Step 1: Pull latest from GitHub
Write-Host "`n[1/5] Pulling latest from GitHub..."
if (!(Test-Path $RepoDir)) {
    git clone https://github.com/teaceo-debug/DEEP6.git $RepoDir
} else {
    Push-Location $RepoDir
    $before = git rev-parse HEAD
    git fetch origin $Branch
    git reset --hard "origin/$Branch"
    $after = git rev-parse HEAD
    Pop-Location

    if ($before -eq $after -and !$Force) {
        Write-Host "  No changes detected. Use -Force to deploy anyway."
        exit 0
    }
    Write-Host "  Updated: $($before.Substring(0,7)) -> $($after.Substring(0,7))"
}

# Step 2: Copy to NT8 Custom directories
Write-Host "`n[2/5] Copying to NinjaTrader Custom/..."
$source = "$RepoDir\ninjatrader\Custom"

# AddOns
$dest = "$NT8Custom\AddOns\DEEP6"
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Copy-Item "$source\AddOns\DEEP6" $dest -Recurse -Force
Write-Host "  AddOns: $(Get-ChildItem $dest -Recurse -Filter *.cs | Measure-Object | Select-Object -Expand Count) files"

# Indicators
$dest = "$NT8Custom\Indicators\DEEP6"
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Copy-Item "$source\Indicators\DEEP6" $dest -Recurse -Force
Write-Host "  Indicators: $(Get-ChildItem $dest -Recurse -Filter *.cs | Measure-Object | Select-Object -Expand Count) files"

# Strategies
$dest = "$NT8Custom\Strategies\DEEP6"
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Copy-Item "$source\Strategies\DEEP6" $dest -Recurse -Force
Write-Host "  Strategies: $(Get-ChildItem $dest -Recurse -Filter *.cs | Measure-Object | Select-Object -Expand Count) files"

# Step 3: Trigger NT8 recompile
Write-Host "`n[3/5] Triggering NinjaScript recompile..."
# NT8 auto-detects file changes in Custom/ and recompiles
# But we can also trigger via the NinjaScript compiler directly:
$compiler = "C:\Program Files\NinjaTrader 8\bin\NinjaScript.exe"
if (Test-Path $compiler) {
    & $compiler /compile 2>&1 | Tee-Object -Variable compileOutput
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  COMPILE FAILED!" -ForegroundColor Red
        Write-Host $compileOutput
        # Send alert (configure your preferred method)
        exit 1
    }
    Write-Host "  Compile successful." -ForegroundColor Green
} else {
    Write-Host "  NinjaScript compiler not found at expected path."
    Write-Host "  NT8 will auto-recompile when it detects file changes."
    Write-Host "  Make sure NT8 is running with a chart open."
}

# Step 4: Verify deployment
Write-Host "`n[4/5] Verifying deployment..."
$addons = Get-ChildItem "$NT8Custom\AddOns\DEEP6" -Recurse -Filter *.cs | Measure-Object | Select-Object -Expand Count
$indicators = Get-ChildItem "$NT8Custom\Indicators\DEEP6" -Recurse -Filter *.cs | Measure-Object | Select-Object -Expand Count
$strategies = Get-ChildItem "$NT8Custom\Strategies\DEEP6" -Recurse -Filter *.cs | Measure-Object | Select-Object -Expand Count
Write-Host "  AddOns: $addons files"
Write-Host "  Indicators: $indicators files"
Write-Host "  Strategies: $strategies files"
Write-Host "  Total: $($addons + $indicators + $strategies) .cs files"

# Step 5: Log deployment
Write-Host "`n[5/5] Logging deployment..."
$logDir = "$RepoDir\ninjatrader\deploy\logs"
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logEntry = @{
    timestamp = Get-Date -Format "o"
    commit = (git -C $RepoDir rev-parse --short HEAD)
    files = $addons + $indicators + $strategies
    status = "SUCCESS"
} | ConvertTo-Json
$logEntry | Out-File -Append "$logDir\deploy-log.jsonl"
Write-Host "  Logged to deploy-log.jsonl"

Write-Host "`n============================================"
Write-Host " DEEP6 deployed successfully!"
Write-Host " Commit: $(git -C $RepoDir rev-parse --short HEAD)"
Write-Host "============================================"
