# NT8 Automation Scripts Reference

All scripts live in: `C:\Users\Tea\DEEP6\ninjatrader\scripts\`

## nt8-deploy.ps1 — Deploy source files to NT8

```
Usage: nt8-deploy.ps1 [-Target <Indicators|Strategies|AddOns|All>] [-Force] [-DryRun]

Examples:
  nt8-deploy.ps1                        # deploy all DEEP6 files
  nt8-deploy.ps1 -Target Strategies     # deploy strategies only
  nt8-deploy.ps1 -DryRun                # preview what would be copied
  nt8-deploy.ps1 -Force                 # force copy even if unchanged
```

## nt8-compile.ps1 — Trigger NT8 recompile via UI automation

```
Usage: nt8-compile.ps1 [-WaitSeconds <int>] [-CheckErrors]

Examples:
  nt8-compile.ps1                       # compile and return
  nt8-compile.ps1 -CheckErrors          # compile then check log for errors
  nt8-compile.ps1 -WaitSeconds 10       # wait 10s for compile to finish
```

NT8 must be running. Script will:
1. Bring NT8 to foreground
2. Open NinjaScript Editor (Tools menu)
3. Send F5 to compile
4. Optionally read log for errors

## nt8-ui.ps1 — NT8 UI interaction primitives

```
Usage: nt8-ui.ps1 -Action <action> [options]

Actions:
  Status              Check if NT8 is running
  BringToFront        Focus NT8 main window
  OpenEditor          Open NinjaScript Editor
  Compile             Compile (editor must be open)
  OpenOutputWindow    Open View > Output Window
  AddIndicator        Add indicator to active chart (interactive prompt)
  Screenshot          Capture NT8 window to file
```

## nt8-status.ps1 — Check NT8 state and recent errors

```
Usage: nt8-status.ps1 [-ShowErrors] [-ShowLog <n>]

Examples:
  nt8-status.ps1                        # running? version? files deployed?
  nt8-status.ps1 -ShowErrors            # show errors from today's log
  nt8-status.ps1 -ShowLog 50            # show last 50 log lines
```

## Combining for a full deploy+compile workflow

```powershell
# Full cycle: deploy → compile → check errors
.\ninjatrader\scripts\nt8-deploy.ps1 -Target All
.\ninjatrader\scripts\nt8-compile.ps1 -WaitSeconds 8 -CheckErrors
.\ninjatrader\scripts\nt8-status.ps1 -ShowErrors
```
