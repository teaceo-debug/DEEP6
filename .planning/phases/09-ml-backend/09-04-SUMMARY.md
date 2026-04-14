---
phase: 09-ml-backend
plan: "04"
subsystem: ml-backend
tags: [performance-tracking, ml-quality, api-routes, testing]
dependency_graph:
  requires: [09-01, 09-02, 09-03]
  provides: [performance-tracker, metrics-api, e7-live-weights, ml-test-suite]
  affects: [deep6/engines/vp_context_engine.py, deep6/api/app.py, deep6/ml/weight_loader.py]
tech_stack:
  added: []
  patterns:
    - "mtime-based caching on WeightLoader.read_current() (T-09-14 mitigate)"
    - "Pure numpy compute for PerformanceTracker (<5ms on 2000 rows)"
    - "TierMetrics.to_dict() replaces inf/nan with None for JSON safety"
key_files:
  created:
    - deep6/ml/performance_tracker.py
    - deep6/api/routes/metrics.py
    - tests/test_ml_backend.py
  modified:
    - deep6/engines/vp_context_engine.py
    - deep6/ml/weight_loader.py
    - deep6/api/store.py
    - deep6/api/schemas.py
    - deep6/api/app.py
decisions:
  - "E7MLQualityEngine computes quality as mean(signal weights) clamped to [0.5, 1.5]"
  - "mtime cache added to WeightLoader.read_current() to fulfill T-09-14 mitigate disposition"
  - "regime_label column added to trade_events (TEXT DEFAULT UNKNOWN) for D-23 per-regime metrics"
metrics:
  duration_minutes: 25
  tasks_completed: 2
  tasks_total: 2
  test_count: 42
  files_created: 3
  files_modified: 5
  completed_date: "2026-04-13"
---

# Phase 9 Plan 04: Performance Tracking, Metrics API, E7 Live Weights, Test Suite

**One-liner:** Rolling window P&L tracker (50/200/500 trades) + /metrics endpoints + E7MLQualityEngine consuming deployed weights via mtime-cached WeightLoader — 42 tests all pass.

## What Was Built

### PerformanceTracker (`deep6/ml/performance_tracker.py`)

Computes win_rate, profit_factor, Sharpe, avg_pnl, total_pnl per signal tier and HMM regime slice.

- **Input:** List of trade event dicts from `EventStore.fetch_trade_events()`
- **Output:** Flat list of `TierMetrics` (all tier × window × regime combinations)
- **Tiers:** TYPE_A, TYPE_B, TYPE_C
- **Windows:** 50, 200, 500 (configurable; defaults to [50, 200, 500] per D-22)
- **Regime slices:** ABSORPTION_FRIENDLY, TRENDING, CHAOTIC (per D-23)
- **Performance:** Pure numpy, <5ms on 2000 rows (T-09-15 accept)

#### TierMetrics fields

| Field | Type | Description |
|-------|------|-------------|
| tier | str | Signal tier label |
| n_trades | int | Trades in rolling window |
| win_rate | float | wins / n_trades |
| profit_factor | float | gross_profit / abs(gross_loss); inf if no losses |
| sharpe | float | mean(pnl) / std(pnl) * sqrt(252); 0 if std=0 |
| avg_pnl | float | Mean P&L per trade |
| total_pnl | float | Sum of P&L for window |
| regime | str or None | None = all regimes; regime name = sliced |
| window | int | Requested rolling window size |

`to_dict()` replaces `inf`/`nan` with `None` for JSON safety.

### Metrics API Routes (`deep6/api/routes/metrics.py`)

Two new endpoints registered at `/metrics`:

#### `GET /metrics/signals`

Returns per-tier performance metrics aggregated across all regimes.

```json
{
  "tiers": [
    {"tier": "TYPE_A", "window": 50, "n_trades": 30, "win_rate": 0.67,
     "profit_factor": 2.0, "sharpe": 1.4, "regime": null, ...},
    ...
  ],
  "generated_at": 1744574400.0
}
```

#### `GET /metrics/regimes`

Returns per-tier metrics sliced by HMM regime label.

```json
{
  "by_regime": {
    "ABSORPTION_FRIENDLY": [...],
    "TRENDING": [...],
    "CHAOTIC": [...]
  },
  "generated_at": 1744574400.0
}
```

Both endpoints read from `request.app.state.event_store` — no side effects.

### E7MLQualityEngine (`deep6/engines/vp_context_engine.py`)

Replaced the static 1.0 stub with a dynamic quality score driven by deployed weights.

#### Quality score calculation

```
quality = mean(deployed_weights.values())
quality = clamp(quality, 0.5, 1.5)
```

Optional regime adjustment: if `regime_detector` is provided and fitted, applies
`regime_adjustments[regime]["quality_multiplier"]` from the weight file if present.

#### Quality score range

| Condition | Result |
|-----------|--------|
| No weight_loader (stub mode) | 1.0 (neutral) |
| Weight file not deployed | 1.0 (neutral) |
| All weights at baseline (1.0) | 1.0 (neutral) |
| Low-confidence weights | 0.5 (minimum clamp) |
| High-confidence weights | 1.5 (maximum clamp) |

