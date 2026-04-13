---
phase: 01-data-pipeline-architecture-foundation
plan: 04
subsystem: data-pipeline
status: checkpoint-pending
tags: [main-entrypoint, integration, validation, footprint-csv, loop-lag, human-verify]

dependency_graph:
  requires:
    - "01-01: SharedState.build(), connect_rithmic(), register_callbacks()"
    - "01-02: BarBuilder, FootprintBar, SessionContext"
    - "01-03: SessionPersistence, FreezeGuard, SharedState"
  provides:
    - "deep6/__main__.py: complete asyncio entry point wiring all Phase 1 components"
    - "scripts/validate_footprint.py: FootprintBar CSV export for TradingView comparison"
    - "scripts/measure_loop_lag.py: event loop lag measurement under DOM callback load"
  affects:
    - "Phase 2+: __main__.py is the permanent production entry point"
    - "ARCH-04: BarHistory deque is populated on first live run; Phase 3 Pearson correlation reads it"

tech_stack:
  added: []
  patterns:
    - "asyncio.Runner(loop_factory=uvloop.new_event_loop) — Python 3.12 uvloop entry point (not deprecated uvloop.install())"
    - "asyncio.gather(*tasks) — concurrent BarBuilders + SessionManager in single event loop"
    - "asyncio.Event for barrier synchronization in validation script (wait for N bars)"

key_files:
  created:
    - scripts/validate_footprint.py
    - scripts/measure_loop_lag.py
  modified:
    - deep6/__main__.py

decisions:
  - "scripts/ directory reused existing NT8-era scripts path — validate_footprint.py and measure_loop_lag.py created there"
  - "validate_footprint.py captures bars via state._on_bar_close_fn hook (established in Plan 03) — no modifications to SharedState needed"
  - "measure_loop_lag.py adds P95 stat and WARN/FAIL distinction beyond plan template — more actionable reporting"
  - "ARCH-04 satisfied by BarHistory deque infrastructure; Pearson matrix deferred to Phase 3 when signal outputs exist"

metrics:
  duration_minutes: ~5
  completed_date: "2026-04-13"
  tasks_completed: 1
  tasks_pending: 1
  files_created: 2
  files_modified: 1
---

# Phase 1 Plan 4: Integration Wiring and Validation Scripts Summary

**One-liner:** Complete asyncio main() entry point wiring SharedState/BarBuilders/RithmicClient/subscriptions via asyncio.gather; CSV footprint export script for TradingView comparison; event loop lag probe script with P50/P95/P99/max reporting.

**Status: CHECKPOINT PENDING** — Task 1 (auto) complete; Task 2 (human-verify: live Rithmic aggressor field + footprint accuracy validation) awaiting execution during RTH.

## What Was Built

### Task 1: Wire __main__.py and Create Validation Scripts (COMPLETE)

**`deep6/__main__.py`** — complete main() entrypoint wiring:
- `SharedState.build(config)` + `await state.persistence.initialize()`
- Dual-TF BarBuilders: `BarBuilder(60, "1m")` + `BarBuilder(300, "5m")`
- `connect_rithmic(config)` + `register_callbacks(client, state)`
- Three DataType subscriptions: `ORDER_BOOK`, `LAST_TRADE`, `BBO`
- `asyncio.gather(*tasks)` with `asyncio.create_task` for bb_1m, bb_5m, session_manager
- Graceful shutdown with CancelledError handler and task.cancel() in finally block
- `cli_entry()` function using `asyncio.Runner(loop_factory=uvloop.new_event_loop)` — Python 3.12 uvloop pattern

**`scripts/validate_footprint.py`** — FootprintBar CSV export:
- `--bars N` (default 10) and `--output path.csv` CLI args
- Captures bars via `state._on_bar_close_fn` async hook
- Exports one CSV row per price level per bar: timestamp_utc, bar_open/high/low/close, total_vol, bar_delta, cvd, poc_price, price_level, ask_vol, bid_vol
- `asyncio.Event` barrier — waits for N bars then cancels pipeline tasks
- Per T-04-02: no credentials in CSV or logs

