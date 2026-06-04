[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFile,
    [int]$MaxIterations = 8,
    [int]$TimeoutSeconds = 60,
    [string]$ArtifactsDir = "./artifacts"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..\..")).Path
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

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

function Invoke-PowerShellJsonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments = @(),
        [switch]$AllowFailure
    )

    # PS 5.1: array splatting passes elements as positional params, not named.
    # Convert @("-Name","Value",...) pairs into a hashtable for proper named-param splatting.
    $splatHash = @{}
    for ($ai = 0; $ai -lt $Arguments.Count; $ai++) {
        $argItem = $Arguments[$ai]
        if ($argItem -is [string] -and $argItem.StartsWith('-')) {
            $pName = $argItem.TrimStart('-')
            if (($ai + 1) -lt $Arguments.Count) {
                $nxt = $Arguments[$ai + 1]
                if ($nxt -is [string] -and $nxt.StartsWith('-')) {
                    $splatHash[$pName] = [switch]$true
                }
                else {
                    $splatHash[$pName] = $nxt
                    $ai++
                }
            }
            else {
                $splatHash[$pName] = [switch]$true
            }
        }
    }
    $rawOutput = & $ScriptPath @splatHash 2>&1
    $exitCode = if ($null -eq $LASTEXITCODE -or $LASTEXITCODE -eq "") { 0 } else { [int]$LASTEXITCODE }
    $json = ConvertFrom-JsonPayload -OutputLines @($rawOutput)

    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "Script failed: $ScriptPath (exit $exitCode)"
    }

    [PSCustomObject]@{
        Output   = @($rawOutput)
        ExitCode = $exitCode
        Json     = $json
    }
}

function New-IterationRecord {
    param(
        [int]$Iteration,
        [int]$ErrorsBefore,
        [int]$ErrorsAfter,
        [object[]]$Fixes,
        [string[]]$Rollbacks,
        [long]$ElapsedMs
    )

    return [ordered]@{
        iteration     = $Iteration
        errors_before = $ErrorsBefore
        errors_after  = $ErrorsAfter
        fixes         = @($Fixes)
        rollbacks     = @($Rollbacks)
        elapsed_ms    = $ElapsedMs
    }
}

function Save-DiffArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [object[]]$DiffEntries
    )

    if (-not $DiffEntries -or $DiffEntries.Count -eq 0) {
        return
    }

    $buffer = New-Object System.Collections.Generic.List[string]
    foreach ($entry in @($DiffEntries)) {
        $buffer.Add(("=" * 80))
        $buffer.Add("FILE: $($entry.file)")
        $buffer.Add("CODE: $($entry.code)")
        $buffer.Add("FIX : $($entry.fix_applied)")
        $buffer.Add(("-" * 80))
        $buffer.Add([string]$entry.diff)
        $buffer.Add("")
    }

    $buffer -join [Environment]::NewLine | Set-Content -LiteralPath $Path -Encoding UTF8
}

if ($MaxIterations -lt 1) {
    throw "MaxIterations must be >= 1"
}

$SourceFile = (Resolve-Path -LiteralPath $SourceFile).Path
$fileName = Split-Path $SourceFile -Leaf
$artifactsRoot = Get-AbsoluteArtifactsDir -PathValue $ArtifactsDir

New-Item -ItemType Directory -Path $artifactsRoot -Force | Out-Null

$runId = "bv-$(Get-Date -Format 'yyyyMMdd-HHmmss')-$((New-Guid).ToString().Substring(0,4))"
$runDir = Join-Path $artifactsRoot $runId
$fixDiffDir = Join-Path $runDir "fix-diffs"
$backupRoot = Join-Path $runDir "backups"

New-Item -ItemType Directory -Path $runDir -Force | Out-Null
New-Item -ItemType Directory -Path $fixDiffDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$iterationLog = New-Object System.Collections.Generic.List[object]
$totalFixes = 0
$totalRollbacks = 0
$result = $null
$finalErrorCount = 0
$completedIterations = 0

