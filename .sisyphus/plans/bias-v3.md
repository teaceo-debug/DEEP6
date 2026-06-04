# DEEP6 Bias Engine v3 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Directional Bias Architecture Evolution

## TL;DR

> **Quick Summary**: Evolve the v2 UnifiedBiasEngine into a v3 architecture with 4 independent bias domains (ICT-Session, Macro-Intermarket, Intraday-Flow, Kronos-ML), a hysteresis state machine for stable bias transitions, and a GO/CAUTION/STOP kill switch that gates execution via the TradeDecisionMachine T2 and T3 transitions.
>
> **Deliverables**:
> - 4 domain engines producing signed integer scores (ICT: +/-4, Macro: +/-3, Flow: +/-2, Kronos: +/-3)
> - Hysteresis FSM: raw score to stable 5-state bias (STRONG_BULL / LEAN_BULL / NEUTRAL / LEAN_BEAR / STRONG_BEAR)
> - Kill switch / traffic light: GO / CAUTION / STOP entry permission system
> - Multi-symbol Rithmic OHLCV ingestion for intermarket data (ZN, DXY, VIX, RTY, TICK, VOLD)
> - MarketBiasSnapshot output consumed by TradeDecisionMachine T2/T3 gates
> - v2 characterization tests (regression baseline)
> - TDD throughout
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â 5 waves
> **Critical Path**: T1 -> T2 -> T5 -> T9 -> T12 -> T13 -> T15 -> T16 -> Final Verification

---

## Context

### Original Request
Evolve DEEP6 v2 bias engine into v3 per docs/market-bias-engine-design.md. Better directional bias for more alpha via signal separation, state management, intermarket confirmation.

### Interview Summary
- **v3 Vision**: Design doc is the blueprint
- **Strategy**: Evolve v2 incrementally
- **Kronos**: 4th bias domain, +/-3 range
- **Data**: Rithmic streams all intermarket instruments
- **Scope**: Full ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â all domains + hysteresis + kill switch
- **Tests**: TDD
- **Gate**: Both T2 (STOP) and T3 (CAUTION)

### Metis Review (Gaps Addressed)
- v2 ZERO test coverage -> Task 1 characterization tests
- UnifiedBiasEngine not in live path -> v3 integrates at TDM T2/T3
- Flow overloaded -> Intraday Flow (CVD/TICK/VWAP) separate from Options Flow (GEX/DEX)
- Kronos output mismatch -> adapter translates to signed -3..+3
- Aggressor gate blocks multi-instrument -> lightweight OHLCV bypass
- Zero intermarket infra -> dedicated task group
- Hysteresis unspecified -> configurable via signal_config.py
- TDM T2 gate is natural integration point

---

## Work Objectives

### Core Objective
v3 bias engine: 4 domains + hysteresis FSM + GO/CAUTION/STOP gates at TDM T2/T3.

### Deliverables
- deep6/engines/session_bias.py, intermarket_bias.py, flow_bias.py, kronos_domain.py
- deep6/engines/bias_composer.py, bias_hysteresis.py, kill_switch.py, market_bias_engine.py
- deep6/engines/intermarket_feed.py, ohlcv_accumulator.py, bias_contracts.py
- Config in signal_config.py, tests for everything

### Definition of Done
- [ ] pytest tests/ all green (new + existing)
- [ ] MarketBiasSnapshot produced correctly from 4 domains
- [ ] TDM T2 returns False on STOP, T3 returns False on CAUTION
- [ ] Hysteresis prevents noisy flipping
- [ ] Stale feeds degrade gracefully (score=0)
- [ ] Zero regression

### Must Have
- 4 independent domain engines, each testable in isolation
- Hysteresis FSM with configurable thresholds
- GO/CAUTION/STOP kill switch
- Multi-symbol Rithmic OHLCV for ZN, DXY, VIX, RTY, TICK, VOLD
- Staleness detection, T2+T3 gates, v2 characterization tests

### Must NOT Have
- DO NOT modify scoring/scorer.py (R3 alpha)
- DO NOT modify live_pipeline.py, setup_tracker.py
- DO NOT modify trade_decision_machine.py until T16/17
- DO NOT modify deep6/bias_engine/ (v2 intact)
- DO NOT merge bias into bar scoring
- DO NOT hard-code thresholds
- DO NOT add GEX as v3 domain
- DO NOT touch chart/NT8/dashboard UI

---

