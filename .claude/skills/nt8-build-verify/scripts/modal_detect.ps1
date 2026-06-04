# modal_detect.ps1 - Detect and safely dismiss NT8 modal dialogs before UIAutomation operations
# Called BEFORE every UIA operation by T9, T14, T16
#
# Usage:
#   modal_detect.ps1 [-WhatIf] [-TimeoutSeconds <n>]
#
# Exit codes: 0 = success, 2 = infrastructure failure (NT8 not running, etc.)
# Output: JSON with modals_found, modals_dismissed, blocked, details

[CmdletBinding(SupportsShouldProcess)]
param(
    [int]$TimeoutSeconds = 5
)

$ErrorActionPreference = "Stop"

# ── Load UIAutomation assemblies ─────────────────────────────────────────────
Add-Type -AssemblyName UIAutomationClient  -ErrorAction SilentlyContinue
Add-Type -AssemblyName UIAutomationTypes   -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue

# ── P/Invoke definitions (from nt8-ui.ps1 pattern) ──────────────────────────
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Modal {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@ -ErrorAction SilentlyContinue

# ── Helper: emit JSON and exit ───────────────────────────────────────────────
function Emit-Result {
    param(
        [int]$Found = 0,
        [int]$Dismissed = 0,
        [bool]$Blocked = $false,
        [string]$Error = $null,
        [array]$Details = @()
    )
    $result = @{
        modals_found     = $Found
        modals_dismissed = $Dismissed
        blocked          = $Blocked
        details          = $Details
    }
    if ($Error) { $result["error"] = $Error }
    Write-Output ($result | ConvertTo-Json -Depth 5 -Compress)
}

# ── 1. Find NinjaTrader process ──────────────────────────────────────────────
$nt8 = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $nt8) {
    Emit-Result -Error "NinjaTrader process not found"
    exit 2
}

$mainHandle = $nt8.MainWindowHandle

# ── 2. Enumerate all NT8 windows via UIAutomation ────────────────────────────
try {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $pidCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $nt8.Id
    )
    $allWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCondition)
} catch {
    Emit-Result -Error "UIAutomation enumeration failed: $($_.Exception.Message)"
    exit 2
}

# ── 3. Detect modals: windows that are NOT the main NT8 window ───────────────
# Known NT8 main windows: ControlCenter, NinjaScript Editor, Chart windows
# Modal dialogs: crash reports, update prompts, save prompts, error dialogs, license dialogs
$knownMainClasses = @("ControlCenter", "NinjaScriptEditorForm", "ChartWindow")
$modalKeywords    = @("save", "crash", "error", "update", "license", "exception", "warning", "confirm", "dialog")
$modals = @()

foreach ($win in $allWindows) {
    try {
        $handle    = $win.Current.NativeWindowHandle
        $title     = $win.Current.Name
        $className = $win.Current.ClassName
        $autoId    = $win.Current.AutomationId
    } catch {
        continue
    }

    # Skip the main window
    if ($handle -eq $mainHandle.ToInt32()) { continue }

    # Skip known NT8 application windows (charts, editor, control center)
    $isKnownMain = $false
    foreach ($cls in $knownMainClasses) {
        if ($className -like "*$cls*") { $isKnownMain = $true; break }
    }

    # Also skip windows with typical NT8 workspace titles (charts have instrument names)
    if ($title -like "*NinjaScript*" -and $className -notlike "*Dialog*") { continue }

    # Detect if this looks like a modal dialog
    $isModal = $false
    $modalReason = "unknown_child_window"

    # Check by class name
    if ($className -like "*Dialog*" -or $className -eq "#32770") {
        $isModal = $true
        $modalReason = "dialog_classname"
    }

    # Check by title keywords
    if (-not $isModal) {
        foreach ($kw in $modalKeywords) {
            if ($title -like "*$kw*") {
                $isModal = $true
                $modalReason = "title_keyword:$kw"
                break
            }
        }
    }

    # Only flag unrecognized windows if they have a non-empty title (actual dialogs have titles)
    # NT8 has many untitled WinForms child windows that are normal UI components, not modals
    if (-not $isModal -and -not $isKnownMain -and $title -and $title -ne "(no title)" -and $title.Trim() -ne "") {
        $isModal = $true
        $modalReason = "titled_child_window"
    }

    if ($isModal) {
        $modals += @{
            Title        = if ($title) { $title } else { "(no title)" }
            ClassName    = if ($className) { $className } else { "(unknown)" }
            AutomationId = if ($autoId) { $autoId } else { "" }
            Handle       = $handle
            Reason       = $modalReason
        }
    }
}

