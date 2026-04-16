---
from: mac (Claude Code)
to: windows (OpenCode)
status: pending
timestamp: 2026-04-16T06:10:00Z
task: NT8 full setup — deploy DEEP6 files, compile, configure bridge
---

## Task

Set up NinjaTrader 8 with all DEEP6 files and activate the Data Bridge. Follow the handoff document exactly.

## Steps

1. `git pull origin main` to get the latest fixes (commit 1d61d0b)
2. Read and execute `ninjatrader/WINDOWS-SETUP-HANDOFF.md` — all 8 steps
3. **CRITICAL:** Use NT8's NinjaScript Editor F5 to compile — do NOT use `dotnet build`
4. Report back: compile result (0 errors?), indicator added to chart?, bridge listening on port 9200?

## Key Fixes in Latest Push

- `FootprintBar.cs` is EXCLUDED from NT8 Registry copy (the PowerShell command in Step 2 now filters it)
- `System.Math.Max` fixes namespace shadowing
- `SharpDX.Direct2D1.DashStyle.Dash` fixes ambiguity  
- `OnChartPanelMouseDown` uses `new` instead of `override` for NT8 version compatibility
- `volatile double` is a .NET 8 issue only — NT8's .NET Framework handles it fine

## Files to Read

- `ninjatrader/WINDOWS-SETUP-HANDOFF.md` — the complete setup guide
- `dashboard/agents/ninjascript-error-surgeon-v2.md` — if any compile errors remain, this has fixes for 44 known errors

## Expected Result

When done, write results to `.handoff/to-mac.md` with:
- F5 compile result (errors? warnings?)
- NT8 Output Window showing `[DEEP6 Bridge] Server started on port 9200`
- This machine's local IP address (for Mac to connect)

Then commit + push:
```
git add .handoff/to-mac.md
git commit -m "handoff: NT8 setup complete — bridge active on port 9200"
git push origin main
```

## After Setup

The Mac will connect with:
```bash
dotnet run --project ninjatrader/simulator -- bridge <YOUR_IP>:9200 --record first-session.ndjson
```
