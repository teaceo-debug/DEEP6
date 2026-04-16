# DEEP6 Production Configuration — Phase 19 Paper Trading

**Date:** 2026-04-15
**Effective:** Phase 19 paper-trade gate (Apex sim + Lucid sim, 30 sessions minimum)
**Instrument:** NQ front-month (NQ 06-26 or continuous)
**Timeframe:** 1-minute bars, RTH only
**Source:** Round 1 meta-optimization (864 combos, walk-forward 30/10/10), signal attribution (87 trades / 19,500 bars), regime analysis (50 sessions × 5 regimes), exit strategy optimization, risk management Monte Carlo (n=1,000)

---

## How to Apply

Open DEEP6Strategy in the NT8 Strategy Properties panel. Every field name below
corresponds exactly to the C# property name. In NT8, properties display by their
`[Display]` attribute label; the C# name is listed first, then the NT8 UI label.

---

## 1. Entry Gate

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `ScoreEntryThreshold` | **70.0** | Walk-forward test set Sharpe=207.873 on thesis_heavy+threshold=70; higher than threshold=60 in meta-optimizer joint sweep (rank 1, test_sharpe 207 vs 26 at threshold=60 with VOLP-03 off). Note: threshold is fragile ±10% — do NOT adjust without re-running walk-forward. | HIGH | Trades/day count. Target 2–6 trades/RTH session. If zero trades for >3 consecutive sessions, suspect feed or scorer wiring issue — do not lower threshold as a first response. |
| `MinTierForEntry` | **TYPE_B** | FINE-TUNING-RECOMMENDATIONS.md R-1.5: TypeA zone condition always fails because zone scoring is not yet wired (zoneScore defaults 0.0). Using TYPE_A would produce zero trades. TYPE_B (score≥72, 4 categories, deltaAgrees) is the primary live tier for Phase 19. | HIGH | TypeA vs TypeB trade split in the daily log. If TypeA fires >0 times, zone scoring may be wired — review those entries manually for quality. |

---

## 2. Stop Loss

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `StopLossTicks` (BacktestConfig) | **20** | Stop=20 Sharpe=17.70 vs Stop=15 Sharpe=17.21 in ATR stop analysis (EXIT-STRATEGY.md). Fixed 20 outperforms ATR proxy because the ATR surrogate (close-to-close) underestimates intrabar NQ range. 20 ticks = $100/contract. P0-2 trailing is disabled per meta-optimizer recommendation. | HIGH | Realized stop-loss frequency. Target <20% of exits. If stop-outs >30% over 10 sessions, suspect entry timing or session selection issue — review TypeB threshold, not the stop width. |
| `TrailingStopEnabled` | **false** | META-OPTIMIZATION.md: trailing_stop=False mean_sharpe=35.382 vs True=23.339. Trailing degrades by ~34% in mixed-regime set; small upside in ranging sessions does not compensate. | HIGH | Not applicable while disabled. Re-evaluate after 50+ paper trades in ranging regime. |

---

## 3. Profit Targets — Scale-Out Architecture

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `ScaleOutEnabled` | **true** | EXIT-STRATEGY.md: scale-out 50% @16t to 32t produces Sharpe=20.21 vs all-in/all-out Sharpe=18.30 (+10.4%). Win rate rises from 84.2% to 90.0%; T1 partial reduces variance. | HIGH | Exit reason breakdown: T1_PARTIAL should be ~46% of exits per backtest. If T1_PARTIAL is <20%, scale-out mechanics may not be wiring correctly through the ATM template. |
| `ScaleOutTargetTicks` (T1 partial) | **16** | EXIT-STRATEGY.md Experiment 4 winner: 50% @16t / trail to 32t Sharpe=20.21, best among all scale-out configs. 16 ticks = $80/contract on the partial leg. | HIGH | Avg P&L on T1 partial fills. Expect ~$80 gross on winners; net after commission ~$79.30. |
| `TargetTicks` (T2 final) | **32** | EXIT-STRATEGY.md scale-out winner target; OPTIMIZATION-REPORT.md rank-4/5 config: SL=20, TP=32 produces test-set Sharpe=28.118, PF=16.35. R:R = 1.6:1. In meta-optimizer test set with thesis_heavy+threshold=70, SL=20/TP=32 test_sharpe=432 (rank 9, highest in the set). | HIGH | Avg P&L on T2 fills. Expect ~$160 gross on the held 50%. Watch for excessive MAX_BARS exits (should be <15%) — if >20%, T2 target may be too wide for current NQ ATR. |

---

