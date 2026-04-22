# nt8-fix-loop.ps1 - AI-assisted NT8 compile error fix loop
#
# Reads compile errors from NT8 via UIAutomation, generates a full context
# snapshot, and formats everything for Claude Code to consume.
#
# Usage:
#   nt8-fix-loop.ps1 [-MaxIterations <int>] [-ContextFile <path>] [-DryRun]
#
# Flags:
#   -MaxIterations  Max fix iterations (default: 5). Currently informational.
#   -ContextFile    Path to write context JSON (default: temp file).
#   -DryRun         Print output only — do not attempt to trigger any actions.

param(
    [int]    $MaxIterations = 5,
    [string] $ContextFile   = "",
    [switch] $DryRun
)

$ErrorActionPreference = "SilentlyContinue"

# ── UIAutomation error reader (inline) ────────────────────────────────────────

Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
Add-Type -AssemblyName UIAutomationTypes  -ErrorAction SilentlyContinue

function Get-NT8Errors {
    $nt8 = Get-Process "NinjaTrader" -ErrorAction SilentlyContinue
    if (-not $nt8) { return @() }

    $root    = [System.Windows.Automation.AutomationElement]::RootElement
    $pidCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $nt8.Id)
    $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)

    $nse = $null
    foreach ($w in $windows) {
        if ($w.Current.Name -like "*NinjaScript*") { $nse = $w; break }
    }
    if (-not $nse) { return @() }

    $gridCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::DataGrid)
    $grid = $nse.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $gridCond)
    if (-not $grid) { return @() }

    $errors = @()
    $rows   = $grid.FindAll([System.Windows.Automation.TreeScope]::Children,
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
        # Error rows: 6 cells where one cell matches CS\d{4}
        if ($vals.Count -ge 4) {
            $codeVal = $vals | Where-Object { $_ -match "^CS\d{4}$" } | Select-Object -First 1
            if ($codeVal) {
                # vals order from observed: (empty), file, message, code, line, col
                $errFile = if ($vals.Count -gt 1) { $vals[1] } else { "" }
                $errMsg  = if ($vals.Count -gt 2) { $vals[2] } else { "" }
                $errLine = if ($vals.Count -gt 4) { [int]$vals[4] } else { 0 }
                $errCol  = if ($vals.Count -gt 5) { [int]$vals[5] } else { 0 }
                $errors += [PSCustomObject]@{
                    File    = $errFile
                    Message = $errMsg
                    Code    = $codeVal
                    Line    = $errLine
                    Col     = $errCol
                }
            }
        }
    }
    return $errors
}

# ── Error hint lookup ─────────────────────────────────────────────────────────
# Returns a short diagnostic hint for common CS error codes.

function Get-ErrorHint {
    param([string]$Code, [string]$Message)

    switch ($Code) {
        "CS0111" { return "DUPLICATE MEMBER: find second declaration and remove it" }
        "CS0103" { return "UNDEFINED IDENTIFIER: check spelling, using directives, or missing field" }
        "CS0234" { return "MISSING NAMESPACE: the referenced namespace or type does not exist" }
        "CS0246" { return "MISSING TYPE: type not found — check using directives or assembly references" }
        "CS1061" { return "MISSING MEMBER: type does not contain that method or property" }
        "CS0117" { return "MISSING MEMBER (static): type does not contain that static member" }
        "CS0029" { return "TYPE MISMATCH: cannot implicitly convert — check cast or type alignment" }
        "CS0019" { return "OPERATOR ERROR: operator cannot be applied to these types" }
        "CS0165" { return "UNINITIALIZED: use of unassigned local variable" }
        "CS0266" { return "IMPLICIT CAST MISSING: explicit cast required for this conversion" }
        "CS0535" { return "MISSING INTERFACE IMPL: class does not implement all interface members" }
        "CS0115" { return "OVERRIDE WITHOUT BASE: no suitable method to override in base class" }
        "CS0508" { return "RETURN TYPE MISMATCH: override return type differs from base method" }
        "CS0051" { return "ACCESSIBILITY MISMATCH: parameter type is less accessible than the method" }
        "CS1002" { return "SYNTAX: missing semicolon" }
        "CS1003" { return "SYNTAX: missing punctuation (bracket, comma, etc.)" }
        "CS1513" { return "SYNTAX: missing closing brace" }
        "CS1519" { return "SYNTAX: invalid token in class/method/accessor declaration" }
        "CS0433" { return "AMBIGUOUS TYPE: same type exists in multiple assemblies — add alias or remove duplicate" }
        "CS0579" { return "DUPLICATE ATTRIBUTE: attribute already applied" }
        default  {
            if ($Message -match "(?i)duplicate|already defines") {
                return "DUPLICATE: find and remove the second declaration"
            }
            if ($Message -match "(?i)does not exist|not found|could not be found") {
                return "NOT FOUND: check type names, namespaces, and using directives"
            }
            if ($Message -match "(?i)cannot convert|cannot implicitly") {
                return "TYPE MISMATCH: add explicit cast or fix the type"
            }
            return "See compiler message above"
        }
    }
}

