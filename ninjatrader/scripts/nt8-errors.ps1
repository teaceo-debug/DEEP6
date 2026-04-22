# nt8-errors.ps1 - Read NT8 NinjaScript Editor Output Window via UIAutomation
# Returns compile errors (CS#### codes and descriptions) from the NT8 Output Window.
# Falls back to tailing the NT8 trace log if the Output Window is not accessible.
#
# Usage: nt8-errors.ps1 [-Format Text|Json] [-Last <n>]
# Exit codes:
#   0 = no errors found
#   1 = errors found
#   2 = NT8 not running or Output Window not accessible (fallback also failed)

param(
    [ValidateSet("Text","Json")]
    [string]$Format = "Text",
    [int]$Last = 0
)

$ErrorActionPreference = "SilentlyContinue"

# ── UIAutomation assemblies ────────────────────────────────────────────────────
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms   # for fallback clipboard trick if needed

# ── Helpers ───────────────────────────────────────────────────────────────────

function Parse-ErrorLine {
    param([string]$line)
    # Normalise: strip leading timestamps / whitespace
    $line = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($line)) { return $null }

    $obj = [PSCustomObject]@{
        type    = "info"
        code    = ""
        message = $line
        file    = ""
        line    = 0
        column  = 0
        raw     = $line
    }

    # Detect type
    if ($line -match "\berror\b" -or $line -match "CS\d{4}" -and $line -match "error") {
        $obj.type = "error"
    } elseif ($line -match "\bwarning\b") {
        $obj.type = "warning"
    }

    # Extract CS#### code
    if ($line -match "(CS\d{4})") {
        $obj.code = $matches[1]
    }

    # Extract file path + line + column
    # Pattern: "C:\path\to\file.cs(42,7): error CS0246: ..."
    if ($line -match "^(.+\.cs)\((\d+),(\d+)\):\s*(error|warning)\s+(CS\d+):\s*(.+)$") {
        $obj.file    = $matches[1]
        $obj.line    = [int]$matches[2]
        $obj.column  = [int]$matches[3]
        $obj.type    = $matches[4].ToLower()
        $obj.code    = $matches[5]
        $obj.message = $matches[6].Trim()
    }
    # Pattern without column: "C:\path\file.cs(42): error CS0246: ..."
    elseif ($line -match "^(.+\.cs)\((\d+)\):\s*(error|warning)\s+(CS\d+):\s*(.+)$") {
        $obj.file    = $matches[1]
        $obj.line    = [int]$matches[2]
        $obj.type    = $matches[3].ToLower()
        $obj.code    = $matches[4]
        $obj.message = $matches[5].Trim()
    }

    return $obj
}

function Is-RelevantLine {
    param([string]$line)
    return ($line -match "CS\d{4}" -or
            $line -match "\berror\b" -or
            $line -match "\bwarning\b" -or
            $line -match "\\Custom\\" -or
            $line -match "\\bin\\Custom\\")
}

function Output-Results {
    param([object[]]$items)

    if ($Last -gt 0 -and $items.Count -gt $Last) {
        $items = $items | Select-Object -Last $Last
    }

    if ($Format -eq "Json") {
        $items | ConvertTo-Json -Depth 3
    } else {
        foreach ($i in $items) {
            $color = switch ($i.type) {
                "error"   { "Red" }
                "warning" { "Yellow" }
                default   { "Gray" }
            }
            Write-Host $i.raw -ForegroundColor $color
        }
    }
}

# ── 1. Verify NT8 is running ───────────────────────────────────────────────────
$nt8 = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
if (!$nt8) {
    if ($Format -eq "Json") {
        Write-Output "[]"
    } else {
        Write-Host "NT8 is not running." -ForegroundColor Yellow
    }
    exit 2
}

# ── 2. UIAutomation tree walk ──────────────────────────────────────────────────
# Strategy:
#   a) Find all top-level windows owned by NT8 process
#   b) For each window, search descendants for TextPattern-capable elements
#      whose Name/AutomationId hints at "Output", "Editor", "NinjaScript"
#   c) Also look for list/data-grid items that contain CS#### text
#   d) Collect all text, filter to relevant lines