## Verification Strategy
- TDD with pytest, ZERO human intervention
- Evidence: .sisyphus/evidence/task-{N}-{slug}.{ext}

## Execution Strategy

### Waves
```
Wave 0: T1 (v2 tests) [deep], T2 (contracts) [quick], T3 (registry) [quick]
Wave 1: T4 (OHLCV accum) [unspec-high], T5 (Rithmic sub) [deep], T6 (hysteresis) [deep], T7 (kill switch) [unspec-high]
Wave 2: T8 (ICT) [deep], T9 (Macro) [deep], T10 (Flow) [deep], T11 (Kronos) [unspec-high]
Wave 3: T12 (Composer) [deep], T13 (wire hysteresis) [unspec-high], T14 (wire kill) [unspec-high], T15 (orchestrator) [deep]
Wave 4: T16 (T2 gate) [deep], T17 (T3 gate) [deep], T18 (FastAPI) [quick]
Final: F1 (oracle), F2 (quality), F3 (QA), F4 (scope)
```

### Critical Path
T1 -> T2 -> T5 -> T9 -> T12 -> T13 -> T15 -> T16 -> F1-F4

### Dependencies
| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â | 2, 3 | 0 |
| 2 | 1 | 4-11 | 0 |
| 3 | 1 | 5, 9, 10 | 0 |
| 4 | 2 | 9, 10 | 1 |
| 5 | 2, 3 | 9, 10 | 1 |
| 6 | 2 | 13 | 1 |
| 7 | 2 | 14 | 1 |
| 8 | 2 | 12 | 2 |
| 9 | 2,3,4,5 | 12 | 2 |
| 10 | 2,3,4,5 | 12 | 2 |
| 11 | 2 | 12 | 2 |
| 12 | 8-11 | 13,14,15 | 3 |
| 13 | 6, 12 | 15 | 3 |
| 14 | 7, 12 | 15 | 3 |
| 15 | 12,13,14 | 16-18 | 3 |
| 16 | 15 | F1-F4 | 4 |
| 17 | 15 | F1-F4 | 4 |
| 18 | 15 | F1-F4 | 4 |

---

## TODOs
### Wave 0 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Foundation

- [x] 1. v2 UnifiedBiasEngine Characterization Tests

  **What to do**: Write pytest tests for deep6/bias_engine/unified_bias.py capturing v2 behavior. Test compute() with deterministic inputs (all-bullish, all-bearish, mixed, unavailable sources, macro_blackout). Test _alignment_confidence() edges, _score_to_grade() boundaries (0.85/0.70/0.55/0.40), _derive_trade_setup() for LONG/SHORT/WAIT, divergence warnings (120pt/80pt). Follow tests/test_narrative.py patterns.

  **Must NOT do**: Do NOT modify unified_bias.py. Do NOT import from deep6.engines.

  **Agent**: deep | **Skills**: [] | **Wave**: 0 | **Blocks**: 2, 3 | **Blocked By**: None

  **References**: tests/test_narrative.py (patterns), tests/test_gex.py (staleness), unified_bias.py:115-370 (all methods)

  **Acceptance**: tests/test_unified_bias_v2.py created, pytest passes (min 15 tests)

  **QA**: pytest tests/test_unified_bias_v2.py -v -> 15+ passed, 0 failed. Evidence: .sisyphus/evidence/task-1-full-suite.txt

  **Commit**: test(bias): add v2 UnifiedBiasEngine characterization tests

