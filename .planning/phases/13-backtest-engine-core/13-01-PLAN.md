---
phase: 13-backtest-engine-core
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - deep6/backtest/__init__.py
  - deep6/backtest/clock.py
  - deep6/backtest/mbo_adapter.py
  - deep6/backtest/result_store.py
  - deep6/backtest/session.py
  - deep6/backtest/config.py
  - deep6/state/shared.py
  - deep6/data/bar_builder.py
  - deep6/data/rithmic.py
  - deep6/state/connection.py
  - deep6/state/persistence.py
  - deep6/engines/gex.py
  - deep6/data/databento_feed.py
  - tests/backtest/__init__.py
  - tests/backtest/test_clock.py
  - tests/backtest/test_mbo_adapter.py
  - tests/backtest/test_result_store.py
  - tests/backtest/test_dom_equivalence.py
  - tests/backtest/test_replay_session.py
  - pyproject.toml
autonomous: true
requirements: [TEST-01, TEST-02, TEST-03]

must_haves:
  truths:
    - "SharedState.clock field exists, defaults to WallClock, no live-path regression"
    - "MBOAdapter dispatches Databento MBO actions T/A/C/M/F/R through the SAME on_tick / on_dom callback signatures as deep6/data/rithmic.py"
    - "bmoscon.OrderBook snapshot converts byte-exact to DOMState array.array('d') via MBOAdapter._book_to_domstate"
    - "ReplaySession produces a positive row count in backtest_bars matching manual bar count over replayed window"
    - "DOM-dependent signals E2/E3/E4 fire at least once during replay (previously impossible with trades-only databento_feed.py)"
    - "databento_feed.py is deprecated with module-level DeprecationWarning and removed from ReplaySession wiring"
    - "All 12 identified time.time()/datetime.now() hot-path sites route through state.clock; live-only sites (API routes, weight_loader) documented as exceptions"
  artifacts:
    - path: "deep6/backtest/clock.py"
      provides: "Clock protocol, WallClock, EventClock"
      min_lines: 80
    - path: "deep6/backtest/mbo_adapter.py"
      provides: "FeedAdapter protocol + MBOAdapter class wrapping bmoscon.OrderBook; action dispatch T/A/C/M/F/R"
      min_lines: 200
    - path: "deep6/backtest/result_store.py"
      provides: "DuckDBResultStore with record_run/record_bar/record_trade/flush; 3 tables created on connect"
      min_lines: 150
    - path: "deep6/backtest/session.py"
      provides: "ReplaySession async context manager wiring Clock + Adapter + SharedState + Store"
      min_lines: 120
    - path: "deep6/backtest/config.py"
      provides: "BacktestConfig pydantic model; YAML loader"
      min_lines: 40
    - path: "tests/backtest/test_dom_equivalence.py"
      provides: "bmoscon book -> DOMState byte-exact equivalence test with 5+ scenarios"
  key_links:
    - from: "deep6/state/shared.py SharedState"
      to: "deep6/backtest/clock.py Clock"
      via: "clock: Clock = field(default_factory=WallClock)"
      pattern: "clock: Clock"
    - from: "deep6/backtest/session.py ReplaySession"
      to: "deep6/backtest/mbo_adapter.py MBOAdapter.run"
      via: "await adapter.run(on_tick=state.on_tick, on_dom=state.on_dom)"
      pattern: "adapter\\.run"
    - from: "deep6/backtest/mbo_adapter.py"
      to: "deep6/state/dom.py DOMState"
      via: "_book_to_domstate converts bmoscon OrderBook snapshot to array.array('d')"
      pattern: "_book_to_domstate"
---

<objective>
Build the backtest engine core that lets DEEP6 replay historical Databento MBO data through the exact same signal pipeline the live Rithmic feed drives. Add a `Clock` abstraction to `SharedState` so time-sensitive logic (session boundaries, persistence, latency) runs correctly in replay. Dispatch MBO actions (T/A/C/M/F/R) through the live callback shape, backed by `bmoscon.OrderBook` for C-accelerated L2 state. Capture per-bar outcomes (OHLC, 44-bit SignalFlags, ScorerResult, simulated fill) into a DuckDB store queryable post-run.

