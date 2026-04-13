---
phase: 03-footprint-signal-engines-e1-e8-e9
plan: "03"
subsystem: tests
tags: [testing, imbalance, delta, auction, tdd]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [imbalance-tests, delta-tests, auction-tests]
  affects: [phase-04-signals]
tech_stack:
  added: []
  patterns: [make_bar-helper, temp-file-sqlite-for-aiosqlite-tests]
key_files:
  created:
    - tests/test_imbalance.py
    - tests/test_delta.py
    - tests/test_auction.py
  modified: []
decisions:
  - "Used temp file SQLite (not :memory:) for async persistence tests because aiosqlite opens a new connection per call — each :memory: connection gets a fresh empty DB"
  - "make_bar() helper pattern consistent across all three test files — dict of {price: (bid_vol, ask_vol)} for explicit level construction"
  - "Persistence round-trip test uses asyncio.run() with tempfile.NamedTemporaryFile to avoid pytest-asyncio loop conflicts"
metrics:
  duration_minutes: 15
  completed_date: "2026-04-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 0
---

# Phase 03 Plan 03: Comprehensive Signal Engine Test Suites Summary

**One-liner:** 76 deterministic tests covering all 25 imbalance/delta/auction signal variants with config overrides and async SQLite persistence round-trip.

## What Was Built

Three test files providing full variant coverage for the Phase 3 signal engines:

### tests/test_imbalance.py (23 tests)
Covers all 11 `ImbalanceType` variants (IMB-01..09 + CONSECUTIVE + REVERSAL):
- IMB-01 Single buy/sell (diagonal ask[P] vs bid[P-1] algorithm)
- IMB-02 Multiple (3+ imbalances in bar)
- IMB-03 Stacked T1/T2/T3 (3/5/7 consecutive levels)
- IMB-04 Reverse (both directions in same bar)
- IMB-05 Inverse trap bearish and bullish
- IMB-06 Oversized (ratio >= 10x)
- IMB-07 Consecutive across two bars
- IMB-08 Diagonal algorithm verification (explicit tick math)
- IMB-09 Reversal (bearish + bullish direction change)
- Config overrides: ratio_threshold, oversized_threshold, stacked_t1
- Edge cases: empty bar, zero-vol bar, single-level bar, strength capped at 1.0

### tests/test_delta.py (26 tests)
Covers all 13 `DeltaType` variants (DELT-01..11 + stateful sequences):
- DELT-01 Rise/Drop
- DELT-02 Tail (both positive and negative)
- DELT-03 Reversal (bearish + bullish hidden reversal)
- DELT-04 Divergence bearish + bullish (5-bar price/CVD mismatch)
- DELT-05 Flip (CVD crosses zero up/down)
- DELT-06 Trap bullish + bearish
- DELT-07 Sweep (volume acceleration across 10 levels)
- DELT-08 Slingshot bullish + bearish (3 quiet + explosive)
- DELT-09 At Min/At Max (session CVD extremes)
- DELT-10 CVD multi-bar divergence bearish + bullish (polyfit regression)
- DELT-11 Velocity (CVD acceleration threshold)
- Engine reset clears all histories and session extremes
- Config overrides: tail_threshold, velocity_accel_ratio

### tests/test_auction.py (27 tests)
Covers all 6 `AuctionType` variants (AUCT-01..05) + E9 FSM states:
- AUCT-01 Unfinished Business at high (+1) and low (-1)
- AUCT-02 Finished Auction at high (-1) and low (+1)
- AUCT-03 Poor High and Poor Low (low-volume extremes)
- AUCT-04 Volume Void (3+ thin levels) + insufficient-levels guard
- AUCT-05 Market Sweep up (+1) and down (-1) with 10-level bars
- ENG-09 FSM: EXPLORING_UP, BALANCED, EXPLORING_DOWN, BREAKOUT, balance_count reset
- Unfinished level tracking: get_unfinished_levels / load_unfinished_levels / clear_finished_level
- Async persistence round-trip: persist → restore → resolve with temp-file SQLite
- Config overrides: poor_extreme_vol_ratio, balance_count_threshold
- Edge cases: empty bar, zero-vol bar, single-level bar, engine reset

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed aiosqlite :memory: incompatibility in persistence tests**
- **Found during:** Task 3 (test_auction_persistence_roundtrip failure)
- **Issue:** `aiosqlite` opens a new OS-level SQLite connection per `async with` block. `:memory:` databases are per-connection — calling `initialize()` in one connection creates the schema, but `persist_auction_levels()` opens a new connection which gets a fresh empty DB with no tables. This causes `sqlite3.OperationalError: no such table: auction_levels`.
- **Fix:** Replaced `:memory:` with `tempfile.NamedTemporaryFile(suffix=".db")` so all connections share the same on-disk database file. File is cleaned up in a `finally` block.
- **Files modified:** `tests/test_auction.py`
- **Commit:** 67b3675

**2. [Rule 1 - Bug] Fixed bearish divergence test scenario**
- **Found during:** Task 2 (test_divergence_bearish failed on first run)
- **Issue:** Initial test set CVD=30.0 on the current bar, matching the prior max CVD exactly. The engine condition is `cvds[-1] < max(cvds[-div_lb:])` (strict less-than), so equal values don't trigger divergence.
- **Fix:** Changed the test to feed a prior bar with CVD=50 (the peak), then have the current bar at CVD=25 — clearly below the prior max, demonstrating bearish divergence correctly.
- **Files modified:** `tests/test_delta.py`
- **Commit:** 1a0d468

## Known Stubs

None — test-only plan, no production stubs introduced.

## Threat Flags

None — test-only plan, no new production surface introduced.

## Self-Check: PASSED

Files exist:
- tests/test_imbalance.py: FOUND
- tests/test_delta.py: FOUND
- tests/test_auction.py: FOUND

Commits exist:
- f923d94: FOUND (imbalance tests)
- 1a0d468: FOUND (delta tests)
- 67b3675: FOUND (auction tests)

All 76 tests pass: `python -m pytest tests/test_imbalance.py tests/test_delta.py tests/test_auction.py` — 76 passed in 0.09s
