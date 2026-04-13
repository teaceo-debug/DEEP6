---
phase: 04-dom-depth-signal-engines-e2-e3-e4-e5
plan: "01"
subsystem: signal-engines
tags: [trapped-traders, volume-patterns, footprint, tdd]
completed: "2026-04-13"
duration_minutes: 25

dependency_graph:
  requires:
    - deep6/state/footprint.py
    - deep6/engines/signal_config.py
  provides:
    - TrapEngine (TRAP-02..05)
    - VolPatternEngine (VOLP-01..06)
    - TrapConfig, VolPatternConfig frozen dataclasses
  affects:
    - deep6/scoring/scorer.py (Phase 7 integration)
    - deep6/engines/narrative.py (downstream consumers)

tech_stack:
  added:
    - numpy.polyfit for CVD slope calculation (TRAP-05)
  patterns:
    - Stateless engine pattern (all inputs passed as arguments)
    - TDD red-green flow per task
    - Frozen config dataclasses in signal_config.py

key_files:
  created:
    - deep6/engines/trap.py
    - deep6/engines/vol_patterns.py
    - tests/test_trap_engine.py
    - tests/test_vol_pattern_engine.py
  modified:
    - deep6/engines/signal_config.py

decisions:
  - TrapEngine is stateless: all state (cvd_history, vol_ema, prior_bar) passed
    in from caller; no instance-level mutable state
  - VolPatternEngine is stateless: bar_history and poc_history passed in as lists
    copied from caller-owned deques
  - TRAP-01 (INVERSE_TRAP) deliberately excluded from TrapEngine; it lives in
    imbalance.py as ImbalanceType.INVERSE_TRAP — docstring cross-references this
  - HVR wick computation uses top/bottom quarter of bar range as the "wick zone"
    rather than strict open/close body — simpler and more robust to doji bars
  - POC wave uses strict monotonicity (all diffs same sign) rather than just
    first-last comparison — prevents false fires from choppy POC
  - VolPatternConfig added to signal_config.py in same commit as TrapConfig
    (task 1) since the plan called for both configs before vol_patterns.py existed

metrics:
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
  tests_added: 54
  tests_total_after: 85
---

# Phase 04 Plan 01: TrapEngine + VolPatternEngine Summary

**One-liner:** TrapEngine (4 trapped-trader variants TRAP-02..05) and VolPatternEngine (6 volume-structure variants VOLP-01..06), both stateless with frozen config dataclasses, tested via TDD.

## What Was Built

### Task 1: TrapEngine (TRAP-02..05)

`deep6/engines/trap.py` — 4 trapped-trader signal variants operating on FootprintBar data:

| Variant | Requirement | Detection Logic |
|---------|-------------|-----------------|
| DELTA_TRAP | TRAP-02 | Prior bar |delta/vol| >= 0.25, current bar price + delta both reverse |
| FALSE_BREAKOUT_TRAP | TRAP-03 | Bar breaks prior extreme, closes back inside on elevated volume (>=1.8x ema) |
| HIGH_VOL_REJECTION_TRAP | TRAP-04 | High volume bar (>=2.5x ema) with wick fraction >= 35% of total vol |
| CVD_TRAP | TRAP-05 | CVD linear slope reverses: numpy polyfit over 8-bar window, current delta opposes slope |

`TrapConfig` added to `signal_config.py` — 6 frozen fields, all with defaults.

### Task 2: VolPatternEngine (VOLP-01..06)

`deep6/engines/vol_patterns.py` — 6 volume structure signal variants:

| Variant | Requirement | Detection Logic |
|---------|-------------|-----------------|
| SEQUENCING | VOLP-01 | 3+ bars each total_vol >= prior * 1.15 |
| BUBBLE | VOLP-02 | Single level vol > 4x avg_level_vol; fires at bubble price |
| SURGE | VOLP-03 | Bar vol > 3x vol_ema; direction from delta if |delta/vol| > 15% |
| POC_MOMENTUM_WAVE | VOLP-04 | POC strictly monotone for 3+ bars in poc_history |
| DELTA_VELOCITY_SPIKE | VOLP-05 | |current_delta - prior_delta| > vol_ema * 0.6 |
| BIG_DELTA_PER_LEVEL | VOLP-06 | Single level |net_delta| > 80 contracts |

`VolPatternConfig` added to `signal_config.py` — 8 frozen fields, all with defaults.

## Security / Threat Model Compliance

| Threat | Mitigation Applied |
|--------|-------------------|
| T-04-01: cvd_history mutation | numpy.polyfit receives a list slice → copy; original never touched |
| T-04-02: empty levels dict | `if bar.total_vol == 0 or not bar.levels: return []` at top of process() |
| T-04-03: division by zero | All divisions guarded: total_vol > 0 checked before any ratio computation |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] HVR test data produced insufficient wick fraction**
- **Found during:** Task 1 GREEN phase (first test run)
- **Issue:** Test used levels at 21000/21005/21010 but the upper quarter zone only caught the 21010 level (8 contracts), giving upper_frac = 0.028 vs threshold 0.35
- **Fix:** Updated test to place 120 contracts at 21005 (= upper zone boundary) out of 300 total → 40% fraction
- **Files modified:** tests/test_trap_engine.py
- **Commit:** 74940a1

**2. [Rule 1 - Bug] make_bar helper didn't accept bar_range kwarg**
- **Found during:** Task 1 GREEN phase second test run
- **Issue:** test_does_not_fire_when_vol_too_low passed `bar_range=10.0` but make_bar() doesn't have that parameter
- **Fix:** Removed unused kwarg from test — bar_range computed from high-low in make_bar
- **Files modified:** tests/test_trap_engine.py
- **Commit:** 74940a1

**3. [Rule 2 - Missing Critical Functionality] VolPatternConfig added in Task 1 commit**
- **Found during:** Task 1 implementation — plan placed VolPatternConfig in signal_config.py as part of Task 2, but the config needed to exist before vol_patterns.py could be written
- **Fix:** Added both TrapConfig and VolPatternConfig to signal_config.py in the Task 1 commit
- **Files modified:** deep6/engines/signal_config.py
- **Commit:** 74940a1

## Commits

| Hash | Message |
|------|---------|
| d0be992 | test(04-01): add failing tests for TrapEngine TRAP-02..05 |
| 74940a1 | feat(04-01): TrapEngine — 4 trapped trader signal variants TRAP-02..05 |
| 2450505 | test(04-01): add failing tests for VolPatternEngine VOLP-01..06 |
| 5ae8a84 | feat(04-01): VolPatternEngine — 6 volume pattern signal variants VOLP-01..06 |

## Test Results

```
85 passed in 0.10s
```

- 23 TrapEngine tests (test_trap_engine.py)
- 31 VolPatternEngine tests (test_vol_pattern_engine.py)
- 31 pre-existing tests (all still passing)

## Known Stubs

None — both engines are fully functional with real detection logic.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. Pure Python signal computation over existing FootprintBar data.

## Self-Check: PASSED

All required files exist and all commits are present in git history:
- deep6/engines/trap.py — FOUND
- deep6/engines/vol_patterns.py — FOUND
- deep6/engines/signal_config.py — FOUND (TrapConfig + VolPatternConfig added)
- tests/test_trap_engine.py — FOUND (23 tests)
- tests/test_vol_pattern_engine.py — FOUND (31 tests)
- Commit 74940a1 (TrapEngine) — FOUND
- Commit 5ae8a84 (VolPatternEngine) — FOUND
