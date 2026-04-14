# Phase 13: Backtest Engine Core — Clock + MBO Adapter + DuckDB Store — Context

**Gathered:** 2026-04-14
**Status:** Ready for planning
**Source:** Discuss-phase (inline, post-research audit of deep6/ time-source and feed surfaces)

<domain>
## Phase Boundary

Unify the live and backtest code paths onto a single runtime by injecting a `Clock` abstraction into `SharedState` and feeding Databento MBO events through the same callback surfaces the live Rithmic feed uses (`on_tick`, `on_dom`). Capture per-bar artifacts (OHLC, 44-bit SignalFlags bitmask, ScorerResult score/tier/direction, DOMSnapshot reference, simulated fill) into a DuckDB result store for post-run analysis.

This is an **integration + plumbing phase**, not greenfield research. The reference for feed shape is `deep6/data/rithmic.py`; the existing `deep6/data/databento_feed.py` is trades-only and is **deprecated and replaced** by `deep6/backtest/mbo_adapter.py` in this phase.

Five components, in build order:

1. **`deep6/backtest/clock.py`** — `Clock` protocol, `WallClock` (live), `EventClock` (replay); pluggable `now()` source
2. **`deep6/backtest/mbo_adapter.py`** — `MBOAdapter` + `FeedAdapter` protocol; wraps Databento MBO stream into the same `on_tick` / `on_dom` callback shape `rithmic.py` uses; backed by `bmoscon/orderbook` for C-accelerated L2 state
3. **`deep6/backtest/result_store.py`** — DuckDB-backed writer; schemas `backtest_runs`, `backtest_bars`, `backtest_trades`
4. **`deep6/backtest/session.py`** — `ReplaySession` orchestrator; wires Clock + MBOAdapter + SharedState + ResultStore
5. **Clock injection into `deep6/state/shared.py`** + audit-and-refactor of ~12 `time.time()` / `datetime.now()` call sites under `deep6/` to use `state.clock`

</domain>

<decisions>
## Implementation Decisions

### Clock
- **Protocol shape:** `class Clock(Protocol): def now(self) -> float: ...  def monotonic(self) -> float: ...` — two methods because existing code mixes wall-clock (session boundaries, persistence) and monotonic (latency instrumentation).
- **Placement:** `state.clock: Clock = field(default_factory=WallClock)` on `SharedState`. Default preserves live-path behavior exactly.
- **Injection:** `ReplaySession` overrides `state.clock` with `EventClock` before any callbacks fire.
- **`EventClock` is driven by MBO event timestamps.** It does NOT advance autonomously — `MBOAdapter` ticks it forward via `clock.advance(ts)` before dispatching each event.
- **Session boundary logic stays in `deep6/state/session.py`** and keeps `zoneinfo("America/New_York")` per STATE.md decision. With `EventClock` set, session boundary detection becomes automatic in replay (clock returns event time, session logic does the rest).

### MBO Adapter
- **Backing book state:** `bmoscon/orderbook` (C-backed `OrderBook`) — already listed as optional in `CLAUDE.md` stack; promoted to required for backtest.
- **Action dispatch:**
  - `action == 'T'` (trade) → build synthetic tick → `make_tick_callback(price, size, aggressor)` — aggressor derived from `side` field per Databento MBO schema
  - `action in ('A', 'C', 'M')` (add/cancel/modify) → apply to `OrderBook` → extract top-N levels → `make_dom_callback(bid_levels, ask_levels)`
  - `action == 'F'` (fill) → treated as trade for footprint purposes
  - `action == 'R'` (clear) → `OrderBook.clear()` + emit empty DOM snapshot
- **DOM equivalence:** a `bmoscon` book snapshot must convert byte-for-byte into DEEP6's `DOMState` (`array.array('d')`) — dedicated equivalence test required. This is the single riskiest correctness boundary in the phase.
- **Feed protocol:** `class FeedAdapter(Protocol)` with `async def run(self, on_tick: TickCB, on_dom: DomCB) -> None` — mirrors the shape already expected by `SharedState.wire_callbacks()`.

