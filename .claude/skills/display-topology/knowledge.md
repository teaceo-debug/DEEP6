# Display Topology Knowledge Base

> 4-screen monitor setup for DEEP6 development environment.
> All applications have RANDOM screen placement — no fixed positions.
> Use the Screen Mapping Table and Runtime Detection Commands to locate windows dynamically.

---

## 1. Overview

DEEP6 uses an ASUS ZenBook Duo UX8406MA with dual 14" OLED screens on the left and an INNOVIEW INVPM609 dual 23.8" IPS external monitor setup directly in front, creating a 4-display 2×2 topology. The laptop screens are the left column, the external screens are the right column, and all applications (NinjaTrader, TradingView, terminal, Claude) can appear on any screen at runtime, so every workflow must detect window placement dynamically.

---

## 2. Screen Mapping Table

> ⚠️ CRITICAL: Windows DISPLAY numbering does NOT match the user's Screen 1–4 numbering.
> Screen 2 = DISPLAY3, Screen 3 = DISPLAY2. The table below is the single source of truth.

| User Name | Windows Device | Hardware ID | Panel | Size | Connection | Physical Position |
|-----------|---------------|-------------|-------|------|------------|-------------------|
| Screen 1 | `\\.\DISPLAY1` (Primary) | SDC419D (UID8392785) | Samsung OLED | 14" | DisplayPort Internal | LEFT, upper |
| Screen 2 | `\\.\DISPLAY3` | SDC419D (UID8388688) | Samsung OLED | 14" | Internal Bus | LEFT, lower |
| Screen 3 | `\\.\DISPLAY2` | YCT428A (UID8261) | InnoView IPS | 23.8" | USB-C (DP Alt Mode) | FRONT, upper |
| Screen 4 | `\\.\DISPLAY4` | YCT428A (UID41016) | InnoView IPS | 23.8" | HDMI | FRONT, lower |

---

## 3. Windows Coordinate System

> Last verified: 2026-05-13
>
> ⚠️ DPI SCALING NOTE: Most Windows APIs (GetWindowRect, Screen.Bounds, Screen.WorkingArea) report
> LOGICAL pixels, NOT native pixels. ZenBook screens have 200% DPI — native 2880×1800 appears as
> 1440×900 in logical coordinates. InnoView screens run at 100% DPI — logical = native.
> Always work in logical pixel coordinates when using Window APIs.

| User Name | Windows ID | Logical Position (X,Y) | Logical Size (W×H) | Working Area H | DPI Scale | Native Resolution |
|-----------|-----------|----------------------|---------------------|----------------|-----------|-------------------|
| Screen 1 | DISPLAY1 | (0, 0) | 1440 × 900 | 852 px | 200% | 2880 × 1800 |
| Screen 2 | DISPLAY3 | (0, 1800) | 1440 × 900 | 852 px | 200% | 2880 × 1800 |
| Screen 3 | DISPLAY2 | (2880, 586) | 1920 × 1080 | 1032 px | 100% | 1920 × 1080 |
| Screen 4 | DISPLAY4 | (2880, 1666) | 1920 × 1080 | 1032 px | 100% | 1920 × 1080 |

**Working Area** = Bounds minus taskbar height (~48px).
**Virtual Desktop**: Total addressable space spans X: 0–4800, Y: 0–2746 (logical pixels).
**Primary screen**: DISPLAY1 — origin (0,0). All other screen positions are relative to this origin.

---

## 4. Physical Layout

```
LEFT (ZenBook Duo — 14" OLED)        FRONT (INNOVIEW INVPM609 — 23.8" IPS)

┌─────────────────────┐
│      Screen 1       │
│      DISPLAY1       │              ┌───────────────────────────┐
│    1440 × 900       │              │         Screen 3          │
│     (PRIMARY)       │              │         DISPLAY2          │
│      200% DPI       │              │       1920 × 1080         │
│     14" OLED        │              │        100% DPI           │
└─────────────────────┘              │      USB-C (DP Alt)       │
                                     └───────────────────────────┘
┌─────────────────────┐              ┌───────────────────────────┐
│      Screen 2       │              │         Screen 4          │
│      DISPLAY3       │              │         DISPLAY4          │
│    1440 × 900       │              │       1920 × 1080         │
│      200% DPI       │              │        100% DPI           │
│     14" OLED        │              │          HDMI             │
└─────────────────────┘              └───────────────────────────┘
```

User sits **in front of** the external monitors. Laptop is to the **left**.

---

## 5. Runtime Window Detection Commands

> Use these inline PowerShell commands to find windows at runtime.
> Do NOT create .ps1 script files — paste these directly into the Bash tool.

### 5a. Find which screen a window is on (by process name)

