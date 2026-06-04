## bias-v3-nt8 Learnings

- The NT8 writer should emit a flat HUD payload with preformatted `confidence_pct` and `domain_scores` ints.
- Atomic writes are safest with temp file + `os.replace()` in the destination directory.
- The default NT8 path should point to `Documents\NinjaTrader 8\templates\DEEP6\bias_v3.json` for parity with `GEXCommand.cs`.
- The schema contract must mirror `BiasJsonWriter._payload()` exactly and constrain HUD-only fields, not engine internals.

- DEEP6BiasV3 should reuse the GEXCommand.cs timer + FileStream(FileShare.ReadWrite) polling pattern, but also cache the last file mtime so unchanged polls only recompute stale state instead of reparsing JSON.
- For a lightweight NT8 bias HUD, a simple top-left SharpDX panel with dedicated direction/mode brushes and explicit OnRenderTargetChanged disposal is enough; no plots or price markers are needed to surface bias state clearly.
- NT8 compile automation can time out without returning CS#### rows, so 
t8-ai-loop.ps1 is the right first verification step, but a timeout with empty error JSON may still require manual Output Window inspection in the running NinjaScript Editor.

- The chart toolbar `ChartWindowIndicatorsButton` is the reliable automation entry point for opening the Indicators dialog; it worked via UIAutomation `InvokePattern` when keyboard/context-menu attempts were inconsistent.
- `DEEP6BiasV3` can be verified end-to-end with a mock JSON payload at `Documents\NinjaTrader 8\templates\DEEP6\bias_v3.json`; the HUD rendered correctly after one refresh interval and became easier to prove after moving it to `HudOffsetX=350`, `HudOffsetY=120`, `HudOpacity=1.0`.
- The indicator’s stale detection is driven by file age (mtime), so forcing stale state is easiest by aging the file write time rather than waiting the full threshold in real time.
