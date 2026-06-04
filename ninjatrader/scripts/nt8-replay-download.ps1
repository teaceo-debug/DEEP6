# nt8-replay-download.ps1 - Automate native NT8 Market Replay downloads
#
# Usage examples:
#   nt8-replay-download.ps1                                  # MNQ latest configured contract, today only
#   nt8-replay-download.ps1 -StartDate 2026-04-21 -EndDate 2026-04-25
#   nt8-replay-download.ps1 -Instrument NQ -Contract 06-26 -StartDate 2026-04-24
#   nt8-replay-download.ps1 -ListContracts
#
# Notes:
# - NT8 must be running.
# - The script drives: Tools > Historical Data > Get Market Replay data.
# - It verifies success by checking Documents\NinjaTrader 8\db\replay\<instrument contract>\YYYYMMDD.nrd.

param(
    [string]$Instrument = 'MNQ',
    [string]$Contract = '06-26',
    [datetime]$StartDate = (Get-Date).Date,
    [datetime]$EndDate = [datetime]::MinValue,
    [int]$TimeoutSecondsPerDay = 90,
    [switch]$ListContracts,
    [switch]$Force,
    [switch]$KeepWindowOpen,
    [switch]$WhatIf
)

if ($EndDate -eq [datetime]::MinValue) {
    $EndDate = $StartDate
}

if ($EndDate -lt $StartDate) {
    throw "EndDate must be on or after StartDate."
}

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NT8ReplayNative {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
}
"@

$ReplayRoot = Join-Path $env:USERPROFILE 'Documents\NinjaTrader 8\db\replay'
$TargetContract = if ($Contract -and $Contract.Trim()) { "$Instrument $Contract" } else { $Instrument }
$TargetFolder = Join-Path $ReplayRoot $TargetContract

function Write-Section {
    param([string]$Text, [string]$Color = 'Cyan')
    Write-Host ""
    Write-Host $Text -ForegroundColor $Color
}

function Get-NT8Process {
    $procs = @(Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue)
    if (!$procs -or $procs.Count -eq 0) {
        throw 'NinjaTrader is not running. Start NT8 first.'
    }
    $main = $procs | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($main) { return $main }
    return ($procs | Select-Object -First 1)
}

function Focus-NativeWindow {
    param([IntPtr]$Handle)
    if ($Handle -eq [IntPtr]::Zero) { return }
    [NT8ReplayNative]::ShowWindow($Handle, 9) | Out-Null
    Start-Sleep -Milliseconds 250
    [NT8ReplayNative]::SetForegroundWindow($Handle) | Out-Null
    Start-Sleep -Milliseconds 300
}

function Get-WindowByName {
    param([string]$Name)
    $proc = Get-NT8Process
    $winCond = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
    )
    $wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
    for ($i = 0; $i -lt $wins.Count; $i++) {
        $w = $wins.Item($i)
        if ($w.Current.Name -eq $Name) { return $w }
    }
    return $null
}

function Find-Control {
    param(
        [Parameter(Mandatory)]$Root,
        [string]$AutomationId,
        [string]$Name,
        [System.Windows.Automation.ControlType]$ControlType,
        [System.Windows.Automation.TreeScope]$Scope = [System.Windows.Automation.TreeScope]::Descendants
    )

    $conds = New-Object System.Collections.Generic.List[System.Windows.Automation.Condition]
    if ($AutomationId) {
        $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$AutomationId)))
    }
    if ($Name) {
        $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$Name)))
    }
    if ($ControlType) {
        $conds.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$ControlType)))
    }

    if ($conds.Count -eq 0) {
        throw 'Find-Control requires at least one selector.'
    }
    if ($conds.Count -eq 1) {
        $cond = $conds[0]
    } else {
        $cond = New-Object System.Windows.Automation.AndCondition($conds.ToArray())
    }
    return $Root.FindFirst($Scope, $cond)
}

function Get-ControlCenterWindow {
    $proc = Get-NT8Process

    if ($proc.MainWindowHandle -ne 0) {
        $main = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
        if ($main) {
            $mainTools = Find-Control -Root $main -Name 'Tools' -ControlType ([System.Windows.Automation.ControlType]::MenuItem)
            if ($mainTools) { return $main }
        }
    }

    $winCond = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
    )
    $wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$winCond)
    for ($i = 0; $i -lt $wins.Count; $i++) {
        $w = $wins.Item($i)
        $tools = Find-Control -Root $w -Name 'Tools' -ControlType ([System.Windows.Automation.ControlType]::MenuItem)
        if ($tools) { return $w }
    }
    throw 'Could not find the NinjaTrader Control Center window.'
}