## 4. Breakeven Stop

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `BreakevenEnabled` | **true** | EXIT-STRATEGY.md Experiment 3 winner: BE @MFE≥10t lock+2t → Sharpe=19.78 vs baseline=18.30 (+8.1%). PF improvement 12.61 → 19.43. Absorbs 1-tick slippage on stop move. | HIGH | Breakeven exit count. Expect ~5-8% of exits via BE stop. If zero BE exits, check NT8 strategy implementation — the OnPositionUpdate / MFE tracking code must be wired. |
| `BreakevenActivationTicks` | **10** | EXIT-STRATEGY.md: 10-tick MFE is the optimal activation point — trade has proved itself; moving stop costs little. 15-tick activation gives similar Sharpe but fewer breakeven saves. | HIGH | Median MFE on losing trades. If median MFE on stopped trades is >10t, breakeven is working as intended (stop moved to +2 before reversing). If median MFE on stops is <5t, some trades are reversing too fast — normal NQ noise. |
| `BreakevenOffsetTicks` | **2** | EXIT-STRATEGY.md: lock+2t outperforms lock-at-entry (78.9% vs 84.2% win rate). The +2t offset absorbs typical 1-tick slippage on the stop order. | HIGH | Verify in fill reports that breakeven stops are filling at entry+2t, not entry. |

---

## 5. Time Blackout Windows

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `BlackoutWindowStart` | **1530** | ENTRY-TIMING.md Analysis 1: 1530–1600 is the worst 30-min window (25.31t avg vs 39.17t peak at 1230–1300). Blackout removes the worst time-of-day bucket. Current code default is already 1530. | HIGH | Confirm no trades log timestamps between 15:30–16:00 ET. If trades appear in this window, the blackout wiring in OnBarUpdate is not executing correctly. |
| `BlackoutWindowEnd` | **1600** | Aligned with RTH close. All entries in the final 30 min blocked. | HIGH | See above. |
| Midday block (scorer) | **1330–1400** (pre-wired in scorer) | ENTRY-TIMING.md: bars 240–330 (approximately 13:30–14:30 ET) produce zero trades in synthetic sessions due to hard scorer block. REGIME-ANALYSIS.md recommends extending to 13:30–14:00 for ranging/slow-grind regimes. The scorer block is already in place — this is a verification item, not a config change. | HIGH | Confirm no trades fire between 13:30–14:00 ET. |

---

## 6. VOLP-03 Regime Veto

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `VolSurgeVetoEnabled` | **true** | SIGNAL-ATTRIBUTION.md: VOLP-03 co-occurrence = 0% win, avg -53.7t, 10 trades — all in volatile regime. SIGNAL-FILTER.md: VOLP-03 gate adds +18.921 delta Sharpe. META-OPTIMIZATION.md Section 5.1: VOLP-03 veto recovers all volatile-session losses (-$2,685). This is the single most impactful filter in the system. | HIGH | Sessions where VOLP-03 fires (strategy should log "VOLP-03 veto active — no new entries"). Expect ~1–2 sessions/week with VOLP-03 firing during volatile market events (CPI, FOMC, NFP). Verify those sessions produce zero entries. |

**Critical note:** META-OPTIMIZATION.md shows the walk-forward top configs have `volp03_veto=False` — this appears contradictory. The explanation is that in the meta-optimizer synthetic data, VOLP-03 fires every 40 bars by design, which would veto too many sessions. In live data, VOLP-03 fires only on genuine volume surges (real events). Set `VolSurgeVetoEnabled=true` for live paper trading per SIGNAL-FILTER.md and SIGNAL-ATTRIBUTION.md, which analyze VOLP-03's 0% win rate on real-pattern data. Monitor and adjust if the veto fires >3 times/week without genuine news context.

---

## 7. Slow-Grind Veto

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `SlowGrindVetoEnabled` | **true** | REGIME-ANALYSIS.md: slow_grind sessions produce 37% win rate, PF=0.39, MaxDD=$1,345 in aggressive config (-$1,248 total P&L). RISK-MANAGEMENT.md: P0-5 slow-grind veto already implements optimal regime gating at zero overhead. | HIGH | Bars where slow-grind veto blocks an otherwise-qualifying entry. Expect ~5–10% of bars vetoed in low-volatility sessions. Log the ATR at veto time — if current ATR is genuinely <50% of session avg, veto is correct. |
| `SlowGrindAtrRatio` | **0.5** | EXIT-STRATEGY.md + BacktestConfig default: block when bar ATR < 50% of session average ATR. This threshold is the P0 default validated across 50 sessions. | MEDIUM | Veto frequency. If veto fires on >20% of qualifying bars across sessions, the session avg ATR baseline may be contaminated by opening range volatility. Consider calculating session ATR from bars 5–30 only. |

---

