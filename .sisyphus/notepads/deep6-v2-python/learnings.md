# Learnings — deep6-v2-python

## Project Context
- Clean room rebuild of DEEP6 as Python-native live runtime for NQ futures auto-trading
- Eliminates NinjaTrader dependency — connects directly to Rithmic via async-rithmic
- 52 signal detectors across 8 scorer categories
- TDD: RED-GREEN-REFACTOR for all new code
- Target: `deep6v2/` package

## Key Architecture Decisions
- Package: `deep6v2/` (NOT `deep6/`)
- Tests: `tests_v2/` (NOT `tests/`)
- Python 3.12+
- async-rithmic 1.5.9 for Rithmic connection
- Pydantic v2 for types and config
- structlog with JSON output
- DuckDB for append-only analytics, SQLite for transactional state

## R3-Optimized Weights (LOCKED — DO NOT CHANGE)
- absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3
- volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0

## Multiplier Chain Order (LOCKED)
base → confluence_mult → zone_bonus → GEX → agreement → IB_mult → VPIN → clip(0,100)

## Tier Thresholds (LOCKED)
TYPE_A ≥ 80, TYPE_B ≥ 72, TYPE_C ≥ 50, QUIET < 50

## Timing
- RTH: 9:30-16:00 ET (Monday-Friday)
- Bar index = minutes since 9:30 RTH open (bar 0 = 9:30, bar 59 = 10:29, bar 60 = 10:30)
- Midday block: bars 60-210 (10:30-13:00 ET) → force QUIET tier
- IB multiplier 1.15×: bars 0-59 (initial balance period)

## Signal Taxonomy
- 52 signals + 3 meta-flags = 55 SignalId enum entries
- ABS(4), EXH(6), IMB(9), DELT(11), AUCT(5), TRAP(5), VOLP(6), ENG(6)
- ENG-02, ENG-03, ENG-05, ENG-07 → NOT SCORED (category=None)
- ENG-04 → absorption category (hidden absorption)
- ENG-06 → poc category (POC/VWAP/VA zone context)

## [2026-05-14] Task 1: Project Scaffolding
- Package structure created at deep6v2/
- Tests at tests_v2/
- pyproject.toml installed via pip install -e .
- Makefile targets: test, lint, typecheck, run, run-dry