Purpose: unify live + backtest onto one codebase; close the gap where `databento_feed.py` is trades-only and DOM signals E2/E3/E4 never fire in backtest.
Output: new `deep6/backtest/` module (5 files), `SharedState.clock` field, 12-site time-source refactor, 5 new test files, DuckDB result store on disk.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/13-backtest-engine-core/13-CONTEXT.md

# DEEP6 integration surfaces
@deep6/state/shared.py
@deep6/state/dom.py
@deep6/state/session.py
@deep6/state/footprint.py
@deep6/data/rithmic.py
@deep6/data/databento_feed.py
@deep6/data/bar_builder.py

<interfaces>
From deep6/data/rithmic.py (callback shapes to mirror):
```python
TickCB = Callable[[float, int, Literal["BUY", "SELL"]], Awaitable[None]]
DomCB  = Callable[[list[tuple[float, int]], list[tuple[float, int]]], Awaitable[None]]
# on_tick(price, size, aggressor); on_dom(bid_levels, ask_levels)  -- top-N sorted
```

From deep6/state/dom.py:
```python
@dataclass
class DOMState:
    bid_vols: array.array  # 'd', pre-allocated, indexed by tick offset
    ask_vols: array.array
    mid_tick: int
```

From deep6/state/shared.py (NEW field added this plan):
```python
@dataclass
class SharedState:
    ...
    clock: Clock = field(default_factory=WallClock)   # NEW
```