$ErrorActionPreference = "Continue"

$allErrorLines = [System.Collections.Generic.List[object]]::new()
$uiSuccess     = $false

try {
    $pidCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
        [int]$nt8.Id
    )

    $nt8Windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        $pidCondition
    )

    if ($nt8Windows -and $nt8Windows.Count -gt 0) {

        # Helper: recursively collect text from an element subtree
        function Get-ElementText {
            param($element, [int]$depth = 0)
            if ($depth -gt 8) { return @() }

            $texts = [System.Collections.Generic.List[string]]::new()

            # Try TextPattern first (richest)
            try {
                $tp = $element.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
                if ($tp) {
                    $docRange = $tp.DocumentRange
                    $text = $docRange.GetText(65536)
                    if (![string]::IsNullOrWhiteSpace($text)) {
                        $text -split "`n" | ForEach-Object { $texts.Add($_) }
                        return $texts
                    }
                }
            } catch {}

            # Try ValuePattern (single-line edits, some list controls)
            try {
                $vp = $element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ($vp) {
                    $val = $vp.Current.Value
                    if (![string]::IsNullOrWhiteSpace($val)) {
                        $val -split "`n" | ForEach-Object { $texts.Add($_) }
                    }
                }
            } catch {}

            # Name property (list items, labels)
            try {
                $name = $element.Current.Name
                if (![string]::IsNullOrWhiteSpace($name) -and $name.Length -lt 2000) {
                    $texts.Add($name)
                }
            } catch {}

            # Recurse into children
            try {
                $children = $element.FindAll(
                    [System.Windows.Automation.TreeScope]::Children,
                    [System.Windows.Automation.Condition]::TrueCondition
                )
                foreach ($child in $children) {
                    Get-ElementText -element $child -depth ($depth + 1) | ForEach-Object { $texts.Add($_) }
                }
            } catch {}

            return $texts
        }

        # Condition: elements whose Name or AutomationId hints at output/editor panels
        $trueCondition = [System.Windows.Automation.Condition]::TrueCondition

        foreach ($win in $nt8Windows) {
            $winName = ""
            try { $winName = $win.Current.Name } catch {}

            # Search descendants for output-related panels
            $candidates = [System.Collections.Generic.List[object]]::new()

            # a) Direct search by AutomationId containing "output" / "editor"
            try {
                $allDesc = $win.FindAll(
                    [System.Windows.Automation.TreeScope]::Descendants,
                    $trueCondition
                )

                foreach ($el in $allDesc) {
                    $elName = ""
                    $elId   = ""
                    try { $elName = $el.Current.Name }         catch {}
                    try { $elId   = $el.Current.AutomationId } catch {}

                    $isOutput = ($elName -match "(?i)output|ninjascript.*editor|compile|error" -or
                                 $elId   -match "(?i)output|ninjascript|compile|error")

                    # Also grab list/document controls that might hold error lines
                    $ctrlType = [System.Windows.Automation.ControlType]::Unknown
                    try { $ctrlType = $el.Current.ControlType } catch {}

                    $isTextControl = ($ctrlType -eq [System.Windows.Automation.ControlType]::Document -or
                                      $ctrlType -eq [System.Windows.Automation.ControlType]::List -or
                                      $ctrlType -eq [System.Windows.Automation.ControlType]::DataGrid -or
                                      $ctrlType -eq [System.Windows.Automation.ControlType]::Tree)

                    if ($isOutput -or $isTextControl) {
                        $candidates.Add($el)
                    }
                }
            } catch {}

            # b) Walk candidates and extract text
            foreach ($cand in $candidates) {
                $lines = Get-ElementText -element $cand
                foreach ($ln in $lines) {
                    if (Is-RelevantLine $ln) {
                        $parsed = Parse-ErrorLine $ln
                        if ($parsed) { $allErrorLines.Add($parsed) }
                    }
                }
            }

            # c) If no candidates found, try TextPattern on the window itself
            if ($candidates.Count -eq 0) {
                $lines = Get-ElementText -element $win
                foreach ($ln in $lines) {
                    if (Is-RelevantLine $ln) {
                        $parsed = Parse-ErrorLine $ln
                        if ($parsed) { $allErrorLines.Add($parsed) }
                    }
                }
            }
        }

        # De-duplicate by raw text
        $seen = [System.Collections.Generic.HashSet[string]]::new()
        $deduped = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $allErrorLines) {
            if ($seen.Add($item.raw)) { $deduped.Add($item) }
        }
        $allErrorLines = $deduped

        if ($allErrorLines.Count -gt 0) {
            $uiSuccess = $true
        }
    }
} catch {
    # UIAutomation failed entirely — will fall through to trace log fallback
    $uiSuccess = $false
}

