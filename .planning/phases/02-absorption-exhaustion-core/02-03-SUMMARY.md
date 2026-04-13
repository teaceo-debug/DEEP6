---
phase: 02-absorption-exhaustion-core
plan: 03
subsystem: test-suite
tags: [absorption, exhaustion, narrative, tests, pytest, ABS-01..07, EXH-01..08]
dependency_graph:
  requires: [02-01, 02-02]
  provides: [test coverage for ABS-01..07 and EXH-01..08]
  affects:
    - tests/test_absorption.py
    - tests/test_exhaustion.py
    - tests/test_narrative.py
tech_stack:
  added: []
  patterns: [autouse-fixture-reset, synthetic-footprint-bar, make_bar-factory, delta-gate-testing]
key_files:
  created:
    - tests/test_absorption.py
    - tests/test_exhaustion.py
    - tests/test_narrative.py
  modified: []
decisions:
  - "make_bar fixture defined locally in each test file (not conftest) — avoids conftest coupling and keeps each file self-contained"
  - "autouse fixtures reset_cooldowns and reset_confirmations in both exhaustion and narrative test files — prevents cross-test state leakage (T-02-05)"
  - "fat_print test uses strictly > 2x average by making fat level 400 vs avg 175 — avoids boundary condition with == threshold"
  - "Worktree was behind main by 02-01 and 02-02 commits — rebased onto main before writing tests"
metrics:
  duration_minutes: 22
  completed_date: "2026-04-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 0
---

# Phase 02 Plan 03: Comprehensive Test Suite Summary

**One-liner:** 67 pytest tests across 3 files prove every ABS and EXH requirement via synthetic FootprintBar construction, covering all 4 absorption variants, all 6 exhaustion variants, the delta trajectory gate, cooldown logic, narrative cascade priority, VA extremes bonus, and absorption confirmation tracking.

## What Was Built

### Task 1 — Absorption Test Suite (ABS-01..07) — `tests/test_absorption.py`

**20 tests** covering:

- **CLASSIC (ABS-01):** `test_classic_absorption_fires` (lower wick balanced → bullish +1), `test_classic_absorption_rejects_unbalanced` (delta_ratio > 0.12 → rejected), `test_classic_absorption_upper_wick_bearish` (upper wick balanced → bearish -1)
- **PASSIVE (ABS-02):** `test_passive_absorption_fires_bullish` (65% vol at bottom, close above zone → fires), `test_passive_absorption_rejects_close_in_zone` (close inside zone → rejected)
- **STOPPING_VOLUME (ABS-03):** `test_stopping_volume_fires_bullish` (POC in lower wick + vol>2x → fires), `test_stopping_volume_rejects_low_volume` (vol ≤ 2x → rejected)
- **EFFORT_VS_RESULT (ABS-04):** `test_effort_vs_result_fires` (vol>1.5x + range<30% ATR → fires), `test_effort_vs_result_rejects_wide_range` (wide range → rejected)
- **VA Extremes (ABS-07):** `test_va_extreme_bonus_at_val` (@VAL in detail, at_va_extreme=True), `test_va_extreme_bonus_at_vah` (@VAH in detail), `test_va_extreme_no_bonus_far_from_va` (far → False), `test_va_extreme_strength_is_boosted` (strength boosted vs no-VA baseline)
- **Config (D-02):** `test_config_defaults_match_original` (all 11 fields verified), `test_custom_config_respected` (strict wick_min reduces signals), `test_none_config_uses_defaults`
- **Structure:** `test_empty_bar_returns_empty`, `test_zero_range_bar_returns_empty`, `test_absorption_signal_has_required_fields` (at_va_extreme field present), `test_multiple_variants_can_fire_simultaneously`

### Task 2 — Exhaustion Test Suite (EXH-01..08) — `tests/test_exhaustion.py`

**25 tests** covering:

- **ZERO_PRINT (EXH-01):** Fires on 0-volume level inside body; exempt from delta gate (confirms gate bypass)
- **EXHAUSTION_PRINT (EXH-02):** Fires at high (direction=-1) with heavy ask vol; fires at low (direction=+1) with heavy bid vol
- **THIN_PRINT (EXH-03):** Fires with 3+ levels < 5% max_vol inside body; direction follows bar direction
- **FAT_PRINT (EXH-04):** Fires when level > 2x avg (400 vs avg 175); uniform volume rejects
- **FADING_MOMENTUM (EXH-05):** Bullish bar + negative delta → direction=-1; bearish + positive delta → direction=+1
- **BID_ASK_FADE (EXH-06):** Fires when curr_ask < 60% of prior_ask; no-fire when at 80%
- **Delta Gate (EXH-07):** Blocks confirming delta; passes opposing delta; disabled gate allows all; small delta (<10%) = noise passthrough; doji always passes
- **Cooldown (EXH-08):** Suppresses bars 1-4 after bar 0 fire; allows at bar 5 (= cooldown_bars); cross-type (FAT fires during ZERO_PRINT cooldown); reset clears
- **Config defaults:** All 7 ExhaustionConfig fields verified

### Task 3 — Narrative Test Suite — `tests/test_narrative.py`

**22 tests** covering:

- **Cascade priority (ABS-05):** ABSORPTION over EXHAUSTION; QUIET on empty bar; NarrativeType IntEnum order verified (1 < 2 < 3 < 4 < 5)
- **Labels (D-10):** "ABSORBED" present; "@VAL" when at_va_extreme; "LOSING STEAM" for exhaustion; "DON'T CHASE" when extended past VAH; "JOIN" when not extended; "QUIET" label
- **All signals available:** absorption/exhaustion/imbalances lists populated regardless of cascade winner; all_signals_count = sum of all three lists
- **Confirmation creation (ABS-06):** `_pending_confirmations` is non-empty after absorption bar
- **Confirmation defense:** Bar 1 with price holding + positive delta → confirmed_absorptions populated
- **Confirmation expiry:** Bar 4 (> window=3) without defense → expired, no confirmed_absorptions
- **Same-bar skip:** Bar where absorption fires has confirmed_absorptions = [] (skip guard)
- **reset_confirmations():** Clears all pending trackers
- **NarrativeResult structure:** All required fields present and correct types

## Verification Results

```
tests/test_absorption.py — 20 passed
tests/test_exhaustion.py — 25 passed
tests/test_narrative.py  — 22 passed
TOTAL: 67 passed in 0.03s
```

## Commits

| Hash | Description |
|------|-------------|
| fa2e372 | test(02-03): absorption test suite — 4 variants + ABS-05/06/07 (20 tests) |
| b984b70 | test(02-03): exhaustion test suite — 6 variants + EXH-07 gate + EXH-08 cooldown (25 tests) |
| 766fe97 | test(02-03): narrative cascade test suite — cascade, labels, confirmation (22 tests) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Worktree missing 02-01 and 02-02 engine changes**
- **Found during:** Task 1 (initial test run — ModuleNotFoundError: No module named 'deep6.engines.signal_config')
- **Issue:** Worktree was branched at `82ef408` (pre-02-01), missing `signal_config.py`, updated `absorption.py`, `exhaustion.py`, and `narrative.py`
- **Fix:** `git stash -u && git rebase main` — rebased worktree onto `0b27605` (latest main with all 02-01 and 02-02 changes)
- **Files modified:** No source files changed — rebase brought worktree up to date

**2. [Rule 1 - Bug] FAT_PRINT test used boundary-equal volume (300 == 300, not > 300)**
- **Found during:** Task 2 first test run
- **Issue:** Fat level vol = 300, avg*2 = 300. Check is `vol > avg * fat_mult` (strictly greater). Equal case rejected.
- **Fix:** Changed fat level to 400 vol (avg = 175, threshold = 350, 400 > 350 ✓)
- **Files modified:** tests/test_exhaustion.py

## Known Stubs

None. All tests exercise production engine code. No placeholder assertions or skip-by-default test bodies.

## Threat Flags

None — test files only; no new network endpoints, auth paths, file access patterns, or schema changes.

## Self-Check: PASSED

Files confirmed present:
- tests/test_absorption.py: FOUND
- tests/test_exhaustion.py: FOUND
- tests/test_narrative.py: FOUND

Commits confirmed:
- fa2e372: absorption suite (20 tests)
- b984b70: exhaustion suite (25 tests)
- 766fe97: narrative suite (22 tests)
