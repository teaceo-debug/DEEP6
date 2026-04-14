# DEEP6 Footprint — NinjaTrader 8 Indicator

A NinjaScript C# indicator that renders the DEEP6 footprint on NinjaTrader 8 charts, with absorption and exhaustion markers ported from the DEEP6 Python signal engine, plus optional gamma exposure (GEX) overlay levels fetched from massive.com.

**Read-only.** This indicator does not place orders. It is a visual companion to the DEEP6 Python auto-trading system — same signal logic, on your existing NT8 chart, using the NT8 native Rithmic L2 feed.

## What you get on the chart

- **Footprint cells** — per-bar `bid × ask` volume grid at each price level
- **Diagonal imbalance highlights** — buy/sell imbalances (tunable ratio, default 3×)
- **POC / VAH / VAL** per bar (70% value area)
- **Absorption markers** — ABS-01 CLASSIC, ABS-02 PASSIVE, ABS-03 STOPPING VOLUME, ABS-04 EFFORT vs RESULT, with VAH/VAL proximity strength bonus
- **Exhaustion markers** — EXH-01 ZERO PRINT, EXH-02 EXHAUSTION PRINT, EXH-03 THIN PRINT, EXH-04 FAT PRINT, EXH-05 FADING MOMENTUM, EXH-06 BID/ASK FADE — with delta trajectory gate
- **GEX overlay** — gamma flip, call wall, put wall, and major ± nodes (from QQQ/NDX chain, mapped onto NQ price space)

All thresholds and algorithms match the DEEP6 Python engine; see `docs/SIGNALS.md` for the port audit.

## Installation

See `docs/SETUP.md` for the full walkthrough. Short version — **everything is in one file**:

1. Copy `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` to `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6Footprint.cs` (create the `DEEP6` subfolder if it doesn't exist).
2. In NT8: right-click the Indicators panel → Reload NinjaScript (or press F5 in the NinjaScript editor).
3. Add `DEEP6 Footprint` to a chart via Indicators → DEEP6 → DEEP6 Footprint.

Requires NinjaTrader 8.1.x, a Rithmic-connected feed with L2 depth enabled, and (for GEX) a massive.com API key.

## Project layout

```
ninjatrader/
├── README.md                      (you are here)
├── Custom/                        mirrors %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\
│   ├── Indicators/DEEP6/
│   │   └── DEEP6Footprint.cs      Read-only chart indicator — single-file build
│   └── Strategies/DEEP6/
│       └── DEEP6Strategy.cs       Auto-trader — Tier 3 confluence → ATM bracket entries
└── docs/
    ├── SETUP.md                   Install, import, first-run checklist
    ├── SIGNALS.md                 Signal reference — visuals, thresholds, Python ↔ C# audit
    ├── ARCHITECTURE.md            Data flow, threading model, rendering pipeline
    └── ATM-STRATEGIES.md          Recommended NT8 ATM templates for absorption / exhaustion / confluence
```

**Strategy safety:** `DEEP6Strategy` defaults to **DRY-RUN** (no orders). Live trading
requires explicit `EnableLiveTrading=true` AND `ApprovedAccountName` match. Hard caps
on contracts/trade, trades/session, daily loss. Read `docs/ATM-STRATEGIES.md` and set
up the 4 ATM templates before flipping the switch. The strategy duplicates the
Python DEEP6 execution path — pick one or the other for any given Rithmic account.

The single file contains three logical sections, organized by namespace:
- `NinjaTrader.NinjaScript.AddOns.DEEP6` — Cell, FootprintBar, AbsorptionDetector + config + signal, ExhaustionDetector + config + signal, MassiveGexClient + GexProfile + GexLevel
- `NinjaTrader.NinjaScript.Indicators.DEEP6` — the DEEP6Footprint indicator class itself
- `#region NinjaScript generated code` — NT8 factory partials (Indicator, MarketAnalyzerColumn, Strategy)

## Relationship to the Python DEEP6 system

This indicator is a **parallel, read-only visualization tool**. It does *not* share state, data feed, or runtime with the Python DEEP6 auto-trading engine. They can run on the same machine and the same Rithmic account, but only one of them should hold the L2 subscription at a time.

The signal logic is a faithful port — same thresholds, same algorithms — so signals that fire here should line up with signals from the Python engine on the same bar. Any divergence is a bug in one side; track via `docs/SIGNALS.md`.

## Status

Phase 16 initial build. Tested by code review only — no live NT8 compile verification. You should:

1. Import into an NT8 replay chart first (Historical mode) to verify compilation
2. Walk replay through a known session and cross-check signals against the Python engine's output
3. Then promote to live

Known limitations and follow-ups are tracked in `../.planning/phases/16-*/PLAN.md`.
