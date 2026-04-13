---
phase: 04-dom-depth-signal-engines-e2-e3-e4-e5
plan: "02"
subsystem: dom-engines
tags: [dom, imbalance, spoof-detection, wasserstein, signal-engine]
dependency_graph:
  requires: [deep6/state/dom.py, deep6/engines/signal_config.py]
  provides: [deep6/engines/trespass.py, deep6/engines/counter_spoof.py]
  affects: [scorer.py, future E4/E5 engines that import TrespassResult]
tech_stack:
  added: [scipy.stats.wasserstein_distance]
  patterns: [pre-allocated weight array (D-03), deque rolling window, frozen config dataclasses]
key_files:
  created:
    - deep6/engines/trespass.py
    - deep6/engines/counter_spoof.py
    - tests/test_trespass_engine.py
    - tests/test_counter_spoof_engine.py
  modified:
    - deep6/engines/signal_config.py
decisions:
  - "Weight array [1/(i+1)] pre-computed at TrespassEngine init — never reallocated (D-03)"
  - "Bull/bear thresholds are heuristic (ratio>1.2/ratio<0.8) — logistic regression deferred to Phase 7 (D-02)"
  - "CounterSpoofEngine uses integer level indices as positions for W1 (not raw prices) — avoids scale sensitivity"
  - "E3 is alert-only — SpoofAlert never feeds into trade signal pipeline (D-07)"
  - "T-04-07 mitigation: _level_timestamps pruned by staleness (5 snapshots) + hard cap at LEVELS=40"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-13T22:00:56Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
  tests_added: 31
  tests_total: 332
---

# Phase 04 Plan 02: E2 TrespassEngine + E3 CounterSpoofEngine Summary

**One-liner:** Weighted DOM queue imbalance (E2) and Wasserstein-1 spoof-cancel detector (E3) operating on periodic DOMState snapshots via pre-allocated weight arrays and deque rolling windows.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | TrespassEngine failing tests | 2cd5303 | tests/test_trespass_engine.py |
| 1 GREEN | TrespassEngine implementation | f7676a8 | deep6/engines/trespass.py, signal_config.py |
| 2 RED | CounterSpoofEngine failing tests | 1f38bfd | tests/test_counter_spoof_engine.py |
| 2 GREEN | CounterSpoofEngine implementation | 90af6c9 | deep6/engines/counter_spoof.py |

## What Was Built

### E2 TrespassEngine (ENG-02)
`deep6/engines/trespass.py` — Multi-level weighted DOM queue imbalance engine.

- `TrespassEngine.__init__` pre-computes `_weights = [1/(i+1) for i in range(40)]` once at init.
- `process(snapshot)` computes `weighted_bid / weighted_ask` over `trespass_depth` (default 10) levels.
- Direction thresholds: `ratio > 1.2 → +1 (bull)`, `ratio < 0.8 → -1 (bear)`, else `0`.
- Probability: logistic approximation `min(max((ratio-1.0)*0.5+0.5, 0), 1)`.
- `depth_gradient = (bid[0] - bid[depth-1]) / depth` — measures book thinning.
- `process(None)` returns `TrespassResult(imbalance_ratio=1.0, direction=0, probability=0.5, detail="DOM_UNAVAILABLE")` per D-13.
- All-zero DOM returns `detail="DOM_EMPTY"` neutral result.
- T-04-04: div-by-zero guard when ask side is fully empty.

### E3 CounterSpoofEngine (ENG-03)
`deep6/engines/counter_spoof.py` — Wasserstein-1 distribution monitor + cancel detector. Alert-only (D-07).

- `ingest_snapshot(bid_prices, bid_sizes, ask_prices, ask_sizes, timestamp)` — called from asyncio timer every 100ms (NOT from 1000/sec DOM callback).
- W1 distance computed between consecutive bid distributions using `scipy.stats.wasserstein_distance` with integer level indices as positions.
- `get_w1_anomaly()` returns latest W1 if `> mean + 3σ`, else `None`. Guards: `< w1_min_samples (5)` entries → `None`; `std < 1e-9` (T-04-06) → `None`.
- `get_spoof_alerts()` returns `list[SpoofAlert]` and clears buffer. SpoofAlert fires when a level had `> 50 contracts` and drops to `< 10` within `200ms` (D-06).
- `reset()` clears all internal state for session starts.
- T-04-07: `_level_timestamps` pruned after 5 snapshots of inactivity + hard cap at `LEVELS=40`.

### Config Additions to signal_config.py
- `TrespassConfig(frozen=True)`: 3 fields — `trespass_depth=10`, `bull_ratio_threshold=1.2`, `bear_ratio_threshold=0.8`.
- `CounterSpoofConfig(frozen=True)`: 6 fields — `spoof_history_len=20`, `spoof_large_order=50.0`, `spoof_cancel_threshold=10.0`, `spoof_cancel_window_ms=200.0`, `w1_anomaly_sigma=3.0`, `w1_min_samples=5`.

## Decisions Made

1. **Weight array pre-computed at init** — satisfies D-03 (< 0.1ms). No per-call allocation.
2. **Heuristic thresholds (D-02)** — logistic regression on (ratio, spread, depth_gradient) deferred to Phase 7 when historical tick data is available.
3. **W1 uses integer positions** — level indices 0..N-1 used as positions rather than raw prices. This makes W1 scale-independent and consistent across sessions with different price levels.
4. **alert-only pipeline separation** — `SpoofAlert` is not imported by scorer.py. E3 is wired separately as an informational flag to avoid polluting the signal pipeline with uncertain data.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Pre-built neutral result singletons**
- **Found during:** Task 1
- **Issue:** Returning `TrespassResult(...)` on every `process(None)` call allocates a new object each time. At 1000 calls/sec this creates GC pressure.
- **Fix:** Pre-built `_NEUTRAL_UNAVAILABLE` and `_NEUTRAL_EMPTY` singletons returned directly on None/empty-DOM paths.
- **Files modified:** `deep6/engines/trespass.py`
- **Commit:** f7676a8

**2. [Rule 2 - Missing critical functionality] W1 all-zeros distribution guard**
- **Found during:** Task 2
- **Issue:** T-04-05 threat — if both bid arrays are all-zeros, wasserstein_distance may produce NaN or unexpected results.
- **Fix:** Explicit zero-sum check before calling wasserstein_distance; returns W1=0 for empty DOM.
- **Files modified:** `deep6/engines/counter_spoof.py`
- **Commit:** 90af6c9

## Known Stubs

None — both engines are fully wired to DOMState.snapshot() interface and return meaningful results with synthetic DOM data.

## Threat Flags

None — no new network endpoints, auth paths, or external data sources introduced. All data flows from existing DOMState internal to the process.

## Test Coverage

| File | Tests Added | Key Scenarios |
|------|-------------|---------------|
| tests/test_trespass_engine.py | 14 | neutral fallback, bull, bear, balanced, depth_gradient, config frozen |
| tests/test_counter_spoof_engine.py | 17 | empty state, identical snapshots, cancel alert, outside window, reset, T-04-05/06/07 |

332 total tests pass (0 failures, 0 errors).

## Self-Check: PASSED
