- 2026-05-20: For NT8 DOM-only overlays, keep `OnMarketDepth()` strictly array/Interlocked based; move persistence filters, top-N scans, and label formatting to a throttled timer callback.
- 2026-05-20: `IsInHitTest` must be the first `OnRender()` guard and `new SharpDX...` allocations should stay confined to `OnRenderTargetChanged()` so grep-based lifecycle checks stay clean.
- 2026-05-20: Session resets on `Bars.IsFirstBarOfSession` should also gate on `IsFirstTickOfBar` to avoid re-clearing DOM state on every tick of the opening bar.
- 2026-05-20: `DEEP6 Liquidity Levels` was already present in the chart's Configured indicators list; NT8 chart screenshots may require minimizing Control Center and capturing the primary screen directly because `nt8-ui.ps1 -Action Screenshot` focuses the Control Center window.
- 2026-05-20: The output/log validation path surfaced only connection/status messages and no exception stack traces; Log tab screenshots are an acceptable fallback when the dedicated Output window is not visibly docked.

- 2026-05-20 visual QA: DEEP6 Liquidity Levels rendered cyan bid and magenta ask horizontal lines on the chart after manually opening the NT8 Indicators dialog and searching for the indicator name; no fallback status text was visible.
- 2026-05-20 visual QA: Output-window capture showed no exception traces or error logs; the visible NT8 view was the Control Center/output area rather than a distinct standalone Output panel.
- 2026-05-20 QA workflow note: NT8 screenshot helper based on primary-screen capture can miss the actual chart because NinjaTrader may be on a non-primary display; capturing the foreground window by HWND was necessary to verify the chart and output views.

- 2026-05-20 audit: F1 plan-compliance confirmed the DOM/render/performance guardrails in DEEP6LiquidityLevels.cs, but approval still depends on an explicit end-of-file NinjaScript factory-region check (#region NinjaScript generated code).

- 2026-05-20: `DEEP6DaleConfirmations.cs` compiled successfully through `ninjatrader/scripts/nt8-compile.ps1 -TimeoutSeconds 45 -Quiet` even after `.claude/skills/nt8-build-verify/scripts/compile_headless.ps1` failed with `editor_window_not_found`; on this machine, the direct NT8 UI compile script is the more reliable verification path.
- 2026-05-20: For TDOFBars overlay indicators that use a hidden volumetric series, storing per-bar volumetric metrics in `Series<double>` and doing all draw decisions on `BarsInProgress == 0` keeps the overlay logic simple and LSP-clean while preserving access to `BarDelta`, `CumulativeDelta`, and per-price bid/ask cells from `VolumetricBarsType`.
