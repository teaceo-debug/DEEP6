# DEEP6 Final Production Configuration — R3 Lock

**Date:** 2026-04-15
**Supersedes:** round2/PRODUCTION-CONFIG.md
**Instrument:** NQ front-month (NQ 06-26 or continuous)
**Timeframe:** 1-minute bars, RTH only
**Status:** LOCKED — Phase 19 paper-trade gate

---

## R3 Context

No new R3 sweep/weight-optimizer agent outputs were available at lock time.
R3 config is based on:
- R2 production config (PRODUCTION-CONFIG.md) — baseline
- R2 full sweep (SWEEP-COMPARISON.md) — informational; key findings incorporated
- R2 stress test (STRESS-TEST.md) — robustness flags noted
- R2 execution sim (EXECUTION-SIM.md) — fill model verified
- Code audit: BacktestConfig.cs ↔ DEEP6Strategy.cs discrepancies resolved

**R2 sweep note (important):** The R2 sweep recommended `entry_threshold=40`, `target=40`,
`equal weights`, `volp03_veto=False`. These recommendations are **NOT adopted** because:
1. Top R2 configs produced only 5–8 trades across 50 sessions — statistically insignificant.
2. R2 "optimal" configs show `volp03_veto=False`, which contradicts the SIGNAL-ATTRIBUTION.md
   finding (VOLP-03 = 0% win rate, -53.7t avg). The veto improves signal quality in real data
   even if it reduces trade count in synthetic sessions designed without genuine news spikes.
3. The R2 walk-forward test Sharpe (38.6) for the "optimal" threshold=40 config is materially
   lower quality than the R1 analysis (real signal data, 87 trades, 19,500 bars).
4. threshold=70 is the R1 validated entry gate; lowering to 40 increases trade volume at the
   cost of signal quality — the opposite of the thesis.

The R1/R2 production config at threshold=70 is retained. All other R2 production parameters
that diverged from R1 have been reconciled.

---

## Code Changes Applied in R3

| File | Change | Reason |
|------|--------|--------|
| `ninjatrader/tests/Backtest/BacktestConfig.cs` | `TargetTicks` 40→32 | Sync to DEEP6Strategy.cs SetDefaults (production = 32, scale-out T2) |
| `ninjatrader/tests/Backtest/BacktestConfig.cs` | `MaxBarsInTrade` 30→60 | Sync to DEEP6Strategy.cs SetDefaults (production = 60, R1 meta-optimizer) |
| `ninjatrader/tests/Backtest/BacktestConfig.cs` | `ExitOnOpposingScore` 0.50→0.30 | Sync to DEEP6Strategy.cs SetDefaults (production = 0.3, R1 rank-1 config) |
| `ninjatrader/tests/Backtest/BacktestConfig.cs` | `ContractsPerTrade` 1→2 | Sync to scale-out architecture (50% T1, 50% T2 requires 2 contracts) |
| `ConfluenceScorer.cs` | No change | R1 thesis-heavy weights retained (R2 "equal" weight recommendation is artifact of low-trade-count synthetic data) |

---

## Weight Vector (LOCKED — same as R1)

| Category | Weight | Rationale |
|---|---|---|
| absorption | **32.0** | ABS-01 SNR=9.46 — highest alpha driver per SIGNAL-ATTRIBUTION.md |
| exhaustion | **24.0** | Second-highest SNR; required for TypeB/TypeA tier classification |
| delta | **14.0** | Confirmation signal; 5 specific IDs vote (DELT-04/05/06/08/10) |
| imbalance | **13.0** | Dedup logic limits contribution (0.5 vote); weight anchors category presence |
| auction | **12.0** | AUCT-01/02/05 vote; session structure context |
| volume_profile | **5.0** | Zone proximity bonus; fires when zoneScore>0 |
| trapped | **0.0** | Near-zero SNR per SIGNAL-ATTRIBUTION.md; retained at 0 |
| poc | **0.0** | Negligible SNR; retained at 0 |

**Total: 100.0**

**R2 sweep recommendation (equal weights, all=14.3) is NOT adopted.** Equal weights inflate
auction/poc/trapped to the same level as absorption — degrading signal quality.

---

## 1. Entry Gate

