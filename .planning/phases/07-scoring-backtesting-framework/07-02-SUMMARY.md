---
phase: 07-scoring-backtesting-framework
plan: "02"
subsystem: backtesting/sweep
tags: [optuna, vectorbt, parameter-sweep, backtesting, signal-attribution]
dependency_graph:
  requires:
    - 07-01-PLAN.md  # ScorerConfig, AbsorptionConfig, DeltaConfig in signal_config.py
  provides:
    - scripts/sweep_thresholds.py  # Bayesian threshold sweep CLI
  affects:
    - deep6/scoring/scorer.py      # scored via run_backtest_with_configs
    - scripts/backtest_signals.py  # build_bars reused (D-06)
tech_stack:
  added:
    - optuna==4.8.0    # Bayesian TPE parameter sweep
    - vectorbt==0.28.5 # portfolio simulation (installed; numpy used for hot-path metrics)
  patterns:
    - Optuna TPESampler seed=42, direction=maximize
    - numpy portfolio metrics (Sharpe, win_rate, avg P&L) — no numba JIT cost
    - --dry-run synthetic bars for CI/import verification
key_files:
  created:
    - scripts/sweep_thresholds.py
  modified:
    - pyproject.toml
decisions:
  - "Use numpy for portfolio metrics in sweep — vectorbt is installed but numpy avoids numba JIT warm-up (~2s) on every trial invocation; vectorbt remains available for standalone analysis"
  - "Added --dry-run mode with 200 synthetic NQ-priced bars for import/syntax verification without Databento API key"
  - "ImbalanceConfig NOT injected into classify_bar (narrative.py does not accept imb_cfg kwarg); swept scorer + abs + exh + delta thresholds instead; TODO in code notes future wiring point"
  - "ExhaustionConfig added to sweep (exhaust_wick_min, fade_threshold) beyond plan spec — classify_bar accepts exh_config, so additional sweep coverage at zero cost"
metrics:
  duration: "~8 min"
  completed: "2026-04-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
  commits:
    - eb7cc4d: "chore(07-02): add vectorbt + optuna to optional-dependencies[dev]"
    - bee9da8: "feat(07-02): Optuna threshold sweep script with signal P&L attribution"
---

# Phase 7 Plan 02: Optuna Threshold Sweep Summary

**One-liner:** Bayesian TPE parameter sweep over ScorerConfig + AbsorptionConfig + ExhaustionConfig + DeltaConfig thresholds using Optuna, outputting ranked CSV by 3-bar P&L with per-category signal attribution.

## What Was Built

### Task 1 — Install vectorbt + optuna (`eb7cc4d`)
- Added `vectorbt>=0.26.0` and `optuna>=3.6.0` to `pyproject.toml` optional-dependencies[dev]
- Both install successfully on Python 3.12/macOS: vectorbt 0.28.5, optuna 4.8.0
- pyproject.toml comment documents installed versions

### Task 2 — `scripts/sweep_thresholds.py` (`bee9da8`)
- Full Optuna Bayesian sweep (TPE sampler, seed=42, direction=maximize) over 14 threshold parameters:
  - `ScorerConfig`: type_a_min, type_b_min, type_c_min, confluence_threshold, zone_high_min, zone_high_bonus, zone_mid_bonus
  - `AbsorptionConfig`: absorb_wick_min, absorb_delta_max, stop_vol_mult, evr_vol_mult
  - `ExhaustionConfig`: exhaust_wick_min, fade_threshold (bonus beyond plan spec)
  - `DeltaConfig`: tail_threshold, trap_delta_ratio
- Objective: total 3-bar P&L for TYPE_A + TYPE_B signals only (TEST-04)
- `run_backtest_with_configs()` mirrors `backtest_signals.run_backtest()` with injected configs (D-06)
- `compute_attribution()` produces per-category P&L breakdown: absorption, exhaustion, delta, auction, poc, imbalance, trapped, volume_profile (TEST-06)
- `compute_portfolio_metrics()` computes n_trades, total_pnl, win_rate, Sharpe, avg_pnl via numpy
- Ranked CSV output: all trials sorted by P&L descending
- `--dry-run` mode: 200 synthetic bars for CI/import verification without Databento key
- Security: DATABENTO_API_KEY from env/dotenv only, sys.exit(1) if missing (T-07-04)

## Usage

```bash
# Full sweep with Databento data
python scripts/sweep_thresholds.py \
    --start 2026-04-09 --end 2026-04-10 \
    --trials 100 --output sweep_results.csv

# Dry-run (no API key needed — synthetic bars)
python scripts/sweep_thresholds.py \
    --start 2026-04-09 --end 2026-04-10 \
    --trials 10 --dry-run
```

## Deviations from Plan

### Auto-additions (within scope)

**1. [Rule 2 - Missing functionality] Added ExhaustionConfig to sweep**
- `classify_bar` already accepts `exh_config`; plan only mentioned absorb/delta/imbalance sweep params
- Added `exhaust_wick_min` and `fade_threshold` to sweep at no cost — broader coverage
- Files modified: `scripts/sweep_thresholds.py`

**2. [Rule 2 - Missing functionality] Added `--dry-run` flag with synthetic bars**
- Plan verification required "Optuna study creation works with dry-run of 1 trial (using mock bars if Databento key unavailable)"
- Implemented as a proper `--dry-run` CLI flag with `_make_synthetic_bars(200)` for realistic engine exercise
- Files modified: `scripts/sweep_thresholds.py`

**3. [Rule 2 - Missing functionality] Added numpy portfolio metrics**
- Plan mentioned vectorbt for portfolio construction; vectorbt's `vbt.Portfolio` has ~2s numba JIT warm-up per call
- Used numpy directly for Sharpe/win_rate/avg_pnl — vectorbt available for standalone deep analysis
- Files modified: `scripts/sweep_thresholds.py`

### Known limitation

**ImbalanceConfig NOT swept via classify_bar** — `narrative.py:classify_bar()` does not accept `imb_cfg` parameter. `detect_imbalances()` is called with defaults. A TODO comment marks the injection point for when `classify_bar` is updated. ScorerConfig thresholds (which affect how imbalance signals are weighted) ARE swept, providing partial coverage.

## Known Stubs

None — all sweep parameters wire through to live signal engines.

## Threat Flags

None — sweep is a local offline optimization tool; no new network endpoints or auth paths introduced beyond the existing Databento API call pattern already present in `backtest_signals.py`.

## Self-Check: PASSED

- `scripts/sweep_thresholds.py` exists: FOUND
- `pyproject.toml` updated with vectorbt + optuna: FOUND (grep verified)
- Commit eb7cc4d: FOUND
- Commit bee9da8: FOUND
- Import verification: `from scripts.sweep_thresholds import make_objective, compute_attribution` — OK
- `--help` runs without error: PASSED
- Dry-run with 5 trials completes end-to-end: PASSED
- Signal P&L attribution per category printed: PASSED (absorption, delta, auction, poc, imbalance, trapped, volume_profile, exhaustion)
- DATABENTO_API_KEY from env only: VERIFIED (sys.exit(1) if missing)