**`scripts/measure_loop_lag.py`** — Event loop lag probe:
- `--duration N` (default 60 seconds) CLI arg
- `probe_loop_lag()` coroutine: schedules 10ms sleeps, measures actual elapsed, computes lag = (actual - 10ms) * 1000
- `report_lag()` prints P50/P95/P99/max/mean with PASS (<1ms) / WARN (1-5ms) / FAIL (>5ms) verdict
- Runs alongside live DOM pipeline for realistic measurement under production callback load
- Per T-04-04: LAG_SAMPLES is module-level list; single event loop; no concurrent writes possible

## Verification Results (Task 1)

```
main() is async: OK
Scripts importable: OK
DataType subscriptions: 3 (ORDER_BOOK, LAST_TRADE, BBO) confirmed
asyncio.create_task: 3 tasks (bar_builder_1m, bar_builder_5m, session_manager) confirmed
asyncio.Runner with uvloop: confirmed
Issue #49 workaround (asyncio.sleep(0.5) in rithmic.py): confirmed
```

All 31 unit tests pass (tests/ excluding test_integration_live.py):
```
tests/test_bar_builder.py  9/9  PASSED
tests/test_footprint.py   11/11 PASSED
tests/test_session.py      6/6  PASSED
tests/test_signal_flags.py 5/5  PASSED
Total: 31/31 PASSED
```

## Checkpoint Pending: Task 2

**Gate:** Human-verify live Rithmic aggressor field + footprint accuracy + loop lag.

This is a blocking gate per D-03: aggressor field must be confirmed non-UNSPECIFIED on 50+ live ticks before Phase 2 footprint accuracy is trusted.

**What to verify:**
1. Aggressor gate passes: `aggressor.verified sample_count=50 unknown_count=0 unknown_pct=0.0%`
2. `scripts/validate_footprint.py --bars 5` produces CSV with non-zero ask_vol/bid_vol
3. Footprint CSV within ~10% of TradingView Bookmap Liquidity Mapper reference
4. `scripts/measure_loop_lag.py --duration 60` reports max lag < 5ms (ideally < 1ms)
5. SessionManager logs `session.fresh_start` or `session.restored_from_db` at 9:30 ET

**Run during RTH (9:30 AM - 4:00 PM ET).**

## ARCH-04 Documentation for Phase 3

`BarHistory` is a `deque(maxlen=200)` factory function (established in Plan 02). `BarBuilder.run()` calls `state.on_bar_close(label, bar)` on each closed bar. `SharedState.on_bar_close()` appends to the deque and invokes `_on_bar_close_fn` for Phase 2+ signal engines.

The pairwise Pearson correlation matrix (ARCH-04) will be computed in Phase 3 once E1/E8/E9 signal engine outputs exist. Phase 1 satisfies ARCH-04 by establishing the BarHistory ring buffer infrastructure with 200-bar capacity (3.3 hours of 1-minute history).

## Deviations from Plan

### Files Already Present

**Finding:** All three files (`deep6/__main__.py`, `scripts/validate_footprint.py`, `scripts/measure_loop_lag.py`) were already committed in commit `1140ef3` from a prior execution of this plan on this worktree branch.

**Action:** Verified all acceptance criteria against existing implementations. The existing code matches or exceeds the plan template (e.g., `measure_loop_lag.py` adds P95 percentile and a three-tier PASS/WARN/FAIL verdict instead of two-tier).

**Classification:** Not a deviation — prior agent execution on this worktree was complete. All plan criteria are satisfied.

## Known Stubs

None — all Plan 04 Task 1 functionality is fully wired. The `state._on_bar_close_fn` hook is `None` by default in SharedState (intentional, Phase 2 signal engines will attach). The validation scripts assign to this hook during collection.

## Threat Surface Scan

No new security-relevant surface beyond the plan's threat model:
- T-04-02: structlog configured in `cli_entry()` and script `main()` functions; no credentials in any bound context
- T-04-01: footprint CSV contains only price/volume data (no credentials); local disk only
- T-04-03: `validate_footprint.py` terminates via `bar_event.wait()` + task.cancel() — no hang risk
- T-04-04: `LAG_SAMPLES` is a module-level list; single event loop; no concurrent mutation

## Self-Check: PASSED

Files confirmed present:
- deep6/__main__.py: FOUND
- scripts/validate_footprint.py: FOUND
- scripts/measure_loop_lag.py: FOUND

Commit confirmed:
- 1140ef3 feat(01-04): wire __main__.py entrypoint and create validation scripts: FOUND

All 31 unit tests: PASS
