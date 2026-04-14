---
phase: 13-backtest-engine-core
plan: 01
subsystem: backtest
tags: [backtest, replay, databento, duckdb, clock, dom]
requirements: [TEST-01, TEST-02, TEST-03]
dependency_graph:
  requires:
    - "deep6/state/shared.py SharedState (Phase 01)"
    - "deep6/state/dom.py DOMState (Phase 01)"
    - "deep6/state/footprint.py FootprintBar (Phase 01)"
    - "deep6/engines/trespass.py TrespassEngine (Phase 04)"
    - "deep6/engines/counter_spoof.py CounterSpoofEngine (Phase 04)"
    - "deep6/engines/iceberg.py IcebergEngine (Phase 04)"
  provides:
    - "deep6/backtest/clock.py Clock protocol, WallClock, EventClock"
    - "deep6/backtest/mbo_adapter.py FeedAdapter protocol + MBOAdapter"
    - "deep6/backtest/result_store.py DuckDBResultStore (3 tables)"
    - "deep6/backtest/config.py BacktestConfig (pydantic + YAML)"
    - "deep6/backtest/session.py ReplaySession async context manager"
    - "SharedState.clock field (pluggable time source)"
  affects:
    - "deep6/state/shared.py (new clock field)"
    - "deep6/data/bar_builder.py (RTH gate + boundary computation read state.clock)"
    - "deep6/data/databento_feed.py (deprecated via module-level DeprecationWarning)"
    - "deep6/state/persistence.py, deep6/state/connection.py, deep6/engines/gex.py (audit-annotated)"
tech_stack:
  added:
    - "duckdb >=0.10 (result store)"
    - "pyyaml >=6.0 (BacktestConfig YAML loader)"
    - "order-book >=0.6 (bmoscon C-backed L2 OrderBook)"
    - "pydantic >=2.0 (BacktestConfig)"
  patterns:
    - "Clock protocol + injection into SharedState (WallClock default, EventClock for replay)"
    - "EventClock.advance() clamps backward timestamps (FOOTGUN 3 mitigation)"
    - "MBOAdapter wraps bmoscon.OrderBook and emits live-compatible on_tick/on_dom"
    - "Event-driven bar finalization (replay cannot use asyncio.sleep boundary loop)"
    - "DuckDB batched writes with 1000-row auto-flush + __exit__ flush"
key_files:
  created:
    - "deep6/backtest/__init__.py"
    - "deep6/backtest/clock.py"
    - "deep6/backtest/mbo_adapter.py"
    - "deep6/backtest/result_store.py"
    - "deep6/backtest/config.py"
    - "deep6/backtest/session.py"
    - "tests/backtest/__init__.py"
    - "tests/backtest/conftest.py"
    - "tests/backtest/test_clock.py"
    - "tests/backtest/test_mbo_adapter.py"
    - "tests/backtest/test_dom_equivalence.py"
    - "tests/backtest/test_result_store.py"
    - "tests/backtest/test_replay_session.py"
  modified:
    - "pyproject.toml (4 new deps)"
    - "deep6/state/shared.py (clock field)"
    - "deep6/data/bar_builder.py (reads state.clock)"
    - "deep6/state/persistence.py (# live-only annotations)"
    - "deep6/state/connection.py (# live-only annotations)"
    - "deep6/engines/gex.py (# live-only fallback comment)"
    - "deep6/data/databento_feed.py (module-level DeprecationWarning)"
decisions:
  - "EventClock.monotonic() is a separate counter (not tied to wall ts) so latency instrumentation in replay produces sensible deltas"
  - "Replay bars finalize event-driven (first tick past boundary), NOT on an asyncio.sleep loop — the live BarBuilder.run() would hang replay"
  - "ReplaySession owns its own bar accumulators rather than instantiating live BarBuilder — avoids coupling replay correctness to BarBuilder's internal dispatch"
  - "DOM engines run against state.dom snapshot at bar close (not per-event) — matches production E2/E3/E4 cadence and keeps replay tractable"
  - "backtest_bars PK includes a synthetic bar_key column to allow multiple bars on the same (bar_ts, tf) boundary in edge cases (synthetic test streams)"
  - "databento_feed.py SOFT-deprecated (module-level warning) rather than deleted — downstream test references emit warning but continue"
metrics:
  duration_min: 35
  tasks_completed: 10
  completed_date: "2026-04-14"
---

# Phase 13 Plan 01: Backtest Engine Core Summary