From bmoscon/orderbook (external):
```python
from orderbook import OrderBook
book = OrderBook(max_depth=40)
book.bids[price] = size   # cancel by setting 0 or del
book.asks[price] = size
# book.bids is a SortedDict descending; book.asks ascending
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>T-13-01-01: Add duckdb + pyyaml + order-book deps; scaffold deep6/backtest/ and tests/backtest/</name>
  <files>pyproject.toml, deep6/backtest/__init__.py, tests/backtest/__init__.py</files>
  <behavior>
    - pyproject.toml adds: duckdb>=0.10, pyyaml>=6.0, order-book>=0.6 (bmoscon pkg name on PyPI)
    - deep6/backtest/__init__.py is empty module marker
    - tests/backtest/__init__.py empty
  </behavior>
  <action>Edit pyproject.toml [project.dependencies] (or appropriate section used by this repo) to add the three deps. Create the two __init__.py files empty.</action>
  <verify>
    <automated>pip install -e . 2>&1 | tail -5 && python -c "import duckdb, yaml, orderbook; print('ok')"</automated>
  </verify>
  <done>Imports succeed; no version resolution conflicts with existing deps.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-02: Write failing tests for Clock protocol (WallClock + EventClock)</name>
  <files>tests/backtest/test_clock.py</files>
  <behavior>
    - test_wallclock_returns_current_time: WallClock().now() within 1s of time.time()
    - test_wallclock_monotonic_increases: two monotonic() calls in order
    - test_eventclock_starts_at_zero_then_advances: initial now() == 0.0 (or sentinel); after advance(1_700_000_000) now() returns exactly that
    - test_eventclock_clamps_backward: advance(100) then advance(50) -> now() still 100; logs warning
    - test_eventclock_monotonic_independent: monotonic() increases by fixed delta per advance, not tied to wall ts
    - test_clock_protocol_structural: WallClock and EventClock both satisfy typing.runtime_checkable Clock protocol
  </behavior>
  <action>Create tests/backtest/test_clock.py with the six tests. Import from deep6.backtest.clock which does not yet exist → all fail with ImportError.</action>
  <verify>
    <automated>pytest tests/backtest/test_clock.py -x -q 2>&1 | grep -E "(ImportError|ModuleNotFoundError|6 failed)"</automated>
  </verify>
  <done>File exists, 6 tests defined, all fail on ImportError.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-03: Implement deep6/backtest/clock.py (Clock protocol, WallClock, EventClock)</name>
  <files>deep6/backtest/clock.py</files>
  <behavior>
    - `class Clock(Protocol)` with `@runtime_checkable`; methods `now() -> float`, `monotonic() -> float`
    - `class WallClock`: `now = time.time`, `monotonic = time.monotonic` (bound as staticmethods or instance methods — trivial)
    - `class EventClock`:
        * `__init__`: `_now = 0.0`, `_mono = 0.0`, `_mono_step = 1e-6` (1µs per advance — tunable)
        * `advance(ts: float) -> None`: clamp `_now = max(_now, ts)`; `_mono += _mono_step`; if `ts < self._now` log structlog warning
        * `now() -> float`: return `_now`
        * `monotonic() -> float`: return `_mono`
    - No global state; each instance independent
  </behavior>
  <action>Create deep6/backtest/clock.py (~90 lines). Use structlog.get_logger(__name__). Add module docstring noting Clock is injected into SharedState; WallClock is default preserving live behavior; EventClock is ticked forward by MBOAdapter.</action>
  <verify>
    <automated>pytest tests/backtest/test_clock.py -x -q</automated>
  </verify>
  <done>All 6 clock tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-04: Inject Clock into SharedState; refactor hot-path time-source sites</name>
  <files>deep6/state/shared.py, deep6/state/connection.py, deep6/state/persistence.py, deep6/data/rithmic.py, deep6/data/bar_builder.py, deep6/engines/gex.py</files>
  <behavior>
    - SharedState gains `clock: Clock = field(default_factory=WallClock)`
    - SharedState.build(...) signature unchanged (clock still optional with default)
    - Hot-path sites that must route through state.clock (correctness for replay):
        * deep6/data/bar_builder.py — bar timestamp assignment
        * deep6/data/rithmic.py — tick/dom event timestamping (only the ingest-side stamps, not the network-layer heartbeat logging)
        * deep6/state/connection.py — reconnect backoff timing
        * deep6/state/persistence.py — session snapshot timestamps
        * deep6/engines/gex.py — GEX data staleness check
    - Live-only sites KEPT AS-IS with inline comment `# live-only: does not need Clock` (API routes, weight_loader, risk/position manager, metrics/sweep/weights routes)
    - Existing tests that construct SharedState without a clock continue to pass (WallClock default)
  </behavior>
  <action>
    Edit deep6/state/shared.py: import Clock, WallClock from deep6.backtest.clock; add field.
    For each hot-path site: replace `time.time()` with `state.clock.now()` (or `self._clock.now()` if class already has a state ref); replace `datetime.now()` with `datetime.fromtimestamp(state.clock.now(), tz=ZoneInfo("America/New_York"))` where wall-clock datetime is required (session boundary only).
    For live-only sites, add a single-line comment documenting the exception.
    Run grep audit post-change: `grep -rn "time\.time()\|datetime\.now(" deep6/` — every remaining hit must have `# live-only` comment on same line or immediately above.
  </action>
  <verify>
    <automated>pytest tests/ -x -q --ignore=tests/backtest 2>&1 | tail -20</automated>
    <manual>grep -rn "time\.time()\|datetime\.now(" deep6/ | grep -v "# live-only"  →  zero unexplained hits</manual>
  </verify>
  <done>All pre-existing tests green; grep audit clean; SharedState.clock accessible.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-05: Write DOM equivalence test (bmoscon OrderBook → DOMState byte-exact)</name>
  <files>tests/backtest/test_dom_equivalence.py</files>
  <behavior>
    Five scenarios; each builds a synthetic book state and asserts `_book_to_domstate(book) == hand_built_domstate`:
    - empty book → empty DOMState (all zeros)
    - single bid level at price P → DOMState with ask_vols[...]=0, bid_vols[P_tick_offset]=size
    - 10 bid + 10 ask levels dense around mid → exact array match
    - cancel then re-add same level → final DOMState matches most recent add only
    - levels far outside DOMState pre-allocated range → truncated silently (out-of-range levels dropped with structlog debug)
  </behavior>
  <action>Create tests/backtest/test_dom_equivalence.py. Use real `orderbook.OrderBook` instance; import `_book_to_domstate` from deep6.backtest.mbo_adapter (does not yet exist → ImportError failures expected). Build hand-crafted DOMState with array.array('d') directly for comparison.</action>
  <verify>
    <automated>pytest tests/backtest/test_dom_equivalence.py -x -q 2>&1 | grep -E "(ImportError|5 failed)"</automated>
  </verify>
  <done>All 5 tests fail with ImportError (adapter not yet created).</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-06: Implement MBOAdapter with FeedAdapter protocol and _book_to_domstate</name>
  <files>deep6/backtest/mbo_adapter.py</files>
  <behavior>
    - `class FeedAdapter(Protocol)` with `async def run(self, on_tick: TickCB, on_dom: DomCB) -> None`
    - `class MBOAdapter(FeedAdapter)`:
        * `__init__(dataset, symbol, start, end, clock: EventClock, tick_size: float)`
        * Holds one `orderbook.OrderBook(max_depth=40)` plus DOMState tick-offset config
        * `async def run(on_tick, on_dom)`:
            - opens Databento client, iterates MBO events
            - for each event: `self._clock.advance(event.ts_event / 1e9)`  # ns → s
            - dispatch by `event.action`:
                - `'T'` or `'F'` → aggressor = `'BUY' if event.side == 'A' else 'SELL'` (Databento MBO side semantics); `await on_tick(event.price, event.size, aggressor)`
                - `'A'` → add to book; emit DOM
                - `'C'` → remove; emit DOM
                - `'M'` → modify; emit DOM
                - `'R'` → `book.clear()`; emit empty DOM
            - DOM emission throttle: coalesce within the same ns-bucket so we don't thrash on contiguous A/C sequences
        * `_book_to_domstate(book) -> DOMState`: iterate `book.bids` and `book.asks`; map each price to tick offset from current mid; fill `array.array('d')`; out-of-range dropped with debug log
        * Symbol roll detection: `event.instrument_id` change → `book.clear()` + reset mid
    - Deprecate `deep6/data/databento_feed.py`: add module-level `warnings.warn("Deprecated, use deep6.backtest.mbo_adapter.MBOAdapter", DeprecationWarning)` at top
  </behavior>
  <action>
    Create deep6/backtest/mbo_adapter.py (~220 lines). Use databento client (already approved dependency). Keep DOM emission lean — construct `DOMState` only when a DOM-changing action fires, not per tick. Add docstring describing action dispatch table.
    Edit deep6/data/databento_feed.py head: add `import warnings; warnings.warn(...)` at import time. Do NOT delete the file — only mark deprecated (any downstream tests will emit warning but continue).
  </action>
  <verify>
    <automated>pytest tests/backtest/test_dom_equivalence.py -x -q</automated>
    <automated>python -c "from deep6.data.databento_feed import *" 2>&1 | grep Deprecation</automated>
  </verify>
  <done>5 equivalence tests pass; deprecation warning emits on databento_feed import.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-07: MBOAdapter run() integration test with synthetic event stream</name>
  <files>tests/backtest/test_mbo_adapter.py</files>
  <behavior>
    - Build a fake MBO iterator (list of event objects with ts_event, action, side, price, size, instrument_id) — does NOT hit network
    - test_adapter_dispatches_trade_to_on_tick: 1 T event → on_tick called once with correct aggressor
    - test_adapter_dispatches_add_to_on_dom: 1 A event → on_dom called with bid_levels containing that price/size
    - test_adapter_clear_on_R: sequence A A R → final on_dom has empty books
    - test_adapter_advances_clock: clock.now() matches last event ts (in seconds)
    - test_adapter_symbol_roll_clears_book: instrument_id change clears OrderBook
  </behavior>
  <action>
    Inject a fake iterator into MBOAdapter (override `_open_stream` or accept `event_source` kwarg for testability). Write the 5 tests above. Capture on_tick / on_dom calls via AsyncMock.
  </action>
  <verify>
    <automated>pytest tests/backtest/test_mbo_adapter.py -x -q</automated>
  </verify>
  <done>All 5 tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-08: Implement DuckDBResultStore + schema creation + test</name>
  <files>deep6/backtest/result_store.py, tests/backtest/test_result_store.py</files>
  <behavior>
    - `class DuckDBResultStore(path: str)`:
        * `__enter__` / `__exit__` (sync manager OK — DuckDB is synchronous)
        * On connect: `CREATE TABLE IF NOT EXISTS` for backtest_runs, backtest_bars, backtest_trades (schemas per 13-CONTEXT.md)
        * `record_run(run_id, symbol, dataset, config_json, git_sha) -> None`
        * `record_bar(run_id, bar_ts, tf, ohlcv, signal_flags: int, score, tier, direction, dom_blob=None)`
        * `record_trade(run_id, ...)`
        * Internal write buffer: flush every 1000 bars OR on explicit `flush()` OR on `__exit__`
        * Uses `executemany` for batched INSERTs
    - Test coverage:
        * test_schema_created: after connect, three tables exist (query duckdb_tables)
        * test_record_bar_round_trip: write 1500 bars, SELECT COUNT(*) → 1500 (triggers one auto-flush at 1000 + final flush at 500)
        * test_signal_flags_pack_int64: write bar with flags bitmask = (1 << 43) | (1 << 22) | 1; read back → exact match
        * test_record_run_json_roundtrip: config_json with nested dict round-trips via DuckDB JSON column
  </behavior>
  <action>Create both files. Use duckdb.connect(path). Gate auto-flush via instance `_buffer: list[tuple]`. Document single-writer contract in docstring.</action>
  <verify>
    <automated>pytest tests/backtest/test_result_store.py -x -q</automated>
  </verify>
  <done>All 4 result-store tests pass; DuckDB file created on disk at test temp path.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-09: BacktestConfig (pydantic + YAML loader)</name>
  <files>deep6/backtest/config.py</files>
  <behavior>
    - `class BacktestConfig(BaseModel)` (pydantic v2):
        * dataset: str (e.g., "GLBX.MDP3"), symbol: str ("NQ.c.0"), start: datetime, end: datetime
        * tf_list: list[str] = ["1m", "5m"]
        * duckdb_path: str = "backtest_results.duckdb"
        * git_sha: str = ""  # populated at runtime
        * fill_model: Literal["perfect"] = "perfect"  # expanded in Phase 14
    - `@classmethod from_yaml(path: str) -> BacktestConfig`
  </behavior>
  <action>Create deep6/backtest/config.py. Validate with pydantic; leverage model_validate for YAML dict.</action>
  <verify>
    <automated>python -c "from deep6.backtest.config import BacktestConfig; c = BacktestConfig(dataset='GLBX.MDP3', symbol='NQ.c.0', start='2026-01-02T09:30', end='2026-01-02T16:00'); print(c)"</automated>
  </verify>
  <done>Config constructs, YAML roundtrip works.</done>
