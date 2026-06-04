[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 60,
    [ValidateSet("devaddon","ninjascript_exe","msbuild","")]
    [string]$PreferredPath = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

$customRoot = Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\bin\Custom"
$ninjaScriptExe = "C:\Program Files\NinjaTrader 8\bin\NinjaScript.exe"
$defaultCsproj = Join-Path $customRoot "NinjaTrader.Custom.csproj"
$defaultDll = Join-Path $customRoot "NinjaTrader.Custom.dll"
$devAddonBaseUrl = "http://localhost:19206"

function New-Result {
    param(
        [string]$PathUsed = "",
        [bool]$Success = $false,
        [int]$ErrorCount = 0,
        [object[]]$Errors = @(),
        [string]$FailureKind = "compile"
    )

    return [ordered]@{
        path_used = $PathUsed
        success = $Success
        error_count = $ErrorCount
        errors = @($Errors)
        failure_kind = $FailureKind
    }
}

function Complete-And-Exit {
    param(
        [hashtable]$Result,
        [int]$ExitCode
    )

    $stopwatch.Stop()
    $timestamp = Get-Date -Format 'o'
    if ($Result.success) {
        Write-Output "[COMPILE-RESULT] SUCCESS $timestamp"
    }
    else {
        Write-Output "[COMPILE-RESULT] FAILED $($Result.error_count)"
    }

    $jsonResult = [ordered]@{
        path_used = $Result.path_used
        success = $Result.success
        error_count = $Result.error_count
        errors = @($Result.errors)
        elapsed_ms = $stopwatch.ElapsedMilliseconds
    }
    Write-Output ($jsonResult | ConvertTo-Json -Depth 6 -Compress)
    exit $ExitCode
}

function Get-AvailablePaths {
    $paths = New-Object System.Collections.Generic.List[string]

    try {
        $null = Invoke-RestMethod "$devAddonBaseUrl/health" -TimeoutSec 2
        $paths.Add("devaddon")
    }
    catch { }

    if (Test-Path -LiteralPath $ninjaScriptExe) {
        $paths.Add("ninjascript_exe")
    }

    $msbuildCmd = Get-Command msbuild -ErrorAction SilentlyContinue
    $csprojCandidates = @(
        $defaultCsproj,
        (Join-Path $customRoot "DEEP6.csproj")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    if ($msbuildCmd -and $csprojCandidates.Count -gt 0) {
        $paths.Add("msbuild")
    }

    return @($paths)
}

function Get-CsErrorsFromLines {
    param([object[]]$Lines)

    $matches = New-Object System.Collections.Generic.List[string]
    foreach ($line in @($Lines)) {
        if ($null -eq $line) { continue }
        $text = [string]$line
        if ($text -match 'error\s+CS\d+:') {
            $matches.Add($text.Trim())
        }
    }
    return @($matches)
}

function Invoke-DevAddonCompile {
    try {
        $null = Invoke-RestMethod "$devAddonBaseUrl/health" -TimeoutSec 2
    }
    catch {
        return @{ infrastructure_failure = $true; errors = @("DEEP6DevAddon health check failed: $($_.Exception.Message)") }
    }

    try {
        $response = Invoke-RestMethod "$devAddonBaseUrl/compile" -Method POST -TimeoutSec $TimeoutSeconds
    }
    catch {
        return @{ infrastructure_failure = $true; errors = @("DEEP6DevAddon compile request failed: $($_.Exception.Message)") }
    }

    # Check 'triggered' FIRST — a not-triggered response has no real errors.
    # PS 5.1: @($response.errors) when .errors is missing produces @($null) with Count=1.
    if ($response.PSObject.Properties.Name -contains 'triggered' -and -not [bool]$response.triggered) {
        $message = if ($response.error) { [string]$response.error } elseif ($response.reason) { [string]$response.reason } else { 'DEEP6DevAddon compile was not triggered.' }
        return @{ infrastructure_failure = $true; errors = @($message) }
    }

    $responseErrors = @()
    if ($response.PSObject.Properties.Name -contains 'errors' -and $null -ne $response.errors) {
        $responseErrors = @($response.errors | Where-Object { $null -ne $_ })
    }

    $successFlag = $null
    foreach ($name in @('success','ok','compiled')) {
        if ($response.PSObject.Properties.Name -contains $name) {
            $successFlag = [bool]$response.$name
            break
        }
    }

    if ($responseErrors.Count -gt 0) {
        return (New-Result -PathUsed 'devaddon' -Success $false -ErrorCount $responseErrors.Count -Errors $responseErrors -FailureKind 'compile')
    }

    if ($null -ne $successFlag -and -not $successFlag) {
        $message = if ($response.error) { [string]$response.error } elseif ($response.reason) { [string]$response.reason } else { 'DEEP6DevAddon reported compile failure without errors array.' }
        return (New-Result -PathUsed 'devaddon' -Success $false -ErrorCount 1 -Errors @($message) -FailureKind 'compile')
    }

    return (New-Result -PathUsed 'devaddon' -Success $true -ErrorCount 0 -Errors @())
}

function Invoke-NinjaScriptExeCompile {
    if (-not (Test-Path -LiteralPath $ninjaScriptExe)) {
        return @{ infrastructure_failure = $true; errors = @("NinjaScript.exe not found at $ninjaScriptExe") }
    }

    try {
        $output = & $ninjaScriptExe /compile 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        return @{ infrastructure_failure = $true; errors = @("NinjaScript.exe invocation failed: $($_.Exception.Message)") }
    }

    $errors = Get-CsErrorsFromLines -Lines @($output)
    if ($errors.Count -gt 0) {
        return (New-Result -PathUsed 'ninjascript_exe' -Success $false -ErrorCount $errors.Count -Errors $errors -FailureKind 'compile')
    }

    if ($exitCode -ne 0) {
        $infraErrors = @($output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
        if ($infraErrors.Count -eq 0) {
            $infraErrors = @("NinjaScript.exe exited with code $exitCode without Roslyn compile errors.")
        }
        return @{ infrastructure_failure = $true; errors = $infraErrors }
    }

    return (New-Result -PathUsed 'ninjascript_exe' -Success $true -ErrorCount 0 -Errors @())
}

function Invoke-MsBuildCompile {
    $msbuildCmd = Get-Command msbuild -ErrorAction SilentlyContinue
    if (-not $msbuildCmd) {
        return @{ infrastructure_failure = $true; errors = @('msbuild command not found in PATH.') }
    }

    $csprojCandidates = @(
        $defaultCsproj,
        (Join-Path $customRoot 'DEEP6.csproj')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    if ($csprojCandidates.Count -eq 0) {
        return @{ infrastructure_failure = $true; errors = @('No NT8-compatible csproj found for MSBuild fallback.') }
    }

    $csproj = $csprojCandidates[0]
    try {
        $output = & $msbuildCmd.Source $csproj /t:Build /p:Configuration=Release 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        return @{ infrastructure_failure = $true; errors = @("MSBuild invocation failed: $($_.Exception.Message)") }
    }

    $errors = Get-CsErrorsFromLines -Lines @($output)
    if ($errors.Count -gt 0) {
        return (New-Result -PathUsed 'msbuild' -Success $false -ErrorCount $errors.Count -Errors $errors -FailureKind 'compile')
    }

    if ($exitCode -ne 0) {
        $infraErrors = @($output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
        if ($infraErrors.Count -eq 0) {
            $infraErrors = @("MSBuild exited with code $exitCode without Roslyn compile errors.")
        }
        return @{ infrastructure_failure = $true; errors = $infraErrors }
    }

    return (New-Result -PathUsed 'msbuild' -Success $true -ErrorCount 0 -Errors @())
}

$availablePaths = Get-AvailablePaths

if ($DryRun) {
    $stopwatch.Stop()
    $dryRunResult = [ordered]@{
        available_paths = @($availablePaths)
        preferred = $PreferredPath
        dry_run = $true
    }
    Write-Output ($dryRunResult | ConvertTo-Json -Depth 4 -Compress)
    exit 0
}

if (-not (Test-Path -LiteralPath $customRoot)) {
    Complete-And-Exit -Result (New-Result -PathUsed '' -Success $false -ErrorCount 0 -Errors @("NT8 Custom folder not found: $customRoot") -FailureKind 'infrastructure') -ExitCode 2
}

if ($PreferredPath) {
    $pathsToTry = @($PreferredPath)
}
else {
    $pathsToTry = @($availablePaths)
}

if ($pathsToTry.Count -eq 0) {
    Complete-And-Exit -Result (New-Result -PathUsed '' -Success $false -ErrorCount 0 -Errors @('No compilation paths are currently available.') -FailureKind 'infrastructure') -ExitCode 2
}

$infraErrors = New-Object System.Collections.Generic.List[string]

foreach ($path in $pathsToTry) {
    $attempt = switch ($path) {
        'devaddon' { Invoke-DevAddonCompile }
        'ninjascript_exe' { Invoke-NinjaScriptExeCompile }
        'msbuild' { Invoke-MsBuildCompile }
        default { @{ infrastructure_failure = $true; errors = @("Unsupported compile path: $path") } }
    }

    if ($attempt -is [hashtable] -and $attempt.ContainsKey('infrastructure_failure') -and $attempt.infrastructure_failure) {
        foreach ($err in @($attempt.errors)) {
            if ($err) { $infraErrors.Add([string]$err) }
        }
        continue
    }

    if ($attempt.success) {
        Complete-And-Exit -Result $attempt -ExitCode 0
    }

    Complete-And-Exit -Result $attempt -ExitCode 1
}

if ($infraErrors.Count -eq 0) {
    $infraErrors.Add('All compilation paths failed for infrastructure reasons.')
}

Complete-And-Exit -Result (New-Result -PathUsed '' -Success $false -ErrorCount 0 -Errors @($infraErrors) -FailureKind 'infrastructure') -ExitCode 2
