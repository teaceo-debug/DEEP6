---
phase: 02-absorption-exhaustion-core
plan: 02
subsystem: signal-engines
tags: [absorption, va-extremes, confirmation, conviction-bonus, defense-window]
dependency_graph:
  requires: [02-01]
  provides: [AbsorptionSignal.at_va_extreme, AbsorptionConfirmation, NarrativeResult.confirmed_absorptions]
  affects: [deep6/engines/absorption.py, deep6/engines/signal_config.py, deep6/engines/narrative.py]
tech_stack:
  added: []
  patterns: [flag-on-dataclass, module-level-stateful-tracker, session-reset-guard]
key_files:
  created: []
  modified:
    - deep6/engines/absorption.py
    - deep6/engines/signal_config.py
    - deep6/engines/narrative.py
decisions:
  - "at_va_extreme flag set in detect_absorption (not narrative) so all 4 variants benefit uniformly"
  - "_absorption_label uses sig.at_va_extreme directly — consistent 2-tick threshold vs recomputing 5.0-point proximity"
  - "Confirmation tracker uses module-level list; reset_confirmations() required at session start (T-02-05)"
  - "confirmed_absorptions propagated on all 5 cascade return paths (ABSORPTION, EXHAUSTION, MOMENTUM, REJECTION, QUIET)"
  - "+2 score bonus intentionally deferred to scorer.py — confirmation is data, scoring is scorer's job"
metrics:
  duration_minutes: 20
  completed_date: "2026-04-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 3
---

# Phase 02 Plan 02: VA Extremes Conviction Bonus + Absorption Confirmation Summary

**One-liner:** AbsorptionSignal gains at_va_extreme flag with +0.15 strength bonus when within 2 ticks of VAH/VAL, plus a 3-bar defense window confirmation tracker that produces confirmed_absorptions events for scorer.py.

## What Was Built

### Task 1 — VA Extremes Conviction Bonus (ABS-07, D-05)

**signal_config.py** — 5 new fields added to `AbsorptionConfig`:
- `va_extreme_ticks: int = 2` — proximity threshold (2 ticks = 0.50 NQ points)
- `va_extreme_strength_bonus: float = 0.15` — additive strength boost
- `confirmation_window_bars: int = 3` — defense window (added here for config cohesion)
- `confirmation_score_bonus: float = 2.0` — scorer bonus when confirmed
- `confirmation_breach_ticks: int = 2` — max breach before defense fails

**absorption.py** — Three changes:
1. `AbsorptionSignal` gains `at_va_extreme: bool = False` field
2. `detect_absorption()` accepts `vah: float | None = None` and `val: float | None = None`
3. Post-detection loop applies VA extreme bonus uniformly across all 4 variants: sets `at_va_extreme=True`, boosts `strength` (capped at 1.0), appends `@VAH` or `@VAL` to `detail`

**narrative.py** — Two changes:
1. `detect_absorption()` call now passes `vah=vah, val=val` through
2. `_absorption_label()` rewritten to use `sig.at_va_extreme` flag directly (consistent 2-tick threshold) instead of recomputing 5.0-point proximity

### Task 2 — Absorption Confirmation Logic (ABS-06, D-06, D-07)

**narrative.py** — Four additions:
1. `AbsorptionConfirmation` dataclass: `signal`, `bar_fired`, `zone_price`, `direction`, `confirmed=False`, `expired=False`
2. Module-level `_pending_confirmations: list[AbsorptionConfirmation] = []`
3. `reset_confirmations()` function — call at session start to prevent cross-session leakage (T-02-05)
4. `NarrativeResult` gains `confirmed_absorptions: list[AbsorptionConfirmation] = field(default_factory=list)`

**classify_bar() confirmation logic** (runs every bar):
- Registers each new absorption signal as a pending `AbsorptionConfirmation`
- Evaluates all non-expired, non-confirmed pending trackers:
  - Expiry: `bar_index - bar_fired > confirmation_window_bars` → `expired=True`
  - Skip: `bar_index == bar_fired` (signal bar itself)
  - Defense: bullish → `bar.low >= zone_price - breach_points`; bearish → `bar.high <= zone_price + breach_points`
  - Delta: bullish → `bar.bar_delta > 0`; bearish → `bar.bar_delta < 0`
  - Both hold → `confirmed=True`, added to `newly_confirmed`
- All 5 cascade return paths (ABSORPTION, EXHAUSTION, MOMENTUM, REJECTION, QUIET) propagate `confirmed_absorptions=newly_confirmed`

**Scorer integration note:** `scorer.py` should read `result.confirmed_absorptions` and add `AbsorptionConfig.confirmation_score_bonus` (+2.0) to zone score for each entry. The +2 bonus is data, not applied here.

## Verification Results

All 5 plan-specified checks passed:
- `AbsorptionSignal.at_va_extreme` field exists, default=False
- `detect_absorption(vah=21010.0, val=21000.25)` → 2 VA extreme signals with `@VAL` in detail
- `AbsorptionConfirmation` dataclass has all 6 required fields
- `NarrativeResult.confirmed_absorptions` field exists
- `AbsorptionConfig` has all 5 required new fields with correct defaults

End-to-end confirmation test:
- Bar 0: 4 absorption signals fire → 4 pending confirmations registered
- Bar 1: defense + positive delta → 3 confirmations upgrade to confirmed=True
- Bar 4: 1 remaining unconfirmed tracker expires (bar_index 4 > bar_fired 0 + window 3)

## Commits

| Hash | Description |
|------|-------------|
| f70fcde | feat(02-02): VA extremes conviction bonus on AbsorptionSignal (ABS-07, D-05) |
| b20f2b2 | feat(02-02): absorption confirmation tracker with 3-bar defense window (ABS-06, D-06, D-07) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. `confirmation_score_bonus` (+2.0) is intentionally deferred to `scorer.py` — this is documented in code comments, not a missing stub. The data carrier (`confirmed_absorptions`) is fully wired.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. T-02-05 (cross-session state leakage via `_pending_confirmations`) is mitigated by `reset_confirmations()`.

## Self-Check: PASSED

Files confirmed present:
- deep6/engines/absorption.py: modified (FOUND)
- deep6/engines/signal_config.py: modified (FOUND)
- deep6/engines/narrative.py: modified (FOUND)

Commits confirmed:
- f70fcde: FOUND
- b20f2b2: FOUND
