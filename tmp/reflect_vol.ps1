$core='C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Core.dll'
$nt='C:\Program Files\NinjaTrader 8\bin\NinjaTrader.NinjaScript.dll'
Add-Type -Path $core
Add-Type -Path $nt
$t=[NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType]
'Type: ' + $t.FullName
'Properties:'
$t.GetProperties() | Sort-Object Name | ForEach-Object { '  ' + $_.PropertyType.FullName + ' ' + $_.Name }
''
'Fields:'
$t.GetFields([System.Reflection.BindingFlags]'Public,NonPublic,Instance,Static') | Where-Object {$_.Name -match 'Vol|vol'} | ForEach-Object { '  ' + $_.FieldType.FullName + ' ' + $_.Name }
''
'Methods matching Volume:'
$t.GetMethods() | Where-Object {$_.Name -match 'Vol|Price|Delta'} | Sort-Object Name | Select-Object -ExpandProperty Name -Unique | ForEach-Object { '  ' + $_ }
