# GSD Quick — NT8 MNQ Replay Downloader Automation

Status: execution kickoff
Source plan: ad-hoc user request in current session

Goal
- Create a native NinjaTrader automation script to download Market Replay data without the MRDD addon.
- Prioritize MNQ usage while keeping the flow reusable for other futures instruments.
- Verify downloads by checking `.nrd` files in the NT8 replay directory.

Execution scope for this pass
1. Inspect existing NT8 automation primitives and local NT8 replay folder state.
2. Build a PowerShell UI Automation downloader flow for `Tools > Historical Data > Load > Market Replay`.
3. Support instrument, contract month, and date range inputs with sensible defaults for MNQ.
4. Add post-download verification against `Documents\\NinjaTrader 8\\db\\replay\\<instrument contract>\\*.nrd`.
5. Validate script syntax and produce usage notes.

Constraints
- Use native NinjaTrader only; no paid addon dependency.
- Avoid replacing existing NT8 automation scripts unless extension is clearly better than a new file.
- Keep the script safe to run repeatedly.
- Prefer verified NT8 paths from local skill knowledge.

Notes
- This is the required execution artifact before repo edits.
- UI labels may vary slightly by NT8 build, so the script should emit diagnostic output when controls are not found.