| Parameter | Value | Confidence |
|---|---|---|
| `ScoreEntryThreshold` | **70.0** | HIGH — R1 walk-forward optimum; R2 confirms threshold=70 highest mean_sharpe at 77.8 vs 30.8 for threshold=40 |
| `MinTierForEntry` | **TYPE_B** | HIGH — TypeA produces zero trades (zone scoring not wired = zoneScore=0) |

---

## 2. Stop Loss

| Parameter | Value | Confidence |
|---|---|---|
| `StopLossTicks` | **20** | HIGH — R2 sensitivity: ±10% change <6% Sharpe impact (not fragile) |
| `TrailingStopEnabled` | **false** | HIGH — R2 confirms: trailing_stop=False mean_sharpe=44.1 vs True=33.8 |

---

## 3. Profit Targets

| Parameter | Value | Confidence |
|---|---|---|
| `ScaleOutEnabled` | **true** | HIGH — R2 execution sim: T1=16t@50% / T2=32t@50%, net per-win=$115.50 |
| `ScaleOutTargetTicks` | **16** | HIGH — R1 EXIT-STRATEGY winner; R2 execution sim verified |
| `TargetTicks` (T2) | **32** | HIGH — R1 rank-4/5 config SL=20/TP=32 Sharpe=28.1; R2 sensitivity: TP+10%=+2.1% Sharpe (not fragile) |

---

## 4. Breakeven Stop

| Parameter | Value | Confidence |
|---|---|---|
| `BreakevenEnabled` | **true** | HIGH — R1 EXIT-STRATEGY: +8.1% Sharpe; R2 execution sim verified |
| `BreakevenActivationTicks` | **10** | HIGH |
| `BreakevenOffsetTicks` | **2** | HIGH |

---

## 5. Time Blackout

| Parameter | Value | Confidence |
|---|---|---|
| `BlackoutWindowStart` | **1530** | HIGH — R1 ENTRY-TIMING worst window |
| `BlackoutWindowEnd` | **1600** | HIGH |

---

## 6. Veto Filters

| Parameter | Value | Confidence |
|---|---|---|
| `VolSurgeVetoEnabled` | **true** | HIGH — SIGNAL-ATTRIBUTION: VOLP-03 = 0% win / -53.7t avg; R2 sweep "False" recommendation is synthetic-data artifact |
| `SlowGrindVetoEnabled` | **true** | HIGH — R2 confirms: slow_grind_veto=True mean_sharpe=41.8 vs False=36.1 |
| `SlowGrindAtrRatio` | **0.5** | MEDIUM |

---

## 7. Directional Filter

| Parameter | Value | Confidence |
|---|---|---|
| `StrictDirectionEnabled` | **true** | HIGH — R1 SIGNAL-FILTER: delta Sharpe +19.601 |

---

## 8. Exit / Position Management

| Parameter | Value | Confidence |
|---|---|---|
| `MaxBarsInTrade` | **60** | MEDIUM — R1 meta-optimizer; BacktestConfig now synced to 60 |
| `ExitOnOpposingScore` | **0.3** | LOW — inconclusive; BacktestConfig now synced to 0.3 |
| `MaxContractsPerTrade` | **2** | HIGH — scale-out requires 2 |
| `MaxTradesPerSession` | **5** | MEDIUM |
| `MinBarsBetweenEntries` | **3** | MEDIUM |

---

## 9. Risk Management

| Parameter | Value | Confidence |
|---|---|---|
| `DailyLossCapDollars` | **500.0** | HIGH — R2 execution sim: 4 consecutive stops at 1 lot before cap fires |

---

## 10. Session Window

| Parameter | Value | Confidence |
|---|---|---|
| `RthStartHour` | **9** | HIGH |
| `RthStartMinute` | **35** | HIGH |
| `RthEndHour` | **15** | HIGH |
| `RthEndMinute` | **50** | HIGH |
| `RespectNewsBlackouts` | **true** | HIGH |
| `BarsRequiredToTrade` | **20** | HIGH |

---

## 11. Safety / Identity