- [x] 2. Data Contracts and Config Dataclasses

  **What to do**: Create deep6/engines/bias_contracts.py with BiasState(IntEnum -2..+2), BiasMode(GO/CAUTION/STOP), BiasComponentState(slots=True: ict_score int -4..+4, macro_score -3..+3, flow_score -2..+2, kronos_score -3..+3, total_score clamped -9..+9, confidence 0-1, setup_quality 0-5, bias_state, mode, reason), MarketBiasSnapshot(slots=True: symbol, asof_ts, bias_label, bias_state, bias_score, confidence, setup_quality, mode, mode_reason, session_label, xamd_phase, intermarket_alignment, kronos_confidence, nearest_support, nearest_resistance, domain_detail dict, meta dict), DomainScore(slots=True: domain, score, max_range, available, stale, detail, updated_at). Add to signal_config.py: BiasHysteresisConfig(enter_strong=7, degrade_strong=4, enter_lean=3, degrade_lean=1, emergency_delta=10), KillSwitchConfig(event_day_mode=STOP, lunch_start=12, lunch_end=13, cutoff=15, vix_crisis=35.0, vix_elevated=25.0, min_domains=2), IntermarketConfig(staleness_sec=300, bar_interval=60, symbols=[ZN,DXY,VIX,RTY,TICK,VOLD,AD]), KronosDomainConfig(max_range=3, high_conf=70.0, low_conf=30.0).

  **Must NOT do**: Do NOT modify existing signal_config.py classes. Do NOT import from deep6/bias_engine/.

  **Agent**: quick | **Skills**: [] | **Wave**: 0 | **Blocks**: 4-11 | **Blocked By**: 1

  **References**: signal_config.py:KronosConfig/ScorerConfig (patterns), docs/market-bias-engine-design.md:460-493 (specs)

  **Acceptance**: bias_contracts.py + signal_config.py updated, pytest tests/test_bias_contracts.py passes

  **QA**: python -c "from deep6.engines.bias_contracts import *; from deep6.engines.signal_config import BiasHysteresisConfig; print(BiasHysteresisConfig().enter_strong_threshold)" -> "7". Evidence: .sisyphus/evidence/task-2-contracts.txt

  **Commit**: feat(bias-v3): add data contracts and config dataclasses

- [x] 3. Intermarket Instrument Registry and Staleness Model

  **What to do**: Create deep6/engines/intermarket_registry.py with InstrumentSpec(symbol, rithmic_symbol, exchange, is_rth_only, bar_interval_sec, description), IntermarketRegistry (register, track active/stale, lookup). Pre-configured: ZN(CME, 24h), DXY(ICE, 24h), VIX(CBOE, RTH), RTY(CME, 24h), TICK(NYSE, RTH), VOLD(NYSE, RTH), AD(NYSE, RTH). Staleness: last_update_ts per instrument, is_stale() vs IntermarketConfig.staleness_sec. RTH-only: is_rth_only=True auto-reports expected_stale outside 9:30-16:00 ET.

  **Must NOT do**: Do NOT implement Rithmic connections. Do NOT hard-code thresholds.

  **Agent**: quick | **Skills**: [] | **Wave**: 0 | **Blocks**: 5, 9, 10 | **Blocked By**: 1

  **References**: gex_client.py:GEXState.timestamp (staleness pattern), state/connection.py:FreezeGuard (connection state)

  **Acceptance**: intermarket_registry.py created, pytest tests/test_intermarket_registry.py passes

  **QA**: Staleness: is_stale False at T+299s, True at T+301s. RTH-only: TICK stale at 20:00 ET. Evidence: .sisyphus/evidence/task-3-staleness.txt

  **Commit**: feat(bias-v3): add intermarket instrument registry and staleness

### Wave 1 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Infrastructure

- [x] 4. OHLCV Accumulator (Lightweight Bar Builder)

  **What to do**: Create deep6/engines/ohlcv_accumulator.py with OHLCVBar(slots=True: symbol, open, high, low, close, volume, bar_start_ts, bar_end_ts, tick_count) and OHLCVAccumulator that accumulates ticks into bars at configurable interval. Interface: feed_tick(price, volume, timestamp) -> Optional[OHLCVBar]. NOT FootprintBar ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â no L2/DOM/delta.

  **Must NOT do**: Do NOT use FootprintBar or BarBuilder. Do NOT include L2 data.

  **Agent**: unspecified-high | **Skills**: [] | **Wave**: 1 | **Blocks**: 9, 10 | **Blocked By**: 2

  **References**: deep6/data/bar_builder.py (pattern reference, but build simpler)

  **Acceptance**: ohlcv_accumulator.py created, pytest tests/test_ohlcv_accumulator.py passes

  **QA**: Feed 10 ticks spanning 60s -> complete bar with correct OHLCV. Evidence: .sisyphus/evidence/task-4-bar.txt

  **Commit**: feat(bias-v3): add OHLCV accumulator and Rithmic subscription (groups with T5)