### Result Store
- **Backend:** DuckDB (embedded, column store, Parquet-export compatible). `duckdb.connect('backtest_results.duckdb')`.
- **Schemas (frozen this phase):**
  ```sql
  CREATE TABLE backtest_runs (
    run_id UUID PRIMARY KEY, start_ts TIMESTAMP, end_ts TIMESTAMP,
    symbol VARCHAR, dataset VARCHAR, config_json JSON, git_sha VARCHAR
  );
  CREATE TABLE backtest_bars (
    run_id UUID, bar_ts TIMESTAMP, tf VARCHAR,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT,
    signal_flags BIGINT,  -- 44-bit mask packed into int64
    score DOUBLE, tier VARCHAR, direction VARCHAR,
    dom_snapshot_blob BLOB,  -- optional compressed DOMState pickle
    PRIMARY KEY (run_id, bar_ts, tf)
  );
  CREATE TABLE backtest_trades (
    run_id UUID, entry_ts TIMESTAMP, exit_ts TIMESTAMP,
    side VARCHAR, qty INT, entry_price DOUBLE, exit_price DOUBLE,
    pnl DOUBLE, tier VARCHAR, fill_model VARCHAR
  );
  ```
- **Writer batching:** 1000-row batch flush on bar close; explicit `flush()` in `ReplaySession.__aexit__`.

### Config
- **`BacktestConfig` (Pydantic dataclass) in `deep6/backtest/config.py`** — YAML-loadable via `pyyaml`. Fields: `dataset`, `symbol`, `start`, `end`, `tf_list`, `duckdb_path`, `git_sha`, `fill_model="perfect"`.

### Scope guard — explicit out-of-scope
| Item | Defer to |
|------|----------|
| Checkpointing / resume-replay | Phase 14 |
| Execution simulator queue model (realistic fills) | Phase 14 |
| CPCV / DSR / PBO statistical gates | Phase 15 |
| Sweep runner parallelism (multiprocessing) | Phase 15 |

### Claude's Discretion
- Exact DuckDB file layout on disk (`results/backtest_*.duckdb` vs single file)
- Logging verbosity during replay (debug vs info per 1000 events)
- Test fixtures (synthetic MBO event streams) — author to taste
- Progress reporting (tqdm vs structlog) during long replays

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### DEEP6 integration surfaces
- `deep6/data/rithmic.py` — live feed; callback shapes `(price, size, aggressor)` / `(bid_levels, ask_levels)` MUST match here
- `deep6/data/databento_feed.py` — trades-only legacy feed; marked DEPRECATED by this phase
- `deep6/state/shared.py` — `SharedState` dataclass; `clock` field added here; `on_bar_close` is the result-store write site
- `deep6/state/dom.py` — `DOMState` (`array.array('d')`) — target shape for `bmoscon` conversion
- `deep6/state/session.py` — session boundary logic using `zoneinfo("America/New_York")`
- `deep6/state/footprint.py`, `deep6/state/persistence.py` — time-source call-sites (part of the ~12 refactor set)
- `.planning/STATE.md` — DOMState decision, session zoneinfo decision
- `.planning/phases/01-*` — ARCH-02/03/04 establish SharedState assembly via `SharedState.build()`

### External
- Databento MBO schema: https://databento.com/docs/schemas-and-data-formats/mbo
- bmoscon/orderbook: https://github.com/bmoscon/orderbook
- DuckDB Python: https://duckdb.org/docs/api/python/overview

### Grep targets (refactor set — ~12 call sites)
Known from `grep time\.time\(\)\|datetime\.now\(\|datetime\.utcnow\(`:
- `deep6/state/connection.py`
- `deep6/state/persistence.py`
- `deep6/data/rithmic.py`
- `deep6/data/bar_builder.py`
- `deep6/engines/gex.py`
- `deep6/ml/weight_loader.py`
- `deep6/execution/risk_manager.py`
- `deep6/execution/position_manager.py`
- `deep6/api/app.py`
- `deep6/api/store.py`
- `deep6/api/routes/weights.py`
- `deep6/api/routes/metrics.py`
- `deep6/api/routes/sweep.py`

Not every site is load-bearing for replay correctness — API/routes/weight_loader are live-service-only and may keep `time.time()` as-is (documented exception). Call-sites on the hot path (bar_builder, rithmic, bar-close, persistence, connection) MUST route through `state.clock`.

