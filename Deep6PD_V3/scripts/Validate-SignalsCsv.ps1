<#
.SYNOPSIS
  Deep6 v3 signals CSV validator (plan r2 Phase 0.14).
  The future Python validator inherits this contract.

.DESCRIPTION
  Checks, against the Phase 0 schema (3.0-p0):
   1. Schema comment line + exact header match.
   2. Every row has the full column count.
   3. No duplicate OPEN per SignalId; CLOSE only after its OPEN; pairing complete
      (un-paired OPENs reported — legitimate only for currently-active signals).
   4. exchangeBarTime monotonic non-decreasing in file order.
   5. evt/exitReason/dir vocabulary valid; ambiguous flag only on CLOSE rows.
   6. Per-cell W/L tallies recomputed from CLOSE rows and printed (the Phase 2
      validator will compare these against the persisted state file bit-for-bit).

.EXAMPLE
  .\Validate-SignalsCsv.ps1 -Path "$env:USERPROFILE\Documents\NinjaTrader 8\Deep6PD\v3\signals_v3_NQ_1m.csv"
#>
param(
    [Parameter(Mandatory = $true)] [string]$Path,
    [switch]$AllowOpenSignals    # pass when validating a live (not terminated) session
)

$ErrorActionPreference = 'Stop'
$failures = New-Object System.Collections.Generic.List[string]
function Fail([string]$msg) { $script:failures.Add($msg) }

if (-not (Test-Path $Path)) { Write-Host "FAIL: file not found: $Path"; exit 1 }

$expectedComment = '# deep6 signals schema=3.0-p0'
$expectedHeader  = 'schemaVersion,signalId,utcWall,exchangeBarTime,codeVersion,instrument,barPeriod,evt,tf,regime,dir,entry,target,stop,exitPrice,exitReason,ambiguous,note'
$expectedCols    = $expectedHeader.Split(',').Count

$lines = Get-Content $Path
if ($lines.Count -lt 2) { Write-Host "FAIL: file too short"; exit 1 }
if ($lines[0] -ne $expectedComment) { Fail "line 1: expected schema comment '$expectedComment', got '$($lines[0])'" }
if ($lines[1] -ne $expectedHeader)  { Fail "line 2: header mismatch" }

$validEvt    = @('OPEN', 'CLOSE', 'ABANDONED')
$validExit   = @('TARGET', 'STOP', 'TIMEOUT', 'INVALIDATED', 'ABANDONED', '')
$validDir    = @('L', 'S')
$openIds     = @{}
$closedIds   = @{}
$lastBarTime = [datetime]::MinValue
$cellTally   = @{}
$rowNum      = 2

foreach ($line in ($lines | Select-Object -Skip 2)) {
    $rowNum++
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $f = $line.Split(',')
    if ($f.Count -ne $expectedCols) { Fail "row ${rowNum}: $($f.Count) columns, expected $expectedCols"; continue }

    $schema = $f[0]; $id = $f[1]; $barTime = $f[3]; $evt = $f[7]; $tf = $f[8]; $regime = $f[9]
    $dir = $f[10]; $exitReason = $f[15]; $ambiguous = $f[16]

    if ($schema -ne '3.0-p0') { Fail "row ${rowNum}: schemaVersion '$schema'" }
    if ($validEvt -notcontains $evt) { Fail "row ${rowNum}: bad evt '$evt'" }
    if ($validDir -notcontains $dir) { Fail "row ${rowNum}: bad dir '$dir'" }
    if ($validExit -notcontains $exitReason) { Fail "row ${rowNum}: bad exitReason '$exitReason'" }
    if ($id.Length -lt 8) { Fail "row ${rowNum}: signalId missing/short" }

    $bt = [datetime]::MinValue
    if (-not [datetime]::TryParse($barTime, [ref]$bt)) { Fail "row ${rowNum}: unparseable exchangeBarTime '$barTime'" }
    elseif ($bt -lt $lastBarTime) { Fail "row ${rowNum}: exchangeBarTime went backwards ($barTime < $lastBarTime)" }
    else { $lastBarTime = $bt }

    if ($evt -eq 'OPEN') {
        if ($openIds.ContainsKey($id)) { Fail "row ${rowNum}: duplicate OPEN for SignalId $id" }
        if ($exitReason -ne '') { Fail "row ${rowNum}: OPEN row carries exitReason" }
        $openIds[$id] = $rowNum
    }
    else {
        if (-not $openIds.ContainsKey($id)) { Fail "row ${rowNum}: $evt without prior OPEN for SignalId $id" }
        if ($closedIds.ContainsKey($id)) { Fail "row ${rowNum}: SignalId $id closed twice" }
        $closedIds[$id] = $rowNum
        if ($evt -eq 'CLOSE') {
            if ($exitReason -eq '') { Fail "row ${rowNum}: CLOSE without exitReason" }
            if ($ambiguous -notin @('0', '1')) { Fail "row ${rowNum}: ambiguous flag '$ambiguous'" }
            $key = "$tf|$regime"
            if (-not $cellTally.ContainsKey($key)) { $cellTally[$key] = @{ W = 0; L = 0 } }
            if ($f[17] -like 'WIN*') { $cellTally[$key].W++ } else { $cellTally[$key].L++ }
        }
    }
}

$unpaired = @($openIds.Keys | Where-Object { -not $closedIds.ContainsKey($_) })
if ($unpaired.Count -gt 0 -and -not $AllowOpenSignals) {
    Fail "$($unpaired.Count) OPEN row(s) never closed (use -AllowOpenSignals for a live session): $($unpaired -join ', ')"
}

Write-Host "=== per-cell tallies recomputed from CSV (validator contract for Phase 2 state diff) ==="
foreach ($k in ($cellTally.Keys | Sort-Object)) {
    $t = $cellTally[$k]
    Write-Host ("  {0,-12} W={1}  L={2}  n={3}" -f $k, $t.W, $t.L, ($t.W + $t.L))
}
Write-Host ("rows={0}  opens={1}  closes={2}  unpaired={3}" -f ($rowNum - 2), $openIds.Count, $closedIds.Count, $unpaired.Count)

if ($failures.Count -eq 0) {
    Write-Host "VALIDATION PASSED"
    exit 0
}
Write-Host "VALIDATION FAILED — $($failures.Count) issue(s):"
$failures | ForEach-Object { Write-Host "  $_" }
exit 1