- [x] 5. Multi-Symbol Rithmic OHLCV Subscription Manager

  **What to do**: Create deep6/engines/intermarket_feed.py. IntermarketFeed: async manager subscribing to multiple Rithmic symbols via BBO/trade ticks (NOT L2 DOM). Maintains one OHLCVAccumulator per symbol. Feeds completed bars to callbacks. Bypasses aggressor gate. Updates IntermarketRegistry staleness on each tick. Graceful degradation on partial symbol failure. Follow FreezeGuard reconnection pattern.

  **Must NOT do**: Do NOT use L2 DOM subscription. Do NOT modify deep6/data/rithmic.py. Fully async.

  **Agent**: deep | **Skills**: [] | **Wave**: 1 | **Blocks**: 9, 10 | **Blocked By**: 2, 3

  **References**: deep6/data/rithmic.py (async-rithmic patterns), state/connection.py:FreezeGuard (reconnection), intermarket_registry.py (T3)

  **Acceptance**: intermarket_feed.py created, pytest tests/test_intermarket_feed.py passes

  **QA**: Mock ticks produce bars + update staleness. Partial symbol failure: DXY works, ZN stale, no crash. Evidence: .sisyphus/evidence/task-5-mock-ticks.txt

  **Commit**: groups with T4

- [x] 6. Hysteresis State Machine (FSM Core)

  **What to do**: Create deep6/engines/bias_hysteresis.py. BiasHysteresisFSM takes raw score -9..+9 -> stable BiasState. States: STRONG_BEAR(-2), LEAN_BEAR(-1), NEUTRAL(0), LEAN_BULL(+1), STRONG_BULL(+2). Transitions from BiasHysteresisConfig: enter_strong>=7, degrade_strong<4, enter_lean>=3, degrade_lean<1. Mirror for bear. Emergency override: abs(delta) >= 10 -> immediate. Structlog transitions (follow hmm_regime.py). Interface: update(raw_score) -> BiasState. Properties: current_state, previous_state, bars_in_state.

  **Must NOT do**: Do NOT hard-code thresholds. Do NOT modify existing FSMs.

  **Agent**: deep | **Skills**: [] | **Wave**: 1 | **Blocks**: 13 | **Blocked By**: 2

  **References**: deep6/ml/hmm_regime.py (FSM pattern), execution/trade_decision_machine.py (guard pattern), signal_config.py:BiasHysteresisConfig (T2)

  **Acceptance**: bias_hysteresis.py created, pytest tests/test_bias_hysteresis.py passes

  **QA**: Sequence [+3,+5,+7,+5,+3,+1,-1,-3] -> [LEAN_BULL,LEAN_BULL,STRONG_BULL,STRONG_BULL,NEUTRAL,NEUTRAL,NEUTRAL,LEAN_BEAR]. Emergency: STRONG_BULL + score -5 (delta=12) -> immediate LEAN_BEAR. Evidence: .sisyphus/evidence/task-6-hysteresis.txt

  **Commit**: feat(bias-v3): add hysteresis FSM and kill switch (groups with T7)

- [x] 7. Kill Switch / Traffic Light Core

  **What to do**: Create deep6/engines/kill_switch.py. KillSwitch evaluates conditions -> BiasMode (GO/CAUTION/STOP) + reason. STOP: event day strict, past cutoff (15:00 ET), VIX >= 35, fewer than 2 domains active, severe intermarket divergence. CAUTION: lunch window (12-13 ET), VIX >= 25, chop (score oscillating near 0), partial staleness. GO: none of above. Interface: evaluate(session_time_et, vix, domains_active, score_history, event_day) -> (BiasMode, reason).

  **Must NOT do**: Do NOT connect to live data. Do NOT hard-code thresholds.

  **Agent**: unspecified-high | **Skills**: [] | **Wave**: 1 | **Blocks**: 14 | **Blocked By**: 2

  **References**: docs/market-bias-engine-design.md:349-361 (triggers), signal_config.py:KillSwitchConfig (T2), po3_detector.py:_phase_from_hour() (session time)

  **Acceptance**: kill_switch.py created, pytest tests/test_kill_switch.py passes

  **QA**: test_stop_event_day -> STOP. test_caution_lunch -> CAUTION at 12:30. test_go_clear -> GO. Evidence: .sisyphus/evidence/task-7-kill-switch.txt

  **Commit**: groups with T6

### Wave 2 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Domain Engines