</task>

<task type="auto" tdd="true">
  <name>T-13-01-10: Implement ReplaySession orchestrator + end-to-end replay test</name>
  <files>deep6/backtest/session.py, tests/backtest/test_replay_session.py</files>
  <behavior>
    - `class ReplaySession` async context manager:
        * `__init__(config: BacktestConfig, state: SharedState)` — builds EventClock, sets state.clock = clock, builds MBOAdapter, opens DuckDBResultStore
        * `async __aenter__` returns self; records run row
        * `async run()`: wires `on_tick = state.on_tick`, `on_dom = state.on_dom`; subscribes a `on_bar_close` hook that writes to result_store.record_bar; `await adapter.run(on_tick, on_dom)`
        * `async __aexit__`: flushes result store, closes DuckDB
    - End-to-end test with synthetic 1-day event stream:
        * test_replay_produces_bars: inject stream covering RTH 09:30-16:00 of 1 day; after session, `SELECT COUNT(*) FROM backtest_bars WHERE run_id=?` > 0 and matches manually counted 1m-bar boundaries
        * test_dom_signals_fire_in_replay: stream includes DOM-heavy A/C pattern near absorption zone; assert at least one ENG-02/03/04 SignalFlag bit set in at least one recorded bar (verifies the core phase premise)
        * test_wallclock_default_preserved: constructing SharedState without session leaves state.clock as WallClock (regression guard)
  </behavior>
  <action>
    Create deep6/backtest/session.py (~150 lines). Use contextlib.asynccontextmanager OR explicit __aenter__/__aexit__ — pick whichever matches existing DEEP6 style (check deep6/api/app.py for precedent).
    Create tests/backtest/test_replay_session.py. Share synthetic event-stream factory with test_mbo_adapter.py via tests/backtest/conftest.py.
    Emit uuid for run_id via uuid4().
  </action>
  <verify>
    <automated>pytest tests/backtest/ -x -q</automated>
    <automated>pytest tests/ -x -q 2>&1 | tail -10</automated>
  </verify>
  <done>All new backtest tests pass; full existing test suite remains green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Databento MBO bytes → MBOAdapter | External; schema validated by databento client |
