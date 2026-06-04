Get-ChildItem 'C:\Program Files\NinjaTrader 8\bin' -Filter 'NinjaTrader*.dll' | ForEach-Object {
  try {
    $asm = [System.Reflection.Assembly]::LoadFrom($_.FullName)
    $types = $asm.GetTypes() | Where-Object { $_.FullName -like '*Volumetric*' }
    foreach ($t in $types) { "$($_.Assembly.GetName().Name) :: $($t.FullName)" }
  } catch {}
}