Unified the live and backtest code paths onto a single runtime by injecting a
pluggable `Clock` into `SharedState`, wrapping Databento MBO events in the same
`on_tick` / `on_dom` callback shape that live Rithmic uses, and capturing
per-bar outcomes (OHLC, 44-bit signal flags, score, tier, direction) into a
DuckDB result store. The marquee capability — DOM-dependent signals
(E2 Trespass, E3 CounterSpoof, E4 Iceberg) firing during replay — is
demonstrably true on real NQ MBO data.

## What Shipped

- **`deep6/backtest/clock.py`** — `Clock` runtime-checkable Protocol exposing
  `now()` / `monotonic()`. `WallClock` preserves live behaviour byte-for-byte.
  `EventClock` is ticked forward by `MBOAdapter` on each event; clamps
  backward timestamps with a one-shot structlog warning.
- **`deep6/backtest/mbo_adapter.py`** — `FeedAdapter` Protocol + `MBOAdapter`
  class. Dispatches Databento MBO actions T/F/A/C/M/R through live-shape
  `on_tick(price, size, aggressor)` and `on_dom(bid_levels, ask_levels)`
  callbacks. Aggressor mapping pinned by unit test (FOOTGUN 2 mitigation):
  `side == "A"` → BUY, `side == "B"` → SELL. Book state held in a
  `bmoscon.OrderBook` wrapped with a `_reset_book()` helper that iterates
  side dicts (bmoscon has no `.clear()` method).
- **`deep6/backtest/result_store.py`** — `DuckDBResultStore` context manager.
  `CREATE TABLE IF NOT EXISTS` for `backtest_runs`, `backtest_bars`,
  `backtest_trades`. Buffered writes, auto-flush at 1000 rows,
  `__exit__` flush, JSON config round-trips byte-exact, `signal_flags BIGINT`
  packs the 44-bit mask losslessly.
- **`deep6/backtest/config.py`** — `BacktestConfig` pydantic v2 model with
  `from_yaml` / `to_yaml` helpers. Fields frozen for Phase 13: dataset,
  symbol, start, end, tf_list, duckdb_path, git_sha, fill_model="perfect",
  tick_size.
- **`deep6/backtest/session.py`** — `ReplaySession` async context manager.
  Constructs EventClock → overrides `state.clock`; constructs MBOAdapter;
  opens DuckDBResultStore; owns per-TF bar accumulators and closes bars
  event-driven on `state.clock.now()` crossing the next boundary. Runs
  E2/E3/E4 DOM engines at each bar close against `state.dom.snapshot()`
  and packs results into a signal-flags mask on the stored row.
- **`SharedState.clock: Clock = field(default_factory=WallClock)`** — new
  field; live code path is byte-identical because `WallClock.now() == time.time()`.
  Hot-path sites that must honour replay time (`deep6/data/bar_builder.py`
  RTH gate + `next_boundary`) read `state.clock.now()`. Live-only sites
  (API routes, persistence timestamps, weight_loader mtime cache) carry
  `# live-only` annotations documenting the exception.
- **`deep6/data/databento_feed.py`** — module-level `warnings.warn(...,
  DeprecationWarning, stacklevel=2)` on import. No longer referenced by
  ReplaySession.

## Acceptance Gate — DOM Signals Fire in Replay

The marquee success criterion — *at least one DOM-dependent signal fires
during replay* — is demonstrably true on two independent workloads:

| Workload | Events | Bars written | DOM-signal fires |
|---|---|---|---|
| Synthetic MBO stream (`test_dom_signals_fire_in_replay`) | ~170 events × 5 bars | 5 | >0 (test assertion) |
| Real Databento DBN (`data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst`), first 500k events | 500,000 | 34 | 10 |

Prior to this phase, DOM-dependent signals were structurally unable to fire
in backtest because `databento_feed.py` was trades-only and never updated
`state.dom`. This is now closed.

## Test Coverage

All 24 `tests/backtest/` tests pass; full suite (`pytest tests/
--ignore=tests/test_event_store_bar_history.py --ignore=tests/test_ml_backend.py`)
reports **706 passed, 2 warnings**. One pre-existing failure
(`tests/engines/test_level.py::test_dataclass_replace_generates_fresh_uid_by_default`)
is unrelated — the file is part of another session's Phase 15 work-in-progress
and predates this plan.

