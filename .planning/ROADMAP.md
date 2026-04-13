# Roadmap: DEEP6 v2.0 — Python Edition

## Overview

DEEP6 v2.0 is built from the data pipeline outward. The foundation is a correct, validated footprint engine driven by Rithmic's native aggressor field — nothing downstream is trustworthy until bid/ask volumes per price level per bar are confirmed accurate. From that foundation, the 44-signal cascade assembles in dependency order: absorption and exhaustion first (highest alpha), then the imbalance/delta/auction family, then DOM depth signals, then volume profile and GEX context with zone lifecycle. The Kronos E10 bias engine and TradingView MCP are built in parallel with the signal cascade since they only need OHLCV. Scoring and backtesting come next to calibrate the system, then execution with mandatory paper trading, then ML optimization, and finally the analytics dashboard once all data flows are stable.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Pipeline + Architecture Foundation** - async-rithmic connection, FootprintBar accumulator, DOMState pre-allocation, aggressor field verification, session persistence, Python package structure
- [ ] **Phase 2: Absorption + Exhaustion Core** - All 4 absorption variants and 6 exhaustion variants with narrative cascade — the highest-alpha signals in the system
- [ ] **Phase 3: Footprint Signal Engines (E1, E8, E9)** - Imbalance (9 types), Delta (11 types), Auction Theory (5 types) implemented via E1 FootprintEngine, E8 CVDEngine, E9 AuctionFSM
- [ ] **Phase 4: DOM Depth Signal Engines (E2, E3, E4, E5)** - Trapped traders, volume patterns, DOM queue imbalance, spoofing detection, iceberg detection, Naive Bayes micro probability
- [ ] **Phase 5: Volume Profile + GEX Context + Zone Registry (E6, E7)** - POC/value area signals, LVN/HVN zone lifecycle FSM, GEX integration, ZoneRegistry, ML quality engine scaffold
- [ ] **Phase 6: Kronos E10 + TradingView MCP** - Kronos-small subprocess with GPU inference, multiprocessing.Pipe bridge, confidence decay; TV MCP configuration and chart interaction
- [ ] **Phase 7: Scoring + Backtesting Framework** - Two-layer confluence scorer, zone bonuses, TypeA/B/C classification, Databento MBO replay, vectorbt parameter sweeps, walk-forward validation
- [ ] **Phase 8: Auto-Execution + Risk Layer** - Direct Rithmic order submission, bracket orders, circuit breakers, reconnection freeze, 30-day paper trading gate
- [ ] **Phase 9: ML Backend** - FastAPI signal/trade event ingestion, XGBoost weight optimization, Optuna threshold tuning, HMM regime detection, walk-forward with purged splits
- [ ] **Phase 10: Analytics Dashboard** - Next.js 15 dashboard with WebSocket real-time updates, signal performance view, regime viz, parameter evolution, footprint chart rendering, session replay

## Phase Details

### Phase 1: Data Pipeline + Architecture Foundation
**Goal**: A running Python process connects to Rithmic, receives real-time L2 DOM and tick data, accumulates correct FootprintBars at bar close, persists session state to disk, and handles reconnection safely — with the aggressor field verified before any signal code is written.
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08, DATA-09, DATA-10, ARCH-01, ARCH-02, ARCH-03, ARCH-04, ARCH-05
**Success Criteria** (what must be TRUE):
  1. async-rithmic connects to Rithmic, subscribes to NQ L2 DOM (40+ levels) and tick feed, and logs incoming data without dropping callbacks at peak DOM velocity
  2. Each FootprintBar at bar close contains correct bid volume and ask volume per price level, verified bar-for-bar against ATAS or Quantower as ground truth
  3. The aggressor field (TransactionType.BUY/SELL) is confirmed present in on_trade callback — not UNKNOWN — before any footprint accumulator is written
  4. Session state (IB anchor, CVD baseline, VWAP) survives a process restart mid-session and signals resume correctly without re-initialization
  5. DOM callbacks operate at 1,000+/sec with zero blocking — event loop lag stays under 1ms measured by asyncio instrumentation
**Plans**: TBD

