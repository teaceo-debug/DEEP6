[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFile,

    [Parameter(Mandatory = $true)]
    [string]$ChartTitle,

    [string]$ClassName,
    [string]$SpecDescription = "",
    [hashtable]$Parameters = @{},
    [string]$Panel = "price",
    [int]$MaxIterations = 8,
    [int]$TimeoutSeconds = 60,
    [int]$SettleMs = 1500,
    [switch]$SkipVisualVerify,
    [switch]$DryRun,
    [string]$ArtifactsDir = "./artifacts"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..\..")).Path
$totalTimer = [System.Diagnostics.Stopwatch]::StartNew()

function Get-AbsoluteArtifactsDir {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    $trimmed = $PathValue
    if ($trimmed.StartsWith(".\\")) {
        $trimmed = $trimmed.Substring(2)
    }
    elseif ($trimmed.StartsWith("./")) {
        $trimmed = $trimmed.Substring(2)
    }

    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        $trimmed = "artifacts"
    }

    return (Join-Path $repoRoot $trimmed)
}

function ConvertFrom-JsonPayload {
    param([object[]]$OutputLines)

    $lines = @($OutputLines | ForEach-Object { if ($null -ne $_) { $_.ToString() } })
    if ($lines.Count -eq 0) {
        return $null
    }

    for ($start = $lines.Count - 1; $start -ge 0; $start--) {
        $candidateLine = $lines[$start].TrimStart()
        if (($candidateLine.StartsWith("{") -or $candidateLine.StartsWith("[")) -and -not $candidateLine.StartsWith("[COMPILE-RESULT]")) {
            $candidate = ($lines[$start..($lines.Count - 1)] -join [Environment]::NewLine)
            try {
                return ($candidate | ConvertFrom-Json -ErrorAction Stop)
            }
            catch {
            }
        }
    }

    return $null
}

function Invoke-JsonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandPath,
        [object[]]$Arguments = @(),
        [switch]$AllowFailure,
        [switch]$UsePython
    )

    if ($UsePython) {
        $rawOutput = & python $CommandPath @Arguments 2>&1
    }
    else {
        # PS 5.1: array splatting passes elements as positional params, not named.
        # Convert @("-Name","Value",...) pairs into a hashtable for proper named-param splatting.
        $splatHash = @{}
        for ($ai = 0; $ai -lt $Arguments.Count; $ai++) {
            $item = [string]$Arguments[$ai]
            if ($item.StartsWith('-')) {
                $paramName = $item.TrimStart('-')
                if (($ai + 1) -lt $Arguments.Count) {
                    $nextItem = $Arguments[$ai + 1]
                    if ($nextItem -is [string] -and $nextItem.StartsWith('-')) {
                        $splatHash[$paramName] = [switch]$true
                    }
                    else {
                        $splatHash[$paramName] = $nextItem
                        $ai++
                    }
                }
                else {
                    $splatHash[$paramName] = [switch]$true
                }
            }
        }
        $rawOutput = & $CommandPath @splatHash 2>&1
    }

    $exitCode = if ($null -eq $LASTEXITCODE -or $LASTEXITCODE -eq "") { 0 } else { [int]$LASTEXITCODE }
    $json = ConvertFrom-JsonPayload -OutputLines @($rawOutput)

    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "Command failed: $CommandPath (exit $exitCode)"
    }

    [PSCustomObject]@{
        Output   = @($rawOutput)
        ExitCode = $exitCode
        Json     = $json
    }
}

function Save-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Data,
        [int]$Depth = 10
    )

    $Data | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-ClassNameFromSource {
    param([string]$ResolvedSourceFile)

    $content = Get-Content -LiteralPath $ResolvedSourceFile -Raw
    if ($content -match '\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\s*:') {
        return $Matches[1]
    }

    return [System.IO.Path]::GetFileNameWithoutExtension($ResolvedSourceFile)
}

