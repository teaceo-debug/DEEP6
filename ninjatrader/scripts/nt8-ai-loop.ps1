# nt8-ai-loop.ps1 - Deploy → Compile → Error-scrape loop for Claude Code
#
# Claude Code calls this script to:
#   1. Deploy source files to NT8 Custom folder
#   2. Trigger compile (via nt8-compile.ps1, which polls the DLL and emits [COMPILE-RESULT])
#   3. If SUCCESS: check Output Window for stray errors, exit 0
#   4. If FAILED: scrape Output Window via nt8-errors.ps1, emit JSON errors, exit 1
#
# Claude Code reads the JSON, fixes the source, and calls this script again.
#
# Usage:
#   nt8-ai-loop.ps1 -SourceFile <path>
#   nt8-ai-loop.ps1 -SourceFile <path> -MaxIterations 1 -Target Indicators -WaitSeconds 30
#
# Exit codes:
#   0 = compile succeeded with no errors
#   1 = compile finished but errors remain (JSON printed to stdout via [COMPILE-RESULT] FAILED block)
#   2 = NT8 not running, deploy failed, or compile infrastructure error
#   3 = max iterations reached without a clean compile

param(
    [Parameter(Mandatory)]
    [string]$SourceFile,

    [ValidateSet("All","Indicators","Strategies","AddOns")]
    [string]$Target = "All",

    # Max deploy+compile cycles before giving up.
    # Default 1: deploy once, compile once, return errors. Claude fixes externally and re-invokes.
    [int]$MaxIterations = 1,

    # Seconds to wait for NT8 DLL to be updated (passed to nt8-compile.ps1 -WaitSeconds)
    [int]$WaitSeconds = 30,

    # Suppress progress banners; errors and [COMPILE-RESULT] lines always go to stdout
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

# ── Helpers ───────────────────────────────────────────────────────────────────

function Log {
    param([string]$msg, [string]$Color = "Cyan")
    if (!$Quiet) { Write-Host $msg -ForegroundColor $Color }
}

function Log-Err {
    param([string]$msg)
    Write-Host $msg -ForegroundColor Red
}

function Assert-NT8Running {
    $p = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
    if (!$p) {
        Log-Err "NT8 is not running. Start NinjaTrader 8 before invoking this script."
        exit 2
    }
    return $p
}

function Require-Script {
    param([string]$Name)
    $path = Join-Path $ScriptDir $Name
    if (!(Test-Path $path)) {
        Log-Err "$Name not found: $path"
        exit 2
    }
    return $path
}

# ── Validate dependencies ─────────────────────────────────────────────────────
$deployScript  = Require-Script "nt8-deploy.ps1"
$compileScript = Require-Script "nt8-compile.ps1"
$errorsScript  = Require-Script "nt8-errors.ps1"

# ── Main loop ─────────────────────────────────────────────────────────────────

Log ""
Log "NT8 AI Loop -- $(Get-Date -Format 'HH:mm:ss')" "White"
Log "  Source  : $SourceFile"
Log "  Target  : $Target"
Log "  MaxIter : $MaxIterations"
Log "  Wait    : ${WaitSeconds}s"
Log "=============================================="

for ($iter = 1; $iter -le $MaxIterations; $iter++) {

    Log ""
    Log "── Iteration $iter / $MaxIterations ───────────────────────────────────" "Magenta"

    # ── 1. Verify NT8 is running ───────────────────────────────────────────────
    $nt8 = Assert-NT8Running
    Log "  [1/3] NT8 running (PID $($nt8.Id))" "Green"

    # ── 2. Deploy ─────────────────────────────────────────────────────────────
    Log "  [2/3] Deploying ($Target)..."
    $deployOut = & $deployScript -Target $Target -Force 2>&1
    $deployExit = $LASTEXITCODE

    if (!$Quiet) { $deployOut | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray } }

    if ($deployExit -ne 0) {
        Log-Err "  Deploy failed (exit $deployExit). Aborting."
        exit 2
    }
    Log "  [2/3] Deploy OK." "Green"

    # ── 3. Compile + poll DLL ─────────────────────────────────────────────────
    Log "  [3/3] Compiling (timeout ${WaitSeconds}s)..."

    # Capture all stdout lines from nt8-compile.ps1 so we can parse [COMPILE-RESULT]
    $compileLines = & $compileScript -WaitSeconds $WaitSeconds -Quiet 2>&1

    if (!$Quiet) {
        $compileLines | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    }

    # Find the [COMPILE-RESULT] sentinel emitted by nt8-compile.ps1
    $resultLine = $compileLines | Where-Object { $_ -match "^\[COMPILE-RESULT\]" } | Select-Object -Last 1

    if (!$resultLine) {
        Log-Err "  No [COMPILE-RESULT] line found in compile output. NT8 may have timed out."
        Write-Output "[COMPILE-RESULT] FAILED no-result-line"
        exit 2
    }

    $compileSuccess = $resultLine -match "^\[COMPILE-RESULT\] SUCCESS"

    # Always echo the result line so the caller sees it
    Write-Output $resultLine

    if ($compileSuccess) {
        # ── Compile succeeded — verify no lingering errors in Output Window ───
        Log "  Compile reports SUCCESS. Verifying Output Window..." "Green"
        $errJson  = & $errorsScript -Format Json 2>&1
        $errExit  = $LASTEXITCODE

        if ($errExit -eq 0) {
            # No errors
            Log ""
            Log "COMPILE OK -- no errors found." "Green"
            exit 0
        } elseif ($errExit -eq 1) {
            # Output Window has errors despite DLL updating (unlikely but possible
            # if NT8 loaded a partial build or warnings were mis-classified)
            Log-Err "Output Window contains errors despite DLL update:"
            Write-Output $errJson
            # Treat as failure
            if ($iter -ge $MaxIterations) {
                exit 3
            }
            # If more iterations allowed, loop back so Claude can fix and retry
            Log "Will retry after Claude fixes source." "Yellow"
            exit 1
        } else {
            # errExit=2: Output Window inaccessible — trust the DLL timestamp
            Log "Output Window inaccessible; trusting DLL timestamp. Assuming SUCCESS." "Yellow"
            exit 0
        }

    } else {
        # ── Compile failed — scrape Output Window for CS#### errors ───────────
        Log-Err "  Compile FAILED. Scraping Output Window for errors..."
        $errJson = & $errorsScript -Format Json 2>&1
        $errExit = $LASTEXITCODE

        if ($errExit -eq 0) {
            # nt8-errors.ps1 found nothing — emit a generic failure payload
            $fallback = '[{"type":"error","code":"","message":"Compile failed but no CS#### errors found in Output Window. Check NT8 Output Window manually (View > Output Window).","file":"","line":0,"column":0}]'
            Write-Output $fallback
        } else {
            Write-Output $errJson
        }

        if ($iter -ge $MaxIterations) {
            Log ""
            Log "Max iterations ($MaxIterations) reached. Returning errors for Claude." "Yellow"
            exit 3
        }

        # With MaxIterations > 1, loop back (caller pattern: Claude fixes in-process)
        Log "Errors returned. Iteration $iter of $MaxIterations complete." "Yellow"
    }
}

# Exhausted iterations with compile still failing
exit 3
