# DEEP6 Footprint — Setup Guide

## Prerequisites

- **NinjaTrader 8.1.x** on Windows (NT8 is Windows-only; no macOS runtime)
- **Rithmic-connected account** with L2 market depth enabled (EdgeClear, AMP, Tradovate-via-Rithmic all work)
- **.NET Framework 4.8** — shipped with NT8 already; nothing to install
- **massive.com API key** (optional, only if you want GEX levels)

## File placement

NinjaTrader keeps its user-space source tree at `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\`. Files under `Indicators\` become indicators; files under `AddOns\` are shared helpers/data classes.

Layout after install:

```
%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\
├── Indicators\
│   └── DEEP6\
│       └── DEEP6Footprint.cs
└── AddOns\
    └── DEEP6\
        ├── FootprintBar.cs
        ├── AbsorptionDetector.cs
        ├── ExhaustionDetector.cs
        └── MassiveGexClient.cs
```

### Step-by-step

The `ninjatrader/Custom/` directory in this repo mirrors NT8's layout 1:1, so you can merge it in place.

1. Close NinjaTrader if it's running.
2. Open File Explorer, go to the repo's `ninjatrader/Custom/` folder.
3. Select both `Indicators` and `AddOns` subfolders and copy them into `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\`. Choose **Merge** when Windows asks about the existing `Indicators` / `AddOns` folders — do NOT replace. The DEEP6 subfolders land alongside any existing content.
4. Start NinjaTrader.
5. Open the **NinjaScript Editor** (New → NinjaScript Editor). Press **F5** to compile.
   - Any compile error appears in the Errors tab at the bottom. The build produces `NinjaTrader.Custom.dll` at `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll`.
6. Once compile succeeds: open any chart, right-click → **Indicators…**, expand **DEEP6** in the tree, double-click **DEEP6 Footprint**, click **OK**.

## First-run configuration

The indicator properties grid is grouped:

1. **Detection** — imbalance ratio (default 3.0), absorption wick-min % (30), exhaustion wick-min % (35). Don't change these unless you're profiling.
2. **Display** — toggle cells, POC, VA, absorption markers, exhaustion markers independently. Font size and column width default to fit a ~6-tick bar.
3. **GEX (massive.com)** — ShowGexLevels, GexUnderlying (`QQQ` or `NDX` — `QQQ` recommended), GexApiKey. Leave API key empty to disable GEX entirely.
4. **Colors** — every visual element is customizable.

## Chart settings that matter

- **Chart type**: if the default OHLC bars are visually noisy behind the footprint cells, switch the chart to **Dot** or **Line** and let the footprint become the primary visual.
- **Tick replay**: footprint requires tick-level intake. Without tick replay enabled, historical bars will show **no footprint** — only live/realtime bars will fill. Enable via chart Data Series → **Tick Replay = True**, and pick a chart type that supports tick granularity (e.g., Volume or Range bars).
- **Calculate = OnEachTick** is set automatically by the indicator.
- **BarsInProgress** routing is handled internally — no secondary data series needed.

## Exporting for distribution

To ship the indicator to another NT8 user:

1. Tools → Export → NinjaScript Add-On.
2. Select `DEEP6Footprint.cs` and the four AddOn files.
3. Name it `DEEP6Footprint`, export. NT writes `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\ExportNinjaScript\DEEP6Footprint.zip`.
4. Recipient imports via Tools → Import → NinjaScript Add-On → pick the `.zip`.

## Troubleshooting

**"Indicator doesn't appear on chart"**
- Check the Indicators panel for compile errors (F5 in NinjaScript editor).
- Confirm `ShowFootprintCells` is true.
- Verify the chart is live (realtime) or has tick replay enabled.

**"Footprint cells are blank on historical bars"**
- Expected without Tick Replay. Turn on Tick Replay in Data Series to populate history.

**"No absorption/exhaustion markers fire"**
- These fire only on bar close. Wait for bars to complete.
- ATR and volume EMA warm up over the first ~20 bars; signals are suppressed during warmup.
- Exhaustion has a 5-bar cooldown per variant — if a bar just fired a ZERO_PRINT, the next 5 bars won't fire another.

**"GEX levels don't appear"**
- Verify API key is populated and `ShowGexLevels` is true.
- Fetch happens every 2 minutes; first render may take up to 2 min.
- Check the NT8 Output window (New → Output Window) for "GEX fetch failed" messages.
- Confirm massive.com plan covers real-time (or delayed, acceptable for GEX) options chain snapshots.

**"NQ levels look wrong"**
- GEX strikes are in QQQ price space; the indicator maps them onto NQ by `spot_ratio = NQ_close / QQQ_close`. This is a rough visual mapping — confirm with your own GEX tool before treating a level as tradeable.

## Running alongside the Python DEEP6 engine

Rithmic only guarantees one L2 depth subscription per account per gateway. If you run both NT8 and the Python engine on the same Rithmic account:

- Use separate Rithmic logins (one demo, one live; or a secondary API-only credential if your broker supports it).
- OR run NT8 and Python at different times (NT8 for manual review, Python for execution).
- OR subscribe to Level 2 in only one (e.g., Python for the live signals, NT8 with Level 1 + tick replay for visual review).