# ── 4. Dismiss modals (if not -WhatIf) ──────────────────────────────────────
$dismissed = 0
$blocked   = $false

foreach ($modal in $modals) {
    if ($WhatIfPreference) {
        # WhatIf mode: just report, don't dismiss
        continue
    }

    $thisDismissed = $false
    $modalHandle   = New-Object IntPtr($modal.Handle)

    try {
        # Get the UIAutomation element for this modal
        $modalElement = [System.Windows.Automation.AutomationElement]::FromHandle($modalHandle)
    } catch {
        $blocked = $true
        continue
    }

    # ── Strategy 1: Send Escape key ──────────────────────────────────────────
    try {
        [Win32Modal]::ShowWindow($modalHandle, 9) | Out-Null
        [Win32Modal]::SetForegroundWindow($modalHandle) | Out-Null
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait("{ESC}")
        Start-Sleep -Milliseconds 300

        # Verify the window is gone
        $stillExists = $false
        try {
            $check = [System.Windows.Automation.AutomationElement]::FromHandle($modalHandle)
            if ($check) { $stillExists = $true }
        } catch {
            $stillExists = $false
        }

        if (-not $stillExists) {
            $thisDismissed = $true
            $dismissed++
            continue
        }
    } catch { }

    # ── Strategy 2: Find and click "Cancel" button via UIAutomation ──────────
    if (-not $thisDismissed) {
        try {
            $btnCondition = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Button
            )
            $buttons = $modalElement.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants, $btnCondition
            )
            foreach ($btn in $buttons) {
                $btnName = $null
                try { $btnName = $btn.Current.Name } catch { continue }
                if ($btnName -eq "Cancel") {
                    $invokePattern = $btn.GetCurrentPattern(
                        [System.Windows.Automation.InvokePattern]::Pattern
                    )
                    $invokePattern.Invoke()
                    Start-Sleep -Milliseconds 300
                    $thisDismissed = $true
                    $dismissed++
                    break
                }
            }
        } catch { }
    }

    # ── Strategy 3: Find and click "No" button (for "Save Changes?" dialogs) ─
    if (-not $thisDismissed) {
        try {
            $btnCondition = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Button
            )
            $buttons = $modalElement.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants, $btnCondition
            )
            foreach ($btn in $buttons) {
                $btnName = $null
                try { $btnName = $btn.Current.Name } catch { continue }
                if ($btnName -eq "No") {
                    $invokePattern = $btn.GetCurrentPattern(
                        [System.Windows.Automation.InvokePattern]::Pattern
                    )
                    $invokePattern.Invoke()
                    Start-Sleep -Milliseconds 300
                    $thisDismissed = $true
                    $dismissed++
                    break
                }
            }
        } catch { }
    }

    # ── Strategy 4: Find and click "Close" button ────────────────────────────
    if (-not $thisDismissed) {
        try {
            $btnCondition = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Button
            )
            $buttons = $modalElement.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants, $btnCondition
            )
            foreach ($btn in $buttons) {
                $btnName = $null
                try { $btnName = $btn.Current.Name } catch { continue }
                if ($btnName -eq "Close") {
                    $invokePattern = $btn.GetCurrentPattern(
                        [System.Windows.Automation.InvokePattern]::Pattern
                    )
                    $invokePattern.Invoke()
                    Start-Sleep -Milliseconds 300
                    $thisDismissed = $true
                    $dismissed++
                    break
                }
            }
        } catch { }
    }

    # ── All strategies exhausted ─────────────────────────────────────────────
    if (-not $thisDismissed) {
        $blocked = $true
    }
}

# ── 5. Output JSON result ────────────────────────────────────────────────────
Emit-Result -Found $modals.Count -Dismissed $dismissed -Blocked $blocked -Details $modals
exit 0