function Close-WindowByName {
    param([Parameter(Mandatory)][string]$Name)
    $existing = Get-WindowByName -Name $Name
    if ($existing) {
        $close = Find-Control -Root $existing -AutomationId 'NTWindowButtonClose' -ControlType ([System.Windows.Automation.ControlType]::Button)
        if ($close) {
            try { $close.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch { }
            Start-Sleep -Milliseconds 700
        }
    }
}

function Open-HistoricalDataWindow {
    Close-WindowByName -Name 'Historical Data'
    Close-WindowByName -Name 'Playback'

    $cc = Get-ControlCenterWindow
    Focus-NativeWindow ([IntPtr]$cc.Current.NativeWindowHandle)
    $tools = Find-Control -Root $cc -Name 'Tools' -ControlType ([System.Windows.Automation.ControlType]::MenuItem)
    if (!$tools) { throw 'Tools menu not found in Control Center.' }
    $tools.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
    Start-Sleep -Milliseconds 400

    $hist = Find-Control -Root ([System.Windows.Automation.AutomationElement]::RootElement) -Name 'Historical Data' -ControlType ([System.Windows.Automation.ControlType]::MenuItem)
    if (!$hist) { throw 'Historical Data menu item not found.' }
    $hist.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Seconds 2

    $window = Get-WindowByName -Name 'Historical Data'
    if (!$window) { throw 'Historical Data window did not open.' }
    Focus-NativeWindow ([IntPtr]$window.Current.NativeWindowHandle)
    return $window
}

function Ensure-ExpandState {
    param(
        [Parameter(Mandatory)]$Element,
        [ValidateSet('Expanded','Collapsed')][string]$State = 'Expanded'
    )
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    $want = [System.Windows.Automation.ExpandCollapseState]::$State
    if ($pattern.Current.ExpandCollapseState -ne $want) {
        if ($State -eq 'Expanded') { $pattern.Expand() } else { $pattern.Collapse() }
        Start-Sleep -Milliseconds 300
    }
}

function Ensure-ReplaySectionOpen {
    param([Parameter(Mandatory)]$Window)

    $treeItems = $Window.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TreeItem))
    )
    if ($treeItems.Count -ge 2) {
        $marketReplayItem = $treeItems.Item(1)
        Ensure-ExpandState -Element $marketReplayItem -State Expanded
        $sel = $marketReplayItem.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $sel.Select()
        Start-Sleep -Milliseconds 200
    }

    $replayExpander = Find-Control -Root $Window -AutomationId 'HistoricalDataWindowMarketReplayExpander'
    if (!$replayExpander) { throw 'Get Market Replay data section not found.' }
    Ensure-ExpandState -Element $replayExpander -State Expanded
}

function Get-ReplaySelector {
    param([Parameter(Mandatory)]$Window)
    $selector = Find-Control -Root $Window -AutomationId 'HistoricalDataWindowMarketReplayInstrumentSelector'
    if (!$selector) { throw 'Replay instrument selector not found.' }
    return $selector
}

function Get-AvailableReplayContracts {
    param([Parameter(Mandatory)]$Window)
    $selector = Get-ReplaySelector -Window $Window
    Ensure-ExpandState -Element $selector -State Expanded
    Start-Sleep -Milliseconds 400

    $proc = Get-NT8Process
    $menuItems = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.AndCondition(
            (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
            (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
        ))
    )

    $contracts = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $menuItems.Count; $i++) {
        $item = $menuItems.Item($i)
        $id = $item.Current.AutomationId
        $name = $item.Current.Name
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        if ($id -in @('instruments','Micros',$Instrument,'NQ','MNQ')) { continue }
        if ($name -eq 'Select') { continue }
        if ($id -match '^[A-Z]+\s\d{2}-\d{2}$') {
            if (-not $contracts.Contains($id)) { [void]$contracts.Add($id) }
        }
    }
    $sorted = $contracts | Sort-Object
    if ((!$sorted -or $sorted.Count -eq 0) -and $Window) {
        # Retry once from a fresh UI state; NT8 sometimes leaves the selector stale.
        Ensure-ReplaySectionOpen -Window $Window
        $selector = Get-ReplaySelector -Window $Window
        Ensure-ExpandState -Element $selector -State Expanded
        Start-Sleep -Milliseconds 600
        $menuItems = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            (New-Object System.Windows.Automation.AndCondition(
                (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
                (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
            ))
        )
        for ($i = 0; $i -lt $menuItems.Count; $i++) {
            $item = $menuItems.Item($i)
            $id = $item.Current.AutomationId
            $name = $item.Current.Name
            if ([string]::IsNullOrWhiteSpace($id)) { continue }
            if ($id -in @('instruments','Micros',$Instrument,'NQ','MNQ')) { continue }
            if ($name -eq 'Select') { continue }
            if ($id -match '^[A-Z]+\s\d{2}-\d{2}$') {
                if (-not $contracts.Contains($id)) { [void]$contracts.Add($id) }
            }
        }
        $sorted = $contracts | Sort-Object
    }
    return $sorted
}

