Add-Type -Path 'C:\Program Files\NinjaTrader 8\bin\SharpDX.dll'
[System.Reflection.Assembly]::LoadFrom('C:\Program Files\NinjaTrader 8\bin\SharpDX.dll').GetTypes() |
  Where-Object { $_.Name -match 'RawColor4|RawRectangleF|Color4|RectangleF' } |
  Sort-Object FullName |
  ForEach-Object { $_.FullName }