## [2026-05-14] Task 2: Core Types
- SignalId: 55 entries (52 signals + 3 meta-flags)
- SignalFlagBits: bit positions from SignalFlagBits.cs (exact C# match)
- SessionContext: mutable dataclass with 7 deque histories (maxlen=50)
- ISignalDetector, IDepthConsumingDetector, IAbsorptionZoneReceiver protocols defined

## [2026-05-14] Task 3: Config System
- AppConfig.from_env() works with defaults
- R3 weights locked in ScoringConfig (absorption=20.0, exhaustion=15.7, etc.)
- dry_run=True is the default safety setting
- Env prefix per sub-config (RITHMIC_, SIGNAL_, SCORING_, EXECUTION_, KRONOS_)

## [2026-05-14] Task 5: Clock Abstraction
- RTH: 9:30:00-16:00:00 ET inclusive (M-F only)
- Bar index 0 = 9:30 ET, 60 = 10:30 ET (midday block start), 210 = 13:00 ET (midday end)
- Use ZoneInfo("America/New_York") � NOT pytz
- EventClock.advance(dt) sets the internal time for replay

## [2026-05-14] Task 6: Logging Foundation
- structlog configured with configure_logging(dev_mode=False) for production JSON output
- get_logger("module.name") returns bound logger with module context
- JSON output includes: event, level, timestamp, module, plus bound vars (bar_index, etc.)
- Use structlog.contextvars for per-request correlation IDs in future

## [2026-05-14] Task 4: Test Infrastructure + Fixtures
- 60 signal fixtures created in tests_v2/fixtures/signals/ (52 individual + 8 composite)
- 5 scoring fixtures in tests_v2/fixtures/scoring/
- conftest.py: sample_footprint_bar, sample_session_context, sample_dom_snapshot fixtures
- Fixture format: {name, bar, context, expected_signal{signal_id, direction, strength_min, strength_max}}
- loader.py: load_signal_fixture("abs_01"), load_scoring_fixture("type-a-all-categories")
- ENG fixtures include dom_snapshot field for depth-consuming detectors
- DOMLevel actual type: {price, volume} — no size/order_count (adapted from spec)
- DOMSnapshot actual type: {timestamp, bids, asks} — no best_bid/best_ask (adapted from spec)
- JSON dict keys (bid_volumes/ask_volumes) auto-coerce from string to float via Pydantic v2
- 10 tests all passing in test_fixtures.py
## [2026-05-14] Task 8: DOM State
- DOMState uses pre-allocated array.array('l') for O(1) price?index updates
- base_price=20000.0, num_levels=4000 covers 20000-21000 NQ range (+1000 points)
- Best bid/ask tracked with simple int index (fast scan on update, no sort needed)
- snapshot() creates DOMSnapshot with up to 40 levels per side
- reset() zeroes arrays for session restart
- 1000 update_level() calls < 1ms verified

## [2026-05-14] Task 7: async-rithmic Connection Manager
- ConnectionState: DISCONNECTED, CONNECTING, CONNECTED, FROZEN, RECONNECTING
- FreezeGuard: freeze() on disconnect ? blocks DOM updates ? reconnect ? reconcile_position() ? unfreeze
- Exponential backoff: base * (2**attempt), configurable in RithmicConfig
- handle_dom_update() silently drops updates when frozen (no exception)
- RithmicClient takes client_factory for dependency injection (testable without real Rithmic)
- Position reconciliation required before unfreeze (safety gate)

## [2026-05-14] Task 9: Tick Classification
- price >= best_ask -> BUY (inclusive boundary)
- price <= best_bid -> SELL (inclusive boundary)
- else -> UNSPECIFIED (inside spread, counts for total_volume but not bid/ask in footprint)
- No BBO -> UNSPECIFIED (DOM not yet populated)
- TickClassifier takes DOMState dependency (reads BBO via get_best_bid/get_best_ask)
- ClassifiedTick is frozen dataclass with slots for performance
- DOMState.update_level() uses string "bid"/"ask" (not OrderSide enum)

## [2026-05-14] Task 12: Event Store
- EventWriter (DuckDB): append-only analytics — bars, signals, scores, fsm_events, executions
- StateStore (SQLite): transactional state — sessions, paper_gate
- Both support ":memory:" for testing
- DuckDB: use .execute() + .fetchdf() for queries
- SQLite: use ON CONFLICT DO UPDATE for upserts (requires Python sqlite3)
- EventWriter.insert_bar() takes FootprintBar + session_id
- StateStore.upsert_session() for session state updates
- DuckDB auto-increment via CREATE SEQUENCE + nextval() (not AUTOINCREMENT)
- 1000 bar inserts < 5s threshold (actual ~3.5s in-memory)
## [2026-05-14] Task 10: Bar Builder
- BarBuilder: accumulates ClassifiedTick ? FootprintBar on minute boundaries
- RTH gating: on_tick() returns early for non-RTH time
- POC = price level with max (bid_vol + ask_vol)
- Value Area: 70% of total volume centered on POC (expand up/down by largest adjacent level)
- CVD accumulates per session, resets on session_reset (RTH open)
- UNSPECIFIED ticks: total_volume += size, but NOT in bid_volumes/ask_volumes
- SessionContext rolling histories updated on each bar close (maxlen=50)
- on_bar_close(bar, ctx) callback triggered on each bar close
- Uses Clock abstraction � injectable EventClock for testing

## [2026-05-14] Task 11: Rithmic Integration Test
- Integration test at tests_v2/integration/test_rithmic_connection.py
- Marked @pytest.mark.integration — skips in CI
- Auto-skips when RITHMIC_USER/PASSWORD/SYSTEM_NAME not set
- Requires network access to wss://rituz00100.rithmic.com
- Run manually: pytest tests_v2/integration/ -v -m integration --timeout=60

## [2026-05-14] Task 13: Absorption Detectors
- Direction: LOW wick absorption ? BULLISH (sellers absorbed at low, reversal up expected)
- Direction: HIGH wick absorption ? BEARISH (buyers absorbed at high, reversal down expected)
- ABS_01: wick_vol > total � 0.3 AND |delta| < total � 0.1 (neutrality threshold)
- ABS_02: extreme vol > vol_ema � 1.5 AND price holds away from extreme (close not at extreme)
- ABS_03: POC in wick zone (top/bottom 25% of range) AND total_vol > vol_ema � 1.5
- ABS_04: total_vol > vol_ema � 1.5 AND range < ATR � 0.5 (compressed bar = absorption)
- IAbsorptionZoneReceiver.mark_absorption_zone() called when ABS_01 fires
- Exception isolation: receiver errors are caught and ignored

## [2026-05-23] Backtest discovery schema
- DuckDB discovery DB should keep exactly 3 tables: iterations, trades, strategies.
- `data/backtests/` is the correct location for discovery/backtest DuckDB artifacts.
- `CREATE TABLE IF NOT EXISTS` is enough for the discovery loop bootstrap; no migration helper needed yet.

## [2026-05-23] Config semantic validation
- Keep `param_bounds.validate_config()` as the numeric bounds layer; semantic checks belong in a separate validator module.
- `StrategyConfig` can be valid at the model layer but still semantically invalid if it lacks a real exit or has contradictory bracket ratios.
- Warning-only cases are useful for search quality signals (e.g. MIDDAY block, VPOC, trailing level exits) without blocking validation.

## [2026-05-23] Backtest harness
- Preprocessed MBO session pickles from `scripts/preprocess_mbo.py` store `footprint_bars`, `wall_events`, and `vp_zones` in one payload keyed by ISO session date.
- Preprocessed bar and wall timestamps are persisted as epoch seconds even though some older specs describe ns; harness helpers should normalize both seconds and ns inputs.
- `StrategyConfig` currently has no `level_approach_ticks` field, so the harness should fall back to `param_bounds.PARAM_BOUNDS["level_approach_ticks"].default` for level proximity checks.