function Select-ReplayContract {
    param(
        [Parameter(Mandatory)]$Window,
        [Parameter(Mandatory)][string]$FullContract
    )

    $selector = Get-ReplaySelector -Window $Window
    Ensure-ExpandState -Element $selector -State Expanded
    Start-Sleep -Milliseconds 400

    $proc = Get-NT8Process
    $allContracts = Get-AvailableReplayContracts -Window $Window
    $candidate = $allContracts | Where-Object { $_ -eq $FullContract } | Select-Object -First 1
    if (!$candidate) {
        $candidate = $allContracts | Where-Object { $_ -like "$Instrument *" } | Sort-Object -Descending | Select-Object -First 1
    }
    if (!$candidate) {
        throw "No replay contract candidates found for $Instrument. Available: $($allContracts -join ', ')"
    }

    $cond = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$candidate)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$proc.Id))
    )
    $item = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
    if (!$item) {
        throw "Replay contract menu item '$candidate' not found."
    }
    $item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Milliseconds 500

    $textBox = Find-Control -Root $Window -AutomationId 'textBox'
    $actual = $textBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    if ($actual -ne $candidate) {
        throw "Instrument selector did not settle on '$candidate' (actual: '$actual')."
    }
    return $candidate
}

function Set-ReplayDate {
    param(
        [Parameter(Mandatory)]$Window,
        [Parameter(Mandatory)][datetime]$Date
    )
    $dateBox = Find-Control -Root $Window -AutomationId 'HistoricalDataWindowMarketReplayDateSelector'
    if (!$dateBox) { throw 'Replay date selector not found.' }
    $dateString = $Date.ToString('MM/dd/yyyy')
    $dateBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($dateString)
    Start-Sleep -Milliseconds 400
    $actual = $dateBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    if ($actual -ne $dateString) {
        throw "Replay date selector did not settle on '$dateString' (actual: '$actual')."
    }
    return $dateString
}

function Get-ReplayFilePath {
    param(
        [Parameter(Mandatory)][string]$ContractName,
        [Parameter(Mandatory)][datetime]$Date
    )
    return (Join-Path (Join-Path $ReplayRoot $ContractName) ($Date.ToString('yyyyMMdd') + '.nrd'))
}

function Wait-ForReplayFile {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastSize = -1
    $stableTicks = 0
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $FilePath) {
            $size = (Get-Item $FilePath).Length
            if ($size -eq $lastSize -and $size -gt 0) {
                $stableTicks++
            } else {
                $stableTicks = 0
                $lastSize = $size
            }
            if ($stableTicks -ge 2) {
                return @{ exists = $true; size = $size; stable = $true }
            }
        }
        Start-Sleep -Seconds 1
    }
    if (Test-Path $FilePath) {
        return @{ exists = $true; size = (Get-Item $FilePath).Length; stable = $false }
    }
    return @{ exists = $false; size = 0; stable = $false }
}

