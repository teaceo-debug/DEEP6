# Roadmap: DEEP6 v2.0

## Overview

DEEP6 v2.0 expands a working 7-engine, 1,010-line NinjaTrader 8 indicator into a full institutional-grade footprint auto-trading system. The journey begins with mandatory architecture surgery (partial class decomposition + GC fixes) before a single new signal is written, then expands through the full 44-signal taxonomy in priority order (absorption/exhaustion first, as the highest-alpha signals), builds the zone registry and GEX integration that provide confluence context, overhauls the scoring system and enables auto-execution, and finally delivers the Python ML backend and Next.js analytics dashboard that make the system adaptive over time. The data bridge starts mid-project to accumulate the signal history the ML backend needs.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Architecture Foundation** - Decompose monolith into partial classes and fix GC hot-path allocations before any signal expansion
- [ ] **Phase 2: Signal Infrastructure** - ATR normalization layer, correlation analysis, and SignalFlags bitmask taxonomy foundation
- [ ] **Phase 3: Absorption and Exhaustion** - All 4 absorption variants, all 6 exhaustion variants (with E8 CVD engine), narrative cascade, and inverse imbalance
- [ ] **Phase 4: Imbalance, Delta, and Trapped Traders** - Complete IMB/DELT/TRAP signal families (25 signals) with bar-close guards
- [ ] **Phase 5: Auction Theory, Volume Patterns, and POC** - Complete AUCT/VOLP/POC signal families (19 signals) and E9 Auction State Machine
- [ ] **Phase 6: Volume Profile Levels and GEX Integration** - LVN/HVN zone detection with lifecycle FSM and FlashAlpha GEX API
- [ ] **Phase 7: Zone Registry and Engine Enhancements** - Centralized ZoneRegistry, SharpDX zone rendering, and upgrade of all 6 existing engines
- [ ] **Phase 8: Scoring Overhaul and Auto-Execution** - Two-layer confluence scorer, TypeA/B/C reclassification, NT8 ATM integration with full risk gate
- [ ] **Phase 9: Data Bridge and Backtesting** - NT8-to-Python TCP bridge, signal/trade CSV export, vectorbt backtesting framework
- [ ] **Phase 10: ML Backend** - FastAPI service, HMM regime detection, XGBoost signal weighting, walk-forward validation
- [ ] **Phase 11: Analytics Dashboard** - Next.js 15 dashboard with signal heatmap, regime visualization, and parameter drift tracking

## Phase Details

### Phase 1: Architecture Foundation
**Goal**: DEEP6.cs decomposed into partial classes with GC pressure eliminated — the codebase is safe to expand without monolith collapse or callback-thread stalls
**Depends on**: Nothing (first phase)
**Requirements**: ARCH-01, ARCH-02
**Success Criteria** (what must be TRUE):
  1. DEEP6.cs compiles as NT8 indicator with engine logic split across AddOns/ partial class files, zero behavior change
  2. OnMarketDepth hot path has zero allocations (Welford replaces LINQ Std(), pre-allocated brush palette, circular buffers replace RemoveAll())
  3. All 9 existing engine results flow through the new partial class structure and produce identical output to pre-refactor
  4. A 1,200-line warning threshold is enforced — new files are created before any file approaches the limit
**Plans**: 4 plans

Plans:
- [ ] 01-01-PLAN.md — Decompose DEEP6.cs into 11 AddOns/ partial class files (ARCH-01)
- [x] 01-02-PLAN.md — E3/E4/Core GC fixes: Welford QueueStats, circular buffers, RunE3 to OnBarUpdate (ARCH-02)
- [ ] 01-03-PLAN.md — Render/Scorer GC fixes: brush palette, manual dot-product loops (ARCH-02)
- [ ] 01-04-PLAN.md — Line count audit + NT8 Windows compilation and visual validation checkpoint

### Phase 2: Signal Infrastructure
**Goal**: Every signal threshold in the system adapts automatically to ATR(20) volatility, a correlation matrix prevents redundant implementation, and the SignalFlags bitmask is ready to receive all 44 signals
**Depends on**: Phase 1
**Requirements**: ARCH-03, ARCH-04, ARCH-05
**Success Criteria** (what must be TRUE):
  1. ATR(20) normalization layer is in place and all threshold parameters accept ATR-scaled values — slow-market and fast-market thresholds differ visibly on chart
  2. Pairwise correlation matrix is computed and documented — any signal pair with r > 0.7 is flagged before implementation begins
  3. SignalFlags bitmask (ulong, 64-bit) covers all 44 signal positions and O(popcount) scoring compiles without error
