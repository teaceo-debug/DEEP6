# nt8-context.ps1 - Full JSON snapshot of NT8 system state for Claude context
#
# Usage:
#   nt8-context.ps1 [-OutFile <path>] [-Pretty]
#
# Output: JSON object with NT8 process info, DLL freshness, HTTP API status,
#         deployed vs repo file sync state, and compile errors.
#
# Always prints to stdout. If -OutFile is specified, also saves to file.

param(
    [string]$OutFile = "",
    [switch]$Pretty
)

$ErrorActionPreference = "SilentlyContinue"

# ── Paths ─────────────────────────────────────────────────────────────────────

$NT8CustomDir = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"
$NT8DllPath   = "$NT8CustomDir\NinjaTrader.Custom.dll"
$RepoRoot     = "$PSScriptRoot\..\.." | Resolve-Path | Select-Object -ExpandProperty Path
$RepoNT8Dir   = "$RepoRoot\ninjatrader\Custom"
$BaseUrl      = "http://localhost:19206"

# ── NT8 Process ───────────────────────────────────────────────────────────────

$nt8Obj = @{
    running        = $false
    pid            = $null
    uptime_minutes = $null
    mem_mb         = $null
}

$nt8Proc = Get-Process "NinjaTrader" -ErrorAction SilentlyContinue
if ($nt8Proc -ne $null) {
    $uptimeMin = [math]::Round(((Get-Date) - $nt8Proc.StartTime).TotalMinutes, 1)
    $memMb     = [math]::Round($nt8Proc.WorkingSet64 / 1MB, 0)
    $nt8Obj = @{
        running        = $true
        pid            = $nt8Proc.Id
        uptime_minutes = $uptimeMin
        mem_mb         = $memMb
    }
}

# ── DLL Freshness ─────────────────────────────────────────────────────────────

$dllObj = @{
    exists      = $false
    mtime       = $null
    age_minutes = $null
    fresh       = $false
}

if (Test-Path $NT8DllPath) {
    $dllInfo    = Get-Item $NT8DllPath
    $dllMtime   = $dllInfo.LastWriteTimeUtc
    $dllAgeMin  = [math]::Round(((Get-Date).ToUniversalTime() - $dllMtime).TotalMinutes, 1)
    $dllObj = @{
        exists      = $true
        mtime       = $dllMtime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        age_minutes = $dllAgeMin
        fresh       = ($dllAgeMin -le 10)
    }
}

# ── Last Compile (install.xml) ─────────────────────────────────────────────────
# NT8 writes NinjaScript install history XML; look for the last compiled timestamp.

$lastCompileObj = @{
    install_xml_timestamp = $null
    matches_dll           = $false
}

$installXml = "$env:USERPROFILE\Documents\NinjaTrader 8\NinjaScript\NinjaScripts.xml"
if (-not (Test-Path $installXml)) {
    # Try alternate location
    $installXml = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\install.xml"
}

if (Test-Path $installXml) {
    [xml]$xmlDoc = Get-Content $installXml -ErrorAction SilentlyContinue
    if ($xmlDoc -ne $null) {
        # Attempt to read the most recent timestamp attribute
        $tsAttr = $null
        try {
            $tsAttr = $xmlDoc.DocumentElement.GetAttribute("lastCompile")
            if ([string]::IsNullOrEmpty($tsAttr)) {
                $tsAttr = $xmlDoc.DocumentElement.GetAttribute("timestamp")
            }
        } catch { }
        if ($tsAttr -ne $null -and $tsAttr -ne "") {
            $lastCompileObj.install_xml_timestamp = $tsAttr
            # Compare with DLL mtime (loose: within 2 minutes counts as match)
            if ($dllObj.mtime -ne $null) {
                try {
                    $xmlDt  = [datetime]::Parse($tsAttr)
                    $dllDt  = [datetime]::Parse($dllObj.mtime)
                    $diffMin = [math]::Abs(($xmlDt - $dllDt).TotalMinutes)
                    $lastCompileObj.matches_dll = ($diffMin -le 2)
                } catch { }
            }
        }
    }
}

# ── HTTP API ──────────────────────────────────────────────────────────────────

$httpObj = @{
    alive  = $false
    health = $null
    status = $null
}

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        $httpObj.alive  = $true
        $httpObj.health = ($resp.Content | ConvertFrom-Json)
    }
} catch { }

if ($httpObj.alive) {
    try {
        $resp2 = Invoke-WebRequest -Uri "$BaseUrl/status" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($resp2.StatusCode -eq 200) {
            $httpObj.status = ($resp2.Content | ConvertFrom-Json)
        }
    } catch { }
}

# ── File Sync ─────────────────────────────────────────────────────────────────
# Compare repo ninjatrader/Custom tree vs NT8CustomDir tree.

function Get-FileHash-Safe {
    param([string]$FilePath)
    try {
        $h = Get-FileHash -Path $FilePath -Algorithm MD5 -ErrorAction Stop
        return $h.Hash
    } catch {
        return $null
    }
}

# Map of relative path (from each root) → full path
$deployedMap = @{}
$repoMap     = @{}

