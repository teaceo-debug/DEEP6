[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFile,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

try {
    $sourceResolved = (Resolve-Path -LiteralPath $SourceFile -ErrorAction Stop).Path
    $sourceName = Split-Path -Path $sourceResolved -Leaf

    if ($sourceName -ieq 'FootprintBar.cs') {
        Fail "Refusing to deploy excluded file: $sourceName"
    }

    $content = Get-Content -LiteralPath $sourceResolved -Raw

    $targetSubdir = 'Indicators'
    if ($content -match 'namespace\s+NinjaTrader\.NinjaScript\.Strategies\b') {
        $targetSubdir = 'Strategies'
    }
    elseif ($content -match 'namespace\s+NinjaTrader\.NinjaScript\.AddOns\b') {
        $targetSubdir = 'AddOns'
    }

    $deep6Suffix = ''
    if ($content -match 'namespace\s+NinjaTrader\.NinjaScript\.[A-Za-z0-9_]+\.DEEP6\b') {
        $deep6Suffix = '\DEEP6'
    }

    $nt8Custom = Join-Path $env:USERPROFILE 'Documents\NinjaTrader 8\bin\Custom'
    $targetDir = Join-Path $nt8Custom ($targetSubdir + $deep6Suffix)
    $targetFile = Join-Path $targetDir $sourceName

    $sourceHash = (Get-FileHash -LiteralPath $sourceResolved -Algorithm SHA256).Hash
    $alreadyDeployed = $false
    $hashMatch = $true

    if (Test-Path -LiteralPath $targetFile) {
        $deployedHash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash
        if ($sourceHash -eq $deployedHash) {
            $alreadyDeployed = $true
        }
    }

    if (-not $DryRun -and -not $alreadyDeployed) {
        if (-not (Test-Path -LiteralPath $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }

        $tmpFile = "$targetFile.tmp"
        if (Test-Path -LiteralPath $tmpFile) {
            Remove-Item -LiteralPath $tmpFile -Force
        }

        Copy-Item -LiteralPath $sourceResolved -Destination $tmpFile -Force
        Move-Item -LiteralPath $tmpFile -Destination $targetFile -Force

        $verifyHash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash
        $hashMatch = ($sourceHash -eq $verifyHash)

        if (-not $hashMatch) {
            Fail "Hash verification failed after deploy: $targetFile"
        }
    }

    $result = [ordered]@{
        source            = $sourceResolved
        target            = $targetFile
        hash_match        = if ($DryRun -or $alreadyDeployed) { $true } else { $hashMatch }
        already_deployed  = $alreadyDeployed
        target_subdir     = $targetSubdir
    }

    Write-Output ($result | ConvertTo-Json -Compress)
    exit 0
}
catch {
    Fail $_.Exception.Message
}
