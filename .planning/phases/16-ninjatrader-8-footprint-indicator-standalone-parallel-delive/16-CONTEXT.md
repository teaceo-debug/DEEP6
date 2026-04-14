# Phase 16: NinjaTrader 8 Footprint Indicator — Context

**Gathered:** 2026-04-14
**Status:** Built
**Source:** Freeform user direction, executed autonomously

<domain>
## Phase Boundary

Standalone NinjaScript C# indicator for NinjaTrader 8 that renders the DEEP6 footprint (bid×ask per price level, POC, VAH/VAL), absorption + exhaustion signal markers ported from the Python engine, and optional GEX overlay levels fetched from massive.com.

**Parallel deliverable** — does NOT replace, share state with, or depend on the DEEP6 Python auto-trading system. Read-only indicator, no order entry.
</domain>

<decisions>
## Implementation Decisions (locked)

### Data source
- NT8 native Rithmic L2 feed via `OnMarketData` + `OnMarketDepth` overrides
- Aggressor classification: `price >= bestAsk` → buy (1); `price <= bestBid` → sell (2); else neutral (0)
- `Calculate.OnEachTick` required for tick-level accumulation
- GEX source: massive.com `/v3/snapshot/options/{QQQ}` aggregated client-side into gamma-flip / call wall / put wall

### Signal scope
- Absorption: 4 variants (CLASSIC, PASSIVE, STOPPING_VOLUME, EFFORT_VS_RESULT) + ABS-07 VAH/VAL proximity bonus
- Exhaustion: 6 variants (ZERO_PRINT, EXHAUSTION_PRINT, THIN_PRINT, FAT_PRINT, FADING_MOMENTUM, BID_ASK_FADE) + delta trajectory gate
- **Not ported**: 44-signal stack, Kronos E10, auto-execution, backtesting. Out of scope.

### Language / platform
- NinjaScript C# targeting NT8 8.1.x, .NET Framework 4.8
- SharpDX Direct2D for custom cell rendering in `OnRender`
- `Draw.TriangleUp/Down/ArrowUp/Down/Diamond` for signal markers (built-in NT8 drawing objects — simpler than custom SharpDX glyphs)

### Rendering
- Custom `OnRender` for footprint cells (per-visible-bar only, not full history)
- Built-in `Draw.*` for signal markers (works across historical + realtime, persists per bar)
- Horizontal GEX lines drawn in `OnRender` (no drawing-object overhead)
- QQQ→NQ price mapping for GEX via spot-ratio multiplier (visual only; not tradeable levels)

### Threading
- Rithmic L2 intake on NT data thread (touches only `_bars` dict and BBO doubles)
- Detectors + Draw on NT chart thread in `OnBarUpdate`
- GEX HTTP on `Task.Run` background; writes to `volatile GexProfile`; render thread reads local copy

### Packaging
- `src/` flat — one indicator .cs, four AddOn .cs
- User copies manually into `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\{Indicators,AddOns}\DEEP6\`
- Export via NT8's Tools → Export after import verified
- Namespace split: `NinjaTrader.NinjaScript.Indicators.DEEP6` for the indicator, `NinjaTrader.NinjaScript.AddOns.DEEP6` for shared types

### Thresholds
All match DEEP6 Python defaults verbatim — see `PORT-SPEC.md` for full table. No tuning; changes to thresholds in Python should replicate here as future work.
</decisions>

<canonical_refs>
## Canonical References

- `ninjatrader/src/` — all source
- `.planning/phases/16-*/PORT-SPEC.md` — authoritative port spec (absorption, exhaustion, footprint, POC/VA, NT8 integration contract)
- `deep6/engines/absorption.py:1-244` — upstream absorption logic (port target)
- `deep6/engines/exhaustion.py:1-317` — upstream exhaustion logic (port target)
- `deep6/state/footprint.py:1-175` — upstream footprint accumulator
- `deep6/engines/signal_config.py:16-73` — thresholds
- `deep6/engines/poc.py:231-257` — VAH/VAL algorithm
- NT8 help: https://ninjatrader.com/support/helpguides/nt8/
- massive.com options chain snapshot: https://massive.com/docs/rest/options/snapshots/option-chain-snapshot

### Out-of-scope references (intentionally not included)
- Kronos E10 bias — Python side only
- 44-signal stack — Python side only
- Auto-execution via async-rithmic — Python side only
</canonical_refs>

<specifics>
## Specific Ideas Implemented

- Signal direction convention: +1 bullish, -1 bearish, 0 neutral (FAT_PRINT only)
- Marker glyphs: cyan/magenta triangles for absorption, yellow/orange arrows for exhaustion
- Imbalance detection: diagonal rule (ask@px vs bid@(px+tick)) with tunable ratio
- Cooldown: 5 bars per exhaustion variant; reset on date change
- Volume EMA warmup: starts at first bar's total vol (not zero seed)
- ATR: simple 20-bar rolling mean of (high-low); close-enough to Wilder's for threshold multiplier use
</specifics>

<deferred>
## Deferred / Future Work

- Live Rithmic coexistence strategy (running NT8 indicator + Python engine on same account) — doc only, not code
- Dedicated NDX options pull (currently only QQQ tested for massive.com chain)
- Custom SharpDX signal glyphs (replacing Draw.*) if performance becomes an issue at 1000+ bars
- Threshold config via JSON file hot-reload (currently NT8 property grid only)
- Session-boundary precision: RTH-aware gate matching Python `zoneinfo` logic
- Automated NT8 replay regression harness (cross-validation vs Python engine output on same bar)
</deferred>

---

*Phase: 16-ninjatrader-8-footprint-indicator-standalone-parallel-delive*
*Built autonomously 2026-04-14 after user direction "spawn multiple agents and go deep"*
