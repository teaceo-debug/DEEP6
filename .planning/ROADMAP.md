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
- [x] **Phase 10: Analytics Dashboard** - Next.js 15 dashboard with WebSocket real-time updates, signal performance view, regime viz, parameter evolution, footprint chart rendering, session replay (completed 2026-04-14)

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
**Plans**: 4 plans (Wave 1: plan-01; Wave 2: plan-02, plan-03 parallel; Wave 3: plan-04)

Plans:
- [x] 01-01-PLAN.md — Python package scaffold, async-rithmic connection, DOMState, aggressor gate, SignalFlags stub
- [x] 01-02-PLAN.md — FootprintBar accumulator, dual-timeframe BarBuilder, SessionContext, ATRTracker
- [x] 01-03-PLAN.md — SQLite session persistence, FreezeGuard reconnection state, GC control, SharedState
- [x] 01-04-PLAN.md — Main entrypoint wiring, footprint validation script, loop lag measurement, human verification checkpoint

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
**Plans**: 3 plans (Wave 1: plan-01; Wave 2: plan-02; Wave 3: plan-03)

Plans:
- [x] 02-01-PLAN.md — Config extraction (AbsorptionConfig/ExhaustionConfig), universal delta trajectory gate (EXH-07), narrative wiring
- [x] 02-02-PLAN.md — VA extremes conviction bonus (ABS-07), absorption confirmation logic (ABS-06)
- [x] 02-03-PLAN.md — Comprehensive test suite for all absorption/exhaustion variants, gate, cooldown, cascade, confirmation

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
**Plans**: 4 plans (Wave 1: plan-01, plan-04 parallel; Wave 2: plan-02; Wave 3: plan-03)

Plans:
- [x] 03-01-PLAN.md — ImbalanceConfig + DeltaConfig extraction, missing imbalance variants (IMB-02/07/09), missing delta variants (DELT-03/07)
- [x] 03-02-PLAN.md — AuctionConfig extraction, unfinished auction cross-session persistence in SQLite
- [x] 03-03-PLAN.md — Comprehensive test suite for all imbalance, delta, and auction variants
- [x] 03-04-PLAN.md — Pairwise Pearson correlation matrix script for all signals

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
**Plans**: 4 plans (Wave 1: plan-01; Wave 2: plan-02, plan-03 parallel; Wave 3: plan-04)

Plans:
- [x] 04-01-PLAN.md — TrapEngine (TRAP-02..05) + VolPatternEngine (VOLP-01..06), config dataclasses
- [x] 04-02-PLAN.md — E2 TrespassEngine (ENG-02) + E3 CounterSpoofEngine (ENG-03)
- [x] 04-03-PLAN.md — E4 IcebergEngine (ENG-04) + E5 MicroEngine (ENG-05)
- [x] 04-04-PLAN.md — Comprehensive test suite for all Phase 4 engines

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
**Plans**: 3 plans (Wave 1: plan-01; Wave 2: plan-02; Wave 3: plan-03)
**UI hint**: yes

Plans:
- [x] 05-01-PLAN.md — POCConfig/VolumeProfileConfig/GexConfig extraction, VPRO-07 multi-session decay, VPRO-08 POC migration tracking
- [x] 05-02-PLAN.md — ZoneRegistry (ZONE-01..05), E6VPContextEngine + E7MLQualityEngine stub (ENG-06, ENG-07)
- [ ] 05-03-PLAN.md — Comprehensive test suite for all POC/VP/GEX/Zone/E6/E7 components

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
**Plans**: 2 plans (Wave 1: plan-01, plan-02 parallel)

Plans:
- [x] 06-01-PLAN.md — KronosConfig + subprocess worker + KronosSubprocessBridge + benchmark script
- [ ] 06-02-PLAN.md — TradingView MCP config, launch script, human verification checkpoint

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
**Plans**: 3 plans

Plans:
- [x] 07-01-PLAN.md — ScorerConfig + confirmation bonus (D-01) + stacked dedup (D-02) + scorer tests
- [x] 07-02-PLAN.md — vectorbt/optuna install + Optuna sweep framework (TEST-04, TEST-06)
- [x] 07-03-PLAN.md — Walk-forward validation, WFE gate, best_params.json, human checkpoint (TEST-05, TEST-07)

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
**Plans**: 4 plans (Wave 1: plan-01; Wave 2: plan-02, plan-03 parallel; Wave 3: plan-04)

