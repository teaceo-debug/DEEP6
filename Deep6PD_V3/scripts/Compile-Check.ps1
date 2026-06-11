# Offline syntax/type check of the Deep6 v3 sources against the installed NT8 assemblies.
# Uses the in-box .NET Framework C# 5 compiler — NOT a substitute for the real NT compile
# (F5 in the NinjaScript editor regenerates the wrapper region), but catches everything
# short of that without launching NT.
#
# The NT-generated wrapper region is STRIPPED before checking: its MarketAnalyzerColumn /
# Strategy partial blocks reference members (e.g. `indicator`) that only exist when NT
# compiles all custom files together. NT itself owns compiling that region.
$ErrorActionPreference = 'Stop'
$nt    = 'C:\Program Files\NinjaTrader 8\bin'
$cust  = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NinjaTrader 8\bin\Custom'
$wpf   = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\WPF'
$csc   = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$out   = Join-Path $env:TEMP 'deep6v3_compilecheck.dll'
$work  = Join-Path $env:TEMP 'deep6v3_compilecheck_src'
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory $work | Out-Null

$sources = @(
    (Join-Path $cust 'AddOns\Deep6PD\Deep6Core.cs'),
    (Join-Path $cust 'AddOns\Deep6PD\Deep6Persistence.cs'),
    (Join-Path $cust 'Indicators\DEEP6\Deep6PremiumDiscountV3.cs')
)
$stripped = @()
foreach ($s in $sources) {
    $txt = [System.IO.File]::ReadAllText($s)
    $idx = $txt.IndexOf('#region NinjaScript generated code')
    if ($idx -ge 0) { $txt = $txt.Substring(0, $idx) }
    $dest = Join-Path $work ([System.IO.Path]::GetFileName($s))
    [System.IO.File]::WriteAllText($dest, $txt)
    $stripped += $dest
}

$refs = @(
    (Join-Path $nt 'NinjaTrader.Core.dll'),
    (Join-Path $nt 'NinjaTrader.Gui.dll'),
    (Join-Path $cust 'NinjaTrader.Custom.dll'),
    (Join-Path $nt 'Newtonsoft.Json.dll'),
    (Join-Path $nt 'SharpDX.dll'),
    (Join-Path $nt 'SharpDX.Direct2D1.dll'),
    (Join-Path $wpf 'PresentationCore.dll'),
    (Join-Path $wpf 'PresentationFramework.dll'),
    (Join-Path $wpf 'WindowsBase.dll'),
    'System.Net.Http.dll',
    'System.ComponentModel.DataAnnotations.dll',
    'System.Xml.dll',
    'System.Xaml.dll'
)
$refArgs = $refs | ForEach-Object { '/r:"' + $_ + '"' }
$srcArgs = $stripped | ForEach-Object { '"' + $_ + '"' }
$cmd = @('/nologo', '/t:library', "/out:`"$out`"", '/warn:1') + $refArgs + $srcArgs
& $csc $cmd
if ($LASTEXITCODE -eq 0) { Write-Host "COMPILE CHECK PASSED -> $out" } else { Write-Host "COMPILE CHECK FAILED ($LASTEXITCODE)" }
exit $LASTEXITCODE
