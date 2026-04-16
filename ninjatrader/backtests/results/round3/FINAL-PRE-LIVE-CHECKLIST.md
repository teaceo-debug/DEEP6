# DEEP6 Final Pre-Live Checklist — R3

**Instrument:** NQ front-month
**Account:** APEX-262674 (Apex funded) — primary; LT-45N3KIV8 (Lucid funded) — secondary
**Gate:** ALL Blocker=YES items must be checked before setting `EnableLiveTrading=true`
**Version:** R3 — adds Groups 8–9 (code audit items + stress-test mitigations)
**Supersedes:** round2/PRE-LIVE-CHECKLIST.md
**Date prepared:** 2026-04-15

---

## Groups 1–7: Carry Forward from R2

*All items 1–73 from round2/PRE-LIVE-CHECKLIST.md apply without modification.*
*Refer to round2/PRE-LIVE-CHECKLIST.md for the full text of items 1–73.*

Key unchanged items:
- Item 1–10: Code Readiness (compile, load, no NullRef, UseNewRegistry=true, shared state wired)
- Item 11–28: Configuration (EnableLiveTrading=false, ApprovedAccountName, all thresholds)
- Item 29–37: Data Validation (Rithmic feed, footprint bars, aggressor field, signals firing)
- Item 38–48: Paper Trading Gate (30 sessions, WR>=75%, PF>=2.0, 30 minimum trades)
- Item 49–58: Risk Management (DailyLossCap, account whitelist, scale-up path)
- Item 59–67: Operational (NT8 stability, latency, backup internet, Output window visible)
- Item 68–73: Mental / Trader Readiness

---

## Group 8: R3 Code Audit Verifications

*New items added based on R3 BacktestConfig sync and code audit findings.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 74 | [ ] Calculate=OnBarClose confirmed in DEEP6Strategy.cs SetDefaults | Search for `Calculate = Calculate.OnBarClose` in DEEP6Strategy.cs SetDefaults block. This must be OnBarClose — NOT OnEachTick or OnPriceChange. OnEachTick would fire the scorer on every DOM update (1,000/sec), producing incorrect bar-close scores and extreme CPU load. Verify once before any paper session. | YES |
| 75 | [ ] RealtimeErrorHandling=StopCancelClose confirmed | Verify `RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose` in SetDefaults. This ensures NT8 closes all open positions on data feed error or disconnect. Without it, a disconnect with an open NQ position is an unmonitored risk. | YES |
| 76 | [ ] BacktestConfig.TargetTicks=32 (R3 sync) matches strategy TargetTicks=32 | Open BacktestConfig.cs and confirm TargetTicks=32. R3 change: was 40 (R2 sweep artifact). BacktestConfig and DEEP6Strategy must agree for offline backtest results to be comparable to live performance. Mismatch = backtest assumes wider target than live strategy uses. | YES |
| 77 | [ ] BacktestConfig.MaxBarsInTrade=60 (R3 sync) matches strategy MaxBarsInTrade=60 | Open BacktestConfig.cs and confirm MaxBarsInTrade=60. R3 change: was 30 (R2 default, not carried forward). Offline backtest now matches live bar-timeout behavior. | YES |
| 78 | [ ] BacktestConfig.ExitOnOpposingScore=0.30 (R3 sync) matches strategy ExitOnOpposingScore=0.3 | Open BacktestConfig.cs and confirm ExitOnOpposingScore=0.30. R3 change: was 0.50. | NO — alignment item |
| 79 | [ ] BacktestConfig.ContractsPerTrade=2 (R3 sync) matches scale-out architecture | Open BacktestConfig.cs and confirm ContractsPerTrade=2. R3 change: was 1. BacktestRunner P&L projections now use scale-out sizing (50% T1@16t, 50% T2@32t) consistent with live ATM template. | YES |
| 80 | [ ] No thread-safety violations in signal registry path | In NT8 Output window, watch for `InvalidOperationException` or `Collection was modified; enumeration operation may not execute` errors during the first 30 minutes of any paper session. These indicate the DetectorRegistry or ScorerSharedState is being read and written from different threads. OnBarUpdate (bar close) and OnMarketData (tick) callbacks can overlap if Calculate=OnEachTick — Calculate=OnBarClose prevents this. If these errors appear, verify Calculate mode first. | YES |
| 81 | [ ] ConfluenceScorer.W_IMBALANCE contribution understood (dedup behavior) | W_IMBALANCE=13.0 in ConfluenceScorer.cs, but the actual score contribution of an imbalance signal is 0.5 to weightSum (dedup: only the highest stacked tier contributes 0.5). The weight=13.0 applies only via CategoryWeight() → baseScore, which adds 13.0 when "imbalance" appears in categoriesAgreeing. The dedup vote (0.5) controls whether the category appears at all, not the category weight. This is correct and intentional — verify no refactor has changed this logic before paper trade. | NO — code integrity check |
| 82 | [ ] dotnet test passes 290/290 before first paper session | Run `dotnet test ninjatrader/tests/ninjatrader.tests.csproj` from the repo. All 290 tests must pass. Any test failure after a code change is a blocker — do not paper-trade with a red test suite. | YES |

---

## Group 9: R2 Stress Test Mitigations

*Items to monitor during paper trade that address the two FAIL findings from STRESS-TEST.md.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 83 | [ ] T2 mitigation: Signal fire rate monitoring enabled (20% signal degradation FAIL) | The stress test showed 20% signal degradation drops PnL to 72% (FAIL threshold). During paper trade, log and count unique signal IDs per session. If ABS-01 fires on <5% of bars in any 5-session window (vs 9.9% baseline per SIGNAL-ATTRIBUTION.md), investigate DetectorRegistry registration or Rithmic feed quality. Do not lower entry threshold as a response — investigate the detector. | NO — monitoring requirement |
| 84 | [ ] T7 overfit note documented: last-25-sessions zero trades is a session-ordering artifact | The T7 overfit warning (test Sharpe=0.00) was caused by synthetic session ordering — last 25 sessions were dominated by slow_grind and volatile regimes where the slow_grind veto and VOLP-03 veto correctly suppress all entries. This is NOT an overfit: the system intentionally fires only in trend/ranging environments. Confirm this understanding is documented before going live — do not disable veto filters to "fix" T7. | NO — documentation requirement |

---

## Final Gate Summary (R3)

**Total items: 84** (73 from R2 + 11 new R3 items)

**Blocker=YES items:** 56 total (R2's 49 + 7 new R3 blockers: items 74, 75, 76, 77, 79, 80, 82)

**Three Most Critical (unchanged from R2):**
1. Item 11: EnableLiveTrading=false
2. Item 39: Paper-trade win rate >= 75% over 30 sessions
3. Item 49: DailyLossCapDollars confirmed at $500

**New critical addition (R3):**
4. Item 74: Calculate=OnBarClose confirmed — incorrect Calculate mode is the highest risk of silent strategy malfunction in NT8 (scorer fires every tick, producing garbage scores and potential runaway order submission at wrong bar state).

---

*Sources: round2/PRE-LIVE-CHECKLIST.md, FINAL-PRODUCTION-CONFIG.md, STRESS-TEST.md, BacktestConfig.cs, DEEP6Strategy.cs*
*Generated: 2026-04-15 — Round 3 Final Pre-Live Checklist*
