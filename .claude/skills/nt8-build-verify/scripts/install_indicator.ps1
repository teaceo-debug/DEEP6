[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ClassName,
    [string]$ChartTitle = "",
    [hashtable]$Parameters = @{},
    [string]$Panel = "price",
    [int]$SettleMs = 1500
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Install {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

function Write-JsonResult {
    param(
        [bool]$Installed,
        [bool]$LegendVerified,
        [string]$Error = $null,
        [bool]$BlockedByModal = $false,
        [int]$ExitCode = 0
    )

    $stopwatch.Stop()
    $result = [ordered]@{
        installed       = $Installed
        chart           = $ChartTitle
        class_name      = $ClassName
        legend_verified = $LegendVerified
        elapsed_ms      = $stopwatch.ElapsedMilliseconds
    }

    if ($BlockedByModal) { $result.blocked_by_modal = $true }
    if ($Error) { $result.error = $Error }

    Write-Output ($result | ConvertTo-Json -Compress)
    exit $ExitCode
}

function Invoke-PowerShellScriptCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    $psArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $ScriptPath
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

    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return $Text | ConvertFrom-Json } catch { return $null }
}

function Get-ElementText {
    param([System.Windows.Automation.AutomationElement]$Element)

    if ($null -eq $Element) { return "" }

    $value = ""
    try {
        $vp = $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $value = $vp.Current.Value
    } catch { }

    if ([string]::IsNullOrWhiteSpace($value)) {
        try { $value = $Element.Current.Name } catch { }
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        try {
            $tp = $Element.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $value = $tp.DocumentRange.GetText(512)
        } catch { }
    }

    return (($value -replace "`r`n|`r|`n", " ").Trim())
}

function Get-ElementNameSafe {
    param([System.Windows.Automation.AutomationElement]$Element)
    try { return $Element.Current.Name } catch { return "" }
}

function Get-ElementAutomationIdSafe {
    param([System.Windows.Automation.AutomationElement]$Element)
    try { return $Element.Current.AutomationId } catch { return "" }
}

function Test-ElementEnabled {
    param([System.Windows.Automation.AutomationElement]$Element)
    try { return [bool]$Element.Current.IsEnabled } catch { return $false }
}

function Set-ElementValue {
    param(
        [System.Windows.Automation.AutomationElement]$Element,
        [string]$Value
    )

    if ($null -eq $Element) { return $false }

    try {
        $vp = $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $vp.SetValue($Value)
        return $true
    } catch { }

    try {
        $Element.SetFocus()
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait("^a")
        Start-Sleep -Milliseconds 100
        [System.Windows.Forms.SendKeys]::SendWait($Value)
        return $true
    } catch {
        return $false
    }
}

function Invoke-ButtonLikeElement {
    param([System.Windows.Automation.AutomationElement]$Element)

    if ($null -eq $Element) { return $false }

    try {
        $ip = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $ip.Invoke()
        return $true
    } catch { }

    try {
        $Element.SetFocus()
        Start-Sleep -Milliseconds 150
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        return $true
    } catch {
        return $false
    }
}

function Select-ListItemLikeElement {
    param([System.Windows.Automation.AutomationElement]$Element)

    if ($null -eq $Element) { return $false }

    try {
        $sp = $Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $sp.Select()
        return $true
    } catch { }

    try {
        $ip = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $ip.Invoke()
        return $true
    } catch { }

    try {
        $Element.SetFocus()
        Start-Sleep -Milliseconds 150
        [System.Windows.Forms.SendKeys]::SendWait("{SPACE}")
        return $true
    } catch {
        return $false
    }
}

function Find-ProcessWindows {
    param([int]$ProcessId)

    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $procCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
        $ProcessId
    )
    return $root.FindAll([System.Windows.Automation.TreeScope]::Children, $procCondition)
}

function Find-ChartWindow {
    param([int]$ProcessId)

    $windows = Find-ProcessWindows -ProcessId $ProcessId
    $fallback = $null

    foreach ($win in $windows) {
        $title = Get-ElementNameSafe $win
        $className = ""
        try { $className = $win.Current.ClassName } catch { }

        if ($ChartTitle -and $title -match [regex]::Escape($ChartTitle)) {
            return $win
        }

        if (-not $fallback -and (
            $title -match 'Chart' -or
            $className -match 'Chart' -or
            $title -match 'Minute|Tick|Volumetric|Order Flow|NQ|MNQ|ES|MES'
        )) {
            $fallback = $win
        }
    }

    return $fallback
}

function Wait-ForDialogWindow {
    param(
        [int]$ProcessId,
        [int]$TimeoutMs = 4000
    )

    $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
    while ((Get-Date) -lt $deadline) {
        $windows = Find-ProcessWindows -ProcessId $ProcessId
        foreach ($win in $windows) {
            $name = Get-ElementNameSafe $win
            $className = ""
            try { $className = $win.Current.ClassName } catch { }

            if ($name -match 'Indicators?' -or $className -match 'Indicator') {
                return $win
            }
        }

        Start-Sleep -Milliseconds 250
    }

    return $null
}

