---
phase: 15-levelbus-confluence-rules-trade-decision-fsm
verified: 2026-04-14T16:30:00Z
status: passed
score: 5/5 plans complete
overrides_applied: 0
---

# Phase 15 Verification Report

**Phase Goal:** Unify DEEP6's three level lineages (VP, narrative, GEX) into a single `LevelBus`, encode the 38 canonical CR-XX confluence rules, and replace bar-close-only execution with a 7-state `TradeDecisionMachine` FSM — all preserving the Phase 12 SignalFlags invariant (bits 0-44 stable).

**Status:** PASSED — Phase 15 complete.

## Goal Achievement — Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Unified `Level` primitive + `LevelKind` (17 variants) + `LevelState` FSM in `deep6/engines/level.py` | PASS | 15-01 SUMMARY; `len(LevelKind) == 17` |
| 2 | `ZoneRegistry` renamed in place to `LevelBus` with `add_level / query_near / query_by_kind / get_top_n / get_all_active` | PASS | 15-01 SUMMARY; `deep6/engines/zone_registry.py` |
| 3 | Narrative signals ≥ 0.4 persist as Levels via `VPContextEngine.process(bar, narrative_result)` + cross-session decay (score × 0.70, touches // 2) | PASS | 15-02 SUMMARY; `_carry_over_strong_levels` + tests/test_vp_context_engine.py |
| 4 | `ConfluenceRules.evaluate()` with 38 CR-XX rules, priority-based regime merge, score mutations keyed by `Level.uid` (C5), DISQUALIFIED veto latching | PASS | 15-03 SUMMARY; `grep -c "^def cr_" deep6/engines/confluence_rules.py` → 38 |
| 5 | 3 meta-flag bits at positions 45/46/47 (PIN_REGIME_ACTIVE, REGIME_CHANGE, SPOOF_VETO); `ScorerResult.meta_flags`; `SignalTier.DISQUALIFIED = -1`; Phase 12 bits 0-44 byte-identical | PASS | 15-03 SUMMARY; `test_signal_flags_bits_preserved` green |
| 6 | 7-state FSM `TradeDecisionMachine` with 11 transitions, 17 entry-trigger taxonomy (4 types), in-bar cascade, EventStore `fsm_transitions` persistence | PASS | 15-04 SUMMARY; `TRANSITION_TABLE` has 11 entries; reachability suite |
| 7 | Every FSM transition T1..T11 reachable from public-API-only synthetic fixtures (D-38) | PASS | 15-05 — `tests/integration/test_fsm_reachability.py` 26/26 green |
| 8 | Every CR-XX rule validated at integration level (trigger + no-trigger) | PASS | 15-05 — `tests/integration/test_cr_goldens_full.py` 79/79 green (38 trigger + 38 no-trigger + inventory + audit + calibration-gated check) |
| 9 | End-to-end pipeline runs clean across all 5 day-type synthetic sessions | PASS | 15-05 — `tests/integration/test_phase15_end_to_end.py` 9/9 green |
| 10 | Performance baseline: `ConfluenceRules.evaluate` p95 < 1ms on 80 Levels (D-34); full 390-bar pipeline < 5s | PASS | 15-05 — measured p95 = 0.85ms, pipeline wall-time = 0.16s |

## Plan-by-plan Completion

| Plan | Title | SUMMARY | Tests new (pass) |
|------|-------|---------|------------------|
| 15-01 | Level + LevelKind/LevelState + LevelBus + LevelFactory + RULES.md + GEX extensions | present | 97 |
| 15-02 | narrative-Level persistence + cross-session decay | present | 31 |
| 15-03 | ConfluenceRules + scorer integration + meta-flags + DISQUALIFIED | present | 76 |
| 15-04 | TradeDecisionMachine FSM + EventStore fsm_transitions + on_bar_via_fsm forward | present | 49 |
| 15-05 | Integration + reachability + CR-XX goldens + perf baseline | present | 132 |

**Total new tests across Phase 15: ≈ 385; all green.**

## Required Artifacts

| Artifact | Status |
|----------|--------|
| `deep6/engines/level.py` (`Level` + `LevelKind` + `LevelState`) | VERIFIED |
| `deep6/engines/level_factory.py` (from_narrative / from_gex / etc.) | VERIFIED |
| `deep6/engines/zone_registry.py` (LevelBus) | VERIFIED |
| `deep6/engines/confluence_rules.py` (evaluate + 38 CR-XX) | VERIFIED |
| `deep6/engines/signal_config.py` (ConfluenceRulesConfig) | VERIFIED |
| `deep6/signals/flags.py` (bits 45/46/47 meta-flags + SIGNAL_BITS_MASK) | VERIFIED |
| `deep6/scoring/scorer.py` (confluence_annotations kwarg + DISQUALIFIED) | VERIFIED |
| `deep6/execution/trade_state.py` (TradeState + TransitionId + EntryTrigger + guards) | VERIFIED |
| `deep6/execution/trade_decision_machine.py` (TradeDecisionMachine) | VERIFIED |
| `deep6/execution/engine.py` (on_bar_via_fsm forward + legacy shim) | VERIFIED |
| `deep6/state/eventstore_schema.py` (fsm_transitions DDL + InMemoryFsmWriter) | VERIFIED |
| `.planning/phases/15-.../RULES.md` (38 canonical CR rows) | VERIFIED |
| Integration suite (`tests/integration/`) | VERIFIED |

## Anti-Pattern Scan

- S6 constraint: FSM does NOT call `confluence_rules.evaluate` — enforced
  by token-aware grep test `test_fsm_does_not_call_evaluate`.
- D-38 constraint: reachability scenarios use PUBLIC API only — enforced
  by token-aware guard `test_reachability_no_hand_state_mutation`.
- Phase 12 invariant: bits 0-44 byte-identical; `test_signal_flags_bits_preserved`
  pins them.
- Calibration-gated rules OFF by default — `test_cr_calibration_gated_off_by_default`.

## Test Suite Summary

| Suite | Count | Status |
|-------|-------|--------|
| `tests/integration/` (new this phase) | 132 | pass |
| `tests/engines/` (confluence + level + registry + vp_context etc.) | see plans | pass |
| `tests/execution/` (FSM + trade_state + engine delegate) | see plans | pass |
| `tests/scoring/` | see plans | pass |
| `tests/state/` | pre-existing | pass |
| `tests/orderflow/` | pre-existing | pass |
| **Targeted regression + integration (phase-15-safe subset)** | **757** | **pass** |

Full-suite (`pytest tests/`) hangs on `test_databento_live.py` + `test_gex.py`
(network-backed; require live API keys). These are pre-existing and not
introduced by Phase 15. The targeted regression deliberately excludes them,
consistent with the Phase 12/13/14 verification pattern.

## Performance Baseline (D-34)

| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| `ConfluenceRules.evaluate` p95 (80 Levels, 500 iters, gc-disabled) | 0.848 ms | < 1.0 ms | PASS |
| `ConfluenceRules.evaluate` median | 0.262 ms | — | — |
| 390-bar end-to-end pipeline wall-time | 0.159 s | < 5.0 s | PASS |

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| ZONE-01 Single store for all zone types | SATISFIED | LevelBus (D-09/D-10) |
| ZONE-02 Cross-type confluence scoring | SATISFIED | `get_confluence` + ConfluenceAnnotations |
| ZONE-03 Same-kind overlap merge | SATISFIED | `LevelBus._find_overlap` + merge path |
| EXEC-01 State-machine-based execution | SATISFIED | TradeDecisionMachine 7 states + 11 transitions |
| EXEC-03 Entry triggers (17 ET-XX taxonomy) | SATISFIED | EntryTrigger + 4-way EntryTriggerType |
| EXEC-04 Stop/Target/Invalidation policies | SATISFIED | `_compute_stop` / `_compute_target` / guard_T8_invalidated |
| EXEC-05 FSM persistence to EventStore | SATISFIED | fsm_transitions table + InMemoryFsmWriter |
| GEX-04 largest_gamma_strike | SATISFIED | GexLevels field + LevelKind.LARGEST_GAMMA |
| GEX-05 zero_gamma alias | SATISFIED | GexLevels.zero_gamma property + LevelKind.ZERO_GAMMA |

## Phase Closure

Phase 15 is complete. All 5 plans delivered; integration gate passed;
performance budget met; no Rule-4 (architectural) deviations outstanding.

Handoff to Phase 16 (bar-engine orchestration): wire PaperTrader /
LiveTrader to call `ExecutionEngine.on_bar_via_fsm` as the canonical
post-15-04 forward path. The legacy `ExecutionEngine.evaluate` shim with
its DeprecationWarning stays in place for one release window.

**Verified on 2026-04-14 from plans 15-01 through 15-05 SUMMARY files,
live test runs, and source introspection.**