$modalScript = Join-Path $scriptDir "modal_detect.ps1"
$deployScript = Join-Path $scriptDir "deploy.ps1"
$compileHeadlessScript = Join-Path $scriptDir "compile_headless.ps1"
$compileEditorScript = Join-Path $scriptDir "compile_editor.ps1"
$parseErrorsScript = Join-Path $scriptDir "parse_errors.py"
$fixRouterScript = Join-Path $scriptDir "fix_router.py"
$errorsScript = Join-Path $repoRoot "ninjatrader\scripts\nt8-errors-full.ps1"

for ($iteration = 1; $iteration -le $MaxIterations; $iteration++) {
    $completedIterations = $iteration
    $iterStart = [System.Diagnostics.Stopwatch]::StartNew()
    $errorsBefore = 0
    $errorsAfter = 0
    $fixesForLog = @()
    $rollbacksForLog = @()

    $modalRun = Invoke-PowerShellJsonScript -ScriptPath $modalScript -Arguments @("-TimeoutSeconds", "5") -AllowFailure
    $modalResult = $modalRun.Json
    if ($modalRun.ExitCode -ne 0 -or $null -eq $modalResult) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "modal_detect failed"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore 0 -ErrorsAfter 0 -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    if ($modalResult.blocked) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "modal_detect reported blocked modal state"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore 0 -ErrorsAfter 0 -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $deployRun = Invoke-PowerShellJsonScript -ScriptPath $deployScript -Arguments @("-SourceFile", $SourceFile) -AllowFailure
    $deployResult = $deployRun.Json
    if ($deployRun.ExitCode -ne 0 -or $null -eq $deployResult -or -not $deployResult.hash_match) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "deploy failed"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore 0 -ErrorsAfter 0 -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $compileRun = Invoke-PowerShellJsonScript -ScriptPath $compileHeadlessScript -Arguments @("-TimeoutSeconds", "$TimeoutSeconds") -AllowFailure
    $compileJson = $compileRun.Json
    if ($compileRun.ExitCode -eq 2 -or $null -eq $compileJson) {
        # Headless failed (infrastructure) — fall back to compile_editor (F5 via UIA)
        $editorFallback = Invoke-PowerShellJsonScript -ScriptPath $compileEditorScript -Arguments @("-TimeoutSeconds", "$TimeoutSeconds") -AllowFailure
        $compileJson = $editorFallback.Json
        if ($editorFallback.ExitCode -eq 2 -or $null -eq $compileJson) {
            $result = "INFRASTRUCTURE_FAILURE"
            $rollbacksForLog += "compile_headless and compile_editor both failed"
            $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore 999 -ErrorsAfter 999 -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
            break
        }
        # Override compileRun with the editor result
        $compileRun = $editorFallback
    }

    $errorsBefore = if ($compileJson.PSObject.Properties.Name -contains 'error_count') { [int]$compileJson.error_count } else { 999 }

    # BUG FIX: Check BOTH success flag AND error_count == 0 before declaring victory
    # compile_editor may return success=true (script ran OK) but error_count > 0 (compile errors exist)
    $compileActuallyClean = $compileJson.success -and ($errorsBefore -eq 0)
    if ($compileActuallyClean) {
        if ($compileJson.path_used -ne "devaddon") {
            $editorRun = Invoke-PowerShellJsonScript -ScriptPath $compileEditorScript -Arguments @("-TimeoutSeconds", "$TimeoutSeconds") -AllowFailure
            $editorJson = $editorRun.Json
            if ($editorRun.ExitCode -eq 2 -or $null -eq $editorJson -or -not $editorJson.success) {
                $result = "INFRASTRUCTURE_FAILURE"
                $rollbacksForLog += "compile_editor failed after headless success"
                $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsBefore -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
                break
            }
        }

        $result = "SUCCESS"
        $finalErrorCount = 0
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter 0 -Fixes @() -Rollbacks @() -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $errorsRaw = @()
    if (Test-Path -LiteralPath $errorsScript) {
        $errorsRun = Invoke-PowerShellJsonScript -ScriptPath $errorsScript -AllowFailure
        if ($errorsRun.Json) {
            if ($errorsRun.Json -is [System.Array]) {
                $errorsRaw = @($errorsRun.Json)
            }
            else {
                $errorsRaw = @($errorsRun.Json)
            }
        }
    }

    if ($errorsRaw.Count -eq 0 -and ($compileJson.PSObject.Properties.Name -contains 'errors')) {
        foreach ($entry in @($compileJson.errors)) {
            if ($entry -is [string]) {
                if ($entry -match '^(?<file>.+?)\((?<line>\d+),(?<col>\d+)\):\s+error\s+(?<code>CS\d+):\s+(?<message>.+)$') {
                    $errorsRaw += [ordered]@{
                        file = $matches.file
                        message = $matches.message
                        code = $matches.code
                        line = [int]$matches.line
                        col = [int]$matches.col
                    }
                }
                elseif ($entry -match 'error\s+(?<code>CS\d+):\s+(?<message>.+)$') {
                    $errorsRaw += [ordered]@{
                        file = $fileName
                        message = $matches.message
                        code = $matches.code
                        line = 0
                        col = 0
                    }
                }
            }
            else {
                $errorsRaw += $entry
            }
        }
    }

    if ($errorsRaw.Count -eq 0) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "no parseable compile errors available"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsBefore -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $errorsJsonInput = $errorsRaw | ConvertTo-Json -Depth 8 -Compress
    $enrichedRaw = $errorsJsonInput | python "$parseErrorsScript" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "parse_errors.py failed"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsBefore -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $enriched = ConvertFrom-JsonPayload -OutputLines @($enrichedRaw)
    if ($null -eq $enriched) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "parse_errors.py returned invalid JSON"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsBefore -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $fixableErrors = @($enriched.errors | Where-Object { $_.fixable })
    if ($fixableErrors.Count -eq 0) {
        $result = "PARTIAL"
        $finalErrorCount = @($enriched.errors).Count
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $finalErrorCount -Fixes @() -Rollbacks @() -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $backupDir = Join-Path $backupRoot "iteration-$iteration"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $backupFile = Join-Path $backupDir $fileName
    Copy-Item -LiteralPath $SourceFile -Destination $backupFile -Force

    $enrichedPath = Join-Path $runDir "enriched-errors-iteration-$iteration.json"
    ($enriched.errors | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $enrichedPath -Encoding UTF8

    $sourceDir = Split-Path $SourceFile -Parent
    $fixRaw = & python "$fixRouterScript" --errors "$enrichedPath" --source-dir "$sourceDir" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "fix_router.py failed"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsBefore -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $fixResult = ConvertFrom-JsonPayload -OutputLines @($fixRaw)
    if ($null -eq $fixResult) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "fix_router.py returned invalid JSON"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsBefore -Fixes @() -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $fixesApplied = if ($fixResult.PSObject.Properties.Name -contains 'fixes_applied') { [int]$fixResult.fixes_applied } else { 0 }
    $totalFixes += $fixesApplied
    $fixesForLog = @($fixResult.diffs)

    if ($fixesForLog.Count -gt 0) {
        $diffPath = Join-Path $fixDiffDir "iteration-$iteration.diff"
        Save-DiffArtifact -Path $diffPath -DiffEntries $fixesForLog
    }

    $redeployRun = Invoke-PowerShellJsonScript -ScriptPath $deployScript -Arguments @("-SourceFile", $SourceFile) -AllowFailure
    $redeployResult = $redeployRun.Json
    if ($redeployRun.ExitCode -ne 0 -or $null -eq $redeployResult -or -not $redeployResult.hash_match) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "redeploy after fix failed"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter 999 -Fixes $fixesForLog -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $recompileRun = Invoke-PowerShellJsonScript -ScriptPath $compileHeadlessScript -Arguments @("-TimeoutSeconds", "$TimeoutSeconds") -AllowFailure
    $recompileJson = $recompileRun.Json
    if ($recompileRun.ExitCode -eq 2 -or $null -eq $recompileJson) {
        $result = "INFRASTRUCTURE_FAILURE"
        $rollbacksForLog += "recompile after fix failed"
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter 999 -Fixes $fixesForLog -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $errorsAfter = if ($recompileJson.PSObject.Properties.Name -contains 'error_count') { [int]$recompileJson.error_count } else { 999 }
    $finalErrorCount = $errorsAfter

    if ($errorsAfter -gt $errorsBefore) {
        Copy-Item -LiteralPath $backupFile -Destination $SourceFile -Force
        $restoreDeploy = Invoke-PowerShellJsonScript -ScriptPath $deployScript -Arguments @("-SourceFile", $SourceFile) -AllowFailure
        $totalRollbacks++
        $rollbacksForLog += "Rolled back - error count increased from $errorsBefore to $errorsAfter"
        if ($restoreDeploy.ExitCode -ne 0) {
            $result = "INFRASTRUCTURE_FAILURE"
            $rollbacksForLog += "rollback deploy failed"
            $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsAfter -Fixes $fixesForLog -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
            break
        }

        $finalErrorCount = $errorsBefore
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsAfter -Fixes $fixesForLog -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
        continue
    }

    # BUG FIX: Check BOTH success AND error_count == 0
    $recompileActuallyClean = $recompileJson.success -and ($errorsAfter -eq 0)
    if ($recompileActuallyClean) {
        if ($recompileJson.path_used -ne "devaddon") {
            $editorRun = Invoke-PowerShellJsonScript -ScriptPath $compileEditorScript -Arguments @("-TimeoutSeconds", "$TimeoutSeconds") -AllowFailure
            $editorJson = $editorRun.Json
            if ($editorRun.ExitCode -eq 2 -or $null -eq $editorJson -or -not $editorJson.success) {
                $result = "INFRASTRUCTURE_FAILURE"
                $rollbacksForLog += "compile_editor failed after fixed headless success"
                $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsAfter -Fixes $fixesForLog -Rollbacks $rollbacksForLog -ElapsedMs $iterStart.ElapsedMilliseconds))
                break
            }
        }

        $result = "SUCCESS"
        $finalErrorCount = 0
        $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter 0 -Fixes $fixesForLog -Rollbacks @() -ElapsedMs $iterStart.ElapsedMilliseconds))
        break
    }

    $iterationLog.Add((New-IterationRecord -Iteration $iteration -ErrorsBefore $errorsBefore -ErrorsAfter $errorsAfter -Fixes $fixesForLog -Rollbacks @() -ElapsedMs $iterStart.ElapsedMilliseconds))
}