function Find-DescendantsByControlType {
    param(
        [System.Windows.Automation.AutomationElement]$Parent,
        [System.Windows.Automation.ControlType]$ControlType
    )

    if ($null -eq $Parent) { return @() }
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        $ControlType
    )

    try {
        return @($Parent.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition))
    } catch {
        return @()
    }
}

function Find-BestSearchControl {
    param([System.Windows.Automation.AutomationElement]$Dialog)

    $candidates = @()
    $candidates += Find-DescendantsByControlType -Parent $Dialog -ControlType ([System.Windows.Automation.ControlType]::Edit)
    $candidates += Find-DescendantsByControlType -Parent $Dialog -ControlType ([System.Windows.Automation.ControlType]::ComboBox)

    $scored = foreach ($candidate in $candidates) {
        $name = Get-ElementNameSafe $candidate
        $autoId = Get-ElementAutomationIdSafe $candidate
        $score = 0

        if ($name -match 'search|filter|find|indicator') { $score += 5 }
        if ($autoId -match 'search|filter|find|indicator') { $score += 5 }
        if (Test-ElementEnabled $candidate) { $score += 2 }

        [PSCustomObject]@{
            Element = $candidate
            Score   = $score
            Name    = $name
            AutoId  = $autoId
        }
    }

    $best = $scored | Sort-Object Score -Descending | Select-Object -First 1
    if ($best) { return $best.Element }
    return $null
}

function Find-MatchingItems {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$Needle
    )

    $types = @(
        [System.Windows.Automation.ControlType]::ListItem,
        [System.Windows.Automation.ControlType]::TreeItem,
        [System.Windows.Automation.ControlType]::DataItem,
        [System.Windows.Automation.ControlType]::Text
    )

    $results = [System.Collections.Generic.List[object]]::new()
    foreach ($type in $types) {
        foreach ($item in (Find-DescendantsByControlType -Parent $Root -ControlType $type)) {
            $text = Get-ElementText $item
            if ($text -eq $Needle -or $text -like "*$Needle*") {
                $results.Add($item)
            }
        }
    }

    return @($results)
}

function Find-ButtonByName {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string[]]$Names
    )

    foreach ($button in (Find-DescendantsByControlType -Parent $Root -ControlType ([System.Windows.Automation.ControlType]::Button))) {
        $name = Get-ElementNameSafe $button
        $autoId = Get-ElementAutomationIdSafe $button
        foreach ($targetName in $Names) {
            if ($name -eq $targetName -or $name -like "*$targetName*" -or $autoId -like "*$targetName*") {
                return $button
            }
        }
    }

    return $null
}

function Test-LegendContainsClass {
    param([System.Windows.Automation.AutomationElement]$ChartWindow)

    if ($null -eq $ChartWindow) { return $false }

    # Best-effort legend scan. NT8 legend text may surface as Text, Custom, or ListItem descendants.
    foreach ($match in (Find-MatchingItems -Root $ChartWindow -Needle $ClassName)) {
        $text = Get-ElementText $match
        if ($text -eq $ClassName -or $text -like "*$ClassName*") {
            return $true
        }
    }

    return $false
}

function Test-DialogAlreadyContainsIndicator {
    param([System.Windows.Automation.AutomationElement]$Dialog)

    # Maintenance note:
    # NT8's Indicators dialog is not stable/documented. This script discovers controls dynamically.
    # Expected hierarchy variants seen in WinForms/WPF dialogs:
    #   Window("Indicators")
    #     -> Edit/ComboBox (search/filter)
    #     -> Tree/List on left (available indicators)
    #     -> Button("Add" | ">>")
    #     -> Tree/List on right (configured indicators already on chart)
    #     -> PropertyGrid / parameter editors
    #     -> Button("OK"), Button("Cancel")
    # We therefore use text + control-type heuristics instead of hard-coded AutomationIds.

    $matchCount = 0
    foreach ($match in (Find-MatchingItems -Root $Dialog -Needle $ClassName)) {
        $text = Get-ElementText $match
        if ($text -eq $ClassName -or $text -like "*$ClassName*") {
            $matchCount++
        }
    }

    return ($matchCount -ge 2)
}

# Step 1: modal detection
$modalScript = Join-Path $scriptDir "modal_detect.ps1"
$modalRun = Invoke-PowerShellScriptCapture -ScriptPath $modalScript -Arguments @("-TimeoutSeconds", "5")
$modalResult = Convert-JsonSafely -Text $modalRun.Output

if ($null -eq $modalResult -or $modalRun.ExitCode -ne 0 -or $modalResult.blocked) {
    Write-JsonResult -Installed $false -LegendVerified $false -Error "modal_blocked" -BlockedByModal $true -ExitCode 2
}