**Plans**: TBD

### Phase 3: Absorption and Exhaustion
**Goal**: All 4 absorption variants and all 6 exhaustion variants fire correctly in the indicator, with narrative candle classification hierarchy active, E8 CVD engine powering fading momentum detection, AND Python vectorbt backtesting framework providing calibration data for signal thresholds before further signal expansion
**Depends on**: Phase 2
**Requirements**: ABS-01, ABS-02, ABS-03, ABS-04, ABS-05, ABS-06, ABS-07, EXH-01, EXH-02, EXH-03, EXH-04, EXH-05, EXH-06, EXH-07, EXH-08, ENG-07, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Classic absorption fires on bars with wick volume >= threshold AND balanced delta — label appears on chart at correct price level
  2. All 4 absorption variants (classic, passive, stopping volume, effort vs result) each produce distinct signal labels visible on historical bars
  3. All 6 exhaustion variants (zero print, exhaustion print, thin print, fat print, fading momentum, bid/ask fade) each produce distinct labels — fading momentum sourced from E8 CVD multi-bar linear regression
  4. Narrative cascade is enforced: absorption label takes priority over exhaustion, exhaustion over momentum, on any bar where multiple signals fire
  5. Exhaustion cooldown suppresses same sub-type for N bars — no signal clustering visible on test data
  6. Delta trajectory divergence gate prevents exhaustion firing when delta direction matches price direction
  7. Python vectorbt backtesting framework runs absorption/exhaustion signals against NQ historical data — win rate, avg P&L, and optimal threshold ranges documented per signal variant
  8. Calibration data from vectorbt informs threshold defaults before Phases 4-5 signal expansion begins
**Plans**: TBD
**UI hint**: yes

### Phase 4: Imbalance, Delta, and Trapped Traders
**Goal**: All 9 imbalance variants, all 11 delta signals, and all 5 trapped-trader signals fire correctly — 25 signals operational with ATR-adaptive thresholds and bar-close guards
**Depends on**: Phase 3
**Requirements**: IMB-01, IMB-02, IMB-03, IMB-04, IMB-05, IMB-06, IMB-07, IMB-08, IMB-09, DELT-01, DELT-02, DELT-03, DELT-04, DELT-05, DELT-06, DELT-07, DELT-08, DELT-09, DELT-10, DELT-11, TRAP-01, TRAP-02, TRAP-03, TRAP-04, TRAP-05
**Success Criteria** (what must be TRUE):
  1. Stacked imbalances classify into T1/T2/T3 tiers (3/5/7 consecutive levels) with distinct label rendering on chart
  2. Inverse imbalance trap (buy imbalances in red bar) fires on historical examples and shows separate label from IMB-05 inverse imbalance signal
  3. Delta divergence (DELT-04) fires when price makes new high while delta fails to confirm — visible on chart with arrow or label
  4. Delta slingshot (DELT-08) fires on compressed-then-explosive delta patterns — does not fire on every high-volume bar
  5. All 25 signals in this phase fire exactly once per bar (Calculate.OnBarClose guards enforced — no intrabar recalculation artifacts)
**Plans**: TBD
**UI hint**: yes

### Phase 5: Auction Theory, Volume Patterns, and POC
**Goal**: All 5 auction theory signals, all 6 volume pattern signals, all 8 POC/Value Area signals, and the E9 Auction State Machine are operational — 19 signals + FSM adding confluence context
**Depends on**: Phase 4
**Requirements**: AUCT-01, AUCT-02, AUCT-03, AUCT-04, AUCT-05, VOLP-01, VOLP-02, VOLP-03, VOLP-04, VOLP-05, VOLP-06, POC-01, POC-02, POC-03, POC-04, POC-05, POC-06, POC-07, POC-08, ENG-08
**Success Criteria** (what must be TRUE):
  1. E9 Auction State Machine transitions between states (unfinished business, finished auction, poor high/low, volume void, market sweep) and current state is readable in the header bar or status pill
  2. Unfinished business (AUCT-01) fires when non-zero bid exists at bar high — complementary to exhaustion signals and does not double-fire on same bar
  3. Volume sequencing pattern (VOLP-01) detects institutional accumulation across 3+ bars — fires on clear historical examples, not on random volume variation
  4. POC classification signals (above/below, extreme, continuous, gap) each produce distinct indicators visible per bar on chart
  5. All 19 signals in this phase enforce bar-close guards and do not produce intrabar recalculation artifacts
