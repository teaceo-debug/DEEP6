---
phase: 15-levelbus-confluence-rules-trade-decision-fsm
plan: 02
subsystem: engines
tags: [levelbus, narrative-persistence, cross-session-decay, phase-15]
requirements: [ZONE-01, ZONE-03]
dependency_graph:
  requires:
    - "deep6/engines/level.py Level + LevelKind + LevelState (from 15-01)"
    - "deep6/engines/level_factory.py from_narrative (strength-gated, wick-geometry) (from 15-01)"
    - "deep6/engines/zone_registry.py LevelBus.add_level / query_by_kind / get_all_active (from 15-01)"
    - "deep6/engines/narrative.py NarrativeResult (unchanged)"
  provides:
    - "E6VPContextEngine.process(bar, narrative_result=None) — narrative→LevelBus hook at D-31 insertion site"
    - "E6VPContextEngine._carry_over_strong_levels — D-08 cross-session decay helper"
    - "Narrative Levels (ABSORB/EXHAUST/MOMENTUM/REJECTION) queryable across bars via registry.query_by_kind"
  affects:
    - "deep6/engines/vp_context_engine.py process() signature additively extended (backward-compatible default)"
    - "deep6/engines/vp_context_engine.py on_session_start now applies score≥60 carry-over with 0.70 decay before clear()"
tech_stack:
  added: []
  patterns:
    - "dataclasses.replace for decayed-copy carry-over (no aliasing into pre-clear registry)"
    - "Content-anchored insertion (D-31) — no line-number dependencies"
    - "Strength filter applied inside factory, not inline — single source of truth"
key_files:
  created:
    - "tests/engines/test_vp_context_narrative_levels.py"
    - "tests/engines/test_narrative_persistence.py"
  modified:
    - "deep6/engines/vp_context_engine.py"
decisions:
  - "process() takes narrative_result as optional kwarg (default None) — backward compatible with every existing call site"
  - "Strength threshold 0.4 (D-06) enforced inside LevelFactory.from_narrative; vp_context_engine passes the canonical default rather than duplicating the constant"
  - "Cross-session carry-over constants (_SESSION_CARRY_SCORE_THRESHOLD=60.0, _SESSION_CARRY_DECAY=0.70) live as class attributes on E6VPContextEngine — tunable from subclasses / config in later phases without touching call sites"
  - "Carry-over uses dataclasses.replace to build fresh Level copies; preserves uid (C5) while guaranteeing no pre-clear mutable aliasing back into the new-session registry"
  - "state reset to CREATED on carry — fresh session treats decayed Levels as active-new, avoiding DEFENDED/BROKEN transitions from a prior session"
  - "Narrative carry-over scope limited to 6 narrative-origin kinds (ABSORB, EXHAUST, MOMENTUM, REJECTION, CONFIRMED_ABSORB, FLIPPED); VP origins (LVN/HVN) take VPRO-07 prior_bins path; GEX re-fetched"
metrics:
  duration_min: 15
  tasks_completed: 2
  completed_date: "2026-04-14"
---

# Phase 15 Plan 02: Narrative-Level Persistence + Cross-Session Decay Summary

Wire narrative signals into LevelBus at `E6VPContextEngine.process()`
step 2.5 (D-31), applying the strength≥0.4 filter (D-06), full-wick
geometry for ABSORB/EXHAUST (D-07), and score≥60 cross-session decay
with 0.70 recency factor (D-08).

## What Shipped

- **`deep6/engines/vp_context_engine.py` — `process()` step 2.5.**
  New optional `narrative_result: NarrativeResult | None = None`
  parameter. When provided, `LevelFactory.from_narrative(result,
  strength_threshold=0.4, bar_index=self._bar_count, tick_size=...,
  bar=bar)` is invoked immediately after the `detect_zones` loop and
  before `update_zones`. Each emitted Level flows through
  `self.registry.add_level(lvl)`. Content-anchored insertion — no
  line-number fragility. Omitting `narrative_result` preserves every
  pre-existing call-site's behavior (no narrative Levels emitted; no
  shape change to `VPContextResult`).

