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

## nt8-replay-download.ps1 — Download NT8 Market Replay data

```
Usage: nt8-replay-download.ps1 [-Instrument <root>] [-Contract <MM-yy>] [-StartDate <date>] [-EndDate <date>] [-ListContracts] [-Force] [-WhatIf]

Examples:
  nt8-replay-download.ps1                                         # MNQ 06-26, today only
  nt8-replay-download.ps1 -StartDate 2026-04-21 -EndDate 2026-04-25
  nt8-replay-download.ps1 -Instrument NQ -Contract 06-26 -StartDate 2026-04-24
  nt8-replay-download.ps1 -ListContracts                          # inspect available contract menu items
```

Uses UI Automation to open `Tools > Historical Data`, expand `Get Market Replay data`, select an instrument contract, set the replay date, click download, and verify the `.nrd` file appears under `Documents\\NinjaTrader 8\\db\\replay\\<contract>\\YYYYMMDD.nrd`.

It now skips Saturdays with a `skipped_weekend` status because CME futures replay downloads for Saturday dates can hang or produce stub files.

If the download button remains disabled, the script returns a diagnostic summary instead of silently failing.

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