function Copy-FixLoopArtifacts {
    param(
        [string]$FixLoopRunDir,
        [string]$DestinationRunDir
    )

    if ([string]::IsNullOrWhiteSpace($FixLoopRunDir) -or -not (Test-Path -LiteralPath $FixLoopRunDir)) {
        return
    }

    $logPath = Join-Path $FixLoopRunDir "fix-loop-log.json"
    if (Test-Path -LiteralPath $logPath) {
        Copy-Item -LiteralPath $logPath -Destination (Join-Path $DestinationRunDir "fix-loop-log.json") -Force
    }

    $diffPath = Join-Path $FixLoopRunDir "fix-diffs"
    if (Test-Path -LiteralPath $diffPath) {
        $destDiffPath = Join-Path $DestinationRunDir "fix-diffs"
        if (Test-Path -LiteralPath $destDiffPath) {
            Remove-Item -LiteralPath $destDiffPath -Recurse -Force
        }
        Copy-Item -LiteralPath $diffPath -Destination $destDiffPath -Recurse -Force
    }
}

function Get-WorkspaceReloadNote {
    param([object]$WorkspaceMutationResult)

    if ($null -eq $WorkspaceMutationResult -or -not $WorkspaceMutationResult.reload_needed) {
        return $null
    }

    return [ordered]@{
        reload_needed = $true
        active_strategies_checked = $false
        restart_performed = $false
        reason = "Workspace mutation requires NT8 reload/restart; orchestrator does not auto-restart per G4/G9. Manual operator review required before any restart."
    }
}

$resolvedSourceFile = (Resolve-Path -LiteralPath $SourceFile).Path
if (-not $ClassName) {
    $ClassName = Get-ClassNameFromSource -ResolvedSourceFile $resolvedSourceFile
}

$artifactsRoot = Get-AbsoluteArtifactsDir -PathValue $ArtifactsDir
$runId = "bv-$(Get-Date -Format 'yyyyMMdd-HHmmss')-$((New-Guid).ToString().Substring(0,4))"
$runDir = Join-Path $artifactsRoot $runId

if ($DryRun) {
    $plan = [ordered]@{
        run_id = $runId
        source_file = $resolvedSourceFile
        class_name = $ClassName
        chart_title = $ChartTitle
        panel = $Panel
        parameters = $Parameters
        spec = $SpecDescription
        max_iterations = $MaxIterations
        timeout_seconds = $TimeoutSeconds
        settle_ms = $SettleMs
        skip_visual = $SkipVisualVerify.IsPresent
        artifacts_dir = $artifactsRoot
        run_dir = $runDir
        pipeline = @(
            "1. VALIDATE: python .claude/skills/nt8-build-verify/lib/nt8_paths.py",
            "2. DEPLOY: deploy.ps1 -SourceFile '$resolvedSourceFile'",
            "3. COMPILE+FIX: fix_loop.ps1 -SourceFile '$resolvedSourceFile' -MaxIterations $MaxIterations -TimeoutSeconds $TimeoutSeconds",
            "4. INSTALL: install_indicator.ps1 -ClassName '$ClassName' -ChartTitle '$ChartTitle' -Panel '$Panel'",
            "5. SETTLE: Start-Sleep -Milliseconds $SettleMs",
            "6. RUNTIME CHECK: runtime_check.ps1 -ClassName '$ClassName' -WindowSeconds 10",
            "7. SCREENSHOT: screenshot_chart.ps1 -ChartTitle '$ChartTitle' -OutputPath '<runDir>\\screenshot-{HHMMSS}.png'",
            "8. VERIFY: verify_visual.py --screenshot '<png>' --spec '$SpecDescription' --artifacts-dir '$runDir' --max-attempts 2",
            "9. REPORT: save timing.json + verdict-{HHMMSS}.json in '$runDir'"
        )
        dry_run = $true
    }
    Write-Output ($plan | ConvertTo-Json -Depth 8)
    exit 0
}

New-Item -ItemType Directory -Path $runDir -Force | Out-Null

$timings = [ordered]@{}
$phaseResults = [ordered]@{}
$finalVerdict = "UNKNOWN"
$finalReason = ""
$finalExitCode = 0

