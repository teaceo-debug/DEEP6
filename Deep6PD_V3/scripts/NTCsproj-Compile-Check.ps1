# Exact replica of NT8.1's F5 compile: parses NinjaTrader.Custom.csproj for the source list
# and reference list, compiles with Roslyn (LangVersion latest, net48, x64). Read-only.
$ErrorActionPreference = 'Stop'
$cust = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NinjaTrader 8\bin\Custom'
$fw   = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
$wpf  = Join-Path $fw 'WPF'
$sdk  = Get-ChildItem 'C:\Program Files\dotnet\sdk' -Directory | Sort-Object Name -Descending | Select-Object -First 1
$csc  = Join-Path $sdk.FullName 'Roslyn\bincore\csc.dll'
$out  = Join-Path $env:TEMP 'nt_csproj_check.dll'
$rsp  = Join-Path $env:TEMP 'nt_csproj_check.rsp'

[xml]$proj = Get-Content (Join-Path $cust 'NinjaTrader.Custom.csproj')

# Sources: csproj Compile Include list (decode %40 -> @), skip Resource.Designer.cs companions that exist
$sources = @()
foreach ($ig in $proj.Project.ItemGroup) {
    foreach ($c in $ig.Compile) {
        if ($null -ne $c.Include) {
            $rel = [System.Uri]::UnescapeDataString($c.Include)
            $p = Join-Path $cust $rel
            if (Test-Path $p) { $sources += $p } else { Write-Host "MISSING SOURCE: $rel" }
        }
    }
}

# References: explicit csproj refs (HintPath if present, else resolve from framework dirs)
$refs = @()
foreach ($ig in $proj.Project.ItemGroup) {
    foreach ($r in $ig.Reference) {
        if ($null -eq $r.Include) { continue }
        if ($r.HintPath) {
            $hp = $r.HintPath -replace 'Framework\\v4.0.30319', 'Framework64\v4.0.30319'
            if (Test-Path $hp) { $refs += $hp } else { Write-Host "MISSING REF: $($r.HintPath)" }
        } else {
            $name = $r.Include + '.dll'
            $p1 = Join-Path $fw $name; $p2 = Join-Path $wpf $name
            if (Test-Path $p1) { $refs += $p1 } elseif (Test-Path $p2) { $refs += $p2 } else { Write-Host "UNRESOLVED GAC REF: $name" }
        }
    }
}
# SDK-style net48 default references (Microsoft.NETFramework.props) + UseWPF set
foreach ($n in @('System.Data.dll','System.Drawing.dll','System.IO.Compression.FileSystem.dll',
    'System.Numerics.dll','System.Runtime.Serialization.dll','System.Configuration.dll')) {
    $p = Join-Path $fw $n; if (Test-Path $p) { $refs += $p }
}
foreach ($n in @('PresentationCore.dll','PresentationFramework.dll','WindowsBase.dll','UIAutomationTypes.dll')) {
    $p = Join-Path $wpf $n; if (Test-Path $p) { $refs += $p }
}
$refs = $refs | Select-Object -Unique

$lines = @('/nostdlib+', '/nologo', '/t:library', "/out:`"$out`"", '/warn:0', '/langversion:latest', '/platform:x64', '/define:TRACE;RELEASE')
foreach ($r in $refs)    { $lines += ('/r:"' + $r + '"') }
foreach ($s in $sources) { $lines += ('"' + $s + '"') }
[System.IO.File]::WriteAllLines($rsp, $lines)

& dotnet $csc "@$rsp"
Write-Host "EXIT: $LASTEXITCODE  (sources: $($sources.Count), refs: $($refs.Count))"
exit $LASTEXITCODE
