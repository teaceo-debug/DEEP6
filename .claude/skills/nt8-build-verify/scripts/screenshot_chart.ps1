# screenshot_chart.ps1 - Targeted NT8 chart window capture via PrintWindow Win32 API
# Usage: screenshot_chart.ps1 -ChartTitle "NQ 09-25" [-OutputPath path.png] [-SettleMs 1500]
#        screenshot_chart.ps1 -MainWindow [-OutputPath path.png] [-SettleMs 1500]
#
# Exit codes: 0=success, 1=chart not found, 2=NT8 not running

[CmdletBinding()]
param(
    [string]$ChartTitle,
    [switch]$MainWindow,
    [string]$OutputPath,
    [int]$SettleMs = 1500
)

$ErrorActionPreference = "Stop"

# --- Assemblies ---
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

# --- P/Invoke ---
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class Win32Screenshot {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left, Top, Right, Bottom;
    }

    // Find all visible windows belonging to a process
    public static List<IntPtr> GetProcessWindows(uint processId) {
        var windows = new List<IntPtr>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (pid == processId && IsWindowVisible(hWnd)) {
                int len = GetWindowTextLength(hWnd);
                if (len > 0) {
                    windows.Add(hWnd);
                }
            }
            return true;
        }, IntPtr.Zero);
        return windows;
    }

    // Get window title
    public static string GetTitle(IntPtr hWnd) {
        int len = GetWindowTextLength(hWnd);
        if (len == 0) return "";
        var sb = new StringBuilder(len + 1);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }
}
"@

# --- Find NinjaTrader process ---
$nt8 = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
if (-not $nt8) {
    Write-Output '{"error":"NinjaTrader process not found"}'
    exit 2
}

# Handle multiple NT8 processes (take first)
if ($nt8 -is [System.Array]) { $nt8 = $nt8[0] }
$nt8Pid = [uint32]$nt8.Id

# --- Validate params ---
if (-not $MainWindow -and -not $ChartTitle) {
    Write-Output '{"error":"must specify -ChartTitle or -MainWindow"}'
    exit 1
}

# --- Find target window ---
$targetHandle = [IntPtr]::Zero

if ($MainWindow) {
    $targetHandle = $nt8.MainWindowHandle
} else {
    # Enumerate all NT8 windows, find by title substring
    $allWindows = [Win32Screenshot]::GetProcessWindows($nt8Pid)
    foreach ($hwnd in $allWindows) {
        $title = [Win32Screenshot]::GetTitle($hwnd)
        if ($title -like "*$ChartTitle*") {
            $targetHandle = $hwnd
            break
        }
    }
}

if ($targetHandle -eq [IntPtr]::Zero) {
    $searchInfo = if ($ChartTitle) { $ChartTitle } else { "MainWindow" }
    Write-Output "{`"error`":`"chart not found`",`"search`":`"$searchInfo`"}"
    exit 1
}

# --- Wait for rendering to settle ---
Start-Sleep -Milliseconds $SettleMs

# --- Bring window to foreground ---
[Win32Screenshot]::ShowWindow($targetHandle, 9) | Out-Null  # SW_RESTORE
Start-Sleep -Milliseconds 200
[Win32Screenshot]::SetForegroundWindow($targetHandle) | Out-Null
Start-Sleep -Milliseconds 200

# --- Get window dimensions ---
$rect = New-Object Win32Screenshot+RECT
[Win32Screenshot]::GetWindowRect($targetHandle, [ref]$rect) | Out-Null
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top

if ($width -le 0 -or $height -le 0) {
    Write-Output '{"error":"invalid window dimensions","width":' + $width + ',"height":' + $height + '}'
    exit 1
}

# --- Capture via PrintWindow ---
$bitmap = $null
$captureMethod = "printwindow"
$captureOk = $false

try {
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $hdc = $graphics.GetHdc()

    try {
        # PW_RENDERFULLCONTENT = 2 (captures even occluded windows on Win 8.1+)
        $result = [Win32Screenshot]::PrintWindow($targetHandle, $hdc, 2)
        if ($result) {
            $captureOk = $true
        }
    } finally {
        $graphics.ReleaseHdc($hdc)
        $graphics.Dispose()
    }
} catch {
    $captureOk = $false
}

# --- Fallback to CopyFromScreen ---
if (-not $captureOk) {
    $captureMethod = "copyfromscreen"
    if ($bitmap) { $bitmap.Dispose(); $bitmap = $null }

    try {
        $bitmap = New-Object System.Drawing.Bitmap($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size($width, $height)))
        $graphics.Dispose()
        $captureOk = $true
    } catch {
        if ($bitmap) { $bitmap.Dispose() }
        Write-Output "{`"error`":`"capture failed: $($_.Exception.Message)`"}"
        exit 1
    }
}

# --- Default output path ---
if (-not $OutputPath) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $PSScriptRoot "..\..\..\..\captures\nt8-chart-$timestamp.png"
}

# Ensure output directory exists
$outDir = Split-Path $OutputPath
if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

# --- Save PNG ---
$bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)

# --- Blank detection: pixel variance sampling ---
$blankCheck = "pass"
try {
    $colors = [System.Collections.Generic.List[double]]::new()
    $stepX = [Math]::Max(1, [int]($width / 20))
    $stepY = [Math]::Max(1, [int]($height / 20))

    for ($x = 0; $x -lt $width; $x += $stepX) {
        for ($y = 0; $y -lt $height; $y += $stepY) {
            $pixel = $bitmap.GetPixel($x, $y)
            $colors.Add([double]($pixel.R + $pixel.G + $pixel.B))
        }
    }

    if ($colors.Count -gt 1) {
        $sum = 0.0; $sumSq = 0.0; $n = $colors.Count
        foreach ($c in $colors) { $sum += $c; $sumSq += $c * $c }
        $mean = $sum / $n
        $variance = ($sumSq / $n) - ($mean * $mean)
        $stddev = [Math]::Sqrt([Math]::Max(0, $variance))

        if ($stddev -lt 5.0) {
            $blankCheck = "warn"
        }
    }
} catch {
    $blankCheck = "error"
}

# --- Dispose bitmap ---
$bitmap.Dispose()

# --- Resolve full path ---
$resolvedPath = (Resolve-Path $OutputPath).Path

# --- JSON output ---
$windowTitle = [Win32Screenshot]::GetTitle($targetHandle)
$result = @{
    path           = $resolvedPath
    width          = $width
    height         = $height
    blank_check    = $blankCheck
    capture_method = $captureMethod
    window_title   = $windowTitle
} | ConvertTo-Json -Compress

Write-Output $result
exit 0