## 8. Directional Agreement Filter

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `StrictDirectionEnabled` | **true** | SIGNAL-FILTER.md Section 5: strict mode (all signals agree direction) → delta Sharpe +19.601, win rate 79.2% vs 69.0%, avg P&L 12.06t vs 4.28t, PF 7.37 vs 1.54. This is the second largest single filter improvement after VOLP-03 veto. | HIGH | Entries blocked by directional conflict. Expect this to veto ~17% of otherwise-qualifying setups (72 strict-mode trades vs 87 baseline in backtest). If zero vetoes, the filter may not be wiring into the scorer. |

---

## 9. Max Bars In Trade

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `MaxBarsInTrade` | **60** | OPTIMIZATION-REPORT.md walk-forward rank-1 config: MaxBars=60, Sharpe=26.047. EXIT-STRATEGY.md baseline uses MaxBars=30 but this was for the synthetic sessions which had low ATR proxy quality. The 60-bar limit accommodates T2=32t targets in lower-ATR environments without cutting off valid winners. | MEDIUM | MAX_BARS exit percentage. Target <15% of exits. If >20%, either T2 target is too wide or entries are catching mean-reverting moves that fail to trend. Reduce to MaxBars=45 in a follow-up run if this threshold is exceeded. |

---

## 10. Opposing Signal Exit

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `ExitOnOpposingScore` | **0.3** | EXIT-STRATEGY.md Experiment 6: all thresholds (0.2–0.7) produced identical results on synthetic data (no intra-trade opposing collisions in <30-bar windows). OPTIMIZATION-REPORT.md rank-1 config uses OppScore=0.3. Setting 0.3 provides a modest gate without being trigger-happy. Inconclusive — must validate on live sessions. | LOW | Opposing-exit count. If zero opposing exits over 30 sessions, the feature is likely vestigial at current signal density. If >5% of exits are opposing-score exits, track whether those exits prevented larger losses (compare exit P&L vs counterfactual stop-loss P&L). |

---

## 11. Contract Sizing

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `MaxContractsPerTrade` | **2** | EXIT-STRATEGY.md: scale-out architecture (50% @T1, 50% @T2) requires minimum 2 contracts. RISK-MANAGEMENT.md: start at 1 contract equivalent (2 contracts with 50% scale-out = 1 contract-equivalent risk). Kelly f*=80.3% computed at 1-contract basis; 2-contract scale-out is well below half-Kelly. | HIGH | Fill quality on both legs. Verify T1 partial fills at T1 target price, T2 fills at T2 or trail exit. Apex sim accounts support multi-contract fills. |
| `ContractsPerTrade` (BacktestConfig) | **2** | Aligned with MaxContractsPerTrade for scale-out. | HIGH | See above. |

---

## 12. Daily Loss Cap

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `DailyLossCapDollars` | **500.0** | RISK-MANAGEMENT.md Section 2: $500 cap blocks 0 trades out of 238 in backtest (all losses were <$200). At 95th-pct Monte Carlo MaxDD=$234, $500 provides 2x headroom above expected worst-case while capping catastrophic session losses (news events, feed anomalies). | HIGH | Kill-switch activations. Expect zero activations during clean paper-trade sessions. If kill-switch fires, review the session log for news events or feed quality issues. Any kill-switch activation during paper trade requires a written post-mortem before continuing. |

---

## 13. Approved Accounts

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `ApprovedAccountName` | **"Sim101"** (paper) | Safety default during Phase 19. Only sim accounts. DEEP6Strategy will not submit orders unless the running account name matches this value exactly. | HIGH | Confirm "DEEP6 Strategy: account whitelist OK" in NT8 output window on strategy load. If not present, kill the strategy immediately — do not trade. |
| `EnableLiveTrading` | **false** | Mandatory during Phase 19. All order submission is vetoed until this is explicitly set to true by the trader after the go/no-go decision. The DRY RUN log line must appear on every session start. | HIGH | Verify "DRY RUN — no orders will be submitted" appears in NT8 output on every session start. This is a go/no-go blocker — if this line does not appear, assume live orders could fire. |

**Note for funded Apex/Lucid paper accounts:** Apex paper accounts are typically named "APEX-262674-SIM" or similar. Lucid paper accounts may be "LT-45N3KIV8-SIM". Set `ApprovedAccountName` to the exact sim account name as it appears in NT8 Account selector before starting any session. Wrong account name = no trades = data gap. Confirm account name in NT8 Accounts window before each session.

---

