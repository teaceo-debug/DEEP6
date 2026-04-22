# NT8 Scripts Reference

PowerShell scripts in `ninjatrader/scripts/` for deploying, compiling, and
inspecting NinjaScript files in NT8.  All scripts are invoked from this
directory or via full path — they use `$PSScriptRoot` internally.

---

## nt8-deploy.ps1

Deploy DEEP6 `.cs` source files from the repo to the NT8 Custom folder.

```powershell
# Deploy everything
nt8-deploy.ps1

# Deploy only indicators
nt8-deploy.ps1 -Target Indicators

# Deploy AddOns (includes DEEP6DevAddon.cs)
nt8-deploy.ps1 -Target AddOns

# Preview what would be copied (no writes)
nt8-deploy.ps1 -DryRun

# Force copy even if files are unchanged
nt8-deploy.ps1 -Force
```

Parameters:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `-Target` | `All` | `All`, `Indicators`, `Strategies`, or `AddOns` |
| `-Force` | off | Copy even when source and dest hashes match |
| `-DryRun` | off | Print what would be copied; write nothing |

Source root: `ninjatrader/Custom/`  
Destination: `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\`

Excluded files: `FootprintBar.cs` (defined inline in DEEP6Footprint.cs for NT8;
the standalone file is for the net8.0 NUnit project only).

---

## nt8-compile.ps1

Trigger a NinjaScript recompile in NT8 via UI automation (SendKeys F5) and
watch the DLL mtime to detect success or failure.

```powershell
# Trigger compile + wait 30s
nt8-compile.ps1

# Longer timeout
nt8-compile.ps1 -TimeoutSeconds 60

# Skip SendKeys; rely on NSE file-watcher (NSE must be open)
nt8-compile.ps1 -AutoReload

# Check NT8 runtime log for errors after compile
nt8-compile.ps1 -CheckErrors

# Machine-parseable output only
nt8-compile.ps1 -Quiet
```

Parameters:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `-TimeoutSeconds` | `30` | Max seconds to wait for DLL to change |
| `-AutoReload` | off | Skip SendKeys; use NSE file-watcher instead |
| `-CheckErrors` | off | Grep NT8 log for runtime errors after compile |
| `-Quiet` | off | Only print the `[COMPILE-RESULT]` line |

Exit line format: `[COMPILE-RESULT] SUCCESS 2026-04-19 14:38:43.123` or
`[COMPILE-RESULT] FAILED timeout`

Note: CS#### compiler errors appear only in the NT8 Output Window, not in
the daily trace log.  Use `nt8-errors.ps1` or `nt8-dev-api.ps1 -Action errors`
to read them.

---

## nt8-errors.ps1

Read compile errors from the NT8 Output Window via UIAutomation (out-of-process).
Falls back to tailing the NT8 trace log if the Output Window is not accessible.

```powershell
# Text output (default)
nt8-errors.ps1

# JSON output — machine-parseable
nt8-errors.ps1 -Format Json

# Last N lines only
nt8-errors.ps1 -Last 20

# JSON, last 10 lines
nt8-errors.ps1 -Format Json -Last 10
```

Parameters:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `-Format` | `Text` | `Text` (colored) or `Json` |
| `-Last` | `0` (all) | Limit to last N relevant lines |

Exit codes: `0` = no errors, `1` = errors found, `2` = NT8 not running or
Output Window inaccessible.

---

## nt8-status.ps1

NT8 health check: process state, deployed file inventory with sync status,
DLL mtime, and Install.xml confirmed compile timestamp.

```powershell
# Quick status
nt8-status.ps1

# Include compile error grep
nt8-status.ps1 -ShowErrors

# Show last 50 log lines
nt8-status.ps1 -ShowLog 50

# Full diagnostic
nt8-status.ps1 -ShowErrors -ShowLog 100
```

Parameters:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `-ShowErrors` | off | Grep NT8 log for `error`, CS####, `compile fail` |
| `-ShowLog` | `0` | Print last N lines from today's NT8 log |

---

## nt8-ui.ps1

Low-level NT8 UI automation: focus/restore NT8 window, open the NinjaScript
Editor, add indicators or strategies to a chart.

```powershell
# Focus NT8 window
nt8-ui.ps1 -Action focus

# Open NinjaScript Editor (Tools > NinjaScript Editor)
nt8-ui.ps1 -Action editor

# Take a screenshot of NT8 (saved to captures/)
nt8-ui.ps1 -Action screenshot
```

---

## nt8-dev-api.ps1  ← NEW

Client for `DEEP6DevAddon` — an HTTP server running **inside NT8's process**
on `localhost:19206`.  Eliminates the need for UIAutomation or SendKeys to
read errors, trigger compiles, or check status.

### Prerequisites

1. Deploy: `nt8-deploy.ps1 -Target AddOns`
2. Compile: `nt8-compile.ps1` (or F5 in NinjaScript Editor)
3. NT8 will auto-load `DEEP6DevAddon` when it starts and start the server.

### Usage

```powershell
# Verify the addon is reachable
nt8-dev-api.ps1 -Action health

# NT8 state, last compile time, DLL mtime, loaded instruments
nt8-dev-api.ps1 -Action status

# Pretty-print status as JSON
nt8-dev-api.ps1 -Action status -Format Json

# Read compile errors (scraped from Output Window in-process)
nt8-dev-api.ps1 -Action errors

# Errors as JSON (for CI / Python callers)
nt8-dev-api.ps1 -Action errors -Format Json

# Trigger compile, then poll and show errors
nt8-dev-api.ps1 -Action compile -Wait

# Trigger compile with custom timeout
nt8-dev-api.ps1 -Action compile -Wait -TimeoutSeconds 60

# Tail last 100 lines of NT8 trace log
nt8-dev-api.ps1 -Action log -Lines 100
```

### Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `-Action` | required | `health`, `status`, `errors`, `compile`, `log` |
| `-Format` | `Text` | `Text` (colored) or `Json`; applies to `errors` and `status` |
| `-Lines` | `50` | Lines to return for `-Action log` |
| `-Wait` | off | For `-Action compile`: poll /status until DLL changes, then show errors |
| `-TimeoutSeconds` | `45` | Max seconds to wait when `-Wait` is set |

### Endpoints (DEEP6DevAddon)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | `{"ok":true}` — liveness probe |
| `GET` | `/status` | NT8 state, compile timestamps, instrument list |
| `GET` | `/errors` | JSON array of compile error lines from Output Window |
| `POST` | `/compile` | Trigger in-process compile; `{"triggered":true}` |
| `GET` | `/log?lines=N` | Last N lines from NT8 trace log |

Port `19206` = DEEP6.

### Why prefer this over nt8-errors.ps1 + nt8-compile.ps1?

| | Out-of-process (old) | In-process / DEEP6DevAddon (new) |
|---|---|---|
| Error source | UIAutomation tree walk (fragile) | Direct WPF visual tree walk inside NT8 |
| Compile trigger | SendKeys F5 via WScript.Shell | Dispatcher.Invoke to NSE CompileAll |
| Works headless? | No (needs NT8 in foreground) | Yes (background thread) |
| Latency | 2–5s UI overhead | <100ms HTTP round-trip |
| CI/CD friendly | Difficult | Yes — pure HTTP |

Use `nt8-compile.ps1` when NT8 is running without the addon (e.g., first
bootstrap).  Use `nt8-dev-api.ps1` for all subsequent development iteration.