function Invoke-ReplayDownload {
    param(
        [Parameter(Mandatory)]$Window,
        [Parameter(Mandatory)][string]$ContractName,
        [Parameter(Mandatory)][datetime]$Date
    )

    $filePath = Get-ReplayFilePath -ContractName $ContractName -Date $Date
    if ($Date.DayOfWeek -eq [System.DayOfWeek]::Saturday) {
        return [pscustomobject]@{
            date = $Date.ToString('yyyy-MM-dd')
            contract = $ContractName
            file = $filePath
            status = 'skipped_weekend'
            note = 'Saturday has no regular CME futures session; NT8 replay downloads may hang or create stub files.'
        }
    }
    if ((Test-Path $filePath) -and -not $Force) {
        return [pscustomobject]@{
            date = $Date.ToString('yyyy-MM-dd')
            contract = $ContractName
            file = $filePath
            status = 'already_exists'
            note = 'Use -Force to attempt re-download.'
        }
    }

    $downloadButton = Find-Control -Root $Window -AutomationId 'HistoricalDataWindowMarketReplayDownloadButton'
    $continueButton = Find-Control -Root $Window -AutomationId 'btnContinue'
    if (!$downloadButton) { throw 'Replay download button not found.' }

    if (-not $downloadButton.Current.IsEnabled) {
        $selector = Find-Control -Root $Window -AutomationId 'HistoricalDataWindowMarketReplayInstrumentSelector'
        $selectorValue = $selector.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
        $dateBox = Find-Control -Root $Window -AutomationId 'HistoricalDataWindowMarketReplayDateSelector'
        $dateValue = $dateBox.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
        $mainTitle = (Get-NT8Process).MainWindowTitle
        return [pscustomobject]@{
            date = $Date.ToString('yyyy-MM-dd')
            contract = $ContractName
            file = $filePath
            status = 'button_disabled'
            note = "Download button disabled. selector='$selectorValue' date='$dateValue' continueEnabled=$($continueButton.Current.IsEnabled) mainWindow='$mainTitle'. Common causes on this machine: NT8 Playback session state/modal windows or local NT8 DB corruption (see trace log SQLite malformed-database errors)."
        }
    }

    if ($WhatIf) {
        return [pscustomobject]@{
            date = $Date.ToString('yyyy-MM-dd')
            contract = $ContractName
            file = $filePath
            status = 'what_if'
            note = 'Download click skipped.'
        }
    }

    $downloadButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $wait = Wait-ForReplayFile -FilePath $filePath -TimeoutSeconds $TimeoutSecondsPerDay
    if ($wait.exists) {
        return [pscustomobject]@{
            date = $Date.ToString('yyyy-MM-dd')
            contract = $ContractName
            file = $filePath
            status = 'downloaded'
            note = "size=$($wait.size) stable=$($wait.stable)"
        }
    }

    return [pscustomobject]@{
        date = $Date.ToString('yyyy-MM-dd')
        contract = $ContractName
        file = $filePath
        status = 'timeout'
        note = "File not observed within ${TimeoutSecondsPerDay}s."
    }
}

Write-Section "NT8 Replay Download -- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" 'Green'
Write-Host "Instrument root : $Instrument"
Write-Host "Requested      : $TargetContract"
Write-Host "Date range      : $($StartDate.ToString('yyyy-MM-dd')) -> $($EndDate.ToString('yyyy-MM-dd'))"
Write-Host "Replay root     : $ReplayRoot"

$window = Open-HistoricalDataWindow
Ensure-ReplaySectionOpen -Window $window
$contracts = Get-AvailableReplayContracts -Window $window

if ($ListContracts) {
    Write-Section 'Available replay contracts'
    if ($contracts.Count -eq 0) {
        Write-Host '  (none found)'
    } else {
        $contracts | ForEach-Object { Write-Host "  $_" }
    }
    exit 0
}

$chosenContract = Select-ReplayContract -Window $window -FullContract $TargetContract
Write-Host "Resolved contract: $chosenContract" -ForegroundColor Yellow

$results = New-Object System.Collections.Generic.List[object]
$current = $StartDate.Date
while ($current -le $EndDate.Date) {
    $dateString = Set-ReplayDate -Window $window -Date $current
    Write-Host "Processing $chosenContract $dateString ..." -ForegroundColor Cyan
    $result = Invoke-ReplayDownload -Window $window -ContractName $chosenContract -Date $current
    [void]$results.Add($result)
    $current = $current.AddDays(1)
}

if (-not $KeepWindowOpen) {
    $close = Find-Control -Root $window -AutomationId 'NTWindowButtonClose'
    if ($close) {
        try { $close.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch { }
    }
}

Write-Section 'Replay download summary'
$results | Format-Table date, contract, status, note -AutoSize

$failures = @($results | Where-Object { $_.status -notin @('downloaded','already_exists','what_if','skipped_weekend') })
if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "One or more dates did not complete cleanly." -ForegroundColor Yellow
    $results | ConvertTo-Json -Depth 4
    exit 2
}

$results | ConvertTo-Json -Depth 4