- [x] 8. ICT-Session Domain Engine (-4 to +4)

  **What to do**: Create deep6/engines/session_bias.py. ICTSessionDomain computes -4..+4 from session structure. Components: price vs Midnight Open (+/-1), price vs Weekly Open (+/-1), Judas confirmed (+/-1), Premium/Discount zone (+/-1). Consumes PO3BiasState read-only. Interface: compute(po3_state) -> DomainScore. Graceful degradation if fields None.

  **Must NOT do**: Do NOT modify PO3BiasDetector. Do NOT duplicate PO3 logic.

  **Agent**: deep | **Skills**: [] | **Wave**: 2 | **Blocks**: 12 | **Blocked By**: 2

  **References**: bias_engine/po3_detector.py (PO3BiasDetector), bias_engine/models.py:PO3BiasState (input), docs/market-bias-engine-design.md:227-239

  **Acceptance**: session_bias.py created, pytest tests/test_session_bias.py passes

  **QA**: All bullish (above MO, above WO, judas bull, discount) -> +4. Partial data -> reduced range. Evidence: .sisyphus/evidence/task-8-ict.txt

  **Commit**: feat(bias-v3): add 4 domain engines (groups with T9-11)

- [x] 9. Macro-Intermarket Domain Engine (-3 to +3)

  **What to do**: Create deep6/engines/intermarket_bias.py. MacroIntermarketDomain computes -3..+3 from cross-market. Components: ZN direction (rising=+1 risk-on), DXY direction (falling=+1 weak dollar bullish NQ), VIX term structure (contango=+1). Sum clamp -3..+3. Consumes OHLCVBar dict from IntermarketFeed. Direction: simple close-vs-open or SMA slope. Stale instrument excluded, max_range reduced.

  **Must NOT do**: Do NOT subscribe to Rithmic directly. Do NOT over-engineer direction detection.

  **Agent**: deep | **Skills**: [] | **Wave**: 2 | **Blocks**: 12 | **Blocked By**: 2, 3, 4, 5

  **References**: docs/market-bias-engine-design.md:241-262, ohlcv_accumulator.py:OHLCVBar (T4), intermarket_registry.py (T3)

  **Acceptance**: intermarket_bias.py created, pytest tests/test_intermarket_bias.py passes

  **QA**: ZN rising + DXY falling + VIX contango -> +3. Stale ZN -> compute from 2 inputs only. Evidence: .sisyphus/evidence/task-9-macro.txt

  **Commit**: groups with T8

- [x] 10. Intraday Flow Domain Engine (-2 to +2)

  **What to do**: Create deep6/engines/flow_bias.py. IntradayFlowDomain computes -2..+2 from live tape. Components: CVD slope (+/-1), TICK thrust (>800 or <-800 sustained, +/-1), price vs VWAP (+/-1, but capped at +/-2 total). NOT options flow ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â CVD/TICK/VWAP only. RTH-only: outside RTH returns 0. Interface: compute(tick_value, cvd_slope, price, vwap) -> DomainScore.

  **Must NOT do**: Do NOT confuse with GEX/options flow. Do NOT duplicate VWAP if it exists in SharedState.

  **Agent**: deep | **Skills**: [] | **Wave**: 2 | **Blocks**: 12 | **Blocked By**: 2, 3, 4, 5

  **References**: docs/market-bias-engine-design.md:253-262

  **Acceptance**: flow_bias.py created, pytest tests/test_flow_bias.py passes

  **QA**: CVD positive + TICK>800 + above VWAP -> +2. Outside RTH -> 0, stale=True. Evidence: .sisyphus/evidence/task-10-flow.txt

  **Commit**: groups with T8

- [x] 11. Kronos Domain Adapter (-3 to +3)

  **What to do**: Create deep6/engines/kronos_domain.py. KronosDomainAdapter translates KronosBias(direction +/-1/0, confidence 0-100) -> DomainScore -3..+3. Translation: direction * (conf>=70: 3, conf>=50: 2, conf>=30: 1, else: 0). Uses KronosDomainConfig. Cold start: if no KronosBias yet, DomainScore(available=False, score=0).

  **Must NOT do**: Do NOT modify kronos_bias.py. Do NOT run inference.

  **Agent**: unspecified-high | **Skills**: [] | **Wave**: 2 | **Blocks**: 12 | **Blocked By**: 2

  **References**: engines/kronos_bias.py:KronosBias (input), signal_config.py:KronosDomainConfig (T2)

  **Acceptance**: kronos_domain.py created, pytest tests/test_kronos_domain.py passes

  **QA**: direction=+1, conf=85 -> +3. Cold start -> available=False, score=0. Evidence: .sisyphus/evidence/task-11-kronos.txt

  **Commit**: groups with T8