# Step 2: find NinjaTrader process and chart window
$nt8 = @(Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue)
if (-not $nt8 -or $nt8.Count -eq 0) {
    Write-JsonResult -Installed $false -LegendVerified $false -Error "NinjaTrader not running" -ExitCode 2
}

$nt8Main = $nt8 | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $nt8Main) { $nt8Main = $nt8 | Select-Object -First 1 }

$chartWindow = Find-ChartWindow -ProcessId $nt8Main.Id
if (-not $chartWindow) {
    Write-JsonResult -Installed $false -LegendVerified $false -Error "Chart window not found" -ExitCode 1
}

# Idempotency pass 1: chart legend already shows target indicator
$alreadyOnLegend = Test-LegendContainsClass -ChartWindow $chartWindow
if ($alreadyOnLegend) {
    Write-JsonResult -Installed $true -LegendVerified $true -ExitCode 0
}

# Step 3: foreground chart window
$chartHandle = [IntPtr]::new($chartWindow.Current.NativeWindowHandle)
[Win32Install]::ShowWindow($chartHandle, 9) | Out-Null
Start-Sleep -Milliseconds 250
[Win32Install]::SetForegroundWindow($chartHandle) | Out-Null
Start-Sleep -Milliseconds 500

# Step 4: open Indicators dialog (Ctrl+I)
[System.Windows.Forms.SendKeys]::SendWait("^i")
Start-Sleep -Milliseconds 1000

# Step 5: locate dialog
$indicatorDialog = Wait-ForDialogWindow -ProcessId $nt8Main.Id -TimeoutMs 5000
if (-not $indicatorDialog) {
    Write-JsonResult -Installed $false -LegendVerified $false -Error "Indicators dialog not found" -ExitCode 1
}

# Idempotency pass 2: detect current indicator list inside dialog before adding
$dialogAlreadyContains = Test-DialogAlreadyContainsIndicator -Dialog $indicatorDialog
if (-not $dialogAlreadyContains) {
    # Step 6: search/filter input discovery
    $searchBox = Find-BestSearchControl -Dialog $indicatorDialog
    if ($searchBox) {
        [void](Set-ElementValue -Element $searchBox -Value $ClassName)
        Start-Sleep -Milliseconds 500
    }

    # Step 7: locate indicator item and add it
    $indicatorItem = $null
    foreach ($candidate in (Find-MatchingItems -Root $indicatorDialog -Needle $ClassName)) {
        if ((Get-ElementText $candidate) -eq $ClassName) {
            $indicatorItem = $candidate
            break
        }
    }

    if (-not $indicatorItem) {
        foreach ($candidate in (Find-MatchingItems -Root $indicatorDialog -Needle $ClassName)) {
            if ((Get-ElementText $candidate) -like "*$ClassName*") {
                $indicatorItem = $candidate
                break
            }
        }
    }

    if (-not $indicatorItem) {
        try { [System.Windows.Forms.SendKeys]::SendWait("{ESC}") } catch { }
        Write-JsonResult -Installed $false -LegendVerified $false -Error "Indicator item not found" -ExitCode 1
    }

    [void](Select-ListItemLikeElement -Element $indicatorItem)
    Start-Sleep -Milliseconds 300

    $addButton = Find-ButtonByName -Root $indicatorDialog -Names @("Add", ">>", "Right", "Insert")
    $added = $false

    if ($addButton -and (Test-ElementEnabled $addButton)) {
        $added = Invoke-ButtonLikeElement -Element $addButton
    }

    if (-not $added) {
        try {
            $indicatorItem.SetFocus()
            Start-Sleep -Milliseconds 150
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            $added = $true
        } catch { }
    }

    if (-not $added) {
        try {
            $indicatorItem.SetFocus()
            Start-Sleep -Milliseconds 150
            [System.Windows.Forms.SendKeys]::SendWait(" ")
            $added = $true
        } catch { }
    }

    Start-Sleep -Milliseconds 500
}

# Parameters/panel intentionally not mutated here; orchestration only installs a single indicator.

# Step 8: close dialog with OK
$okButton = Find-ButtonByName -Root $indicatorDialog -Names @("OK")
if (-not $okButton) {
    $okButton = Find-ButtonByName -Root $indicatorDialog -Names @("Apply")
}

if (-not $okButton) {
    try {
        $indicatorDialog.SetFocus()
        Start-Sleep -Milliseconds 150
        [System.Windows.Forms.SendKeys]::SendWait("%o")
    } catch {
        Write-JsonResult -Installed $false -LegendVerified $false -Error "OK button not found" -ExitCode 1
    }
} else {
    [void](Invoke-ButtonLikeElement -Element $okButton)
}

# Step 9: wait for chart render
Start-Sleep -Milliseconds $SettleMs

# Step 10: best-effort legend verification
$legendVerified = Test-LegendContainsClass -ChartWindow $chartWindow

Write-JsonResult -Installed $true -LegendVerified $legendVerified -ExitCode 0