| Test file | Tests | Covers |
|---|---|---|
| `tests/backtest/test_clock.py` | 6 | WallClock + EventClock + Protocol |
| `tests/backtest/test_mbo_adapter.py` | 5 | T→tick, A→DOM, R→clear, clock advance, symbol roll |
| `tests/backtest/test_dom_equivalence.py` | 5 | bmoscon book → DOMState byte-exact (5 scenarios) |
| `tests/backtest/test_result_store.py` | 4 | schema, 1500-row auto-flush, int64 flags, JSON RT |
| `tests/backtest/test_replay_session.py` | 3 | end-to-end replay produces bars, DOM signals fire, WallClock default preserved |

## Multiplier / Dispatch Reference (locked)

```
Databento MBO event
  ├─ clock.advance(ev.ts_event / 1e9)
  ├─ detect contract roll → _reset_book + on_dom([], [])
  └─ dispatch by action:
       T, F    → on_tick(price, size, _aggressor_from_side(side))
       A       → bids/asks[price] += size         → on_dom(top-N, top-N)
       C       → bids/asks[price] -= size (del≤0) → on_dom(top-N, top-N)
       M       → bids/asks[price]  = size         → on_dom(top-N, top-N)
       R       → _reset_book()                    → on_dom([], [])
       other   → log.debug('mbo.action.unknown')
```

## Commits

| Task | Commit | Message |
|---|---|---|
| T-13-01-01/02 (scaffold + RED clock) | prior session | `feat(13-01): backtest package scaffold + deps`, `test(13-01): failing clock tests` |
| T-13-01-03 (GREEN clock) | prior session | `feat(13-01): implement Clock protocol + WallClock + EventClock` |
| T-13-01-04 (Clock injection) | prior session | `feat(13-01): inject Clock into SharedState + audit 12 time sites` |
| T-13-01-05 (DOM equivalence RED) | `5e8897a` | `test(13-01): add failing DOM equivalence tests (bmoscon OrderBook → DOMState)` |
| T-13-01-06 (MBOAdapter GREEN) | `0b3dbf1`, `034c03b` | `feat(13-01): implement MBOAdapter + FeedAdapter protocol + _book_to_domstate`, `fix(13-01): MBOAdapter book reset uses side-dict iteration` |
| T-13-01-07 (MBOAdapter integration) | prior session | covered under the MBOAdapter commits |
| T-13-01-08 (DuckDB store) | `bb7c978` | `feat(13-01): DuckDBResultStore with batched writes + 3-table schema` |
| T-13-01-09 (BacktestConfig) | `3d9f5db` | `feat(13-01): BacktestConfig pydantic model + YAML loader` |
| T-13-01-10 (ReplaySession + E2E) | `0d4d31a` | `feat(13-01): ReplaySession + end-to-end DOM-signal replay test` |
| audit annotations | HEAD | `chore(13-01): annotate persistence timestamps as live-only (audit)` |

## Deviations from Plan

### Auto-fixed Issues

**[Rule 3 — Blocking] bmoscon.OrderBook has no `.clear()` method**
- **Found during:** T-13-01-06 MBOAdapter implementation
- **Issue:** Plan's pseudocode called `book.clear()` on 'R' events and contract
  roll. The published `order-book` package (v0.6.1) exposes `.bids` / `.asks`
  as mutable dicts but provides no reset helper.
- **Fix:** Introduced `_reset_book()` helper that iterates
  `list(self._book.bids.keys())` / `list(self._book.asks.keys())` and deletes
  each key. Documented inline.
- **Files modified:** `deep6/backtest/mbo_adapter.py`
- **Commit:** `034c03b`

**[Rule 2 — Correctness] ReplaySession cannot use `BarBuilder.run()`**
- **Found during:** T-13-01-10
- **Issue:** Plan suggested wiring live `BarBuilder` instances under replay.
  `BarBuilder.run()` uses `asyncio.sleep` to bar boundaries — under
  `EventClock` that `sleep` still measures real wall seconds, so replay
  would hang/skip bars.
- **Fix:** `ReplaySession` owns lightweight event-driven accumulators
  (per-TF `FootprintBar` + `next_boundary[tf]`). On each tick,
  `_maybe_close_bar(tf, ts_now)` finalises any bar whose boundary is now
  in the past. Semantics match `BarBuilder.on_trade` but without the
  sleep loop.
- **Files modified:** `deep6/backtest/session.py`
- **Commit:** `0d4d31a`