### Phase 2: Absorption + Exhaustion Core
**Goal**: All 4 absorption variants and all 6 exhaustion variants fire correctly from live FootprintBar data with proper narrative prioritization — the system can identify the highest-conviction reversal signals.
**Depends on**: Phase 1
**Requirements**: ABS-01, ABS-02, ABS-03, ABS-04, ABS-05, ABS-06, ABS-07, EXH-01, EXH-02, EXH-03, EXH-04, EXH-05, EXH-06, EXH-07, EXH-08
**Success Criteria** (what must be TRUE):
  1. Classic, passive, stopping volume, and effort-vs-result absorption each fire on bars where the defining footprint condition is present, confirmed by visual review of Bookmap/ATAS reference
  2. Zero print, exhaustion print, thin print, fat print, bid/ask fade, and fading momentum each detect correctly with the delta trajectory divergence gate suppressing false positives
  3. Absorption signals appear first in the narrative cascade above exhaustion, momentum, and rejection — narrative labels are human-readable (e.g., "ABSORBED @VAH")
  4. Exhaustion cooldown suppresses the same sub-type for N bars after firing — no signal clustering on consecutive bars
  5. Absorption at value area extremes (VAH/VAL) produces a conviction bonus flag visible in bar output
**Plans**: TBD

### Phase 3: Footprint Signal Engines (E1, E8, E9)
**Goal**: All 25 imbalance, delta, and auction theory signals are implemented in E1 FootprintEngine, E8 CVDEngine, and E9 AuctionFSM — every signal fires on the correct bar condition with the right tier/sub-type classification.
**Depends on**: Phase 2
**Requirements**: IMB-01, IMB-02, IMB-03, IMB-04, IMB-05, IMB-06, IMB-07, IMB-08, IMB-09, DELT-01, DELT-02, DELT-03, DELT-04, DELT-05, DELT-06, DELT-07, DELT-08, DELT-09, DELT-10, DELT-11, AUCT-01, AUCT-02, AUCT-03, AUCT-04, AUCT-05, ENG-01, ENG-08, ENG-09
**Success Criteria** (what must be TRUE):
  1. All 9 imbalance types (single, multiple, stacked T1/T2/T3, reverse, inverse, oversized, consecutive, diagonal, reversal pattern) fire correctly — diagonal imbalance uses ask[P] vs bid[P-1] per confirmed algorithm
  2. All 11 delta signals (rise/drop, tail, reversal, divergence, flip, trap, sweep, slingshot, min/max, CVD multi-bar regression, velocity) compute from FootprintBar data without float key errors
  3. All 5 auction theory signals (unfinished business, finished auction, poor high/low, volume void, market sweep) detect correctly — unfinished auction levels persist cross-session in SQLite
  4. E8 CVDEngine runs numpy polyfit linear regression over 5-20 bar rolling window and divergence flag matches visual inspection on 10+ reference bars
  5. Pairwise Pearson correlation matrix is computed for all implemented signals — any pair with r > 0.7 is documented before Phase 7 scorer is finalized
**Plans**: TBD

### Phase 4: DOM Depth Signal Engines (E2, E3, E4, E5)
**Goal**: Trapped trader signals, volume pattern signals, DOM queue imbalance, spoofing detection, iceberg detection, and Naive Bayes micro probability are all operational — providing the second tier of signal confirmation from order book depth and flow analysis.
**Depends on**: Phase 3
**Requirements**: TRAP-01, TRAP-02, TRAP-03, TRAP-04, TRAP-05, VOLP-01, VOLP-02, VOLP-03, VOLP-04, VOLP-05, VOLP-06, ENG-02, ENG-03, ENG-04, ENG-05
**Success Criteria** (what must be TRUE):
  1. All 5 trapped trader signals (inverse imbalance trap, delta trap, false breakout trap, high-volume rejection trap, CVD trap) fire on bars matching their defining condition, confirmed by replay
  2. All 6 volume pattern signals (sequencing, bubble, surge, POC momentum wave, delta velocity spike, big delta per level) compute correctly from FootprintBar and bar history
  3. E2 TrespassEngine computes multi-level weighted DOM queue imbalance from DOMSnapshot and logistic regression output without blocking the event loop
  4. E3 CounterSpoofEngine produces Wasserstein-1 distance on DOM distributions and fires cancel detection alert when a large order disappears within the detection window
  5. E4 IcebergEngine detects both native icebergs (trade > DOM) and synthetic icebergs (refill < 250ms); E5 MicroEngine combines E1/E2/E4 outputs via Naive Bayes without redundancy
**Plans**: TBD

