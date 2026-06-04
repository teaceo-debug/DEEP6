Set WshShell = CreateObject("WScript.Shell")
pythonw = "C:\Users\Tea\AppData\Local\Programs\Python\Python311\pythonw.exe"
script = "C:\Users\Tea\DEEP6\scripts\telegram\mad_levels_service.py"
WshShell.Run """" & pythonw & """ """ & script & """", 0, False