| MBOAdapter → SharedState callbacks | Internal; same shape as live Rithmic path |
| bmoscon OrderBook → DOMState | Internal; correctness guarded by equivalence test |
| ResultStore → DuckDB file | Local FS; single-writer assumption |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-13-01-01 | Tampering | DOMState mismatch silently corrupts signal E2/E3/E4 output | mitigate | 5-scenario equivalence test in T-13-01-05 |
| T-13-01-02 | Tampering | Clock refactor breaks live hot path | mitigate | Refactor gated by full tests/ pass in T-13-01-04; live-only sites explicitly commented |
| T-13-01-03 | DoS | Non-monotonic MBO timestamps across contract roll | mitigate | EventClock.advance clamps backward + warns |
| T-13-01-04 | Information Disclosure | run_id collision in DuckDB across sessions | accept | uuid4 collision probabilistically impossible |
| T-13-01-05 | Repudiation | Replay outcome differs from live on same bars | defer | Full equivalence validation is Phase 14 (backtest-live parity harness) |
</threat_model>

<verification>
- `pytest tests/backtest/ -x` → all new tests green (clock ×6, dom_equivalence ×5, mbo_adapter ×5, result_store ×4, replay_session ×3)
- `pytest tests/ -x` → full suite green, zero regression
- `grep -rn "time\.time()\|datetime\.now(" deep6/ | grep -v "# live-only"` → zero hits
- `python -c "import duckdb; c = duckdb.connect('backtest_results.duckdb'); print(c.execute('SELECT name FROM duckdb_tables').fetchall())"` shows backtest_runs, backtest_bars, backtest_trades
- `python -c "from deep6.data.databento_feed import *"` emits DeprecationWarning
- Manual: after running an end-to-end test session, `SELECT COUNT(*) FROM backtest_bars` > 0 and matches expected bar count for the synthetic window
</verification>

