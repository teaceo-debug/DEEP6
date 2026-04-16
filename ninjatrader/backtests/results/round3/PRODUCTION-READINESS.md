# DEEP6 Production Readiness — Round 3 Sign-Off

**Date:** 2026-04-15  
**Instrument:** NQ front-month (RTH, 1-min bars)  
**Accounts:** APEX-262674 (Apex funded), LT-45N3KIV8 (Lucid funded)  
**Status:** Pre-paper-trade — Phase 18 plan-04 (parity gate) still outstanding  
**Sources:** Round 1 + Round 2 backtest corpus (50 sessions × 5 regimes, 19,500 bars, 238 trades), 290 NUnit tests, Phase 18 context, FINE-TUNING-RECOMMENDATIONS.md, STRESS-TEST.md, PRE-LIVE-CHECKLIST.md, PRODUCTION-CONFIG.md, all attribution and optimization reports.

---

## 1. System Scorecard

| Dimension | Score | Rationale |
|---|---|---|
| Signal quality | **7 / 10** | 10 active detectors (of 44 ported) have real fire-rate and attribution data. ABS-01 is the dominant alpha engine: SNR=9.46, 77.8% win rate, 13.4t avg P&L. EXH-02 has positive expectancy (65%) when regime-filtered. IMB-01 co-occurrence amplifies quality. However: only 10 signals have live backtest attribution — the remaining 34 (TRAP, DELT-02/05/06/08-11, AUCT-02–05, etc.) are ported but unvalidated in the scorer context. VOLP-03 is a regime marker, not a directional signal. Delta (DELT-04) is conditionally toxic — 100% win in ranging, 0% in volatile. Signal quality is meaningfully concentrated. |
| Scoring accuracy | **6 / 10** | Two-layer confluence scorer is correctly architected. Walk-forward top configs show Sharpe=26–28 on 10-session hold-out. Critical flaw: `volume_profile` category weight=10 is phantom (zone scoring at 0.0 defaults, TypeA `hasZone` always fails). TypeA is structurally unreachable today. TypeB is the operational tier and shows 87.5% win rate / 12.9t avg P&L in backtest attribution. Phase 18 plan-04 (C#↔Python parity gate, |Δ|≤0.05 per bar) is not yet complete — exact scorer wiring in NT8 is unverified at bar level. Threshold=70 fragility is documented: ±10% causes >50% Sharpe drop. |
| Entry timing | **6 / 10** | Time-of-day blackouts are well-calibrated (1530–1600, pre-wired 1330–1400 midday block). Bar-close entry lag is a structural cost: system enters at next bar open, missing the first 20–40 ticks of the reversal move. ENTRY-TIMING.md shows 1230–1300 ET is the peak window (39.17t avg, 100% WR), but this depends on relaxed-mode synthetic data — not validated on live RTH sessions. BarsRequiredToTrade=20 adds a 20-bar warm-up buffer. MinBarsBetweenEntries=3 prevents optimal double-absorption re-entry. Entry confidence is moderate. |
| Exit management | **7 / 10** | Scale-out architecture (50% @T1=16t, hold to T2=32t) is the validated best config: Sharpe=20.21 vs 18.30 all-in/all-out (+10.4%). Breakeven @MFE≥10t lock+2t is the best breakeven config (+8.1% Sharpe). Opposing-exit feature is inconclusive (identical results at all thresholds in synthetic data — never fires intra-trade). TrailingStop disabled per meta-optimizer finding (trailing=False: mean_sharpe=35.382 vs True=23.339, -34% degradation). The ATM template scale-out wiring (DEEP6_Confluence: 2 contracts, T1=16t, T2=32t, SL=20t) must be verified before first session. |
| Risk management | **8 / 10** | Risk architecture is thorough and layered: $500 daily kill-switch (blocks 0/238 trades in backtest), VOLP-03 veto (recovers $2,685 in volatile session losses), slow-grind ATR veto, strict direction filter (+19.6 delta Sharpe), RTH window gate, news blackouts (3 hard-coded windows), account whitelist with EnableLiveTrading=false DRY RUN gate, RealtimeErrorHandling=StopCancelClose. Monte Carlo 95th-pct MaxDD=$234.81 on 1-contract baseline. Kelly f*=80.3% — running 2 contracts (scale-out) is still well below half-Kelly. The one gap: weekly/monthly drawdown caps are trader-discipline rules, not code-enforced. |
| Regime awareness | **7 / 10** | Regime gating is the strongest feature. Conservative config produces 0 trades in volatile and slow_grind sessions — both are correctly avoided by VOLP-03 and ATR veto respectively. Ranging sessions: 98% WR, PF=385.96. Trend sessions: 81–87% WR. Slow grind with aggressive config shows -$1,248 / MaxDD=$1,345 — the veto correctly blocks this. SIGNAL-ATTRIBUTION.md confirms the regime split is decisive. Weakness: regime detection is reactive (VOLP-03 fires on the bad bar, not predictively), and slow-grind ATR veto has MEDIUM confidence due to potential session ATR contamination from the opening range. |
| Code quality | **6 / 10** | Phase 17 completed: all 44 ISignalDetector implementors ported, UseNewRegistry=true flipped. Phase 18 plans 01–03 completed: ConfluenceScorer.cs, NarrativeCascade.cs, ScorerSharedState hand-off, EvaluateEntry migration. Phase 18 plan-04 (parity gate) is NOT complete — C#↔Python scoring parity at bar level has not been validated. FINE-TUNING-RECOMMENDATIONS.md documents 4 critical blockers: (1) zone scoring unwired / TypeA phantom, (2) bar-close entry lag understated in backtest, (3) re-entry after stop missing, (4) delta chase threshold not ATR-normalized. Memory leak risk (Dict cleanup cutoff) noted in PRE-LIVE-CHECKLIST.md. No threading issues in NT8 (single-threaded NinjaScript). |
| Test coverage | **7 / 10** | 290 NUnit tests across detector registry, scorer fixtures, and parity harness (Phase 17 + 18). Fixture-level parity is bit-for-bit (4 decimals) per 18-CONTEXT.md decisions. Session-replay parity (|Δ|≤0.05 per bar, ≥5 recorded NQ sessions) is the Phase 18 plan-04 deliverable and is not yet confirmed passed. The 290 tests cover the critical signal logic and scoring formula. Operational gaps: no live feed integration tests, no ATM template fill tests, no NT8 crash recovery tests. |
| Backtest validity | **4 / 10** | This is the most significant limitation. All backtests run on synthetic NDJSON sessions generated to approximate NQ regimes — not on real Rithmic tick data or Databento MBO replay. STRESS-TEST.md confirms: T7 overfit detector (25/25 split) returned Test/Train Sharpe=0.00 (FAIL, OVERFIT WARNING). T2 signal degradation at 20% miss rate: only 72% of iterations profitable (FAIL). Entry-timing analysis required relaxed mode (VOLP-03 veto off) because strict mode produced only 1 trade in 50 sessions. Walk-forward holds out 10 sessions of synthetic data — not a live forward test. Sharpe numbers (17–208) are inflated by synthetic data smoothness. Real NQ sessions have fat tails, news gaps, and bid/ask spread not modeled. The edge direction (absorption + regime filter) is credible but the quantitative metrics should not be taken at face value for sizing decisions. |
| Live-readiness | **5 / 10** | Phase 18 plan-04 (parity gate) is the last code gate before Phase 19. Until parity is confirmed on real recorded sessions, the NT8 scorer may diverge from the Python reference in ways not caught by unit tests. All 73 YES-blocker checklist items in PRE-LIVE-CHECKLIST.md are defined but none have been checked — Phase 19 has not started. Key pre-paper-trade steps still required: NT8 compilation verification, live Rithmic feed validation, ScorerSharedState wiring confirmation, ATM template DEEP6_Confluence verification, 30-session paper run. The system architecture is complete but live validation is zero. |

**Overall weighted score: 63 / 100** — Architecturally sound, analytically thorough, but carrying two material gaps: synthetic-only backtest data and incomplete parity gate before paper trading.

---

## 2. Go/No-Go Assessment — Phase 19 Success Criteria

| Criterion | Status | Notes |
|---|---|---|
| **SC1: Strategy runs 30 consecutive RTH sessions without crashes** | **NEEDS WORK** | Phase 19 not started. Code compiles per Phase 17/18 reports. Phase 18 plan-04 (last code gate) still outstanding — parity harness with live sessions not yet validated. Cannot confirm NT8 stability without running live. Blocker: complete Phase 18 plan-04, then start paper sessions. |
| **SC2: Daily P&L log with per-signal attribution** | **NEEDS WORK** | DEEP6Strategy log output is implemented (`[DEEP6 Scorer] bar=N score=X tier=Y narrative=Z` per bar per 18-CONTEXT.md plan 03). Per-session trade log with signal attribution is spec'd in PRE-LIVE-CHECKLIST.md item 45, 63. Log file export to disk (NT8 log export config) is a STRONGLY RECOMMENDED non-blocker item — must be activated before first paper session to enable post-session attribution. |
| **SC3: All risk gates verified firing correctly** | **NEEDS WORK** | All 5 risk gates (account whitelist, news blackout, daily loss cap, max trades/session, RTH window) are implemented in DEEP6Strategy.cs. None have been verified firing on a live session. PRE-LIVE-CHECKLIST.md items 43, 46 require: each gate logs at least once across 30 sessions; daily loss cap must be manually triggered in a dedicated test session. The gate code is present; verification requires live sessions. |
| **SC4: Slippage report per signal tier** | **NEEDS WORK** | No live slippage data exists. PRE-LIVE-CHECKLIST.md item 42 defines the acceptance criterion: 95th-percentile fill slippage ≤4 ticks per side. STRESS-TEST.md T3 shows the system is profitable through 5 ticks of slippage (PASS), but this is on synthetic data. Real NQ slippage at market entry on a 1-min close bar: expect 1–3 ticks in normal conditions, 4–8 ticks on news-driven bars. TypeB entries (score=72+, strict direction) should have favorable fill conditions vs low-conviction entries. Actual slippage report requires 30 paper sessions. |
| **SC5: Written go/no-go decision document committed** | **BLOCKED** | The go/no-go decision document (`.planning/GO-NOGO-PHASE19.md`) per PRE-LIVE-CHECKLIST.md item 48 cannot be written until 30 paper sessions are completed and metrics are available. This is the terminal gate — no live trading until this document exists and is committed. |

---

## 3. Known Risks + Mitigations

Ranked by Probability × Impact (High = immediate action required):

| Rank | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Backtest-to-live performance gap (synthetic data)** | HIGH | HIGH | All 50 backtest sessions are synthetic NDJSON, not real Rithmic/Databento MBO data. The stress test T7 overfit detector failed (Test Sharpe=0.00). Accept that the first 30 paper sessions are the real backtest. Do not size up until live WR≥75% and PF≥2.0 are confirmed. Use Phase 19 as a calibration run, not an income run. |
| 2 | **Phase 18 plan-04 parity failure** | MEDIUM-HIGH | HIGH | If C#↔Python scoring diverges >0.05 on recorded sessions, entry signals in NT8 may differ materially from the backtested edge. Complete plan-04 before starting paper trade. If divergence is found, root-cause before proceeding — a broken scorer invalidates all backtest conclusions. |
| 3 | **TypeA tier permanently unenterable (zone scoring unwired)** | HIGH | MEDIUM | zoneScore=0.0 default means TypeA `hasZone` always fails. This is a structural code gap, not a configuration issue. Documented as R-1.1 (P0) in FINE-TUNING-RECOMMENDATIONS.md. Mitigation: Phase 19 runs on TypeB, which is the primary live tier. TypeA trades are zero — acceptable for paper trade validation. Track whether any TypeA fires (Checklist item 47); if zero over 30 sessions, mark as Phase 20 work item. |
| 4 | **VOLP-03 veto misfires in live data** | MEDIUM | HIGH | PRODUCTION-CONFIG.md identifies a tension: meta-optimizer walk-forward top configs have volp03_veto=False (because synthetic sessions fire VOLP-03 every 40 bars, making it too restrictive). In live NQ, VOLP-03 should fire only on genuine volume surges (news events). If VOLP-03 fires >3×/week on non-news sessions, the veto is over-triggering and blocking valid trades. Monitor: if veto fires >3×/week, audit the session logs against news calendars before adjusting. |
| 5 | **Prop firm trailing drawdown breach** | LOW-MEDIUM | VERY HIGH | Apex/Lucid trailing drawdown limits (typically $2,000–$3,000) are a hard account termination trigger. With $500 daily loss cap and Monte Carlo 95th-pct MaxDD=$234.81 (synthetic), the margin looks safe. However: synthetic MaxDD is not a reliable live predictor. A single runaway session (data feed gap with open position, FOMC gap-and-go) can produce $500–$1,500 loss before NT8 RealtimeErrorHandling=StopCancelClose triggers. Mitigation: paper trade only until go/no-go, one account at a time, human monitoring every live session, backup internet confirmed. |
| 6 | **Aggressor field corruption (BBO state race)** | MEDIUM | MEDIUM | PRE-LIVE-CHECKLIST.md item 31: if >80% of ticks show aggressor=0 (unknown), all delta signals are corrupted. This is a known NT8/Rithmic feed issue where OnMarketData receives Last before Bid/Ask is updated. DEEP6Footprint must verify aggressor resolution in the first RTH session before trusting delta or DELT signal outputs. |
| 7 | **ScorerSharedState wiring failure (score always 0.0)** | MEDIUM | HIGH | If the indicator publishes ScorerSharedState and the strategy reads 0.0 on every bar, zero entries fire and the paper-trade session produces no data. Checklist item 7 / 23 catches this: verify non-zero scores in Output window within first 5 bar updates. If silent failure, likely indicator/strategy load order or namespace mismatch. |
| 8 | **ScoreEntryThreshold fragility (±10% = >50% Sharpe drop)** | LOW | HIGH | META-OPTIMIZATION.md stability analysis documents that threshold=70 is a narrow peak — not a stable plateau. Any accidental change (NT8 property serialization, strategy reload with wrong default) can drop Sharpe dramatically. Mitigation: verify threshold=70.0 in the properties panel at every session start. Never tune threshold during Phase 19. |
| 9 | **Bar-close entry timing lag** | HIGH | MEDIUM | Structural. Entries fire at next-bar open, not at signal-bar close. The backtest models entries at bar-close price. On a fast reversal, actual live fill will be 2–4 ticks worse than assumed. FINE-TUNING-RECOMMENDATIONS.md R-2.1 (P1) proposes adjusting BacktestConfig.StopLossTicks=22, TargetTicks=38 to account for this drift. Monitored during paper trade via live vs expected price comparison. |
| 10 | **Slow-grind ATR baseline contamination** | MEDIUM | LOW-MEDIUM | SlowGrindAtrRatio=0.5 compares bar ATR to session average. If session average ATR is inflated by opening-range bars (bars 0–5 on NQ typically have 3–5× higher ATR than mid-session), the veto may trigger too frequently in mid-session quiet conditions. PRE-LIVE-CHECKLIST.md item 82 (SlowGrindAtrRatio watch) notes: if veto fires >20% of qualifying bars, the baseline ATR calculation should shift to bars 5–30 only. Track during paper trade. |
| 11 | **NT8 memory leak under continuous multi-session operation** | LOW | MEDIUM | Checklist item 10: `_bars` Dictionary cleanup cutoff at `CurrentBar-500` and `_l2Bids/Asks` purge — if not implemented, NT8 RAM grows unboundedly. Must be verified over 60+ continuous minutes during the first paper session. Symptom: NT8 RAM growth >500MB/hr in Task Manager. |
| 12 | **DEEP6Strategy and legacy Python execution path conflict** | LOW | HIGH | If the Python execution path (async-rithmic, not current live runtime) is accidentally running simultaneously, it could submit conflicting orders on the same Rithmic account. Checklist item 64 blocks this. Mitigation: confirm only DEEP6Strategy is active in NT8 Strategy Monitor before any live session. |

---

## 4. Confidence Level

**MEDIUM — estimated 55–60% confidence in sustained edge in live NQ trading.**

**Honest reasoning:**

The signal thesis (absorption + exhaustion as highest-alpha reversal signals, filtered by VOLP-03 regime gate and strict direction) is grounded in real orderflow mechanics, not curve-fit parameters. The regime-conditional results are qualitatively coherent: 98% win rate in ranging sessions makes sense for a mean-reversion signal hitting LVN/HVN extremes; 0% in volatile sessions where momentum overrides mean-reversion is also mechanistically correct. The risk architecture is unusually thorough for this stage of development — 73 yes-blocker checklist items, Monte Carlo sizing, daily kill-switch.

However, three honest deficiencies prevent HIGH confidence:

1. **Zero live validation.** Every metric in this report derives from synthetic NDJSON sessions. The stress test T7 returned a 0.00 out-of-sample Sharpe on a 25/25 session split — a direct overfit warning. Synthetic sessions do not model order book resilience, partial fills, connection drops, or NQ's actual fat-tailed distribution (2018, 2020, 2022 crash days are not represented).

2. **Phase 18 plan-04 is incomplete.** The parity gate (C#↔Python scoring |Δ|≤0.05 per bar on ≥5 real recorded sessions) is the last code gate before the system runs on live data. Until this passes, the exact scoring behavior of NT8 DEEP6Strategy on real NQ bars is unverified.

3. **TypeA is permanently unreachable.** The highest-conviction tier — the one the system's architecture was designed to produce — cannot fire until zone scoring is wired. Every paper trade during Phase 19 will be on TypeB signals only. This is not a fatal flaw (TypeB shows 87.5% win rate in attribution), but it means the system will be validated on a lower tier than its design intent.

A system with these characteristics — strong signal thesis, verified regime gating, thorough risk controls, but synthetic-only backtest data and incomplete parity verification — warrants MEDIUM confidence. The edge direction is likely real; the quantitative magnitude (Sharpe=207, PF=16) is almost certainly overstated and will compress materially in live execution. A profitable but more modest edge (Sharpe 2–5, PF 1.8–3.0) is the realistic live expectation based on analogous order-flow systems that have survived synthetic-to-live transition.

---

## 5. Recommended Next Steps (ordered)

### 1. Complete Phase 18 Plan-04 (first priority — do this before any paper trade)

Run the `ScoringParityHarness` on ≥5 recorded NQ sessions (from `ninjatrader/captures/`). The parity gate requirement is |python_score - csharp_score| ≤ 0.05 per bar AND identical TypeA/B/C tier per bar. Any divergence >0.05 must be root-caused via per-layer diff (engine-agreement delta, category-agreement delta, zone bonus delta) and fixed before starting paper trade. If parity passes, commit `18-04-PARITY-REPORT.md` and `18-VALIDATION.md`. This is the only remaining code gate.

### 2. Execute PRE-LIVE-CHECKLIST.md Groups 1–3 (before first paper session)

Work through all 73 YES-blocker items systematically. Critical path:
- Groups 1 (Code Readiness, items 1–10): Compile, load on sim chart, verify DRY RUN log line, UseNewRegistry=true, ScorerSharedState non-zero scores within 5 bars
- Group 2 (Configuration, items 11–28): Set all PRODUCTION-CONFIG.md values, verify EnableLiveTrading=false is the last check
- Group 3 (Data Validation, items 29–37): Run one RTH session on Rithmic sim to verify aggressor field, footprint accumulation, signal firing frequency, and score outputs

### 3. Paper trade Phase 19 — 30 consecutive RTH sessions

Run DEEP6Strategy on both Apex sim and Lucid sim simultaneously. Track per session:
- Total trades, win rate, profit factor
- Signal tier breakdown (TypeA count — expected 0; TypeB count)
- Exit reason distribution (T1_PARTIAL target 46%, STOP_LOSS target <20%, MAX_BARS target <15%)
- VOLP-03 veto frequency vs news calendar correlation
- Aggressor resolution rate (confirm >20% non-zero aggressor across session bars)
- Memory (NT8 RAM after 390 bars per session)

During paper trade, watch specifically for:
- Any session producing zero entries despite market moving: likely ScorerSharedState wiring failure
- VOLP-03 veto firing on non-news days: likely synthetic artifact in live VOLP-03 sensitivity
- MaxDD per session vs Monte Carlo prediction: if any session exceeds $300 MaxDD, full post-mortem before continuing
- Score drift: if TypeB stops firing (score consistently <72), suspect ATR initialization issue or regime lock

### 4. When to go live

**Do not flip EnableLiveTrading=true until ALL of the following are confirmed:**

- 30 paper sessions complete without crash or stall
- Paper-trade win rate ≥ 75% (PRE-LIVE-CHECKLIST.md item 39)
- Paper-trade profit factor ≥ 2.0 (item 40)
- Minimum 30 total trades (item 41)
- 95th-pct slippage ≤ 4 ticks per side (item 42)
- All 5 risk gates verified firing at least once (item 43)
- VOLP-03 veto respected on all identified volatile events (item 46)
- Written go/no-go decision document committed to `.planning/GO-NOGO-PHASE19.md` (item 48)
- Apex prop firm trailing drawdown limit for APEX-262674 documented in the go/no-go doc (item 52)
- Scale-up path (Phase 1: 2 contracts, Phase 2 at 100 trades/Sharpe≥3: 16 contracts, Phase 3 at 300 trades: 34 contracts) written and agreed (item 54)

If paper-trade win rate is 70–74% (below threshold but above break-even), extend to 45 sessions before making the go/no-go call. Do not go live with fewer than 30 validated trades regardless of win rate.

**Expected timeline from today:** Phase 18 plan-04 (1–2 days) → Phase 19 paper sessions (30 RTH sessions = ~6 calendar weeks) → go/no-go decision → live capital deployment earliest **late May 2026** if paper metrics pass.

---

## Appendix: Phase 19 Success Criteria Reference

From ROADMAP.md Phase 19:

| # | Criterion | Go-Live Gate |
|---|---|---|
| SC1 | 30 consecutive RTH sessions without crash or stall | YES |
| SC2 | Daily P&L log with per-signal attribution | YES |
| SC3 | All 5 risk gates verified firing correctly | YES |
| SC4 | Slippage report: median + 95th-pct per signal tier | YES |
| SC5 | Written go/no-go decision committed to `.planning/` | YES (terminal gate) |

All 5 success criteria require live paper-trade data. None can be satisfied pre-Phase 19.

---

*Sources: OPTIMIZATION-REPORT.md, SIGNAL-ATTRIBUTION.md, REGIME-ANALYSIS.md, EXIT-STRATEGY.md, ENTRY-TIMING.md, META-OPTIMIZATION.md, RISK-MANAGEMENT.md, WEIGHT-OPTIMIZATION.md, SIGNAL-FILTER.md, FINE-TUNING-RECOMMENDATIONS.md, STRESS-TEST.md, PRODUCTION-CONFIG.md, PRE-LIVE-CHECKLIST.md, ROADMAP.md Phase 18/19, 18-CONTEXT.md*  
*Generated: 2026-04-15 — Round 3 Production Readiness Sign-Off*
