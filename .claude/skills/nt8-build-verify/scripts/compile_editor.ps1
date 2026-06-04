[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 60,
    [switch]$AutoReload
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..\..")).Path
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

function Invoke-PowerShellScriptCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $false)]
        [string[]]$Arguments = @()
    )

    $psArgs = @(
        "-NoProfile"
        "-ExecutionPolicy"
        "Bypass"
        "-File"
        $ScriptPath
    ) + @($Arguments)

    $rawOutput = & powershell.exe @psArgs 2>&1
    $exitCode = $LASTEXITCODE

    $textOutput = @($rawOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine

    [PSCustomObject]@{
        Output   = $textOutput
        ExitCode = $exitCode
    }
}

function Convert-JsonSafely {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    try {
        return $Text | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

# Step 1: Modal detection — abort if BLOCKED
$modalScript = Join-Path $scriptDir "modal_detect.ps1"
$modalRun = Invoke-PowerShellScriptCapture -ScriptPath $modalScript -Arguments @("-TimeoutSeconds", "5")
$modalResult = Convert-JsonSafely -Text $modalRun.Output

if ($null -eq $modalResult -or $modalRun.ExitCode -ne 0 -or $modalResult.blocked) {
    Write-Output "[COMPILE-RESULT] FAILED modal_blocked"
    $result = @{
        success = $false
        error_count = 0
        errors = @()
        dll_reloaded = $false
        elapsed_ms = 0
        blocked_by_modal = $true
    }
    Write-Output ($result | ConvertTo-Json -Depth 5 -Compress)
    exit 2
}

# Step 2: Record DLL timestamp before compile
$dllPath = Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll"
$dllBefore = if (Test-Path $dllPath) { (Get-Item $dllPath).LastWriteTime } else { $null }

# Step 3: Trigger compile via nt8-compile.ps1
$compileScript = Join-Path $repoRoot "ninjatrader\scripts\nt8-compile.ps1"
$compileArgs = @("-TimeoutSeconds", "$TimeoutSeconds")
if ($AutoReload) { $compileArgs += "-AutoReload" }
$compileRun = Invoke-PowerShellScriptCapture -ScriptPath $compileScript -Arguments $compileArgs

# Step 4: Check DLL timestamp after compile
$dllAfter = if (Test-Path $dllPath) { (Get-Item $dllPath).LastWriteTime } else { $null }
$dllReloaded = ($null -ne $dllBefore -and $null -ne $dllAfter -and $dllAfter -gt $dllBefore)

# Step 5: Parse compile result from sentinel
$compileSuccess = $false
$compileSentinel = $null
if (-not [string]::IsNullOrWhiteSpace($compileRun.Output)) {
    foreach ($line in ($compileRun.Output -split "`r?`n")) {
        if ($line -match '\[COMPILE-RESULT\]\s+SUCCESS') {
            $compileSuccess = $true
            $compileSentinel = $line.Trim()
            break
        }
        if ($line -match '\[COMPILE-RESULT\]\s+FAILED') {
            $compileSentinel = $line.Trim()
        }
    }
}

# BUG FIX: Only override success if exit code is 0 AND no errors were found
# Previously this would mark success=true even when compile errors exist
if (-not $compileSuccess -and $compileRun.ExitCode -eq 0) {
    # Don't override yet — wait until we check error count below
    $exitCodeWasZero = $true
} else {
    $exitCodeWasZero = $false
}

# Step 6: Collect errors via nt8-errors-full.ps1
$errors = @()
$errorCount = 0
$errorsScript = Join-Path $repoRoot "ninjatrader\scripts\nt8-errors-full.ps1"
if (Test-Path $errorsScript) {
    try {
        $errorsRun = Invoke-PowerShellScriptCapture -ScriptPath $errorsScript -Arguments @()
        $errorsResult = Convert-JsonSafely -Text $errorsRun.Output

        if ($null -ne $errorsResult) {
            if ($errorsResult -is [System.Array]) {
                $errors = @($errorsResult)
            }
            elseif ($errorsResult.PSObject.Properties.Name -contains "error") {
                $errors = @()
            }
            else {
                $errors = @($errorsResult)
            }
        }

        $errorCount = @($errors).Count
    }
    catch {
        $errors = @()
        $errorCount = 0
    }
}

# Step 7: Emit sentinel
if ($compileSuccess) {
    if (-not $compileSentinel) {
        $compileSentinel = "[COMPILE-RESULT] SUCCESS $(Get-Date -Format 'o')"
    }
    Write-Output $compileSentinel
} else {
    Write-Output "[COMPILE-RESULT] FAILED $errorCount"
}

# Step 8: Return JSON
$stopwatch.Stop()
# BUG FIX: success depends on BOTH compile process AND zero errors
if (-not $compileSuccess -and $exitCodeWasZero -and $errorCount -eq 0) {
    $compileSuccess = $true
}
# If errors exist, success must be false regardless of exit code
if ($errorCount -gt 0) {
    $compileSuccess = $false
}

$result = @{
    success = $compileSuccess
    error_count = $errorCount
    errors = $errors
    dll_reloaded = $dllReloaded
    elapsed_ms = $stopwatch.ElapsedMilliseconds
    blocked_by_modal = $false
    path_used = "editor_uia"
}
Write-Output ($result | ConvertTo-Json -Depth 5 -Compress)
exit $(if ($compileSuccess) { 0 } else { 1 })
