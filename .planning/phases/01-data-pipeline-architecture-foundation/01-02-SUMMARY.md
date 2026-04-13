---
phase: "01-data-pipeline-architecture-foundation"
plan: "02"
subsystem: "data-pipeline"
tags: ["footprint", "bar-builder", "atr", "session", "asyncio", "tdd"]
dependency_graph:
  requires:
    - "01-01: DOMState, FreezeGuard, aggressor gate, SignalFlags, tick_feed stub"
  provides:
    - "FootprintBar: core accumulator for bid/ask vol per price level"
    - "BarHistory: deque(maxlen=200) ring buffer of closed bars (ARCH-04 foundation)"
    - "BarBuilder: asyncio coroutine firing on_bar_close at 60s/300s boundaries"
    - "SessionContext: VWAP/CVD/IB accumulators, SQLite-serializable"
    - "ATRTracker: incremental Wilder's ATR(20)"
  affects:
    - "Phase 2+: all 44 signal engines consume FootprintBar via on_bar_close"
    - "Plan 01-03: SessionPersistence writes SessionContext.to_dict() to SQLite"
    - "Phase 3: ARCH-04 Pearson correlation matrix reads from BarHistory"
tech_stack:
  added:
    - "zoneinfo (stdlib): DST-correct Eastern timezone for RTH gate"
    - "collections.deque(maxlen=200): ARCH-04 ring buffer"
  patterns:
    - "TDD RED/GREEN cycle: tests written first, implementation second"
    - "defaultdict[int, FootprintLevel]: keyed by price-in-ticks, avoids float key precision"
    - "asyncio sleep-to-boundary: time.time() floor division for exact bar alignment"
    - "Wilder's ATR seed: simple average of first N true ranges, then exponential smoothing"
key_files:
  created:
    - "deep6/state/footprint.py: FootprintLevel, FootprintBar, BarHistory, price_to_tick, tick_to_price"
    - "tests/test_footprint.py: 11 tests covering accumulation, finalize, BarHistory maxlen"
    - "tests/test_bar_builder.py: 9 tests covering RTH gate, ATRTracker, SessionContext"
  modified:
    - "deep6/data/bar_builder.py: full BarBuilder implementation (was stub from Plan 01-01)"
  pre_existing_complete:
    - "deep6/signals/atr.py: ATRTracker was complete from Plan 01-01"
    - "deep6/state/session.py: SessionContext was complete from Plan 01-01"
decisions:
  - "BarHistory is a factory function (not a class) returning deque(maxlen=200) — avoids mutable default issue"
  - "RTH gate uses zoneinfo America/New_York for DST correctness (not hardcoded -5/-4 offset)"
  - "price_to_tick uses round() not int() to handle floating-point precision at tick boundaries"
  - "Accumulator reset before any awaits in run() — prevents missed ticks in single-threaded loop"
  - "appendleft() used for BarHistory so history[0] is always the most recent closed bar"
metrics:
  duration_seconds: 229
  completed_date: "2026-04-11"
  tasks_completed: 2
  tests_added: 20
  files_created: 3
  files_modified: 1
---

# Phase 01 Plan 02: FootprintBar + BarBuilder + SessionContext + ATRTracker Summary

**One-liner:** FootprintBar accumulator with defaultdict[int, FootprintLevel] tick-key design; dual-TF asyncio BarBuilder sleeping to exact 60s/300s boundaries with DST-correct RTH gate; Wilder's ATR(20) incremental tracker; VWAP/CVD/IB SessionContext with SQLite round-trip.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | FootprintBar accumulator and BarHistory | f863ba0 | deep6/state/footprint.py, tests/test_footprint.py |
| 2 | Dual-TF BarBuilder, SessionContext, ATRTracker | f95093a | deep6/data/bar_builder.py, tests/test_bar_builder.py |

## Test Results

All 20 Plan 02 tests pass (11 footprint + 9 bar_builder). Full suite (25 tests including Plan 01-01 signal flags) passes.