if (-not $result) {
    $result = if ($finalErrorCount -eq 0) { "SUCCESS" } else { "MAX_ITERATIONS" }
}

try {
    $loopLog = [ordered]@{
        run_id = $runId
        result = [string]$result
        iterations = [int]$completedIterations
        final_error_count = [int]$finalErrorCount
        total_fixes = [int]$totalFixes
        total_rollbacks = [int]$totalRollbacks
        iteration_details = @($iterationLog.ToArray())
    }
    $loopLog | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $runDir "fix-loop-log.json") -Encoding UTF8
}
catch {
    Write-Warning "fix-loop-log serialization failed: $($_.Exception.GetType().Name): $($_.Exception.Message) at line $($_.InvocationInfo.ScriptLineNumber)"
    # Write minimal log
    [ordered]@{ run_id = $runId; result = [string]$result; error = $_.Exception.Message } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "fix-loop-log.json") -Encoding UTF8
}

if ($result -eq "SUCCESS") {
    Write-Output "[COMPILE-RESULT] SUCCESS $(Get-Date -Format 'o')"
}
else {
    Write-Output "[COMPILE-RESULT] FAILED $finalErrorCount"
}

$stopwatch.Stop()
$summary = [ordered]@{
    result = $result
    iterations = $completedIterations
    final_error_count = $finalErrorCount
    total_fixes = $totalFixes
    total_rollbacks = $totalRollbacks
    run_dir = $runDir
    elapsed_ms = $stopwatch.ElapsedMilliseconds
}
Write-Output ($summary | ConvertTo-Json -Compress)

switch ($result) {
    "SUCCESS" { exit 0 }
    "PARTIAL" { exit 1 }
    "INFRASTRUCTURE_FAILURE" { exit 2 }
    "MAX_ITERATIONS" { exit 3 }
    default { exit 1 }
}