#### Constructor signature

```python
E7MLQualityEngine(
    weight_loader: WeightLoader | None = None,      # None = stub mode (backward compat)
    regime_detector: HMMRegimeDetector | None = None  # Optional regime adjustment
)
```

Existing `E6VPContextEngine` creates `E7MLQualityEngine()` with no args — continues to work (stub mode, returns 1.0).

### WeightLoader mtime cache (`deep6/ml/weight_loader.py`)

Added mtime-based caching to `read_current()` per T-09-14 (threat: mitigate disposition).

- Re-reads from disk only when `os.path.getmtime()` changes since last read
- Cache invalidated on `write_atomic()` and `rollback()`
- Hot path (file unchanged): O(1) — no syscall beyond `stat()`
- Cache miss (file updated): one `open()` + `json.load()`

### Schema updates

- `trade_events` table: added `regime_label TEXT NOT NULL DEFAULT 'UNKNOWN'`
- `TradeEventIn` schema: added `regime_label: str = "UNKNOWN"`
- `EventStore.insert_trade_event()`: persists `regime_label` field

### Test Suite (`tests/test_ml_backend.py`)

42 tests across 5 component groups. All pass. No external services required.

| Class | Tests | Coverage |
|-------|-------|---------|
| TestEventStore | 8 | CRUD, tier filter, OOS count, regime_label persistence |
| TestFeatureBuilder | 5 | Feature count (47), uniqueness, category flags, GEX one-hot, empty input |
| TestDeployGate | 7 | Token gate, WFE gate, OOS gate, weight cap, all-pass, before/after |
| TestWeightLoader | 6 | None-on-missing, atomic write, backup creation, rollback, no-backup, mtime cache |
| TestPerformanceTracker | 9 | TierMetrics list, empty input, win_rate, profit_factor inf, regime slices, rolling window, 3 windows, JSON safety, open trades excluded |
| TestE7MLQualityEngine | 7 | Stub mode, process() alias, no-file, range, clamp low, clamp high, mean calc |

## How to Wire HMMRegimeDetector into the Live Bar Loop

The `E7MLQualityEngine` accepts an optional `regime_detector` parameter. To activate per-regime quality adjustment in live bar processing:

```python
from deep6.ml.weight_loader import WeightLoader
from deep6.ml.hmm_regime import HMMRegimeDetector
from deep6.engines.vp_context_engine import E6VPContextEngine, E7MLQualityEngine

# Create components
loader = WeightLoader("./deep6_weights.json")
regime_detector = HMMRegimeDetector()

# Wire into E6 engine (replace the default E7 stub)
e6_engine = E6VPContextEngine(gex_api_key=...)
e6_engine._ml_engine = E7MLQualityEngine(
    weight_loader=loader,
    regime_detector=regime_detector
)

# Nightly retrain (schedule with asyncio or APScheduler)
await regime_detector.retrain(event_store)
```

The `regime_adjustments` dict in the weight file can carry per-regime `quality_multiplier` values:
```json
{
  "regime_adjustments": {
    "CHAOTIC": {"quality_multiplier": 0.7},
    "TRENDING": {"quality_multiplier": 1.1}
  }
}
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] WeightLoader mtime cache**
- **Found during:** Task 2
- **Issue:** T-09-14 threat register marks `mitigate` disposition for repeated disk I/O in E7 weight reads, but existing WeightLoader had no caching
- **Fix:** Added `_cached_mtime` / `_cached_data` fields and mtime-check logic to `read_current()`; cache invalidated on `write_atomic()` and `rollback()`
- **Files modified:** `deep6/ml/weight_loader.py`
- **Commit:** d86b055

**2. [Rule 3 - Blocking Issue] weight_loader.py appeared missing but existed**
- **Found during:** Task 2 investigation
- **Issue:** Plan referenced weight_loader.py as if it needed creation; file existed from Plan 03 with a complete implementation
- **Fix:** Used existing file, only added mtime cache enhancement
- **Impact:** No rework needed

## API Routes Summary

All 7 required routes registered and verified:

| Route | Method | Purpose |
|-------|--------|---------|
| `/events/signal` | POST | Ingest signal event from scorer |
| `/events/trade` | POST | Ingest trade event from PaperTrader |
| `/weights/current` | GET | Read currently deployed weights |
| `/weights/deploy` | POST | Deploy new weights (gated) |
| `/ml/sweep` | POST | Trigger Optuna sweep |
| `/metrics/signals` | GET | Per-tier rolling window metrics (all regimes) |
| `/metrics/regimes` | GET | Per-tier metrics sliced by HMM regime |

## Self-Check: PASSED

All created files found on disk. Both task commits verified in git log.

| Check | Result |
|-------|--------|
| deep6/ml/performance_tracker.py | FOUND |
| deep6/api/routes/metrics.py | FOUND |
| tests/test_ml_backend.py | FOUND |
| deep6/engines/vp_context_engine.py | FOUND |
| Commit b6963b8 (Task 1) | FOUND |
| Commit d86b055 (Task 2) | FOUND |