### Phase 5: Volume Profile + GEX Context + Zone Registry (E6, E7)
**Goal**: Session volume profile with LVN/HVN detection, the 5-state zone lifecycle FSM, GEX integration, centralized ZoneRegistry, and the E6/E7 engine scaffold are all operational — providing the macro context layer that all high-conviction signals require.
**Depends on**: Phase 4
**Requirements**: POC-01, POC-02, POC-03, POC-04, POC-05, POC-06, POC-07, POC-08, VPRO-01, VPRO-02, VPRO-03, VPRO-04, VPRO-05, VPRO-06, VPRO-07, VPRO-08, GEX-01, GEX-02, GEX-03, GEX-04, GEX-05, GEX-06, ZONE-01, ZONE-02, ZONE-03, ZONE-04, ZONE-05, ENG-06, ENG-07
**Success Criteria** (what must be TRUE):
  1. Session volume profile bins correctly at tick resolution — LVN zones (< 30% of session average) and HVN zones (> 170%) are detected and match manual review of Bookmap reference
  2. Each LVN zone transitions through the 5-state FSM (Created → Defended → Broken → Flipped → Invalidated) when the correct price action triggers the transition, with multi-session persistence and decay weighting
  3. GEX data ingests from FlashAlpha API every 60 seconds — call wall, put wall, gamma flip, and HVL are available as priced levels; stale flag activates when data age exceeds threshold
  4. ZoneRegistry consolidates absorption, exhaustion, LVN, HVN, and GEX zones — overlapping same-direction zones merge with combined score; confluence between zone types produces the highest conviction flag
  5. E7 MLQualityEngine returns 1.0 (neutral) when model not yet trained — system functions correctly before ML pipeline is built in Phase 9
**Plans**: TBD
**UI hint**: yes

### Phase 6: Kronos E10 + TradingView MCP
**Goal**: Kronos-small runs in a dedicated subprocess with persistent GPU model load providing directional bias every 5 bars with confidence decay; TradingView MCP is configured so Claude can read chart state, inject Pine Script, and capture screenshots for visual confirmation.
**Depends on**: Phase 1
**Requirements**: KRON-01, KRON-02, KRON-03, KRON-04, KRON-05, KRON-06, TVMCP-01, TVMCP-02, TVMCP-03, TVMCP-04, TVMCP-05, TVMCP-06, ENG-10
**Success Criteria** (what must be TRUE):
  1. Kronos-small loads from HuggingFace in a dedicated subprocess — the main event loop is never blocked during 200-400ms inference; pipe.recv runs via thread executor
  2. 20 stochastic samples per inference produce a directional confidence score (0-100) that updates every 5 bars with 0.95/bar decay between inferences — E10 score integrates into confluence scorer
  3. GPU inference latency is benchmarked on production hardware (M2 Mac MPS) — if latency exceeds bar duration budget, CPU fallback is activated with documented tolerance
  4. TradingView Desktop launches with --remote-debugging-port=9222 and Claude can read current price, indicators, and Pine Script levels from the chart
  5. Claude can inject the Bookmap Liquidity Mapper Pine Script on a live chart and read the resulting absorption/exhaustion zone levels as cross-reference for signal validation
**Plans**: TBD

### Phase 7: Scoring + Backtesting Framework
**Goal**: The two-layer confluence scorer synthesizes all 44 signal flags into a typed ScorerResult; the Databento MBO replay engine generates ground-truth labeled bars; vectorbt runs parameter sweeps; walk-forward validation gates any weight changes.
**Depends on**: Phase 5, Phase 6
**Requirements**: SCOR-01, SCOR-02, SCOR-03, SCOR-04, SCOR-05, SCOR-06, TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, TEST-07
**Success Criteria** (what must be TRUE):
  1. Two-layer scorer produces a ScorerResult for every bar close — engine-level agreement ratio + category-level confluence multiplier (1.25x when 5+ categories agree) + zone bonus (+6 to +8 points) are all applied correctly
  2. TypeA signal requires absorption/exhaustion + zone confluence + 5+ category agreement simultaneously — TypeB and TypeC thresholds produce distinct entry quality tiers visible in signal CSV export
  3. Databento MBO replay runs on historical NQ data and generates identical signals as the live engine on the same bars — divergence over 2% from live triggers investigation
  4. vectorbt parameter sweep tests all 44 thresholds over historical data and produces a ranked output by signal P&L attribution — identifying which signals add edge vs noise
  5. Walk-forward validation with WFE > 70% gate passes before any weight file is applied — purged splits prevent future leakage
**Plans**: TBD