if (Test-Path $NT8CustomDir) {
    Get-ChildItem -Path $NT8CustomDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".cs", ".xml") } |
        ForEach-Object {
            $rel = $_.FullName.Substring($NT8CustomDir.Length).TrimStart("\")
            $deployedMap[$rel] = $_.FullName
        }
}

if (Test-Path $RepoNT8Dir) {
    Get-ChildItem -Path $RepoNT8Dir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".cs", ".xml") } |
        ForEach-Object {
            $rel = $_.FullName.Substring($RepoNT8Dir.Length).TrimStart("\")
            $repoMap[$rel] = $_.FullName
        }
}

$deployedFiles = @()
foreach ($rel in $deployedMap.Keys | Sort-Object) {
    $fullPath    = $deployedMap[$rel]
    $itemInfo    = Get-Item $fullPath
    $repoRelKey  = $rel  # same relative structure
    $inRepo      = $repoMap.ContainsKey($repoRelKey)
    $syncStatus  = "deployed-only"

    if ($inRepo) {
        $hashDeployed = Get-FileHash-Safe $fullPath
        $hashRepo     = Get-FileHash-Safe $repoMap[$repoRelKey]
        if ($hashDeployed -ne $null -and $hashDeployed -eq $hashRepo) {
            $syncStatus = "in-sync"
        } else {
            $syncStatus = "drift"
        }
    }

    $deployedFiles += @{
        path        = $rel
        size_bytes  = $itemInfo.Length
        mtime       = $itemInfo.LastWriteTimeUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
        in_repo     = $inRepo
        sync        = $syncStatus
    }
}

$repoFiles = @()
foreach ($rel in $repoMap.Keys | Sort-Object) {
    $deployedRelKey = $rel
    $isDeployed     = $deployedMap.ContainsKey($deployedRelKey)
    $syncStatus     = "repo-only"

    if ($isDeployed) {
        $hashDeployed = Get-FileHash-Safe $deployedMap[$deployedRelKey]
        $hashRepo     = Get-FileHash-Safe $repoMap[$rel]
        if ($hashDeployed -ne $null -and $hashDeployed -eq $hashRepo) {
            $syncStatus = "in-sync"
        } else {
            $syncStatus = "drift"
        }
    }

    # Normalize to forward slashes for repo paths
    $repoRelPath = "ninjatrader/Custom/" + $rel.Replace("\", "/")

    $repoFiles += @{
        path     = $repoRelPath
        deployed = $isDeployed
        sync     = $syncStatus
    }
}

# ── Errors (UIAutomation) ──────────────────────────────────────────────────────

$errorsArr = @()

if ($nt8Obj.running) {
    try {
        Add-Type -AssemblyName UIAutomationClient  -ErrorAction Stop
        Add-Type -AssemblyName UIAutomationTypes   -ErrorAction Stop

        $root    = [System.Windows.Automation.AutomationElement]::RootElement
        $pidCond = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $nt8Proc.Id)
        $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)

        $nse = $null
        foreach ($w in $windows) {
            if ($w.Current.Name -like "*NinjaScript*") { $nse = $w; break }
        }

        if ($nse -ne $null) {
            $gridCond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::DataGrid)
            $grid = $nse.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $gridCond)

            if ($grid -ne $null) {
                $rows = $grid.FindAll([System.Windows.Automation.TreeScope]::Children,
                    [System.Windows.Automation.Condition]::TrueCondition)

                foreach ($row in $rows) {
                    $cells = $row.FindAll([System.Windows.Automation.TreeScope]::Children,
                        [System.Windows.Automation.Condition]::TrueCondition)
                    $vals = @()
                    foreach ($cell in $cells) {
                        try {
                            $vp = $cell.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                            $v  = $vp.Current.Value
                            if ($v) { $vals += $v }
                        } catch { }
                    }
                    if ($vals.Count -ge 4) {
                        $codeVal = $vals | Where-Object { $_ -match "^CS\d{4}$" } | Select-Object -First 1
                        if ($codeVal -ne $null) {
                            $errFile = if ($vals.Count -gt 1) { $vals[1] } else { "" }
                            $errMsg  = if ($vals.Count -gt 2) { $vals[2] } else { "" }
                            $errLine = if ($vals.Count -gt 4) { [int]$vals[4] } else { 0 }
                            $errCol  = if ($vals.Count -gt 5) { [int]$vals[5] } else { 0 }
                            $errorsArr += @{
                                file    = $errFile
                                message = $errMsg
                                code    = $codeVal
                                line    = $errLine
                                col     = $errCol
                            }
                        }
                    }
                }
            }
        }
    } catch { }
}

# ── Assemble Output ────────────────────────────────────────────────────────────

$ctx = @{
    timestamp     = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    nt8           = $nt8Obj
    dll           = $dllObj
    last_compile  = $lastCompileObj
    http_api      = $httpObj
    deployed_files = $deployedFiles
    repo_files    = $repoFiles
    errors        = $errorsArr
}

$depth = 5
if ($Pretty) {
    $json = $ctx | ConvertTo-Json -Depth $depth
} else {
    $json = $ctx | ConvertTo-Json -Depth $depth -Compress
}

# Always print to stdout
Write-Output $json

# Optionally save to file
if ($OutFile -ne "") {
    $json | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "(Context saved to: $OutFile)" -ForegroundColor DarkGray
}