**Plans**: TBD
**UI hint**: yes

### Phase 6: Volume Profile Levels and GEX Integration
**Goal**: LVN/HVN zones are detected from session volume profile with 5-state lifecycle FSM, GEX levels from FlashAlpha API are displayed on chart with staleness handling, and zone scoring formula is applied to every zone
**Depends on**: Phase 2
**Requirements**: VPRO-01, VPRO-02, VPRO-03, VPRO-04, VPRO-05, VPRO-06, VPRO-07, VPRO-08, GEX-01, GEX-02, GEX-03, GEX-04, GEX-05, GEX-06
**Success Criteria** (what must be TRUE):
  1. Session volume profile is computed and LVN zones (< 30% of session average volume) appear as horizontal lines on chart with correct price range
  2. HVN zones (> 170% of session average) appear as distinct horizontal lines with visual differentiation from LVN
  3. LVN zone FSM transitions through create → defend → broken → flipped → invalidated states — a defended zone shows increased opacity, a broken zone is visually marked as such
  4. Call wall, put wall, gamma flip level, and HVL from FlashAlpha API display as labeled horizontal lines matching GEX levels visible on TradingView reference chart
  5. GEX staleness indicator activates in header bar when data age exceeds threshold — GEX weight decays automatically after 1 hour
  6. Zone scoring formula (type 0.35 + recency 0.25 + touches 0.25 + defense 0.15) produces a numerical score readable per zone
**Plans**: TBD
**UI hint**: yes

### Phase 7: Zone Registry and Engine Enhancements
**Goal**: Centralized ZoneRegistry manages all zone types with visual tiering, and all 6 existing engines are upgraded with improved calibration, decorrelated inputs, and expanded feature sets
**Depends on**: Phase 6
**Requirements**: ZONE-01, ZONE-02, ZONE-03, ZONE-04, ZONE-05, ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06
**Success Criteria** (what must be TRUE):
  1. ZoneRegistry holds all zone types (absorption, exhaustion, LVN, HVN, GEX levels) in a single data structure — adding a zone in one engine is immediately visible to the scorer
  2. Overlapping same-direction zones merge into a single consolidated zone with combined score — no duplicate zone lines at the same price
  3. Zone visual tiering renders strong/medium/weak zones with distinct opacity levels and border styles via SharpDX
  4. E2 Trespass, E3 CounterSpoof, E4 Iceberg engines each accept ATR-adaptive thresholds — their firing rate changes visibly between slow and volatile market sessions
  5. E5 Micro Bayes engine uses decorrelated inputs — signal pairs with r > 0.7 from Phase 2 correlation matrix are not fed as independent features
  6. E7 ML Quality engine uses expanded 16+ feature logistic classifier incorporating signal categories from Phases 3-5
**Plans**: TBD
**UI hint**: yes

### Phase 8: Scoring Overhaul and Auto-Execution
**Goal**: Two-layer confluence scorer replaces the current voting system, TypeA/B/C signal classification is updated to require zone confluence, and auto-execution via NT8 ATM fires on TypeA/B signals with full risk gate active from day one
**Depends on**: Phase 7
**Requirements**: SCOR-01, SCOR-02, SCOR-03, SCOR-04, SCOR-05, SCOR-06, EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06
**Success Criteria** (what must be TRUE):
  1. Two-layer consensus score (engine agreement ratio × category confluence multiplier) produces a 0-100 value visible on chart — TypeA bars are clearly distinguishable from TypeB and TypeC
  2. TypeA classification requires absorption/exhaustion signal + zone confluence + 5+ category agreement — TypeA fires fewer than 3 times per session on average
  3. Auto-execution places an NT8 ATM order on TypeB or TypeA signal — entry order appears in NT8 execution log within 1 bar of signal
  4. Stop is placed beyond absorption/exhaustion zone boundary, target at opposing zone or VWAP — both are visible as NT8 ATM lines on chart
  5. Daily loss circuit breaker halts all further entries when max daily loss threshold is hit — no orders fire after circuit breaker trips until next session
  6. Regime-aware execution gate disables auto-entry in specified GEX regimes or low-volume conditions — enable/disable status is visible in header bar