</canonical_refs>

<specifics>
## Specific Ideas

- `WallClock.now()` = `time.time()`, `WallClock.monotonic()` = `time.monotonic()` — trivial shim; zero allocation overhead
- `EventClock.advance(ts: float)` is the only mutator; `now()` returns last advanced ts; `monotonic()` returns a separate increasing counter seeded from first advance
- `MBOAdapter` must handle Databento continuous symbol roll (`NQ.c.0`) — reset `OrderBook` on symbol change event
- `ResultStore.record_bar()` packs SignalFlags into int64 (44 bits fit); direction enum → VARCHAR
- `ReplaySession` is an async context manager; owns MBOAdapter lifecycle + DuckDB connection lifecycle
- Every `asyncio.get_event_loop().time()` call already present in live code is NOT a refactor target — it is monotonic by definition and works in replay without issue

</specifics>

<deferred>
## Deferred Ideas

- Parquet export of `backtest_bars` (trivial `COPY TO`; add when sweep phase needs it)
- Live-mode result store mirror (dual-write live bars to DuckDB) — premature; EventStore already covers live
- `DatabaseReplayFeed` pulling directly from on-disk Databento DBN files without Python iteration — optimize only if replay throughput < 100x realtime
- GEX + ML weight snapshotting into `backtest_runs.config_json` — add in Phase 15 when sweeps need it
- WebSocket live replay viewer in dashboard (Phase 10+)

</deferred>

## Success Criteria (what must be TRUE at phase end)

1. `deep6/backtest/` module exists with `clock.py`, `mbo_adapter.py`, `result_store.py`, `session.py`, `config.py` — importable, no circular imports
2. `SharedState.clock` exists, defaults to `WallClock`, and zero existing live tests regress (`pytest tests/ -x`)
3. Replay of 1 day of Databento MBO for NQ front-month runs end-to-end and `on_bar_close` fires `N` times equal to a manual count over the session window
4. DOM-dependent signals E2/E3/E4 produce **non-zero output at least once** during replay — per codebase audit these currently never fire in backtest because `databento_feed.py` is trades-only
5. `duckdb.connect('backtest_results.duckdb').execute("SELECT COUNT(*) FROM backtest_bars WHERE run_id = ?", [run_id]).fetchone()` returns a positive count matching the bar count from criterion 3
6. DOMState equivalence test passes: `bmoscon.OrderBook` snapshot converted via `MBOAdapter._book_to_domstate()` equals a `DOMState` assembled by hand from the same price/size pairs
7. `databento_feed.py` is marked deprecated (module-level warning + README note) and is no longer referenced by `ReplaySession`

## Risks

- **DOM state equivalence (HIGHEST):** `bmoscon` stores levels in a `SortedDict`-like structure keyed by price; `DOMState` is a flat `array.array('d')` indexed by tick offset from a reference price. Conversion must be exact at every replay step. **Mitigation:** dedicated equivalence test with synthetic book states covering edge cases (empty book, single level, far-OTM levels, level cancellation).
- **Clock injection footprint:** 12 grep targets, some live-only (API routes, ML deploy), some hot-path (bar_builder, rithmic). Wrong call refactored → silent bug in live. **Mitigation:** refactor in two PRs conceptually — hot-path first with tests, live-service paths second with live-only gate.
- **Deprecating `databento_feed.py`:** anything currently importing it breaks. **Mitigation:** grep + point fixes; backward-compat shim that proxies to `MBOAdapter` is NOT added (premature; we want clean break).
- **EventClock monotonic drift:** MBO timestamps can be non-monotonic across contracts on roll. **Mitigation:** `EventClock.advance()` clamps to `max(last, new)`; logs warning on backward event.
- **DuckDB lock contention:** single writer assumption holds within one ReplaySession; future sweep parallelism (Phase 15) will need per-run files. **Mitigation:** document in module docstring.
- **Performance:** `bmoscon` is C-backed and fast; Python-side Databento iteration is the bottleneck. **Mitigation:** no optimization in this phase — correctness first; profile in Phase 14.

---

*Phase: 13-backtest-engine-core*
*Context gathered: 2026-04-14 via discuss + code audit (grep of time-source call sites + feed surface review)*
