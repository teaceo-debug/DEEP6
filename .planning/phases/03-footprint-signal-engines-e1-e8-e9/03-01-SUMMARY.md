---
phase: 03-footprint-signal-engines-e1-e8-e9
plan: "01"
subsystem: signal-engines
tags: [imbalance, delta, config, signal-config, footprint]
dependency_graph:
  requires: []
  provides: [ImbalanceConfig, DeltaConfig, IMB-02, IMB-07, IMB-09, DELT-03, DELT-07]
  affects: [deep6/engines/narrative.py, scripts/backtest_signals.py, deep6/engines/scoring]
tech_stack:
  added: []
  patterns: [frozen-dataclass-config, config-driven-thresholds]
key_files:
  created:
    - deep6/engines/signal_config.py
  modified:
    - deep6/engines/imbalance.py
    - deep6/engines/delta.py
decisions:
  - "ImbalanceConfig and DeltaConfig follow the AbsorptionConfig/ExhaustionConfig frozen dataclass pattern from Phase 2 (D-01)"
  - "Default values in config match original hardcoded kwargs exactly — no threshold changes until Phase 7 sweeps (D-02)"
  - "IMB-07 CONSECUTIVE uses a two-pass diagonal scan: scan prior bar, intersect with current bar imbalance ticks"
  - "IMB-09 REVERSAL uses 2x dominance ratio: prior dominant buy + current dominant sell (or vice versa)"
  - "DELT-03 REVERSAL is bar-level approximation: delta sign contradicts bar direction with min ratio gate"
  - "DELT-07 SWEEP detects volume acceleration through bar levels (second half > first half * ratio)"
  - "stacked_gap_tolerance raised to 2 (from hardcoded 2 in original) — now configurable"
metrics:
  duration: "~8 minutes"
  completed: "2026-04-13T17:57:00Z"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 3
---

# Phase 3 Plan 1: ImbalanceConfig + DeltaConfig + Missing Variants Summary

**One-liner:** Extracted all imbalance/delta thresholds into frozen config dataclasses and implemented IMB-02 Multiple, IMB-07 Consecutive, IMB-09 Reversal, DELT-03 Reversal approximation, and DELT-07 Sweep.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add ImbalanceConfig + DeltaConfig + missing variants | b788de3 | signal_config.py (created), imbalance.py, delta.py |

## What Was Built

### signal_config.py — New config dataclasses

**ImbalanceConfig** (frozen dataclass):
- `ratio_threshold` (3.0) — IMB-01 diagonal ratio
- `oversized_threshold` (10.0) — IMB-06 oversized promotion
- `stacked_t1/t2/t3` (3/5/7) — IMB-03 tier thresholds
- `multiple_min_count` (3) — IMB-02 minimum imbalances
- `consecutive_min_bars` (2) — IMB-07 cross-bar tracking
- `inverse_min_imbalances` (3) — IMB-05 trap threshold
- `stacked_gap_tolerance` (2) — configurable tick gap

**DeltaConfig** (frozen dataclass):
- `lookback` (20), `tail_threshold` (0.95), `divergence_lookback` (5)
- `trap_delta_ratio` (0.3), `slingshot_quiet_ratio` (0.1), `slingshot_explosive_ratio` (0.4)
- `slingshot_quiet_bars` (2), `cvd_divergence_min_bars` (10), `cvd_slope_divergence_factor` (0.3)
- `velocity_accel_ratio` (0.3), `sweep_min_levels` (5), `sweep_vol_increase_ratio` (1.5)
- `reversal_min_delta_ratio` (0.15)

### imbalance.py — Three new variants

**IMB-02 MULTIPLE:** After diagonal scan, if total buy_imb_ticks >= multiple_min_count, fires one MULTIPLE signal at median tick. Same for sell side.

**IMB-07 CONSECUTIVE:** Re-runs diagonal scan on prior_bar; intersects prior buy/sell imbalance tick sets with current bar's imbalance ticks. Each matching tick fires a CONSECUTIVE signal with strength=0.75.

**IMB-09 REVERSAL:** Counts buy/sell imbalances in prior bar; applies 2x dominance check (dominant = count >= 2 AND count > opposite * 2). Fires REVERSAL when dominant direction flips between prior and current bar.

### delta.py — Two new variants + config wiring

**DELT-03 REVERSAL (bar-level approximation):** Fires when bar direction (close vs open) contradicts delta sign AND |delta|/vol >= reversal_min_delta_ratio. Bearish hidden: bar closed up but delta negative. Bullish hidden: bar closed down but delta positive.

**DELT-07 SWEEP:** Fires when bar has >= sweep_min_levels price levels AND second-half volume >= first-half volume * sweep_vol_increase_ratio. Uses sorted tick levels split at midpoint.

All DeltaEngine hardcoded values replaced with `self.config.*` fields.

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria verified.

## Verification Results

```
Config classes OK
All variants and config wiring verified
```

- `python -c "from deep6.engines.signal_config import ImbalanceConfig, DeltaConfig"` — PASS
- `python -c "from deep6.engines.imbalance import detect_imbalances; from deep6.engines.delta import DeltaEngine"` — PASS
- `python scripts/backtest_signals.py --help` — PASS (no import errors)
- All 11 ImbalanceType enum members present — PASS
- All 13 DeltaType enum members present — PASS

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- `deep6/engines/signal_config.py` — FOUND (created)
- `deep6/engines/imbalance.py` — FOUND (modified)
- `deep6/engines/delta.py` — FOUND (modified)
- Commit b788de3 — FOUND