**Plans**: TBD
**UI hint**: yes

### Phase 9: Data Bridge and Backtesting
**Goal**: Every signal firing and every trade is streamed from NT8 to Python via TCP bridge, backtesting framework validates signal edge before ML optimization, and Market Replay Recorder is active accumulating DOM data
**Depends on**: Phase 8
**Requirements**: BRDG-01, BRDG-02, BRDG-03, BRDG-04, BRDG-05, TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):
  1. NT8 indicator streams signal events to Python backend via TCP socket — Python FastAPI server receives and logs events in real time during live session
  2. ConcurrentQueue + background thread keeps NT8 bar thread non-blocking — no callback latency increase measurable when bridge is active
  3. NT8 Strategy Analyzer backtest runs on E1/E5/E6/E7 signals and exports CSV with timestamp, signal type, score, price, outcome
  4. vectorbt parameter sweep runs against exported signal CSV and produces threshold optimization report
  5. Walk-forward validation pipeline produces WFE metric — no ML weight candidates proceed without WFE > 70%
  6. P&L attribution report shows contribution per signal type — which signals have positive edge vs noise
**Plans**: TBD

### Phase 10: ML Backend
**Goal**: FastAPI ML service ingests signal history, classifies market regime via HMM, optimizes signal weights via XGBoost + Optuna, and produces human-gated JSON weight files that NT8 reads at session start
**Depends on**: Phase 9
**Requirements**: ML-01, ML-02, ML-03, ML-04, ML-05, ML-06, ML-07
**Success Criteria** (what must be TRUE):
  1. FastAPI service receives signal and trade events from NT8 bridge and stores them in SQLite via SQLAlchemy — database grows correctly during live session
  2. HMM regime classifier identifies current regime (TrendBull/TrendBear/Balance/HighVol/LowVol) — regime classification is readable via FastAPI /regime endpoint
  3. XGBoost model produces per-signal weight recommendations after training on 200+ OOS trades per signal class
  4. Optuna Bayesian optimization runs hyperparameter sweep and produces a ranked candidate weight file
  5. Walk-forward validation with purged splits clears WFE > 70% gate before any weight file is written to disk for NT8
  6. Operator approval gate requires explicit human action (CLI command or API call) before weight file is deployed to NT8 config path
**Plans**: TBD

### Phase 11: Analytics Dashboard
**Goal**: Next.js 15 dashboard provides real-time signal performance visibility, regime context, parameter drift tracking, and session replay — consuming ML endpoints and live signal stream
**Depends on**: Phase 10
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07
**Success Criteria** (what must be TRUE):
  1. Next.js dashboard loads and displays real-time signal feed via SSE — new signal events from live NT8 session appear in dashboard within 2 seconds
  2. Signal performance view shows win rate, avg P&L, and frequency per signal type with time-range filter — each of the 44 signal types has its own row
  3. Regime timeline shows current and historical regime classification — regime changes are visible as colored bands overlaid on price chart
  4. Parameter evolution view shows how ML is adjusting thresholds over sessions — before/after comparison is available for any threshold
  5. Zone analysis view shows which zone types produce best outcomes with zone lifecycle statistics
  6. Session replay reconstructs any historical session with all signals and zones visible — user can scrub through bars and see what fired
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11

Note: Phase 9 (Data Bridge) can begin collecting data in parallel with Phases 6-7 to provide the 6-8 week lead time the ML backend needs.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Architecture Foundation | 0/4 | In progress | - |
| 2. Signal Infrastructure | 0/TBD | Not started | - |
| 3. Absorption and Exhaustion | 0/TBD | Not started | - |
| 4. Imbalance, Delta, and Trapped Traders | 0/TBD | Not started | - |
| 5. Auction Theory, Volume Patterns, and POC | 0/TBD | Not started | - |
| 6. Volume Profile Levels and GEX Integration | 0/TBD | Not started | - |
| 7. Zone Registry and Engine Enhancements | 0/TBD | Not started | - |
| 8. Scoring Overhaul and Auto-Execution | 0/TBD | Not started | - |
| 9. Data Bridge and Backtesting | 0/TBD | Not started | - |
| 10. ML Backend | 0/TBD | Not started | - |
| 11. Analytics Dashboard | 0/TBD | Not started | - |