Plans:
- [x] 08-01-PLAN.md — ExecutionConfig + ExecutionEngine + FreezeGuard position reconciliation
- [ ] 08-02-PLAN.md — PositionManager (lifecycle, breakeven, events)
- [ ] 08-03-PLAN.md — RiskManager (circuit breakers, GEX regime gate)
- [x] 08-04-PLAN.md — PaperTrader (slippage model, 30-day gate, full pipeline)

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
**Plans**: 4 plans (Wave 1: plan-01; Wave 2: plan-02; Wave 3: plan-03, plan-04 parallel)

Plans:
- [x] 09-01-PLAN.md — FastAPI app factory + EventStore (aiosqlite signal_events + trade_events)
- [x] 09-02-PLAN.md — LightGBM meta-learner + HMM regime detector (3-state Gaussian)
- [x] 09-03-PLAN.md — Optuna sweep endpoint + full weight deploy gate (WFE + OOS count + token)
- [x] 09-04-PLAN.md — PerformanceTracker + E7 wiring + test suite

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
**Plans**: 5 plans (Wave 1: plan-01; Wave 2: plan-02; Wave 3: plan-03, plan-04, plan-05 parallel)

Plans:
- [x] 10-01-PLAN.md — FastAPI WebSocket endpoint + /backtest/* API + WS broadcast wiring
- [x] 10-02-PLAN.md — Next.js 15 scaffold + Tailwind dark theme + WS client + Zustand stores + two-tab shell
- [x] 10-03-PLAN.md — LIVE tab: SignalFeed + RegimePanel + KronosBiasGauge + PositionPanel
- [x] 10-04-PLAN.md — Footprint chart: LW Charts v5.1 custom series plugin + zone overlays
- [x] 10-05-PLAN.md — BACKTEST tab: config form + equity curve + trade table + Optuna sweep subtab
**UI hint**: yes

### Phase 11: DEEP6 Trading Web App
**Goal**: Full-stack trading platform replacing TradingView dependency — Next.js 15 frontend with Lightweight Charts v5.1 custom footprint rendering, one-click trade execution panel connected to Rithmic via FastAPI WebSocket, real-time signal alerts with full context, mobile push notifications for TYPE_A signals, and complete session replay with bar-by-bar stepping.
**Depends on**: Phase 10
**Requirements**: APP-01, APP-02, APP-03, APP-04, APP-05, APP-06, APP-07, APP-08
**Success Criteria** (what must be TRUE):
  1. Custom footprint chart renders bid/ask volume per price level per bar via Lightweight Charts v5.1 custom series plugin — LVN/HVN zones, GEX levels, absorption/exhaustion zones overlaid directly on chart
  2. Trade execution panel shows live TYPE_A/B signals with full context (all category votes, GEX regime, zone info, Kronos bias) — operator can one-click confirm or auto-execute is enabled
  3. Real-time WebSocket push from FastAPI delivers signal events, bar updates, position state, and P&L within 200ms of bar close — no polling
  4. Session replay mode reconstructs any historical session with all signals, zones, orders visible — step forward/back bar by bar with full state at each step
  5. Mobile-responsive with push notifications via service worker — TYPE_A alerts reach operator's phone within 5 seconds of signal firing
  6. Portfolio dashboard shows live P&L, daily/weekly/monthly performance, win rate by tier, drawdown chart, and circuit breaker status
  7. No TradingView dependency — entire trading workflow (chart analysis, signal review, execution, replay) happens within the DEEP6 web app
  8. Authentication + multi-device support — operator can monitor from laptop and phone simultaneously
**Plans**: 4 plans (Wave 0: plan-01; Wave 1: plan-02; Wave 2: plan-03; Wave 3: plan-04)

Plans:
- [x] 11-01-PLAN.md — Backend extensions: bar_history EventStore table + WSManager + /ws/live multiplexed WebSocket + /api/replay endpoints (APP-03, APP-04 prerequisite)
- [x] 11-02-PLAN.md — Next.js 15 + Tailwind + shadcn scaffold; UI-SPEC design tokens; shared TypeScript types mirroring LiveMessage union; Zustand store with ring buffers + dispatcher tests
- [x] 11-03-PLAN.md — useWebSocket hook, LW Charts v5.1 footprint custom series + renderer, ZoneOverlay canvas, SignalFeed, TapeScroll, ScoreWidget (28px focal point), HeaderStrip
- [x] 11-04-PLAN.md — Replay mode (store + controller + controls), ReturnToLivePill, PnlStatus (APP-06 lite), ErrorBanner, operator smoke-test checkpoint
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11
Note: Phase 6 (Kronos + TVMCP) can begin after Phase 1 completes, running in parallel with Phases 2-5. Phase 6 TVMCP portion is optional — Phase 11 replaces TradingView as the primary trading interface.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Pipeline + Architecture Foundation | 2/4 | In Progress|  |
| 2. Absorption + Exhaustion Core | 0/3 | Not started | - |
| 3. Footprint Signal Engines (E1, E8, E9) | 0/4 | Not started | - |
| 4. DOM Depth Signal Engines (E2, E3, E4, E5) | 0/? | Not started | - |
| 5. Volume Profile + GEX Context + Zone Registry | 0/3 | Not started | - |
| 6. Kronos E10 + TradingView MCP | 0/2 | Not started | - |
| 7. Scoring + Backtesting Framework | 0/? | Not started | - |
| 8. Auto-Execution + Risk Layer | 0/? | Not started | - |
| 9. ML Backend | 0/? | Not started | - |
| 10. Analytics Dashboard | 5/5 | Complete    | 2026-04-14 |
| 11. DEEP6 Trading Web App | 4/4 | Complete   | 2026-04-14 |

### Phase 12: Integrate borrowed orderflow patterns: VPIN confidence modifier, Delta Slingshot, Delta At Extreme, setup state machine, per-regime walk-forward tracker

**Goal:** Integrate five vetted orderflow patterns from the kronos-tv-autotrader reference implementation into DEEP6's existing 44-signal engine, LightGBM meta-learner, and HMM regime detector — (1) VPIN as a continuous 0.2x-1.2x confidence modifier on fused LightGBM score, (2) running intrabar max/min delta on FootprintBar that fixes the existing DELT_TAIL (bit 22) to use real extremes, (3) new TRAP_SHOT signal at bit 44 (2/3/4-bar trapped-trader reversal, session-bounded, GEX-wall bypass), (4) dual-timeframe (1m + 5m) setup state machine with soak-bonus + explicit-close transition rule, and (5) per-category × per-regime walk-forward tracker with auto-disable/recovery feeding back into LightGBM fusion.
**Requirements**: OFP-01, OFP-02, OFP-03, OFP-04, OFP-05, OFP-06, OFP-07, OFP-08
**Depends on:** Phase 11
**Success Criteria** (what must be TRUE):
  1. VPIN engine produces continuous 0.2x-1.2x confidence multiplier using exact aggressor split (no BVC), applied only to FUSED LightGBM score as final stage with clip to [0, 100]
  2. FootprintBar tracks running max_delta/min_delta/running_delta on every add_trade; DELT_TAIL (bit 22) uses true intrabar extreme (proxy removed); SignalFlags bits 0-43 unchanged
  3. TRAP_SHOT fires at NEW bit 44 for 2/3/4-bar trapped-trader reversal (z-score > 2.0), with delta_history reset at RTH session boundary, 30-bar warmup, and triggers_state_bypass when within GEX wall proximity
  4. Dual-TF SetupTracker (1m + 5m simultaneously) with SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN; 10-bar soak = 5x weight (linear ramp); MANAGING → COOLDOWN is explicit-close-only (no auto); 30-bar failsafe; every transition persisted to EventStore
  5. WalkForwardTracker records every signal with per-category (8 groups) × per-regime (HMM state) outcome resolution at 5/10/20 bar horizons, labels EXPIRED for signals within 20 bars of RTH close, auto-disables cells with 200-signal rolling Sharpe < threshold, auto-recovers on 50-signal Sharpe recovery, feeds back into WeightFile.regime_adjustments; persistence via phase 09-01 EventStore only (no JSON sink)
**Plans**: 5 plans (Wave 1: plan-01, plan-02 parallel; Wave 2: plan-03; Wave 3: plan-04; Wave 4: plan-05)

Plans:
- [x] 12-PLAN-01-vpin-confidence-modifier.md — VPINEngine (exact aggressor, 1000-contract × 50 buckets) + scorer final-stage multiplier
- [x] 12-PLAN-02-intrabar-delta-and-delt-tail-fix.md — Running max/min delta on FootprintBar + DELT_TAIL (bit 22) rewired to true extreme; no new bit
- [x] 12-PLAN-03-trap-shot-slingshot.md — TRAP_SHOT at bit 44 (2/3/4-bar), session reset, 30-bar warmup, GEX-wall bypass signal
- [x] 12-PLAN-04-setup-state-machine.md — Dual-TF (1m+5m) 5-state machine with soak bonus, explicit-close rule, EventStore transition log
- [x] 12-PLAN-05-walk-forward-tracker.md — Per-category × per-regime outcomes at 5/10/20 horizons, auto-disable/recovery, LightGBM weight feedback via EventStore

**Status:** Phase 12 COMPLETE (2026-04-14) — all 5 plans shipped, 628 tests pass.

### Phase 13: Backtest Engine Core — Clock + MBO Adapter + DuckDB Store

**Goal:** Unify live and backtest code paths by injecting a `Clock` abstraction into `SharedState` and feeding Databento MBO events through the same `on_tick`/`on_dom` callback surfaces the live Rithmic feed uses. Capture per-bar artifacts (OHLC, 44-bit SignalFlags, ScorerResult, DOMSnapshot, simulated fill) into a DuckDB result store for post-run analysis. Integration + plumbing — the existing `deep6/data/databento_feed.py` (trades-only) is deprecated in favor of `deep6/backtest/mbo_adapter.py`.
**Requirements**: TBD
**Depends on:** Phase 12
**Plans:** 1 plan (scaffolded)

Plans:
- [ ] 13-01-PLAN.md — Clock protocol + WallClock/EventClock, MBOAdapter + FeedAdapter protocol (bmoscon/orderbook backed), DuckDB result_store, ReplaySession orchestrator, clock injection refactor

### Phase 14: Databento Live Feed

**Goal:** Build a live Databento MBO feed adapter that replaces Rithmic market data in the live pipeline — same MBO schema used in backtest, eliminating data drift. Rithmic continues to handle order execution only. New `deep6/data/databento_live.py` feeds the same `DOMState` and `FootprintBar` pipeline; data source selected via `DEEP6_DATA_SOURCE` env var (`"databento"` default | `"rithmic"`).
**Requirements**: TBD
**Depends on:** Phase 13
**Plans:** 0 plans (context gathered)

Plans:
- [ ] TBD (run /gsd-plan-phase 14 to break down)

### Phase 15: LevelBus + Confluence Rules + Trade Decision FSM

**Goal:** Unify tape-derived zones (LVN/HVN/VPOC/VAH/VAL/ABSORB/EXHAUST/MOMENTUM/REJECTION/FLIPPED) and GEX levels (call_wall, put_wall, gamma_flip, zero_gamma, hvl, largest_gamma) into a single `LevelBus` with normalized `Level` dataclass. Persist narrative signals (absorption/exhaustion/momentum/rejection) as lifecycle-tracked zones with VA-proximity boost and confirmation-boost scoring (BOOKMAP Pine methodology). Implement `ConfluenceRules` module encoding ~47 cross-stream rules from research (8 VP/GEX confluence, 12 vendor/academic, 12 microstructure, 15 auction-theory trade plans). Build `TradeDecisionMachine` 7-state FSM (IDLE→WATCHING→ARMED→TRIGGERED→IN_POSITION→MANAGING→EXITING) with 17 entry triggers + stop/target/invalidation/sizing policies replacing the current bar-close-only execution path. Research basis: `.planning/research/pine/*.md` + `.planning/research/pine/deep/*.md` (~12,500 words, 47 rules, 35 papers).
**Requirements**: TBD
**Depends on:** Phase 14
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 15 to break down)