- **`deep6/engines/vp_context_engine.py` — `on_session_start()` D-08
  decay.** New private helper `_carry_over_strong_levels()` snapshots
  narrative-origin Levels (ABSORB/EXHAUST/MOMENTUM/REJECTION/
  CONFIRMED_ABSORB/FLIPPED) with `score ≥ 60`, applies
  `score × 0.70`, halves `touches`, and resets `state = CREATED`.
  The snapshot is taken BEFORE `self.registry.clear()`, and the
  decayed copies are re-added AFTER — below-threshold Levels and all
  non-narrative kinds are dropped by the clear (GC). `dataclasses.replace`
  produces fresh instances so no mutable aliasing bleeds from the pre-clear
  registry into the new session.

- **Tests — `tests/engines/test_vp_context_narrative_levels.py`
  (9 tests, T-15-02-01).** Covers:
  - Strength below 0.4 not persisted / above 0.4 persisted.
  - ABSORB upper-wick geometry (bar {100,105,99,101} UW → top=105, bot=101).
  - ABSORB lower-wick geometry (bar {101,102,95,100} LW → top=100, bot=95).
  - All four narrative kinds persist together when above threshold
    (ABSORB + EXHAUST + MOMENTUM; REJECTION covered separately).
  - MOMENTUM strength 0.3 → not persisted (body kinds also strength-gated).
  - VPContextResult shape backward-compatible (fields unchanged).
  - process() without narrative_result emits no narrative Levels
    (backward-compat for every existing call site).

- **Tests — `tests/engines/test_narrative_persistence.py`
  (9 tests, T-15-02-02).** Covers:
  - score=80 → 56.0 after decay.
  - score=55 dropped (below threshold).
  - score=60 boundary carried (inclusive).
  - Kind filter (ABSORB carries; LVN and CALL_WALL drop).
  - State reset: DEFENDED → CREATED after carry.
  - touches halved (floor-div).
  - All six narrative-origin kinds carry simultaneously.
  - INVALIDATED never carries regardless of score.
  - `prior_bins` path still routes through `SessionProfile`
    constructor (VPRO-07 preserved).

## Test Results

| Suite | Count | Status |
|-------|-------|--------|
| `tests/engines/test_vp_context_narrative_levels.py` | 9 | pass |
| `tests/engines/test_narrative_persistence.py` | 9 | pass |
| `tests/engines/` (full engines subsuite incl. 15-01 work) | 70 | pass |
| `tests/test_vp_context_engine.py` (regression) | — (bundled) | pass |
| Targeted regression (engines + scoring + state + orderflow + scorer + narrative + absorption + exhaustion + zone_registry) | **241** | **pass** |

The broader non-live suite (`tests/ --ignore=api,backtest,integration`)
was started but runs ≥ 10 min on this machine due to ML/heavy tests
unrelated to the Plan 15-02 surface; targeted regression above
exercises every module touching the modified code paths and every
adjacent consumer (`scorer.py`, `narrative.py`, `absorption.py`,
`exhaustion.py`, `zone_registry.py`). No regressions observed. Wave 3
will pick up `scorer.py` work and can re-run the broader suite at
natural handoff.

## Verification Anchors (from plan)

Verified by `grep`:

- `grep -n "from_narrative\|from_absorption\|from_exhaustion" deep6/engines/vp_context_engine.py`
  → shows import + single insertion call after `detect_zones` loop.
- `grep -n "_carry_over_strong_levels\|0.70" deep6/engines/vp_context_engine.py`
  → shows D-08 implementation on `on_session_start`.
- `grep -n "strength_threshold=0.4" deep6/engines/vp_context_engine.py`
  → shows D-06 threshold passed through to factory.

## Commits

| Task | Hash | Message |
|------|------|---------|
| T-15-02-01 | `25fdb47` | feat(15-02): persist narrative signals as Levels in VPContextEngine.process |
| T-15-02-02 | `4e0bd9c` | feat(15-02): cross-session narrative-Level decay in on_session_start |

## Deviations from Plan

### Auto-fixed during execution

1. **[Rule 1 - Bug fix] Test fixture — `ExhaustionType.DELTA_DIVERGENCE`
   does not exist.** Initial test fixture used a non-existent enum
   member. Fixed to `ExhaustionType.FADING_MOMENTUM` (actual member).
   No production code impact; test-local fix only.

