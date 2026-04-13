---
phase: 07-scoring-backtesting-framework
plan: "03"
subsystem: backtesting
tags: [walk-forward, wfe-gate, purged-splits, determinism, optuna]
dependency_graph:
  requires: [07-02-PLAN.md]
  provides: [walk-forward validation, WFE gate, best_params.json schema]
  affects: [Phase 8 execution — best_params.json read only with operator approval]
tech_stack:
  added: []
  patterns: [purged walk-forward cross-validation, WFE gating, Optuna per-fold optimization]
key_files:
  created:
    - scripts/walk_forward.py
    - tests/test_walk_forward.py
  modified: []
decisions:
  - split_folds uses walk-forward (not k-fold) to preserve temporal ordering — OOS windows are non-overlapping slices at end of each sub-period
  - ExhaustionConfig used as 4th param to run_backtest_with_configs (plan interface showed ImbalanceConfig but actual sweep_thresholds.py uses ExhaustionConfig — aligned to actual code)
  - 9 tests created (vs 8 specified) — added test_compute_wfe_zero_is_exact_zero for edge case coverage
  - best_params.json written only when WFE gate passes (T-07-07 mitigated)
metrics:
  duration: ~12 min
  completed: 2026-04-13
  tasks_completed: 2
  tasks_total: 3
  files_created: 2
  checkpoint_status: pending-human-verify
---

# Phase 7 Plan 03: Walk-Forward Validation Summary

**One-liner:** Purged walk-forward validator with WFE >= 70% gate, per-fold Optuna optimization, TEST-07 determinism check, and 9-test suite.

## Status: CHECKPOINT PENDING

Tasks 1 and 2 are complete and committed. Task 3 is a `checkpoint:human-verify` — awaiting human review of test suite and WFE gate logic before best_params.json is treated as authoritative.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | walk_forward.py with purged folds, WFE gate, TEST-07 | e17965a | scripts/walk_forward.py |
| 2 | Unit tests: fold splitting, purge logic, WFE gate | 36529b6 | tests/test_walk_forward.py |

## What Was Built

### scripts/walk_forward.py

Walk-forward validation framework for TEST-05 (WFE > 70% gate) and TEST-07 (determinism):

- **split_folds(bars, n_folds=5, oos_frac=0.20, purge_bars=10)** — Splits bars into non-overlapping (train, OOS) pairs with a purge gap between IS end and OOS start. Purge gap prevents leakage from multi-bar lookback signals (D-10). Minimum 20-bar OOS window enforced.

- **compute_wfe(is_pnls, oos_pnls)** — `mean(OOS P&L) / mean(IS P&L)`. Returns 0.0 when IS mean <= 0 to avoid division by negative/zero.

- **wfe_gate(wfe, threshold=0.70)** — Returns True if WFE meets threshold. Gate fail: `sys.exit(1)` with "GATE FAILED: WFE=X.XX < 0.70".

- **run_fold(train, oos, n_trials=30, fold_idx)** — Optuna TPESampler(seed=42+fold_idx) optimizes 30 trials on IS, evaluates best params on OOS. Returns fold metrics including is_pnl, oos_pnl, best_params, oos_signals.

- **check_determinism(bars)** — TEST-07: Runs run_backtest_with_configs twice on same 100 bars with same default config. Asserts all pnl_3bar and tier values identical across both runs.

- **main()** — CLI with --start, --end, --folds (5), --trials (30), --output (best_params.json), --bar-seconds (60), --wfe-threshold (0.70). Prints fold breakdown table. Gate pass writes best_params.json with wfe + gate_status + fold_breakdown + params from best OOS fold.

### tests/test_walk_forward.py

9 unit tests, all passing, no Databento required:

| Test | What it checks |
|------|----------------|
| test_split_folds_count | 100 bars / n_folds=3 → 3 fold tuples |
| test_purge_gap | train[-1] + purge_bars < oos[0] for every fold |
| test_oos_non_overlapping | fold OOS end < next fold OOS start |
| test_compute_wfe_normal | mean([75,60,70])/mean([100,80,90]) ≈ 0.796 |
| test_compute_wfe_zero_is | negative IS mean → WFE = 0.0 |
| test_compute_wfe_zero_is_exact_zero | zero IS mean → WFE = 0.0 |
| test_wfe_gate_pass | wfe_gate(0.70..1.50, 0.70) → True |
| test_wfe_gate_fail | wfe_gate(0.69..−0.5, 0.70) → False |
| test_fold_min_oos_size_insufficient | 15 bars → 0 folds |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ExhaustionConfig vs ImbalanceConfig in run_backtest_with_configs**
- **Found during:** Task 1 implementation
- **Issue:** Plan interfaces section showed `imb_cfg: ImbalanceConfig` as 4th param to `run_backtest_with_configs`. Actual sweep_thresholds.py uses `exh_cfg: ExhaustionConfig` (ExhaustionConfig, not ImbalanceConfig).
- **Fix:** Used ExhaustionConfig throughout walk_forward.py to match actual function signature. This prevents runtime TypeError on import/call.
- **Files modified:** scripts/walk_forward.py
- **Commit:** e17965a

**2. [Rule 2 - Enhancement] Extra WFE zero-IS edge case test**
- **Found during:** Task 2
- **Issue:** Plan specified 8 tests; zero IS mean (distinct from negative IS mean) is a separate edge case worth testing.
- **Fix:** Added `test_compute_wfe_zero_is_exact_zero` covering IS pnls=[0.0, 0.0].
- **Files modified:** tests/test_walk_forward.py
- **Commit:** 36529b6

## Known Stubs

None — walk_forward.py requires live Databento API key for main(). All unit tests use synthetic integer bar lists and pass without any API calls.

## Threat Flags

None — no new network endpoints or auth paths introduced beyond existing Databento client pattern.

## Self-Check: PASSED

- scripts/walk_forward.py: FOUND
- tests/test_walk_forward.py: FOUND
- Commit e17965a: FOUND (feat(07-03): walk-forward validation...)
- Commit 36529b6: FOUND (test(07-03): unit tests...)
- All 9 tests: PASSED
- All 18 Phase 7 tests (test_scorer.py + test_walk_forward.py): PASSED
