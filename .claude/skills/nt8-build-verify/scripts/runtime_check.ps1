[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ClassName,

    [int]$WindowSeconds = 10,

    [string]$LogFile
)

$ErrorActionPreference = "Stop"

$logDir = Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\log"

if (-not $LogFile) {
    $today = Get-Date -Format "yyyyMMdd"
    if (Test-Path $logDir) {
        $logFiles = Get-ChildItem $logDir -Filter "log.$today.*.txt" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
        if ($logFiles.Count -gt 0) {
            $LogFile = $logFiles[0].FullName
        }
    }
}

if (-not $LogFile -or -not (Test-Path -LiteralPath $LogFile)) {
    $result = @{
        runtime_errors_found = 0
        errors               = @()
        check_window_seconds = $WindowSeconds
        log_status           = "log_not_found"
    }
    Write-Output ($result | ConvertTo-Json -Depth 5 -Compress)
    exit 0
}

$cutoff = (Get-Date).AddSeconds(-$WindowSeconds)
$errors = @()
$lines = Get-Content -LiteralPath $LogFile -Tail 500 -ErrorAction SilentlyContinue

function Get-LogTimestamp {
    param([string]$Line)

    if ($Line -match '^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)') {
        $timestampText = "$($Matches[1]) $($Matches[2])"
        foreach ($format in @('yyyy-MM-dd HH:mm:ss.fff', 'yyyy-MM-dd HH:mm:ss')) {
            try {
                return [datetime]::ParseExact($timestampText, $format, $null)
            } catch {
            }
        }
    }

    return $null
}

$currentException = $null

foreach ($line in $lines) {
    $lineTime = Get-LogTimestamp -Line $line
    $isWithinWindow = $true

    if ($lineTime) {
        $isWithinWindow = $lineTime -ge $cutoff
    }

    if ($currentException -and $lineTime -and $line -notmatch '^\s') {
        $errors += [pscustomobject]$currentException
        $currentException = $null
    }

    if (-not $currentException -and $isWithinWindow) {
        if ($line -match [regex]::Escape($ClassName) -and ($line -match 'Exception|Error|OnBarUpdate|OnStateChange|NullReference|IndexOutOfRange')) {
            $currentException = [ordered]@{
                timestamp  = $lineTime
                exception  = $line.Trim()
                stacktrace = ""
            }
            continue
        }
    }

    if ($currentException) {
        if ($line -match '^\s+at\s' -or $line -match '^\s+---' -or $line -match '^\s+in\s') {
            $currentException.stacktrace += $line.TrimEnd() + "`n"
            continue
        }

        if ($line -notmatch '^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}') {
            $currentException.stacktrace += $line.TrimEnd() + "`n"
            continue
        }
    }
}

if ($currentException) {
    $errors += [pscustomobject]$currentException
}

$result = @{
    runtime_errors_found = $errors.Count
    errors               = $errors
    check_window_seconds = $WindowSeconds
    log_file             = $LogFile
}

Write-Output ($result | ConvertTo-Json -Depth 5 -Compress)
exit 0