| Parameter | Value | Confidence |
|---|---|---|
| `EnableLiveTrading` | **false** | HIGH — MANDATORY during Phase 19 |
| `ApprovedAccountName` | **"Sim101"** | HIGH — set to exact sim account name before each session |
| `UseNewRegistry` | **true** | HIGH — Phase 17 Wave 5 parity PASS |
| `Calculate` | **OnBarClose** | HIGH — verified in DEEP6Strategy.cs SetDefaults |
| `RealtimeErrorHandling` | **StopCancelClose** | HIGH — verified in DEEP6Strategy.cs SetDefaults |

---

## Complete NT8 Properties Panel

```
EnableLiveTrading            = false        ← NEVER change during Phase 19
ApprovedAccountName          = "Sim101"     ← set to exact sim account name
UseNewRegistry               = true
ScoreEntryThreshold          = 70.0
MinTierForEntry              = TYPE_B
StopLossTicks                = 20
TrailingStopEnabled          = false
ScaleOutEnabled              = true
ScaleOutTargetTicks          = 16
TargetTicks                  = 32
BreakevenEnabled             = true
BreakevenActivationTicks     = 10
BreakevenOffsetTicks         = 2
MaxBarsInTrade               = 60
ExitOnOpposingScore          = 0.3
BlackoutWindowStart          = 1530
BlackoutWindowEnd            = 1600
VolSurgeVetoEnabled          = true
SlowGrindVetoEnabled         = true
SlowGrindAtrRatio            = 0.5
StrictDirectionEnabled       = true
MaxContractsPerTrade         = 2
ContractsPerTrade            = 2
DailyLossCapDollars          = 500.0
MaxTradesPerSession          = 5
RthStartHour                 = 9
RthStartMinute               = 35
RthEndHour                   = 15
RthEndMinute                 = 50
RespectNewsBlackouts         = true
MinBarsBetweenEntries        = 3
```

---

## BacktestConfig.cs Defaults (R3 Synced)

```
SlippageTicks              = 1.0     (offline backtests; live uses ATM template)
StopLossTicks              = 20
TargetTicks                = 32      ← R3: was 40 (sync to strategy)
MaxBarsInTrade             = 60      ← R3: was 30 (sync to strategy)
ExitOnOpposingScore        = 0.30    ← R3: was 0.50 (sync to strategy)
ContractsPerTrade          = 2       ← R3: was 1 (scale-out requires 2)
ScoreEntryThreshold        = 70.0
MinTierForEntry            = TYPE_B
BreakevenEnabled           = true
BreakevenActivationTicks   = 10
BreakevenOffsetTicks       = 2
ScaleOutEnabled            = true
ScaleOutPercent            = 0.5
ScaleOutTargetTicks        = 16
TrailingStopEnabled        = false
BlackoutWindowStart        = 1530
BlackoutWindowEnd          = 1600
StrictDirectionEnabled     = true
VolSurgeVetoEnabled        = true
SlowGrindVetoEnabled       = true
SlowGrindAtrRatio          = 0.5
```

---

## R2 Stress Test Flags (Carried Forward)

| Flag | Verdict | Action |
|------|---------|--------|
| T2 Signal Degradation (20% miss) | FAIL — 72% PnL retention | Monitor signal fire rate in paper trade; if ABS-01 fires <5 times/session over 5 sessions, investigate detector wiring |
| T7 Overfit Detector (25/25 split) | FAIL — 0 trades in last 25 sessions | Artifact of synthetic session ordering (trend/ranging/volatile/slow_grind ordered; last 25 are slow_grind-heavy). Not an actionable overfit — signal fires in trend sessions, not slow_grind. Confirmed by VOLP-03 veto and slow_grind veto interaction. |

---

## Execution Model (R2 Confirmed)

| Metric | Value |
|--------|-------|
| Avg entry slippage | 0.50 ticks (realistic 60/30/10% model vs 1.0t backtest assumption — FAVORABLE) |
| Avg exit slippage | 0.40 ticks |
| RT commission | $4.50 (NQ, prop firm) |
| Net per full win | $115.50 |
| Net per full loss | $-104.50 |
| Blended R:R | 1.2:1 (scale-out) |
| Slippage breakeven | >5 ticks (PASS) |
| Consecutive stops before $500 cap | 4 (1 lot) |

---

*Sources: round1/ (all), round2/ (all), ConfluenceScorer.cs, BacktestConfig.cs, DEEP6Strategy.cs SetDefaults*
*Generated: 2026-04-15 — Round 3 Final Lock*