function Save-FinalArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Verdict,
        [string]$Reason = ""
    )

    $reportTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $timestamp = Get-Date -Format "HHmmss"

    if ($totalTimer.IsRunning) {
        $totalTimer.Stop()
    }

    $timings["total_ms"] = $totalTimer.ElapsedMilliseconds

    $verdictData = [ordered]@{
        verdict = $Verdict
        reason = $Reason
        run_id = $runId
        class_name = $ClassName
        chart_title = $ChartTitle
        source_file = $resolvedSourceFile
        run_dir = $runDir
        timestamp = (Get-Date -Format "o")
    }

    Save-JsonFile -Path (Join-Path $runDir "timing.json") -Data $timings
    Save-JsonFile -Path (Join-Path $runDir "verdict-$timestamp.json") -Data $verdictData

    $reportTimer.Stop()
    $timings["report_ms"] = $reportTimer.ElapsedMilliseconds
    Save-JsonFile -Path (Join-Path $runDir "timing.json") -Data $timings
}

try {
    # === STEP 1: VALIDATE ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $pathsRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "..\lib\nt8_paths.py") -UsePython -AllowFailure
    $phaseTimer.Stop()
    $timings["validate_ms"] = $phaseTimer.ElapsedMilliseconds

    if ($pathsRun.Json) {
        $phaseResults["validate"] = $pathsRun.Json
        Save-JsonFile -Path (Join-Path $runDir "validate-log.json") -Data $pathsRun.Json
    }

    $nt8RootExists = $false
    if ($pathsRun.Json -and $pathsRun.Json.validation -and $pathsRun.Json.validation.nt8_root) {
        $nt8RootExists = [bool]$pathsRun.Json.validation.nt8_root.exists
    }

    if ($pathsRun.ExitCode -ne 0 -or -not $pathsRun.Json -or -not $nt8RootExists) {
        $finalVerdict = "INFRASTRUCTURE_FAIL"
        $finalReason = "NT8 paths validation failed"
        $finalExitCode = 2
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    # === STEP 2: DEPLOY ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $deployRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "deploy.ps1") -Arguments @("-SourceFile", $resolvedSourceFile) -AllowFailure
    $phaseTimer.Stop()
    $timings["deploy_ms"] = $phaseTimer.ElapsedMilliseconds

    if ($deployRun.Json) {
        $phaseResults["deploy"] = $deployRun.Json
        Save-JsonFile -Path (Join-Path $runDir "deploy-log.json") -Data $deployRun.Json
    }

    if ($deployRun.ExitCode -ne 0 -or -not $deployRun.Json -or -not $deployRun.Json.hash_match) {
        $finalVerdict = "DEPLOY_FAIL"
        $finalReason = "Deploy failed or hash verification failed"
        $finalExitCode = 2
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    # === STEP 3: COMPILE + FIX ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $fixLoopRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "fix_loop.ps1") -Arguments @(
        "-SourceFile", $resolvedSourceFile,
        "-MaxIterations", $MaxIterations,
        "-TimeoutSeconds", $TimeoutSeconds,
        "-ArtifactsDir", $runDir
    ) -AllowFailure
    $phaseTimer.Stop()
    $timings["compile_fix_ms"] = $phaseTimer.ElapsedMilliseconds

    if ($fixLoopRun.Json) {
        $phaseResults["compile_fix"] = $fixLoopRun.Json
        Save-JsonFile -Path (Join-Path $runDir "compile-log.json") -Data $fixLoopRun.Json
        Copy-FixLoopArtifacts -FixLoopRunDir $fixLoopRun.Json.run_dir -DestinationRunDir $runDir
    }

    if ($fixLoopRun.ExitCode -ne 0 -or -not $fixLoopRun.Json -or $fixLoopRun.Json.result -ne "SUCCESS") {
        $errorsPayload = [ordered]@{
            status = "compile_failed"
            result = if ($fixLoopRun.Json) { $fixLoopRun.Json.result } else { "UNKNOWN" }
            final_error_count = if ($fixLoopRun.Json) { $fixLoopRun.Json.final_error_count } else { $null }
        }
        Save-JsonFile -Path (Join-Path $runDir "errors.json") -Data $errorsPayload
        $finalVerdict = "COMPILE_FAILED"
        $finalReason = if ($fixLoopRun.Json) {
            "Fix loop result: $($fixLoopRun.Json.result); final errors: $($fixLoopRun.Json.final_error_count)"
        }
        else {
            "Fix loop failed without JSON output"
        }
        $finalExitCode = if ($fixLoopRun.ExitCode -eq 2) { 2 } else { 1 }
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    Save-JsonFile -Path (Join-Path $runDir "errors.json") -Data @{ errors = @() }

    # === STEP 4: INSTALL ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $installArgs = @(
        "-ClassName", $ClassName,
        "-ChartTitle", $ChartTitle,
        "-Panel", $Panel,
        "-SettleMs", $SettleMs,
        "-Parameters", $Parameters
    )
    $installRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "install_indicator.ps1") -Arguments $installArgs -AllowFailure
    $installMode = "uia"
    $workspaceReloadNote = $null

    if ($installRun.ExitCode -ne 0 -or -not $installRun.Json -or -not $installRun.Json.installed) {
        $installMode = "workspace_mutator"
        $workspaceRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "workspace_mutator.py") -UsePython -Arguments @(
            "--class-name", $ClassName,
            "--chart-title", $ChartTitle,
            "--panel", $Panel
        ) -AllowFailure

        if ($workspaceRun.Json) {
            $workspaceReloadNote = Get-WorkspaceReloadNote -WorkspaceMutationResult $workspaceRun.Json
            $phaseResults["workspace_mutator"] = if ($workspaceReloadNote) {
                [ordered]@{
                    workspace_mutation = $workspaceRun.Json
                    reload_note = $workspaceReloadNote
                }
            }
            else {
                $workspaceRun.Json
            }
        }

        if ($workspaceRun.ExitCode -ne 0 -or -not $workspaceRun.Json -or -not $workspaceRun.Json.injected) {
            $phaseTimer.Stop()
            $timings["install_ms"] = $phaseTimer.ElapsedMilliseconds
            $installFailure = [ordered]@{
                install_mode = $installMode
                uia_result = $installRun.Json
                workspace_result = $workspaceRun.Json
            }
            Save-JsonFile -Path (Join-Path $runDir "install-log.json") -Data $installFailure
            $finalVerdict = "INSTALL_FAILED"
            $finalReason = "Both UIA install and workspace mutation failed"
            $finalExitCode = 1
            Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
            exit $finalExitCode
        }
    }

    $phaseTimer.Stop()
    $timings["install_ms"] = $phaseTimer.ElapsedMilliseconds
    $installPayload = [ordered]@{
        install_mode = $installMode
        uia_result = $installRun.Json
    }
    if ($phaseResults["workspace_mutator"]) {
        $installPayload.workspace_result = $phaseResults["workspace_mutator"]
    }
    Save-JsonFile -Path (Join-Path $runDir "install-log.json") -Data $installPayload
    $phaseResults["install"] = $installPayload

    # === STEP 5: SETTLE ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Start-Sleep -Milliseconds $SettleMs
    $phaseTimer.Stop()
    $timings["settle_ms"] = $phaseTimer.ElapsedMilliseconds

    # === STEP 6: RUNTIME CHECK ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $runtimeRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "runtime_check.ps1") -Arguments @(
        "-ClassName", $ClassName,
        "-WindowSeconds", 10
    ) -AllowFailure
    $phaseTimer.Stop()
    $timings["runtime_check_ms"] = $phaseTimer.ElapsedMilliseconds

    if ($runtimeRun.Json) {
        $phaseResults["runtime_check"] = $runtimeRun.Json
    }

    if ($runtimeRun.ExitCode -ne 0 -or -not $runtimeRun.Json) {
        $finalVerdict = "INFRASTRUCTURE_FAIL"
        $finalReason = "Runtime check did not return valid JSON"
        $finalExitCode = 2
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    if ([int]$runtimeRun.Json.runtime_errors_found -gt 0) {
        Save-JsonFile -Path (Join-Path $runDir "runtime-errors.json") -Data $runtimeRun.Json
        $finalVerdict = "RUNTIME_ERROR"
        $finalReason = "Runtime exceptions detected for $ClassName"
        $finalExitCode = 1
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    # === STEP 7: SCREENSHOT ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $screenshotTimestamp = Get-Date -Format "HHmmss"
    $screenshotPath = Join-Path $runDir "screenshot-$screenshotTimestamp.png"
    $screenshotRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "screenshot_chart.ps1") -Arguments @(
        "-ChartTitle", $ChartTitle,
        "-OutputPath", $screenshotPath,
        "-SettleMs", 500
    ) -AllowFailure
    $phaseTimer.Stop()
    $timings["screenshot_ms"] = $phaseTimer.ElapsedMilliseconds

    if ($screenshotRun.Json) {
        $phaseResults["screenshot"] = $screenshotRun.Json
        Save-JsonFile -Path (Join-Path $runDir "screenshot-log.json") -Data $screenshotRun.Json
    }

    $resolvedScreenshotPath = $null
    if ($screenshotRun.Json -and $screenshotRun.Json.path) {
        $resolvedScreenshotPath = [string]$screenshotRun.Json.path
    }

    if ($screenshotRun.ExitCode -ne 0 -or -not $screenshotRun.Json -or -not $resolvedScreenshotPath -or -not (Test-Path -LiteralPath $resolvedScreenshotPath)) {
        $finalVerdict = "INFRASTRUCTURE_FAIL"
        $finalReason = "Screenshot capture failed"
        $finalExitCode = 2
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    # === STEP 8: VERIFY ===
    $phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $visualVerdict = "PASS_WITH_NOTES"
    $verifyRun = $null
    if (-not $SkipVisualVerify -and -not [string]::IsNullOrWhiteSpace($SpecDescription)) {
        $verifyRun = Invoke-JsonScript -CommandPath (Join-Path $scriptDir "verify_visual.py") -UsePython -Arguments @(
            "--screenshot", $resolvedScreenshotPath,
            "--spec", $SpecDescription,
            "--artifacts-dir", $runDir,
            "--max-attempts", 2
        ) -AllowFailure

        if ($verifyRun.Json) {
            $phaseResults["verify_visual"] = $verifyRun.Json
            Save-JsonFile -Path (Join-Path $runDir "verify-log.json") -Data $verifyRun.Json
            $visualVerdict = [string]$verifyRun.Json.verdict
        }
        else {
            $visualVerdict = "PASS_WITH_NOTES"
        }
    }
    else {
        $phaseResults["verify_visual"] = [ordered]@{
            skipped = $true
            reason = if ($SkipVisualVerify) { "SkipVisualVerify switch set" } else { "SpecDescription empty" }
            max_attempts = 0
        }
        Save-JsonFile -Path (Join-Path $runDir "verify-log.json") -Data $phaseResults["verify_visual"]
    }
    $phaseTimer.Stop()
    $timings["visual_verify_ms"] = $phaseTimer.ElapsedMilliseconds

    if ($verifyRun -and ($verifyRun.ExitCode -ne 0 -or $visualVerdict -eq "FAIL")) {
        $finalVerdict = "VISUAL_FAIL"
        $finalReason = if ($verifyRun.Json) {
            "Visual verification failed: $($verifyRun.Json.auto_checks | ConvertTo-Json -Compress)"
        }
        else {
            "Visual verification failed without JSON output"
        }
        $finalExitCode = 1
        Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
        exit $finalExitCode
    }

    # === STEP 9: REPORT ===
    $finalVerdict = $visualVerdict
    $finalReason = "Pipeline completed successfully"
    $finalExitCode = 0
    Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason

    $summary = [ordered]@{
        run_id = $runId
        verdict = $finalVerdict
        reason = $finalReason
        source_file = $resolvedSourceFile
        class_name = $ClassName
        chart_title = $ChartTitle
        run_dir = $runDir
        screenshot = $resolvedScreenshotPath
        install_mode = $installMode
        timings = $timings
    }

    Write-Output "[ORCHESTRATOR] Pipeline complete: $finalVerdict"
    Write-Output ($summary | ConvertTo-Json -Compress -Depth 10)
    exit $finalExitCode
}
catch {
    $finalVerdict = "CRASH"
    $finalReason = $_.Exception.Message
    $finalExitCode = 2
    Save-FinalArtifacts -Verdict $finalVerdict -Reason $finalReason
    Write-Error "Pipeline crashed: $($finalReason)"
    exit $finalExitCode
}
