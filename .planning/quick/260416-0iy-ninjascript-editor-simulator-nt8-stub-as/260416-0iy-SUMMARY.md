# Quick Task 260416-0iy: NinjaScript Editor Simulator

**Completed:** 2026-04-16
**Commit:** 15f865f

## What Was Built

A three-layer NinjaScript simulator that validates and tests NinjaScript code on macOS without NinjaTrader installed.

### Layer 1 — NT8 Stub Assembly (`ninjatrader/simulator/NinjaTrader.Stubs/`)

Mock implementations of every NT8 namespace referenced by DEEP6:
- **NinjaTrader.Cbi** — Account, Position, Order, Execution, Instrument, enums
- **NinjaTrader.Data** — Bars, ISeries<T>, MarketDataEventArgs, MarketDepthEventArgs
- **NinjaTrader.Core** — Globals (D2DFactory, DirectWriteFactory), FloatingPoint
- **NinjaTrader.Gui** — ChartControl, ChartScale, ChartPanel, ChartAnchor, Serialize
- **NinjaTrader.Gui.NinjaScript** — IndicatorRenderBase, StrategyRenderBase, MarketAnalyzerColumnBase
- **NinjaTrader.NinjaScript** — NinjaScriptBase, IndicatorBase, StrategyBase, State machine, Draw.*
- **SharpDX** — RenderTarget, Brush, SolidColorBrush, StrokeStyle, TextFormat, TextLayout
- **System.Windows.Media** — Color, Brush, SolidColorBrush, Brushes (WPF stubs)
- **System.Drawing** — RectangleF, PointF

### Layer 2 — Lifecycle Simulator (`ninjatrader/simulator/Lifecycle/`)

State machine that drives NinjaScript through the full NT8 lifecycle:
```
SetDefaults → Configure → DataLoaded → Historical (replay bars) → Terminated
```

Features:
- Bar replay with OHLCV + tick-level data for OnMarketData
- DOM depth replay for OnMarketDepth
- Configurable instrument (symbol, tick size, point value)
- Strategy-specific: Account, Position simulation
- `ValidateOnly<T>()` for quick state-machine-only checks
- `Run<T>()` for full lifecycle with 60-bar synthetic NQ session

### Layer 3 — CLI Validator (`ninjatrader/simulator/Cli/`)

```bash
dotnet run --project ninjatrader/simulator -- validate           # compile + state machine
dotnet run --project ninjatrader/simulator -- validate indicator  # indicator only
dotnet run --project ninjatrader/simulator -- validate strategy   # strategy only
dotnet run --project ninjatrader/simulator -- run                 # full lifecycle replay
```

## Source File Changes (backward-compatible)

| File | Change | Why |
|------|--------|-----|
| DEEP6Footprint.cs | `#if !NINJASCRIPT_SIM` around inline Cell/FootprintBar | Avoid duplicate types with Registry versions |
| DEEP6Strategy.cs | `#if NINJASCRIPT_SIM` around volatile double | volatile double not supported in .NET 8+ |
| CaptureHarness.cs | `Registry.FootprintBar` → `FootprintBar` | Pre-existing bug (wrong namespace qualifier) |
| DEEP6Footprint.cs, DEEP6GexLevels.cs | `Math.Max` → `System.Math.Max` in legacy types | DEEP6.Math namespace shadows System.Math |

## Validation Results

- **Compile**: All 34 NinjaScript files (3,086 LOC indicator + strategy) compile against stubs
- **Lifecycle**: Both indicator and strategy pass full state machine + 60-bar replay
- **Existing tests**: All 290 NUnit tests pass (zero regressions)
