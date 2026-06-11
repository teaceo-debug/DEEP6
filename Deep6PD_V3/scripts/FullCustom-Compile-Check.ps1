# Full offline replica of NT8.1's F5 compile using the Roslyn compiler (modern C#),
# against the real .NET Framework 4.8 + NT8 + vendor assemblies. Read-only: outputs to TEMP.
$ErrorActionPreference = 'Stop'
$nt   = 'C:\Program Files\NinjaTrader 8\bin'
$cust = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NinjaTrader 8\bin\Custom'
$fw   = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
$wpf  = Join-Path $fw 'WPF'
$sdk  = Get-ChildItem 'C:\Program Files\dotnet\sdk' -Directory | Sort-Object Name -Descending | Select-Object -First 1
$csc  = Join-Path $sdk.FullName 'Roslyn\bincore\csc.dll'
$out  = Join-Path $env:TEMP 'nt_custom_fullcheck.dll'
$rsp  = Join-Path $env:TEMP 'nt_custom_fullcheck.rsp'

$sources = Get-ChildItem $cust -Recurse -Filter *.cs | Select-Object -ExpandProperty FullName

$refs = @()
foreach ($n in @('mscorlib.dll','System.dll','System.Core.dll','System.Xml.dll','System.Xml.Linq.dll',
    'System.Net.Http.dll','System.ComponentModel.DataAnnotations.dll','System.Xaml.dll',
    'System.Web.dll','System.Web.Extensions.dll','System.Windows.Forms.dll','System.Drawing.dll',
    'Microsoft.CSharp.dll','System.Runtime.Serialization.dll','System.ServiceModel.dll',
    'System.Configuration.dll','System.Management.dll','System.IO.Compression.dll',
    'System.IO.Compression.FileSystem.dll','System.Numerics.dll','System.Data.dll')) {
    $p = Join-Path $fw $n
    if (Test-Path $p) { $refs += $p }
}
foreach ($n in @('PresentationCore.dll','PresentationFramework.dll','WindowsBase.dll',
    'UIAutomationProvider.dll','UIAutomationTypes.dll','WindowsFormsIntegration.dll')) {
    $p = Join-Path $wpf $n
    if (Test-Path $p) { $refs += $p }
}
function Test-Managed($path) {
    try { [void][System.Reflection.AssemblyName]::GetAssemblyName($path); return $true } catch { return $false }
}
$aliased = @()
foreach ($d in (Get-ChildItem $nt -Filter *.dll | Where-Object { $_.Name -ne 'NinjaTrader.Custom.dll' -and $_.Name -ne 'NinjaTrader.Client.dll' })) {
    if (Test-Managed $d.FullName) { $refs += $d.FullName }
}
foreach ($d in (Get-ChildItem $cust -Filter *.dll | Where-Object { $_.Name -ne 'NinjaTrader.Custom.dll' })) {
    if (-not (Test-Managed $d.FullName)) { continue }
    if ($d.Name -eq 'Replikanto.dll') { $aliased += $d.FullName } else { $refs += $d.FullName }
}

$lines = @('/nostdlib+', '/nologo', '/t:library', "/out:`"$out`"", '/warn:0', '/langversion:latest', '/define:NT8')
foreach ($r in $refs)    { $lines += ('/r:"' + $r + '"') }
$ai = 0
foreach ($r in $aliased) { $lines += ('/r:vendoralias' + $ai + '="' + $r + '"'); $ai++ }
foreach ($s in $sources) { $lines += ('"' + $s + '"') }
[System.IO.File]::WriteAllLines($rsp, $lines)

& dotnet $csc "@$rsp"
Write-Host "EXIT: $LASTEXITCODE  (sources: $($sources.Count), refs: $($refs.Count))"
exit $LASTEXITCODE