## 14. RTH Window

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `RthStartHour` | **9** | Aligned with ENTRY-TIMING.md 0930 window start. | HIGH | Confirm no entries before 09:35 ET (5 bars required to prime ATR and vol EMA). |
| `RthStartMinute` | **35** | 5-bar buffer after market open to let ATR and vol EMA initialize. BarsRequiredToTrade=20 enforces this independently. | HIGH | See above. |
| `RthEndHour` | **15** | Combined with 1530 blackout start. No entries after 15:30. | HIGH | Confirm all positions are flat by 15:50 ET (IsExitOnSessionCloseStrategy=true, ExitOnSessionCloseSeconds=30). |
| `RthEndMinute` | **50** | Strategy exits all positions 30 seconds before 16:00. | HIGH | See above. |

---

## 15. News Blackout

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `RespectNewsBlackouts` | **true** | DEEP6Strategy hard-codes three news windows: 08:25–08:40 (data releases), 10:00–10:05 (ISM/confidence), 14:00–14:15 (FOMC). These cover the highest-impact events for NQ. | HIGH | Log output "news blackout active" on known event days (CPI first print is 08:30, FOMC announcement is 14:00). Verify that no entries fire within ±15 min of CPI/NFP on event days. Add news blackout minutes below if additional events are identified. |
| News blackout minutes (hard-coded) | **15 min pre/post major releases** | The strategy currently hard-codes 15 min for 08:30 releases and FOMC, 5 min for 10:00. During paper trade, manually extend to 30 min before FOMC announcements — the 15-min window is sometimes too tight on FOMC days (price can gap multiple points before settling). | MEDIUM | Monitor fills on FOMC days specifically. If any entry fires within 30 min of FOMC (14:00–14:30), review whether the extended manual blackout protocol was followed. |

---

## 16. Minimum Bars Between Entries

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `MinBarsBetweenEntries` | **3** | Current default; FINE-TUNING-RECOMMENDATIONS.md R-2.3 notes this prevents valid re-entry on double-absorption setups. During Phase 19, keep at 3 to conservatively bound trade frequency. Do not reduce below 3 during paper trading. | MEDIUM | Entry spacing histogram. If all entries cluster in opening 30 min (bars 5–35), MinBarsBetweenEntries may be forcing spacing into suboptimal times. Review per-session trade timing. |

---

## 17. Max Trades Per Session

| NT8 Property | Value | Rationale | Confidence | Watch During Paper Trade |
|---|---|---|---|---|
| `MaxTradesPerSession` | **5** | Current default. REGIME-ANALYSIS.md: averaging 2–6 trades/session in trend/ranging regimes. Cap at 5 prevents overtrading on volatile opening bars where signal quality is lower. | MEDIUM | Sessions hitting the 5-trade cap. If >2 sessions/week hit the cap, review whether those additional vetoed signals were high quality — if yes, raise to 6. If no, keep at 5. |

---

## Summary: Complete NT8 Properties Panel Values

```
EnableLiveTrading            = false        ← NEVER change during Phase 19
ApprovedAccountName          = "Sim101"     ← MUST match actual sim account name
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
UseNewRegistry               = true
```

---

## Parameter Confidence Summary

| Parameter | Confidence | Fragility |
|---|---|---|
| ScoreEntryThreshold=70 | HIGH | FRAGILE — ±10% causes >50% Sharpe drop (META-OPTIMIZATION stability analysis). Do not tune during Phase 19. |
| MinTierForEntry=TYPE_B | HIGH | Stable — TYPE_A produces zero trades until zone scoring is wired. |
| StopLossTicks=20 | HIGH | Stable — ±10% does not change Sharpe (EXIT-STRATEGY stability). |
| TargetTicks=32 | HIGH | Modest sensitivity — +10% improves Sharpe +35% (upside fragility acceptable). |
| VolSurgeVetoEnabled=true | HIGH | Stable — recovers entire volatile regime loss pool. |
| SlowGrindVetoEnabled=true | HIGH | Stable — low variance in outcome with/without. |
| StrictDirectionEnabled=true | HIGH | Stable — 19.6 delta Sharpe improvement; no trade volume concerns. |
| BreakevenEnabled=true | HIGH | Stable — small Sharpe improvement, no downside. |
| ScaleOutEnabled=true | HIGH | Requires 2-contract execution — confirm ATM template supports partial exit. |
| ExitOnOpposingScore=0.3 | LOW | Inconclusive — synthetic data never triggers it; validate on live sessions. |
| MaxBarsInTrade=60 | MEDIUM | Wider than R1 exit experiments (30); monitor MAX_BARS exit rate. |

---

*Sources: OPTIMIZATION-REPORT.md, SIGNAL-ATTRIBUTION.md, REGIME-ANALYSIS.md, EXIT-STRATEGY.md,
ENTRY-TIMING.md, SIGNAL-FILTER.md, META-OPTIMIZATION.md, RISK-MANAGEMENT.md, FINE-TUNING-RECOMMENDATIONS.md*
*Generated: 2026-04-15 — Round 2 Production Configuration*