```powershell
Add-Type -AssemblyName System.Windows.Forms
$proc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if ($proc) {
    $screen = [System.Windows.Forms.Screen]::FromHandle($proc.MainWindowHandle)
    Write-Output "Process on: $($screen.DeviceName) | Bounds: $($screen.Bounds) | Primary: $($screen.Primary)"
} else {
    Write-Output "Process not found or no visible window"
}
```

Replace `'NinjaTrader'` with any process name: `'TradingView'`, `'WindowsTerminal'`, `'Code'`, etc.

### 5b. List all screens with live coordinates (re-scan)

```powershell
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    "$($_.DeviceName) | Primary=$($_.Primary) | Bounds=$($_.Bounds) | WorkingArea=$($_.WorkingArea)"
}
```

Run this to re-verify coordinates after driver updates or cable swaps.

### 5c. Get a window's exact bounding rectangle (logical pixels)

```powershell
Add-Type -AssemblyName System.Windows.Forms
$proc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if ($proc) {
    $screen = [System.Windows.Forms.Screen]::FromHandle($proc.MainWindowHandle)
    Write-Output "Screen: $($screen.DeviceName) | ScreenBounds: $($screen.Bounds)"
}
```

### 5d. Map a pixel coordinate to its screen

```powershell
Add-Type -AssemblyName System.Windows.Forms
$x = 3000; $y = 700  # Example coordinates — replace with actual values
$screen = [System.Windows.Forms.Screen]::FromPoint([System.Drawing.Point]::new($x, $y))
Write-Output "Point ($x,$y) is on: $($screen.DeviceName)"
```

---

## 6. Edge Cases

### Minimized Windows
Position reports as **(-32000, -32000)** when minimized. Must restore the window first:
```powershell
# Restore before querying position
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$proc = Get-Process -Name 'NinjaTrader' | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($proc) { [Win32]::ShowWindow($proc.MainWindowHandle, 9) }  # SW_RESTORE = 9
```
For full P/Invoke window management, use `ninjatrader/scripts/nt8-ui.ps1` via the `nt8-expert` skill.

### Multi-Process Applications
NinjaTrader and TradingView spawn multiple processes (data feeds, helpers, etc.). Most have no visible window. Always filter:
```powershell
$proc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
```

### Window Spanning Two Screens
`Screen.FromHandle()` returns the screen that contains the **majority** of the window's area. If a window is exactly half-and-half, behavior is implementation-defined.

### TradingView Process Names
- **TradingView Desktop app**: Process name = `TradingView`
- **Browser-based TradingView**: Process name varies — `chrome`, `msedge`, `firefox` depending on browser

### Windows DISPLAY IDs Can Change
After driver updates, GPU driver reinstalls, or cable swaps, Windows may reassign DISPLAY1/DISPLAY2/etc. numbers. The hardware (SDC419D, YCT428A) stays the same. Run the **Re-scan Command** below to re-verify the mapping.

### Negative Coordinates
If a monitor is positioned to the left of or above the primary screen in Windows display settings, it will have negative coordinates. Current setup has DISPLAY1 at (0,0) as primary — all others have positive coordinates.

---

## 7. Re-scan Command

Run this to re-verify the full topology after any hardware change:

```powershell
Add-Type -AssemblyName System.Windows.Forms

Write-Output "=== DISPLAY TOPOLOGY SCAN ==="
Write-Output "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output ""

# Screen bounds and working areas
Write-Output "--- Logical Screen Bounds ---"
[System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    Write-Output "Device: $($_.DeviceName)"
    Write-Output "  Primary:     $($_.Primary)"
    Write-Output "  Bounds:      X=$($_.Bounds.X), Y=$($_.Bounds.Y), W=$($_.Bounds.Width), H=$($_.Bounds.Height)"
    Write-Output "  WorkingArea: X=$($_.WorkingArea.X), Y=$($_.WorkingArea.Y), W=$($_.WorkingArea.Width), H=$($_.WorkingArea.Height)"
    Write-Output ""
}

# Monitor hardware identification
Write-Output "--- Monitor Hardware IDs ---"
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID | ForEach-Object {
    $name = ($_.UserFriendlyName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join ''
    $mfg  = ($_.ManufacturerName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join ''
    Write-Output "Instance: $($_.InstanceName)"
    Write-Output "  Manufacturer: $mfg | FriendlyName: $(if ($name) { $name } else { '(none)' })"
    Write-Output ""
}

# Connection types
Write-Output "--- Connection Types ---"
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorConnectionParams | ForEach-Object {
    $tech = switch ($_.VideoOutputTechnology) {
        5  { "HDMI" }
        10 { "DisplayPort" }
        2147483648 { "Internal" }
        default { "Unknown ($($_.VideoOutputTechnology))" }
    }
    Write-Output "$($_.InstanceName) → $tech"
}
```

---

*This knowledge base is maintained by the `display-topology` skill. Do not add window-moving commands, screenshot logic, or hardware specs beyond coordinate math.*