### Phase 8: Auto-Execution + Risk Layer
**Goal**: Direct Rithmic order submission fires from TypeA/B confluence signals with server-side bracket orders, full circuit-breaker risk management, reconnection freeze on disconnect, and a mandatory 30-day paper trading validation period before live capital.
**Depends on**: Phase 7
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06, EXEC-07, EXEC-08
**Success Criteria** (what must be TRUE):
  1. TypeA signal triggers a Rithmic bracket order (entry + stop + target) submitted via async-rithmic OrderPlant — stop placed beyond absorption/exhaustion zone boundary, target at opposing zone or next LVN/HVN
  2. Daily loss limit circuit breaker halts all new entries when threshold is reached — consecutive loss limit and max-contracts position sizing each enforce independently without requiring the other to trigger
  3. TRADING_FROZEN flag activates immediately on reconnection — no new orders are submitted until Rithmic position API confirms position reconciliation completes
  4. GEX regime gate disables execution in specified regimes (e.g., positive gamma mean-reversion mode with high HVL proximity) — no entries fire in excluded regimes regardless of signal score
  5. 30-day paper trading period completes with documented P&L, win rate, and drawdown before the live execution flag is enabled — operator cannot bypass this gate
**Plans**: TBD

### Phase 9: ML Backend
**Goal**: FastAPI receives all signal and trade events in the same asyncio event loop; XGBoost trains on signal history to produce optimized per-signal weights; Optuna sweeps all 44 thresholds; HMM detects market regime; no weight file deploys without human approval.
**Depends on**: Phase 7, Phase 8
**Requirements**: ML-01, ML-02, ML-03, ML-04, ML-05, ML-06, ML-07, ML-08
**Success Criteria** (what must be TRUE):
  1. FastAPI service ingests signal events and trade outcomes in real time via the existing asyncio event loop — no threading conflicts; signal history accumulates in a queryable store
  2. XGBoost model trains on accumulated signal history and produces a weight file with per-signal weights and per-regime adjustments — training runs without blocking the live event loop
  3. Optuna Bayesian optimization sweeps all 44 signal thresholds and produces a candidate threshold file — any single-signal weight is capped at 3x baseline without manual override
  4. Walk-forward cross-validation with purged splits requires 200+ out-of-sample trades per signal before that signal's weights are updated — WFE > 70% gate enforced
  5. Weight file deploy requires explicit operator confirmation in the dashboard — system continues running on previous weights during review; ML-07 performance tracking shows before/after comparison
**Plans**: TBD

### Phase 10: Analytics Dashboard
**Goal**: Next.js 15 dashboard provides real-time signal monitoring, signal performance analytics, regime visualization, ML parameter evolution, zone analysis, footprint chart rendering, and full session replay — all backed by WebSocket from FastAPI.
**Depends on**: Phase 9
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07
**Success Criteria** (what must be TRUE):
  1. Dashboard connects to FastAPI via WebSocket and displays live signal events and ScorerResult updates within 500ms of bar close — no polling, pure push
  2. Signal performance view shows win rate, average P&L, and frequency per signal type with time range filters — filterable to any signal sub-type (e.g., ABS-03 stopping volume alone)
  3. Footprint chart renders via Lightweight Charts v5.1 custom series — each bar displays bid/ask volume per price level with LVN/HVN zones overlaid
  4. Session replay reconstructs any historical session with all signal events, zone states, and orders visible — operator can step through bar by bar
  5. ML parameter evolution view shows threshold history over time and regime classification alongside market price — operator can see what the optimizer changed and why
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10
Note: Phase 6 (Kronos + TVMCP) can begin after Phase 1 completes, running in parallel with Phases 2-5.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Pipeline + Architecture Foundation | 0/? | Not started | - |
| 2. Absorption + Exhaustion Core | 0/? | Not started | - |
| 3. Footprint Signal Engines (E1, E8, E9) | 0/? | Not started | - |
| 4. DOM Depth Signal Engines (E2, E3, E4, E5) | 0/? | Not started | - |
| 5. Volume Profile + GEX Context + Zone Registry | 0/? | Not started | - |
| 6. Kronos E10 + TradingView MCP | 0/? | Not started | - |
| 7. Scoring + Backtesting Framework | 0/? | Not started | - |
| 8. Auto-Execution + Risk Layer | 0/? | Not started | - |
| 9. ML Backend | 0/? | Not started | - |
| 10. Analytics Dashboard | 0/? | Not started | - |