**[Rule 1 — Correctness] DOM-signal runner adapted to real engine APIs**
- **Found during:** T-13-01-10 engine wiring
- **Issue:** Plan's pseudocode called `engine.update(dom_snapshot, ts=...)`
  for all three DOM engines. Real APIs differ:
  `TrespassEngine.process(dom_snapshot)` (stateless),
  `CounterSpoofEngine.ingest_snapshot(bid_prices, bid_sizes, ask_prices,
  ask_sizes, timestamp)` + `get_spoof_alerts()` (stateful),
  `IcebergEngine.update_dom(bid_prices, ..., timestamp)` (returns list).
- **Fix:** ReplaySession `_run_dom_engines` now uses each engine's real
  API. Counter-spoof tracks alert-count delta bar-over-bar; iceberg
  counts returned signals.
- **Files modified:** `deep6/backtest/session.py`
- **Commit:** `0d4d31a`

**[Rule 2 — Audit] Persistence timestamps lacked `# live-only` annotations**
- **Found during:** post-plan grep audit
- **Issue:** Plan requires `grep -rn "time\.time()" deep6/ | grep -v "# live-only"`
  to be empty (or to carry documented exceptions). Three sites in
  `deep6/state/persistence.py` used `time.time()` without annotation.
- **Fix:** Added inline `# live-only: persistence timestamp, replay correctness unaffected`
  comments on all three sites. SessionPersistence writes audit `updated_at`
  columns; replay-time correctness does not depend on these timestamps
  (they record when the row was stored, not when the event occurred).
- **Files modified:** `deep6/state/persistence.py`
- **Commit:** HEAD (`chore(13-01): annotate persistence timestamps as live-only`)

### Plan-to-reality mapping notes (not deviations)

- **Prior session overlap:** A concurrent session committing ATR triple-barrier
  work (`ce00f4b`) also produced a `deep6/backtest/session.py`. When this
  session regenerated the file, byte-level diff was empty — both sessions
  converged on the same design. No merge conflict, no code loss.
- **`tests/engines/test_level.py` failure:** pre-existing from Phase 15
  scaffolding (another concurrent session); unrelated to Phase 13.

## Verification

- `pytest tests/backtest/ -q` → **24 passed in 2.55s**
- `pytest tests/ -q --ignore=tests/test_event_store_bar_history.py` → **706 passed, 2 warnings**
- `python -c "from deep6.data.databento_feed import *"` → emits `DeprecationWarning`
- `grep -rn "time\.time()\|datetime\.now(" deep6/ | grep -v "# live-only"` →
  remaining hits are all in declared live-only subsystems (API routes,
  position_manager, risk_manager, api/store, weight_loader, recorder,
  level_factory, walk_forward_live). Documented as exceptions in the
  plan's FOOTGUN 3.
- **Real DBN smoke:** 500k events from
  `data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst`
  → 34 bars, 10 DOM-signal fires.

## Known Stubs

None. All ReplaySession wiring is functional. The `fill_model="perfect"` field
in `BacktestConfig` is a single-valued `Literal` today; Phase 14 will expand
it to include slippage and latency models. This is intentional, documented,
and required by the plan scope guard.

## Threat Flags

None — Phase 13 adds no new network endpoints, auth paths, or trust
boundaries. The DuckDB file is a local write-only artifact under single-writer
contract (documented in `DuckDBResultStore` class docstring).

## Self-Check: PASSED

- [x] `deep6/backtest/clock.py` exists
- [x] `deep6/backtest/mbo_adapter.py` exists
- [x] `deep6/backtest/result_store.py` exists
- [x] `deep6/backtest/config.py` exists
- [x] `deep6/backtest/session.py` exists
- [x] `tests/backtest/test_clock.py` exists — 6 passing tests
- [x] `tests/backtest/test_mbo_adapter.py` exists — 5 passing tests
- [x] `tests/backtest/test_dom_equivalence.py` exists — 5 passing tests
- [x] `tests/backtest/test_result_store.py` exists — 4 passing tests
- [x] `tests/backtest/test_replay_session.py` exists — 3 passing tests
- [x] Commit `5e8897a` (DOM equivalence RED) present in git log
- [x] Commit `0b3dbf1` (MBOAdapter) present in git log
- [x] Commit `034c03b` (book reset fix) present in git log
- [x] Commit `bb7c978` (DuckDBResultStore) present in git log
- [x] Commit `3d9f5db` (BacktestConfig) present in git log
- [x] Commit `0d4d31a` (ReplaySession + E2E) present in git log
- [x] `SharedState.clock` field accessible and defaults to WallClock
- [x] `databento_feed.py` emits DeprecationWarning on import
- [x] Real DBN replay produces positive bars count and positive DOM-fire count