### Wave 3 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Composition

- [x] 12. Bias Composer ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Domain Sum + Confidence

  **What to do**: Create deep6/engines/bias_composer.py. BiasComposer takes 4 DomainScores, sums -> BiasComponentState. Sum: ict+macro+flow+kronos, clamp -9..+9. Confidence: base=abs(total)/9, reduce if domains disagree (max positive + max negative abs > 5 -> halve), reduce if stale, reduce if < min_domains. Setup quality 0-5: agreement(+1), session(+1), proximity(+1), flow clean(+1), rvol(+1). Interface: compose(domains, session_quality, proximity_bonus, flow_clean, rvol_bonus) -> BiasComponentState.

  **Must NOT do**: Do NOT apply hysteresis (T13). Do NOT apply kill switch (T14).

  **Agent**: deep | **Skills**: [] | **Wave**: 3 | **Blocks**: 13, 14, 15 | **Blocked By**: 8-11

  **References**: docs/market-bias-engine-design.md:302-348, bias_contracts.py (T2)

  **Acceptance**: bias_composer.py created, pytest tests/test_bias_composer.py passes

  **QA**: All bullish ICT=+4,Macro=+3,Flow=+2,Kronos=+3 -> total=+9, high conf. Disagreement ICT=+4,Macro=-3,Flow=-2,Kronos=+2 -> total=+1, conf halved. Evidence: .sisyphus/evidence/task-12-composer.txt

  **Commit**: feat(bias-v3): add bias composer and market bias engine (groups with T13-15)

- [x] 13. Wire Hysteresis FSM Into Composer

  **What to do**: Connect BiasHysteresisFSM (T6) to BiasComposer (T12). Feed raw total_score into FSM.update() -> BiasState. Set BiasComponentState.bias_state to stabilized state. Integration wiring only.

  **Must NOT do**: Do NOT modify FSM internals. Do NOT bypass hysteresis.

  **Agent**: unspecified-high | **Wave**: 3 | **Blocks**: 15 | **Blocked By**: 6, 12

  **Acceptance**: Composer outputs via hysteresis. Score +3 -> LEAN_BULL, then +2 -> still LEAN_BULL.

  **Commit**: groups with T12

- [x] 14. Wire Kill Switch Into Composer

  **What to do**: Connect KillSwitch (T7) to composition pipeline. After compose(), evaluate kill switch. Set mode and reason on BiasComponentState. Kill switch affects MODE only, NOT bias_state or score. Design doc principle: "kill switch affects entries, not bias display."

  **Must NOT do**: Do NOT let kill switch modify bias_state or total_score.

  **Agent**: unspecified-high | **Wave**: 3 | **Blocks**: 15 | **Blocked By**: 7, 12

  **Acceptance**: Event day -> mode=STOP but bias_state unchanged, score unchanged.

  **Commit**: groups with T12

- [x] 15. Market Bias Engine Orchestrator

  **What to do**: Create deep6/engines/market_bias_engine.py. MarketBiasEngine orchestrates all components -> MarketBiasSnapshot. Holds: 4 domain engines, BiasComposer, BiasHysteresisFSM, KillSwitch, IntermarketRegistry. Main: compute_bias(po3_state, latest_bars, tick_value, cvd_slope, price, vwap, kronos_bias, session_time_et, vix_level, event_day) -> MarketBiasSnapshot. Flow: domains -> composer -> hysteresis -> kill switch -> snapshot. Cold start: < min_domains -> NEUTRAL + CAUTION.

  **Must NOT do**: Do NOT connect to live data. Takes all inputs as parameters.

  **Agent**: deep | **Wave**: 3 | **Blocks**: 16-18 | **Blocked By**: 12, 13, 14

  **References**: All T2-14 outputs, docs/market-bias-engine-design.md:460-493

  **Acceptance**: market_bias_engine.py created, full pipeline test with mock data passes. Cold start -> NEUTRAL + CAUTION.

  **Commit**: groups with T12

### Wave 4 ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Integration