<success_criteria>
1. `deep6/backtest/` module importable; 5 files present (clock, mbo_adapter, result_store, session, config)
2. `SharedState.clock` exists; WallClock default; no live regression
3. `bmoscon.OrderBook` → `DOMState` conversion byte-exact across 5 scenarios
4. Replay end-to-end produces populated `backtest_bars` table with non-zero DOM-signal bits set
5. `databento_feed.py` emits DeprecationWarning and is no longer wired into ReplaySession
6. All 12 time-source refactor targets either route through state.clock or carry `# live-only` exception comment
</success_criteria>

<footguns>
**FOOTGUN 1 — DOM equivalence silent drift:** `bmoscon.OrderBook.bids` is a sorted-by-price descending structure; our `DOMState` is indexed by tick offset from mid. Getting the offset math wrong produces a *silently* shifted book where E2/E3/E4 fire on the wrong price bucket. **Mitigation LOCKED:** dedicated 5-scenario equivalence test (T-13-01-05) — no implementation proceeds without it.

**FOOTGUN 2 — Aggressor side mapping:** Databento MBO `side == 'A'` means ask-aggressor (buyer lifted the ask) = BUY aggressor. `side == 'B'` means bid-aggressor = SELL. Getting this inverted flips every delta in the replay. **Mitigation:** explicit docstring in MBOAdapter.run + unit test with fixed T event asserting aggressor string.

**FOOTGUN 3 — Refactoring time.time() on live-only sites:** Reconnect backoff in connection.py MUST use state.clock (so replay doesn't hang waiting for real seconds). But `weight_loader.py` mtime cache uses filesystem time — using state.clock there would break live ML deployment. **Mitigation:** explicit per-site decision documented with `# live-only` comment; grep audit enforces no silent drift.

**FOOTGUN 4 — DuckDB write buffer forgotten:** If ReplaySession exits without `__aexit__` firing (KeyboardInterrupt, exception mid-replay), unflushed rows are lost. **Mitigation:** `record_bar` flushes every 1000 rows AND on context exit; document that interrupt loss is bounded to <1000 bars.

**FOOTGUN 5 — Deprecating databento_feed while tests still reference it:** blind delete breaks ImportError chain. **Mitigation:** soft deprecation (warning, not removal); explicit ReplaySession wires to MBOAdapter only; grep check post-change for any remaining ReplaySession-adjacent import of databento_feed.
</footguns>

<rollback>
If Phase 13 introduces regressions:
1. `SharedState.clock = WallClock()` override at build-site — disables replay-mode clock without code changes (safe for live).
2. Full rollback: `git revert` this plan's commit. `deep6/backtest/` module becomes orphan but harmless (unreferenced). databento_feed.py deprecation reverts.
3. Hot-path time-source refactor is the only change affecting live behavior; if a specific site causes regression, revert just that file and restore its `time.time()` call — state.clock field is backward-compatible (WallClock.now() == time.time()).
</rollback>

<output>
After completion, create `.planning/phases/13-backtest-engine-core/13-01-SUMMARY.md`
</output>