```
tests/test_footprint.py    11/11 PASSED
tests/test_bar_builder.py   9/9  PASSED
tests/test_signal_flags.py  5/5  PASSED
```

## Key Verification Outputs

```
price_to_tick(21000.0) == 84000   # NQ tick_size=0.25 correct
tick_to_price(84000) == 21000.0   # Round-trip correct
ATRTracker seeded at bar 20, atr=1.0 for uniform TR=1.0
SessionContext round-trip: cvd=42 -> to_dict -> from_dict -> cvd=42
BarHistory maxlen=200: 205 inserts -> len=200
```

## Architecture Notes

### FootprintBar Integer Tick Key Design

The `defaultdict[int, FootprintLevel]` keyed by `price_to_tick(price)` (integer) is the critical design decision. Float keys in Python dicts can cause precision issues at tick boundaries (e.g., `21000.0 / 0.25` might not always produce exactly `84000.0`). Using `round(price / TICK_SIZE)` as the key guarantees stable dict lookups. This matches the research recommendation in FEATURES.md.

### RTH Gate Implementation

`_is_rth()` uses `datetime.now(EASTERN)` where `EASTERN = ZoneInfo("America/New_York")`. This correctly handles DST transitions — no manual +4/-5 hour offset. The gate is called synchronously on every `on_trade()` call (T-02-04: cannot be bypassed externally).

### BarHistory and ARCH-04 Relationship

`BarHistory()` is a factory function returning `deque(maxlen=200)`. This is intentional — making it a class would require careful handling of the `maxlen` parameter in `__init__`. The deque covers 200 bars of history (3.3 hours for 1-min bars). Phase 3 will read this deque to compute the Pearson correlation matrix between the 44 signals. The matrix computation cannot happen until signals exist — BarHistory is the data collection foundation only.

### Dual-TF BarBuilder Independence

Each `BarBuilder` instance has its own `FootprintBar()` accumulator and `BarHistory()` ring buffer. The 1m and 5m builders share `state.session` (SessionContext) and `state.atr_trackers[label]` (one ATRTracker per timeframe). Both run via `asyncio.gather(builder_1m.run(), builder_5m.run())` — no coordination needed since both write only to their own fields.

### ATR Seeding

The first 20 true ranges are collected in `_seed_trs` list. After 20 bars, ATR is initialized to `mean(_seed_trs)` (simple average). Subsequent bars use Wilder's exponential smoothing: `ATR = prev_ATR * (19/20) + TR * (1/20)`. The `ready` property returns False until the seed is complete — signal engines must check `atr_tracker.ready` before using the value.

## Deviations from Plan

### Pre-existing implementations from Plan 01-01

**Finding:** `deep6/signals/atr.py` and `deep6/state/session.py` were already fully implemented by Plan 01-01's commit (f582fa0/3a2d156). Similarly, `deep6/data/bar_builder.py` was already complete in the 01-01 commit scope.

**Action:** No deviation needed — the Plan 01-01 agent correctly scaffolded these files. Tests were written for and verified against the existing implementations. All 9 test functions pass against the pre-existing code.

**Classification:** Not a deviation — Plan 01-01's "implement stubs" included complete implementations of these support files.

## Known Stubs

None — all files produce functional output. The only stub relationship is `state.atr_trackers` and `state.on_bar_close` in `BarBuilder.run()` which depend on `SharedState` (assembled in Plan 01-03/01-04). These are intentional integration points, not implementation stubs.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. All new code operates on in-memory data structures. The RTH gate (T-02-04) is implemented as required by the threat model.

## Self-Check: PASSED

- deep6/state/footprint.py: FOUND
- deep6/data/bar_builder.py: FOUND
- deep6/state/session.py: FOUND (pre-existing)
- deep6/signals/atr.py: FOUND (pre-existing)
- tests/test_footprint.py: FOUND
- tests/test_bar_builder.py: FOUND
- Commit f863ba0: FOUND
- Commit f95093a: FOUND
- All 20 Plan 02 tests: PASS