- [x] 16. T2 Gate ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â STOP Blocks WATCHING->ARMED

  **What to do**: Modify trade_decision_machine.py: in guard_T2_ready(), add v3 check. If MarketBiasSnapshot.mode==STOP -> return False. Log reason via structlog. ADDITIONAL to existing guards, not replace. Use lsp_find_references on guard_T2_ready first.

  **Must NOT do**: Do NOT remove existing T2 guards. Do NOT modify other TDM methods.

  **Agent**: deep | **Wave**: 4 | **Blocks**: F1-F4 | **Blocked By**: 15

  **References**: execution/trade_decision_machine.py:guard_T2_ready(), market_bias_engine.py (T15)

  **Acceptance**: guard_T2_ready() False on STOP, True on GO. Existing TDM tests pass.

  **QA**: Mock STOP -> False. Mock GO -> True. Evidence: .sisyphus/evidence/task-16-t2.txt

  **Commit**: feat(bias-v3): integrate v3 bias into TDM T2/T3 gates (groups with T17-18)

- [x] 17. T3 Gate ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â CAUTION Blocks ARMED->TRIGGERED

  **What to do**: Modify trade_decision_machine.py: in T3 transition (ARMED->TRIGGERED), add v3 check. CAUTION -> False (stay ARMED). STOP -> also False. Log reason.

  **Must NOT do**: Do NOT modify other transitions.

  **Agent**: deep | **Wave**: 4 | **Blocks**: F1-F4 | **Blocked By**: 15

  **Acceptance**: T3 blocked by CAUTION and STOP. Existing tests pass.

  **Commit**: groups with T16

- [x] 18. FastAPI Endpoint for v3 Bias

  **What to do**: Create deep6/api/routes/bias_v3.py. GET /api/v3/bias -> MarketBiasSnapshot JSON. GET /api/v3/bias/domains -> domain scores. GET /api/v3/bias/history -> last N snapshots. Follow existing bias.py route patterns. Return 503 if not initialized.

  **Must NOT do**: Do NOT modify existing bias.py routes.

  **Agent**: quick | **Wave**: 4 | **Blocks**: F1-F4 | **Blocked By**: 15

  **Acceptance**: bias_v3.py created, pytest tests/test_bias_v3_api.py passes

  **Commit**: groups with T16

---

## Final Verification Wave

> 4 agents in PARALLEL. ALL must APPROVE. Present to user, get explicit okay.

- [x] F1. **Plan Compliance Audit** ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â oracle: Verify all Must Have/Must NOT Have. Check evidence files. VERDICT.
- [x] F2. **Code Quality Review** ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â unspecified-high: pytest + lint. No type:ignore, empty catches, hard-coded thresholds. VERDICT.
- [x] F3. **Real Manual QA** ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â unspecified-high: Execute ALL QA scenarios. Cross-task integration. Edge cases. VERDICT.
- [x] F4. **Scope Fidelity Check** ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â deep: Spec-to-impl 1:1. Only TDM modified (T16/17). No contamination. VERDICT.

---

## Commit Strategy

| Wave | Message | Pre-commit |
|------|---------|------------|
| 0 | test(bias): add v2 UnifiedBiasEngine characterization tests | pytest tests/test_unified_bias_v2.py |
| 0 | feat(bias-v3): add data contracts and config dataclasses | pytest tests/test_bias_contracts.py |
| 0 | feat(bias-v3): add intermarket instrument registry | pytest tests/test_intermarket_registry.py |
| 1 | feat(bias-v3): add OHLCV accumulator and Rithmic subscription | pytest tests/ |
| 1 | feat(bias-v3): add hysteresis FSM and kill switch | pytest tests/ |
| 2 | feat(bias-v3): add 4 domain engines | pytest tests/ |
| 3 | feat(bias-v3): add bias composer and market bias engine | pytest tests/ |
| 4 | feat(bias-v3): integrate v3 bias into TDM T2/T3 gates | pytest tests/ |

---

## Success Criteria

### Verification Commands
```
pytest tests/ -v
pytest tests/test_unified_bias_v2.py -v
pytest tests/test_bias_composer.py -v
pytest tests/test_bias_hysteresis.py -v
pytest tests/test_kill_switch.py -v
pytest tests/test_tdm_bias_v3.py -v
python -c "from deep6.engines.market_bias_engine import MarketBiasEngine; print('ok')"
```

### Final Checklist
- [ ] All Must Have present
- [ ] All Must NOT Have absent
- [ ] All tests pass (new + existing)
- [ ] v2 UnifiedBiasEngine unchanged
- [ ] scoring/scorer.py untouched (R3 weights)
- [ ] TDM T2/T3 gates respect GO/CAUTION/STOP
- [ ] Domain engines degrade gracefully on stale data
- [ ] All thresholds in signal_config.py