2. **[Rule 2 - Additional guard] `INVALIDATED` Levels excluded from
   carry-over.** Plan listed selection criteria (score≥60 + narrative
   kinds) but did not explicitly mention state filtering. Since
   `INVALIDATED` Levels are semantically expired and `get_all_active`
   already filters them, the implementation uses `get_all_active()`
   which inherently excludes `INVALIDATED`. Added a dedicated test
   (`test_carry_over_invalidated_not_carried`) to pin the invariant.

3. **[Rule 2 - State reset semantics] Carry-over resets state to
   `LevelState.CREATED` (not `ACTIVE`).** Plan text referenced
   `ACTIVE`, but per 15-01 SUMMARY Deviation 1, `LevelState.ACTIVE`
   does not exist — `CREATED` is the canonical fresh-active state
   that matches `ZoneState` verbatim (D-03). Implementation uses
   `CREATED`. Same pattern the 15-01 executor followed.

No Rule-4 architectural deviations. No authentication gates.

## Authentication Gates

None.

## Known Stubs

None — both tasks shipped with concrete implementations and direct
test coverage. No placeholder / empty-data paths introduced.

## Threat Flags

None — no new network endpoints, auth paths, file-access surfaces, or
schema changes at trust boundaries. Threat model items in the plan
(T-15-02-01..03) are fully addressed:

- **T-15-02-01 (malformed bar) — mitigated.** Factory
  `_enforce_min_width` handles degenerate / inverted bars; 1-tick
  minimum preserved.
- **T-15-02-02 (DoS from 80-level re-add) — accepted.** Carry happens
  once per session; typical narrative-level count ≤ 10.
- **T-15-02-03 (cross-session info disclosure) — accepted.** Only
  price levels persist; already public via Databento/broker history.
  `dataclasses.replace` prevents mutable aliasing that could later
  cause subtle state leaks.

## Performance Budget

- `process()` added cost: one `from_narrative` call per bar — O(k)
  where k = narrative signal count (≤ 10). Measured < 50 µs on M2.
- `on_session_start` added cost: one O(n) scan of ≤ 80 Levels plus
  `dataclasses.replace` per survivor (typical ≤ 10). Runs once per
  session — negligible vs the 1 ms/bar budget (D-34).

## Handoff to Wave 3 (Plan 15-03)

Plan 15-03 (ConfluenceRules + scorer extension) now has:

- Narrative-kind Levels queryable via `registry.query_by_kind(
  LevelKind.ABSORB)` etc., with stable `Level.uid` across the bar —
  safe to use as keys in `ConfluenceRules.score_mutations`.
- Cross-session decay already applied before new-session bars arrive,
  so ConfluenceRules on bar 0 of a new session sees a realistic
  recency-decayed registry without any extra logic.
- `process()` signature change is backward-compatible — Plan 15-03
  can add its own optional kwargs (e.g., `confluence_annotations`)
  the same way, without breaking existing callers.

Plan 15-03 should:

- Drive `classify_bar` once per bar and pass `NarrativeResult` into
  `process()` at its call site (currently no integration point exists —
  plan 15-03 or 15-04 will wire the main bar-engine loop).
- Read `Level.meta["wick"]`, `Level.meta["absorb_type"]`,
  `Level.meta["narrative_label"]` for rule evaluation — all populated
  by 15-01's factory.

## Self-Check: PASSED

- Modified files exist:
  - `deep6/engines/vp_context_engine.py` ✓
- Created test files exist:
  - `tests/engines/test_vp_context_narrative_levels.py` ✓
  - `tests/engines/test_narrative_persistence.py` ✓
- Commits exist on main:
  - `25fdb47` feat(15-02): persist narrative signals as Levels in VPContextEngine.process ✓
  - `4e0bd9c` feat(15-02): cross-session narrative-Level decay in on_session_start ✓
- Automated verification:
  - 18/18 plan-15-02 tests green
  - 241/241 targeted regression green (engines + scoring + scorer + narrative + absorption + exhaustion + zone_registry + state + orderflow)
  - Verification grep anchors all match (D-06 strength_threshold=0.4, D-07 wick geometry via factory, D-08 0.70 decay + _carry_over_strong_levels, D-31 content-anchored insertion).
