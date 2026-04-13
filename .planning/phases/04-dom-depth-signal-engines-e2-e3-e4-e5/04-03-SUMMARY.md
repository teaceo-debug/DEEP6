---
phase: 04-dom-depth-signal-engines-e2-e3-e4-e5
plan: 03
subsystem: engines
tags: [iceberg, micro-probability, dom, naive-bayes, eeng-04, eng-05]
requirements: [ENG-04, ENG-05]

dependency_graph:
  requires:
    - deep6/state/dom.py         # DOMState.snapshot() tuple format
    - deep6/engines/trespass.py  # TrespassResult as MicroEngine input
  provides:
    - deep6/engines/iceberg.py   # IcebergEngine, IcebergSignal, IcebergType
    - deep6/engines/micro_prob.py # MicroEngine, MicroResult
    - deep6/engines/signal_config.py # IcebergConfig, MicroConfig, TrespassConfig added
  affects:
    - deep6/engines/signal_config.py  # Extended with IcebergConfig + MicroConfig

tech_stack:
  added: []
  patterns:
    - Naive Bayes with heuristic priors (no sklearn, pure float math)
    - Per-level deque-based depletion tracking with timestamp pruning
    - Peak-size tracking for refill comparison across state transitions
    - Tick-rounding (0.25) for all price-level dict lookups

key_files:
  created:
    - deep6/engines/iceberg.py
    - deep6/engines/micro_prob.py
    - deep6/engines/trespass.py
  modified:
    - deep6/engines/signal_config.py

decisions:
  - "Used _level_peak_sizes dict to track pre-depletion size, enabling refill comparison after prior_size is updated to the depleted value — without this, refill detection would always fail"
  - "Naive Bayes denominator guard (denom < 1e-9 → 0.5) per T-04-09 prevents div-by-zero when both P_bull and P_bear collapse to near-zero"
  - "TrespassConfig + CounterSpoofConfig added to signal_config.py as plan 02 dependencies (plan 02 TDD RED commit existed but implementation was absent)"

metrics:
  duration: "~25 minutes"
  completed: "2026-04-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 4 Plan 3: E4 IcebergEngine + E5 MicroEngine Summary

**One-liner:** Native iceberg detection (fill > DOM * 1.5) and synthetic iceberg detection (level refills within 250ms) combined with heuristic Naive Bayes micro probability from decorrelated E2/E4/imbalance features.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | E4 IcebergEngine — native + synthetic iceberg detection | ddc79f1 | iceberg.py, signal_config.py, trespass.py |
| 2 | E5 MicroEngine — Naive Bayes micro probability | 5e509b1 | micro_prob.py |

## What Was Built

### E4 IcebergEngine (`deep6/engines/iceberg.py`)

**IcebergType enum:** NATIVE, SYNTHETIC

**IcebergSignal dataclass:**
- `iceberg_type`, `price`, `size`, `refill_count`, `at_absorption_zone`, `conviction_bonus`, `direction`, `detail`
- `conviction_bonus = 3` when at absorption zone (D-10), `0` otherwise

**IcebergEngine:**
- `check_trade(price, size, aggressor_side, dom_snapshot, timestamp)` — NATIVE detection when `trade.size > dom_size * 1.5` (D-08)
- `update_dom(bid_prices, bid_sizes, ask_prices, ask_sizes, timestamp)` — SYNTHETIC detection via depletion/refill tracking (D-09)
- `mark_absorption_zone(price, radius_ticks=4)` — marks price ± 4 ticks as absorption zone
- `is_at_absorption_zone(price)` — checks if price is in marked zone
- `reset()` — clears all internal state for session boundary

**Internal state:**
- `_level_depletions: dict[float, deque]` — timestamps of depletion events per price level
- `_level_prior_sizes: dict[float, float]` — last observed size per level
- `_level_peak_sizes: dict[float, float]` — pre-depletion size for refill comparison
- `_refill_counts: dict[float, int]` — refill count per level

### E5 MicroEngine (`deep6/engines/micro_prob.py`)

**MicroResult dataclass:** `probability`, `direction`, `feature_count`, `detail`

**MicroEngine:**
- `process(trespass, iceberg_signals, imbalance_direction)` — stateless, re-entrant
- Three binary features: trespass direction (E2), iceberg presence (E4), imbalance direction
- Heuristic Naive Bayes: `bull_likelihood=0.65` per-feature update, normalized
- Returns `probability=0.5, direction=0, detail="DOM_UNAVAILABLE"` when all inputs are neutral (D-13)

### signal_config.py additions

- `IcebergConfig` (7 fields): native ratio, depletion thresholds, refill window, conviction bonus
- `MicroConfig` (3 fields): bull_likelihood, bull/bear thresholds
- `TrespassConfig` (3 fields): depth, bull_ratio, bear_ratio — added as plan 02 dependency
- `CounterSpoofConfig` (6 fields): sampling interval, Wasserstein params, cancel detection — added as plan 02 dependency

## Decisions Made

### Key architectural decision: `_level_peak_sizes`

The SYNTHETIC detection requires comparing a refilled level against the size it had *before* depletion. Without `_level_peak_sizes`, after `prior_size` updates to the depleted value (~2), the next refill check fails `>= iceberg_min_size(30)`. The fix is to record `peak_sizes[price] = prior_size` at the moment of depletion, then compare `current_size >= peak_sizes[price] * refill_ratio` on refill.

### Naive Bayes denominator guard (T-04-09)

Per threat model T-04-09: when both P_bull and P_bear collapse to near-zero (all features are active and contradictory), the denominator can underflow. Guard: `if denom < 1e-9: return 0.5`.

### Plan 02 dependency injection

Plan 02 had a TDD RED commit (`2cd5303`) adding failing tests for TrespassEngine, but the implementation (trespass.py, full signal_config.py) was absent from the worktree. Since plan 03's micro_prob.py imports `TrespassResult` from `trespass.py`, both files were created as part of this plan execution. TrespassConfig and CounterSpoofConfig were added to signal_config.py to satisfy plan 02's test expectations.

## Deviations from Plan

### Auto-added dependency (Rule 2 — Missing Critical Functionality)

**Found during:** Task 2 setup

**Issue:** `micro_prob.py` imports `TrespassResult` from `deep6.engines.trespass`. Plan 02 was not yet executed in this worktree (only the TDD RED test commit `2cd5303` existed). Without `trespass.py`, plan 03 would fail to import.

**Fix:** Created `deep6/engines/trespass.py` with `TrespassResult` and `TrespassEngine`. Also added `TrespassConfig` and `CounterSpoofConfig` to `signal_config.py` so plan 02's existing failing tests can be made green in the next execution.

**Files modified:** `deep6/engines/trespass.py`, `deep6/engines/signal_config.py`

**Commit:** ddc79f1

## Known Stubs

None. Both engines are fully wired with real logic. MicroEngine `feature_count` field tracks active features, `detail` provides computation trace.

## Threat Flags

None. No new network endpoints, auth paths, or external trust boundaries introduced. All processing is pure in-memory computation on DOM snapshot tuples.

## Self-Check: PASSED

Files confirmed present:
- `deep6/engines/iceberg.py` — FOUND
- `deep6/engines/micro_prob.py` — FOUND
- `deep6/engines/trespass.py` — FOUND
- `deep6/engines/signal_config.py` — FOUND

Commits confirmed:
- `ddc79f1` — FOUND (feat(04-03): E4 IcebergEngine)
- `5e509b1` — FOUND (feat(04-03): E5 MicroEngine)