# ── Step 1: Generate full context snapshot ────────────────────────────────────

$tempCtxFile = $ContextFile
if ($tempCtxFile -eq "") {
    $tempCtxFile = [System.IO.Path]::GetTempFileName() -replace "\.tmp$", ".json"
}

$contextScript = "$PSScriptRoot\nt8-context.ps1"

Write-Host ""
Write-Host "Generating NT8 context snapshot..." -ForegroundColor Cyan

$contextJson = ""
if (Test-Path $contextScript) {
    if ($DryRun) {
        $contextJson = & powershell.exe -NonInteractive -File $contextScript -OutFile $tempCtxFile -Pretty 2>$null
    } else {
        $contextJson = & powershell.exe -NonInteractive -File $contextScript -OutFile $tempCtxFile -Pretty 2>$null
    }
    if ($contextJson -eq "" -and (Test-Path $tempCtxFile)) {
        $contextJson = Get-Content $tempCtxFile -Raw
    }
} else {
    Write-Host "  WARNING: nt8-context.ps1 not found at $contextScript" -ForegroundColor Yellow
    Write-Host "  Context snapshot will be skipped." -ForegroundColor Yellow
    $contextJson = '{"error":"nt8-context.ps1 not found"}'
}

# ── Step 2: Read errors ───────────────────────────────────────────────────────

Write-Host "Reading NT8 compile errors via UIAutomation..." -ForegroundColor Cyan

$errors = Get-NT8Errors

# ── Step 3: If no errors, exit clean ─────────────────────────────────────────

if ($errors.Count -eq 0) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "  No errors found — system is healthy." -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""

    # Still print context so Claude has a clean snapshot
    Write-Host "=== CONTEXT SNAPSHOT ===" -ForegroundColor DarkGray
    Write-Output $contextJson
    Write-Host ""

    exit 0
}

# ── Step 4: Format error summary ──────────────────────────────────────────────

Write-Host ""
Write-Host ("=" * 68) -ForegroundColor Red
Write-Host "=== NT8 COMPILE ERRORS ($($errors.Count) errors) ===" -ForegroundColor Red
Write-Host ("=" * 68) -ForegroundColor Red
Write-Host ""

$idx = 1
foreach ($err in $errors) {
    $hint = Get-ErrorHint -Code $err.Code -Message $err.Message
    $locStr = if ($err.Line -gt 0) { ":$($err.Line)" } else { "" }
    $colStr = if ($err.Col -gt 0)  { " col $($err.Col)" } else { "" }

    Write-Host "[$idx] $($err.File)$locStr ($($err.Code))$colStr" -ForegroundColor Red
    Write-Host "    $($err.Message)" -ForegroundColor Yellow
    Write-Host "    -> $hint" -ForegroundColor Cyan
    Write-Host ""
    $idx++
}

Write-Host ("=" * 68) -ForegroundColor DarkGray
Write-Host "=== CONTEXT SNAPSHOT ===" -ForegroundColor DarkGray
Write-Host ("=" * 68) -ForegroundColor DarkGray
Write-Host ""
Write-Output $contextJson
Write-Host ""

Write-Host ("=" * 68) -ForegroundColor DarkGray
Write-Host "=== NEXT STEP ===" -ForegroundColor DarkGray
Write-Host ("=" * 68) -ForegroundColor DarkGray
Write-Host ""

if ($DryRun) {
    Write-Host "  [DRY RUN] No actions taken." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  To apply fixes, re-run without -DryRun." -ForegroundColor Gray
} else {
    Write-Host "  Run:  /nt8-fix" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Or paste this output to Claude with:" -ForegroundColor Gray
    Write-Host "    ""Fix these NT8 compile errors""" -ForegroundColor White
    Write-Host ""
    Write-Host "  Max iterations configured: $MaxIterations" -ForegroundColor DarkGray
}

if ($ContextFile -ne "" -or $tempCtxFile -ne "") {
    Write-Host ""
    Write-Host "  Context JSON saved to: $tempCtxFile" -ForegroundColor DarkGray
}

Write-Host ""

# Exit non-zero so callers can detect errors
exit 1