# ── 3. Fallback: NT8 trace log ─────────────────────────────────────────────────
if (!$uiSuccess) {
    $traceDir = "$env:USERPROFILE\Documents\NinjaTrader 8\trace"
    $logDir   = "$env:USERPROFILE\Documents\NinjaTrader 8\log"

    $traceFile = $null

    # Check trace directory first (most detailed compile output)
    if (Test-Path $traceDir) {
        $traceFile = Get-ChildItem $traceDir -Filter "*.log" -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTime -Descending |
                     Select-Object -First 1 -ExpandProperty FullName

        if (!$traceFile) {
            $traceFile = Get-ChildItem $traceDir -Filter "*.txt" -ErrorAction SilentlyContinue |
                         Sort-Object LastWriteTime -Descending |
                         Select-Object -First 1 -ExpandProperty FullName
        }
    }

    # Fall back to daily log
    if (!$traceFile -and (Test-Path $logDir)) {
        $todayLog = Join-Path $logDir "$(Get-Date -Format 'yyyy-MM-dd').txt"
        if (Test-Path $todayLog) {
            $traceFile = $todayLog
        } else {
            $traceFile = Get-ChildItem $logDir -Filter "*.txt" -ErrorAction SilentlyContinue |
                         Sort-Object LastWriteTime -Descending |
                         Select-Object -First 1 -ExpandProperty FullName
        }
    }

    if ($traceFile -and (Test-Path $traceFile)) {
        # Read last 500 lines — compile events are recent
        $logLines = Get-Content $traceFile -Tail 500 -ErrorAction SilentlyContinue
        if ($logLines) {
            foreach ($ln in $logLines) {
                if (Is-RelevantLine $ln) {
                    $parsed = Parse-ErrorLine $ln
                    if ($parsed) { $allErrorLines.Add($parsed) }
                }
            }
        }

        if ($allErrorLines.Count -gt 0) {
            $uiSuccess = $true  # fallback produced results
        }
    }
}

# ── 4. Output results ─────────────────────────────────────────────────────────
if ($allErrorLines.Count -eq 0) {
    if ($Format -eq "Json") {
        Write-Output "[]"
    } else {
        if (!$uiSuccess) {
            Write-Host "NT8 Output Window not accessible and no trace log found." -ForegroundColor Yellow
            exit 2
        }
        Write-Host "No compile errors found." -ForegroundColor Green
    }
    exit 0
}

$errors   = $allErrorLines | Where-Object { $_.type -eq "error" }
$warnings = $allErrorLines | Where-Object { $_.type -eq "warning" }

if ($Format -ne "Json") {
    Write-Host ""
    Write-Host "NT8 Compile Output -- $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "  Errors:   $($errors.Count)" -ForegroundColor $(if ($errors.Count -gt 0) { "Red" } else { "Green" })
    Write-Host "  Warnings: $($warnings.Count)" -ForegroundColor $(if ($warnings.Count -gt 0) { "Yellow" } else { "Gray" })
    Write-Host ""
}

Output-Results -items $allErrorLines

if ($errors.Count -gt 0) { exit 1 }
exit 0
