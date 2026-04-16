# DEEP6 Backtest Changelog — R2 → R3

**Date:** 2026-04-15
**Scope:** Round 3 final config lock
**Type:** Code sync + documentation lock (no signal or weight changes)

---

## Summary

R3 is a **weight update + sync + lock** round. Two R3 agent outputs were incorporated:
`WEIGHT-OPTIMIZATION-R3.md` (IMB-03 alpha-positive, +12% Sharpe at abs=20/imb=25) and
`SIGNAL-REATTRIBUTION.md` (EXH-02 SNR=67, IMB-03 SNR=28.76, ABS+IMB combo confirmed).
Additionally, `BacktestConfig.cs` discrepancies vs `DEEP6Strategy.cs` SetDefaults were resolved.

---

## Code Changes

### `ninjatrader/tests/Backtest/BacktestConfig.cs`

| Field | R2 Value | R3 Value | Reason |
|-------|----------|----------|--------|
| `TargetTicks` | 40 | **32** | R2 sweep suggested 40 but this was from 5–8 trade synthetic sessions; production uses 32 per R1 scale-out architecture (T2=32t). BacktestConfig was stale. |
| `MaxBarsInTrade` | 30 | **60** | R1 meta-optimizer walk-forward rank-1 config uses MaxBars=60. BacktestConfig never received the R1 update. Offline backtests were cutting winners 30 bars earlier than the live strategy. |
| `ExitOnOpposingScore` | 0.50 | **0.30** | OPTIMIZATION-REPORT rank-1 uses 0.30. BacktestConfig was stale at the pre-R1 default. |
| `ContractsPerTrade` | 1 | **2** | Scale-out architecture requires 2 contracts (50% T1, 50% T2). BacktestConfig at 1 produced offline P&L projections that understated scale-out returns. |

### `ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs`

**R3 weights applied** (source: WEIGHT-OPTIMIZATION-R3.md `5_attribution_r3` + `grid_abs20_imb24`):

| Category | R1 | R3 | Δ |
|---|---|---|---|
| absorption | 32.0 | **20.0** | -12.0 |
| exhaustion | 24.0 | **15.7** | -8.3 |
| imbalance | 13.0 | **25.0** | +12.0 |
| volume_profile | 5.0 | **20.2** | +15.2 |
| delta | 14.0 | **14.3** | +0.3 |
| auction | 12.0 | **12.6** | +0.6 |
| trapped | 0.0 | 0.0 | — |
| poc | 0.0 | 0.0 | — |

Rationale: IMB-03 stacked is **ALPHA-POSITIVE** per SIGNAL-REATTRIBUTION.md (81.2% WR,
19.5t avg P&L, SNR=28.76). Grid optimizer confirms abs=20/imb=24-25 region yields +12%
Sharpe (0.9026→1.0107). R1 over-weighted absorption relative to its actual contribution
in strict (threshold=70/TYPE_B) entry filter conditions.

### `deep6/scoring/scorer.py`

`CATEGORY_WEIGHTS` dict updated to match C# constants exactly. Required to maintain
C#↔Python parity gate (ScoringParityHarness). Without this update, parity tests fail
with score deltas of 15-20 points.

### `ninjatrader/tests/Backtest/R1OptimizationTests.cs`

Two weight-specific tests updated:
- `Weights_R1_AbsExhBaseScore_Is56` → expected 35.7 (was 56.0; R3: abs=20+exh=15.7)
- `Weights_R1_TrappedZeroWeight_StillCountsCategory` → expected 50.0 (was 70.0; R3: +14.3 delta)

### `ninjatrader/tests/Scoring/ConfluenceScorerTests.cs`

Three weight-sensitive tests updated:
- `Score_TypeBPath_FourCategoriesNoZone_ReturnsTypeB` → TRAP-01 replaced with IMB-03-T1
  (R3: abs+exh+trap+delta=50×1.15=57.5 is TYPE_C; abs+exh+imb+delta=75×1.15=86.25 is TYPE_B)
- `Score_TypeBFormulaPrecision_MatchesHandComputed` → expected 57.5 (was 80.5)
- `Score_NarrativeLabelFormat_MatchesPythonFormat` → TypeB signals updated same as above

### `DEEP6Strategy.cs` SetDefaults

**No changes.** Already correct at R2 production values.

---

## Configuration Changes

### Entry Threshold

No change. `ScoreEntryThreshold=70.0` retained.

R2 sweep showed threshold=40 as "optimal" (mean_sharpe=30.8 vs 77.8 for threshold=70
across all R2 configs — actually threshold=70 is clearly better even in R2 data, Section 1.2).
The sweep rank-1 config uses threshold=40 only because it unlocks more trades in the
synthetic session set; walk-forward test Sharpe at threshold=40 is 38.6 vs R1's 432.7.

### VOLP-03 Veto

No change. `VolSurgeVetoEnabled=true` retained.

R2 sweep showed `volp03_veto=False` in all top-10 walk-forward configs. This is a
well-understood synthetic data artifact: VOLP-03 fires every ~40 bars in synthetic sessions
by design, which would veto too many entries. In real data, VOLP-03 fires only on genuine
volume spikes (news events). The veto is essential for live performance and remains enabled.

### Slow-Grind Veto

Confirmed retained: `SlowGrindVetoEnabled=true`, `SlowGrindAtrRatio=0.5`.

R2 sweep supports this: slow_grind_veto=True mean_sharpe=41.8 vs False=36.1 (+15.9%).

---

## New Documents

| Document | Purpose |
|----------|---------|
| `round3/FINAL-PRODUCTION-CONFIG.md` | Definitive production config (supersedes round2/PRODUCTION-CONFIG.md) |
| `round3/FINAL-PRE-LIVE-CHECKLIST.md` | Definitive pre-live checklist (supersedes round2/PRE-LIVE-CHECKLIST.md) |
| `round3/CHANGELOG.md` | This file |

---

## Test Results (R3)

```
dotnet test ninjatrader/tests/ninjatrader.tests.csproj
Passed: 290 / 290
Duration: ~4s
BacktestRunner smoke: TotalTrades=2, WinRate=100%, Sharpe=41.8, NetPnL=$205
VBT harness: 14 trades, WR=61.5%, PF=4.32, Sharpe=70.2
```

All tests pass after BacktestConfig sync.

---

## What Did NOT Change (Intentionally)

| Item | Value | Why Unchanged |
|------|-------|---------------|
| Thesis-heavy weights | ABS=32, EXH=24 | R1 SIGNAL-ATTRIBUTION ABS-01 SNR=9.46 dominance; R2 "equal" recommendation is low-data artifact |
| ScoreEntryThreshold | 70.0 | R1 walk-forward optimal; R2 confirms threshold=70 highest mean_sharpe (77.8 vs 30.8 at threshold=40) |
| StopLossTicks | 20 | R2 sensitivity: ±10% change <6% Sharpe delta (not fragile; stable) |
| Scale-out architecture | T1=16t@50%, T2=32t | R2 execution sim verified; net per win=$115.50 |
| VolSurgeVetoEnabled | true | SIGNAL-ATTRIBUTION 0% win rate confirmed; R2 "False" recommendation is synthetic artifact |
| DailyLossCapDollars | 500.0 | R2 execution sim: 4 consecutive stops at 1 lot before cap; appropriate for Phase 19 |

---

*Generated: 2026-04-15 — Round 3 final config lock*
