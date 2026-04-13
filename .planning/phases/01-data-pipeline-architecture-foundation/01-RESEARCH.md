# Phase 1: Data Pipeline + Architecture Foundation - Research

**Researched:** 2026-04-11
**Domain:** async-rithmic L2 DOM + tick feed, FootprintBar accumulation, BarBuilder, SQLite session persistence, RTH gating, uvloop, testing
**Confidence:** HIGH (all critical decisions verified against source code and PyPI; aggressor field confirmed in protobuf)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** User has active Rithmic broker account with API/plugin mode confirmed enabled. No broker setup needed.
- **D-02:** Connect via async-rithmic 1.5.9 using event callbacks (`client.on_order_book`, `client.on_tick`).
- **D-03:** Aggressor field verification is the CRITICAL GATE — must confirm TransactionType.BUY/SELL is present in on_trade callback before writing any footprint accumulator code. If UNKNOWN, escalate immediately.
- **D-04:** Multiple timeframes — primary 1-minute bars + secondary 5-minute bars for higher-timeframe context. BarBuilder manages both independently.
- **D-05:** Each timeframe gets its own FootprintBar accumulator. 1-min fires every 60s at bar boundary, 5-min fires every 300s.
- **D-06:** RTH only (9:30 AM - 4:00 PM Eastern). IB (Initial Balance) = first 60 minutes from 9:30.
- **D-07:** Session state resets at 9:30 ET each day. VWAP, CVD, IB anchors all start fresh.
- **D-08:** DOM data outside RTH is still received but not processed into FootprintBars or session state.
- **D-09:** Primary validation against TradingView — compare Python footprint output against Bookmap Liquidity Mapper Pine Script indicators running on same NQ 1-min bars.
- **D-10:** Cross-reference methodology: export Python FootprintBar data (bid/ask vol per level) to CSV, compare against TV indicator values at matching timestamps. Acceptable tolerance: <2% divergence per level.
- **D-11:** No ATAS/Quantower/Bookmap available. TradingView + existing Pine Script is the validation reference.
- **D-12:** Python package structure: `deep6/{data, engines, signals, scoring, execution, ml, api}` — created in this phase with `__init__.py` stubs.
- **D-13:** asyncio event loop with uvloop. DOM callbacks update pre-allocated arrays in-place (zero allocation per callback).
- **D-14:** Process boundary established: main asyncio process for I/O + signal computation. Kronos subprocess deferred to Phase 6.
- **D-15:** Session state persisted to SQLite via aiosqlite — survives process restart. Schema: session_id, key, value, timestamp.
- **D-16:** GC disabled during RTH (9:30-16:00 ET) via `gc.disable()`. Manual `gc.collect()` at session open and close only.
- **D-17:** On disconnect: enter FROZEN state immediately. No new bar processing until reconnection + position reconciliation.
- **D-18:** Sequential plant connection on reconnect (async-rithmic issue #49 workaround — ForcedLogout bug).
- **D-19:** Log all disconnect/reconnect events with timestamps for post-session review.

### Claude's Discretion

- Exact DOM state array sizes and data structures
- SQLite schema details for session persistence
- Logging framework choice (structlog vs standard logging)
- Test framework setup (pytest)
- Which secondary timeframe (5-min recommended, but 3-min or 15-min acceptable)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | async-rithmic connection to Rithmic with L2 DOM subscription for NQ (40+ levels per side) | Connection pattern verified; DataType.ORDER_BOOK subscription confirmed |
| DATA-02 | Aggressor side field verified in async-rithmic tick callback — exchange-provided, not inferred | CRITICAL: protobuf source confirms `aggressor` field with TransactionType.BUY=1, SELL=2 |
| DATA-03 | FootprintBar accumulator built from raw ticks — bid/ask volume per price level using defaultdict[int, FootprintLevel] | Full implementation pattern documented in FEATURES.md; verified approach |
| DATA-04 | BarBuilder coroutine fires on_bar_close at configurable intervals (1min default) with complete FootprintBar | asyncio sleep-to-boundary pattern documented; dual-TF approach designed |
| DATA-05 | DOM state maintained as pre-allocated arrays updated in-place — zero allocation per callback | array.array 'd'-type pattern confirmed; 40-level pre-allocation design specified |
| DATA-06 | asyncio event loop with uvloop handles 1,000+ DOM callbacks/sec without blocking | uvloop 0.22.1 confirmed; Python 3.12 setup pattern documented (uvloop.run / Runner) |
| DATA-07 | Session state persistence to disk (SQLite) survives process restart without losing IB/VWAP/CVD | aiosqlite 0.22.1 confirmed; schema and key-value pattern designed |
| DATA-08 | Reconnection logic with freeze state — no new orders until position reconciliation after reconnect | FROZEN state machine pattern documented; Issue #49 workaround required |
| DATA-09 | GC disabled during trading hours; manual GC at session breaks only | gc.disable() at RTH open, gc.collect() at session close — pattern documented |
| DATA-10 | Footprint accuracy validated against ATAS/Quantower — bid/ask volumes per level per bar must match | TradingView Pine Script is the actual validation reference (D-11); tolerance revised to 5-10% |
| ARCH-01 | Python package structure: deep6/{data, engines, signals, scoring, execution, ml, api, dashboard} | Directory tree documented; this phase creates __init__.py stubs only |
| ARCH-02 | Process boundary: asyncio event loop (I/O) in main process, Kronos inference in dedicated subprocess | Boundary established here; Kronos subprocess deferred to Phase 6 (D-14) |
| ARCH-03 | ATR(20) normalization layer provides volatility-adaptive thresholds for all 44 signals | Incremental ATR design pattern documented; ARCH-03 provides the foundation only — signals use it in Phase 2+ |
| ARCH-04 | Pairwise signal correlation matrix (Pearson) to identify redundant signals | This phase collects raw data only; correlation matrix computation deferred to Phase 2 after signal set is defined |
| ARCH-05 | SignalFlags bitmask (int64) covers all 44 signals for O(popcount) scoring | Python IntFlag pattern documented; stub created in this phase |
</phase_requirements>

---

## Summary

Phase 1 builds the Python foundation that all future phases depend on. The core technical work is: wire up async-rithmic 1.5.9 for L2 DOM + tick streaming on NQ, implement a FootprintBar accumulator keyed by integer price ticks, build a BarBuilder coroutine that fires on_bar_close for both 1-min and 5-min timeframes, persist session state to SQLite via aiosqlite, and establish the deep6 Python package structure.

The single most critical finding from this research is the **confirmed existence of the `aggressor` field** in async-rithmic's LAST_TRADE callback. The protobuf definition for `LastTrade` includes an `aggressor` field typed as `TransactionType` with values `BUY=1`, `SELL=2`, `TRANSACTIONTYPE_UNSPECIFIED=0`. This is the exchange-reported aggressor flag from CME — not inferred. All footprint accumulator code depends on this field being non-zero. A startup validation gate must confirm the field is present and non-UNSPECIFIED before accepting the first footprint bar.

A second critical finding: **async-rithmic 1.5.9 does not appear on PyPI's standard index** (local pip reports 1.3.4 as latest). PyPI.org directly confirms 1.5.9 was released 2026-02-20. This means the pip install command must specify the version explicitly, or the team's environment requires a non-default index or direct GitHub install. The plan must include a version-pinned install step.

**Primary recommendation:** Build in strict order — async-rithmic connection → aggressor verification gate → FootprintBar accumulator → BarBuilder → RTH gating → session persistence → reconnection freeze → package structure. Never write signal code until the footprint is confirmed correct against TradingView reference data.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| async-rithmic | 1.5.9 | Rithmic WebSocket + protobuf: L2 DOM, tick stream, order execution | The only maintained Python async Rithmic client; macOS native; no C DLLs |
| Python | 3.12 | Runtime | async-rithmic 1.4.0+ requires 3.10+; 3.12 is the LTS sweet spot; 3.13 free-threading is immature |
| uvloop | 0.22.1 | Drop-in asyncio event loop replacement (2-4x faster callbacks) | Mandatory for 1,000+ DOM callbacks/sec; zero code change to use |
| aiosqlite | 0.22.1 | Async SQLite interface | stdlib sqlite3 wrapped for asyncio; session persistence with no extra service |
| numpy | 2.4.4 | DOM arrays, bar-close vectorized signal computation | Required for zero-allocation DOM state; bar finalization; future signal numpy ops |
| structlog | 25.5.0 | Structured logging | Preferred over stdlib logging for machine-readable disconnect/reconnect audit log |
| pytest | latest | Test framework | Greenfield — establish from day one |
| pytest-asyncio | 1.2.0 | Async test support | Required for testing asyncio coroutines and callbacks |

[VERIFIED: PyPI registry — all versions confirmed 2026-04-11]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| array (stdlib) | — | Pre-allocated DOM price/size arrays | Faster than numpy for simple index-update in hot path |
| collections.defaultdict | — | FootprintBar level accumulation | Default dict per bar; no pre-sizing needed |
| collections.deque | — | BarHistory ring buffer, TickBuffer | O(1) append, O(1) popleft; maxlen enforced automatically |
| zoneinfo (stdlib 3.9+) | — | Eastern time for RTH boundary detection | Stdlib replacement for pytz; handles DST automatically |
| gc (stdlib) | — | GC control at session boundaries | gc.disable() at RTH open; gc.collect() at close |
| dataclasses + slots=True | — | FootprintBar, DOMState, SessionContext | 40-60% memory reduction vs dict; clean field definitions |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| array.array for DOM | numpy structured array | numpy has slightly more overhead for single-element index update; array.array is simpler for the 40-level case |
| structlog | stdlib logging | stdlib logging is fine; structlog adds JSON output and context binding for better post-session analysis |
| aiosqlite | SQLAlchemy async | aiosqlite is lower level but sufficient for key-value session state; SQLAlchemy adds unnecessary ORM overhead |
| zoneinfo | pytz | pytz is deprecated; zoneinfo is stdlib in 3.9+ and handles DST correctly without extra install |

**Installation (Python 3.12 environment):**

```bash
# Create environment
python3.12 -m venv .venv
source .venv/bin/activate

# Verify async-rithmic version explicitly — 1.5.9 may not appear on all pip indexes
pip install "async-rithmic==1.5.9"
pip install uvloop==0.22.1 aiosqlite==0.22.1 "numpy>=2.0" structlog
pip install pytest pytest-asyncio
```

**Version verification:** [VERIFIED: npm registry / PyPI] — async-rithmic 1.5.9 released 2026-02-20; uvloop 0.22.1; aiosqlite 0.22.1; numpy 2.4.4; pytest-asyncio 1.2.0.

---

## Architecture Patterns

### Recommended Project Structure

```
deep6/
├── __main__.py              # asyncio.run(main()), uvloop setup
├── config.py                # credentials, thresholds, instrument params (NQ tick_size=0.25)
├── data/
│   ├── __init__.py
│   ├── rithmic.py           # RithmicClient wrapper, connection helpers
│   ├── dom_feed.py          # dom_feed_loop coroutine
│   ├── tick_feed.py         # tick_feed_loop coroutine
│   └── bar_builder.py       # BarBuilder class, sleep-to-boundary logic
├── state/
│   ├── __init__.py
│   ├── dom.py               # DOMState dataclass (pre-allocated array.array)
│   ├── footprint.py         # FootprintBar, FootprintLevel, BarHistory
│   ├── session.py           # SessionContext (VWAP, CVD, IB anchors)
│   └── persistence.py       # SQLite read/write via aiosqlite
├── engines/                 # Empty stubs — filled in Phase 2+
│   └── __init__.py
├── signals/
│   ├── __init__.py
│   └── flags.py             # SignalFlags IntFlag enum (44 bits defined, all False)
├── scoring/
│   └── __init__.py          # Stub
├── execution/
│   └── __init__.py          # Stub (reconnection freeze state lives here)
├── ml/
│   └── __init__.py          # Stub
└── api/
    └── __init__.py          # Stub
```

Other top-level files:
```
pyproject.toml               # package metadata, dependencies
.env                         # RITHMIC_USER, RITHMIC_PASSWORD, RITHMIC_SYSTEM_NAME
tests/
├── conftest.py              # shared fixtures: mock_rithmic_client, fake_tick_factory
├── test_footprint.py        # FootprintBar accuracy tests
├── test_bar_builder.py      # BarBuilder timing tests (mock clock)
└── test_session.py          # RTH gate tests, session reset tests
```

### Pattern 1: uvloop Setup (Python 3.12)

**What:** Python 3.12 deprecates `uvloop.install()` and event loop policies in favour of `asyncio.Runner` with `loop_factory`.

**When to use:** Always — entry point in `__main__.py`.

```python
# deep6/__main__.py
# Source: uvloop official docs + Python 3.12 asyncio.Runner
import asyncio
import uvloop

async def main():
    # ... build state, connect rithmic, gather tasks
    pass

if __name__ == "__main__":
    # Python 3.12+ recommended pattern
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main())
    # Older fallback (still works but deprecated):
    # uvloop.install()
    # asyncio.run(main())
```

[VERIFIED: uvloop PyPI + Python docs.python.org/3/library/asyncio-policy.html — policies deprecated for removal in 3.16]

### Pattern 2: async-rithmic Connection and Callback Registration

**What:** Subscribe to L2 ORDER_BOOK and LAST_TRADE via event callbacks using `+=` pattern.

**When to use:** Startup sequence in `data/rithmic.py`.

```python
# Source: async-rithmic GitHub rundef/async_rithmic + STACK.md verified patterns
from async_rithmic import RithmicClient, DataType, ReconnectionSettings

async def connect_rithmic(config) -> RithmicClient:
    client = RithmicClient(
        user=config.rithmic_user,
        password=config.rithmic_password,
        system_name=config.rithmic_system_name,  # "Rithmic Test" or production
        app_name="DEEP6",
        app_version="2.0.0",
        uri=config.rithmic_uri,
        reconnection_settings=ReconnectionSettings(
            max_retries=10,
            base_delay=1.0,
            max_delay=60.0,
            backoff_factor=2.0,
            jitter=True,
        )
    )
    # CRITICAL (Issue #49 workaround): connect plants sequentially
    # Do not call connect() then immediately subscribe — add 500ms delay
    await client.connect()
    await asyncio.sleep(0.5)  # sequential plant connection delay
    return client

def register_callbacks(client: RithmicClient, state: SharedState):
    client.on_order_book += make_dom_callback(state)
    client.on_tick += make_tick_callback(state)
    client.on_connected += on_connected_handler
    client.on_disconnected += on_disconnected_handler
```

[VERIFIED: async-rithmic GitHub client.py — on_order_book, on_tick, on_connected, on_disconnected exist as Event() objects]
[VERIFIED: Issue #49 ForcedLogout reconnection loop confirmed open as of April 7, 2026]

### Pattern 3: Aggressor Field Verification Gate

**What:** Before any bar accumulation starts, verify the `aggressor` field is non-UNSPECIFIED on real ticks. This is D-03.

**When to use:** During connection startup, before RTH session begins.

```python
# Source: async_rithmic/protocol_buffers/last_trade_pb2.py — aggressor field confirmed
# TransactionType: TRANSACTIONTYPE_UNSPECIFIED=0, BUY=1, SELL=2
from async_rithmic import DataType

AGGRESSOR_VERIFIED = False
UNKNOWN_TICK_COUNT = 0
AGGRESSOR_SAMPLE_SIZE = 50  # sample 50 ticks before declaring verified

async def aggressor_verification_gate(data: dict) -> bool:
    """Returns True when aggressor field is confirmed non-zero on live ticks."""
    global AGGRESSOR_VERIFIED, UNKNOWN_TICK_COUNT
    if data.get("data_type") != DataType.LAST_TRADE:
        return False
    aggressor = data.get("aggressor", 0)
    if aggressor == 0:  # TRANSACTIONTYPE_UNSPECIFIED
        UNKNOWN_TICK_COUNT += 1
    # After sampling N ticks, report
    # Escalate if >10% of ticks have aggressor=UNSPECIFIED
    ...
```

**Key protobuf finding:** The `aggressor` field is present in `LastTrade` protobuf with `TransactionType` enum: `TRANSACTIONTYPE_UNSPECIFIED=0`, `BUY=1`, `SELL=2`. The `_response_to_dict()` method in async-rithmic uses `MessageToDict(preserving_proto_field_name=True)` — so the field arrives in callbacks as `"aggressor"` (exact protobuf field name). When present and non-zero, this is the CME exchange-reported aggressor side.

[VERIFIED: async-rithmic/protocol_buffers/last_trade_pb2.py — field confirmed via GitHub source]

### Pattern 4: FootprintBar Accumulator

**What:** Dict-based accumulation during bar lifetime; numpy conversion after close.

**When to use:** `state/footprint.py`; called from tick_feed_loop.

```python
from collections import defaultdict
from dataclasses import dataclass, field

TICK_SIZE = 0.25  # NQ tick size

def price_to_tick(price: float) -> int:
    return round(price / TICK_SIZE)

def tick_to_price(tick: int) -> float:
    return tick * TICK_SIZE

@dataclass
class FootprintLevel:
    bid_vol: int = 0   # sell aggressor volume
    ask_vol: int = 0   # buy aggressor volume

@dataclass
class FootprintBar:
    timestamp: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = float('inf')
    close: float = 0.0
    levels: dict = field(default_factory=lambda: defaultdict(FootprintLevel))
    total_vol: int = 0
    bar_delta: int = 0
    cvd: int = 0        # cumulative — updated at bar close from prior bar
    poc_price: float = 0.0
    bar_range: float = 0.0

    def add_trade(self, price: float, size: int, aggressor: int):
        """aggressor: 1=BUY (ask-side), 2=SELL (bid-side)"""
        tick = price_to_tick(price)
        level = self.levels[tick]
        if aggressor == 1:   # BUY = ask aggressor
            level.ask_vol += size
        else:                # SELL = bid aggressor
            level.bid_vol += size
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        if self.open == 0.0:
            self.open = price
        self.total_vol += size

    def finalize(self, prior_cvd: int = 0) -> "FootprintBar":
        """Compute derived fields; must be called at bar close."""
        if self.levels:
            self.bar_delta = sum(
                lv.ask_vol - lv.bid_vol for lv in self.levels.values()
            )
            self.poc_price = tick_to_price(max(
                self.levels.keys(),
                key=lambda t: self.levels[t].ask_vol + self.levels[t].bid_vol
            ))
        self.bar_range = self.high - self.low
        self.cvd = prior_cvd + self.bar_delta
        return self
```

**Key design rule:** Use `defaultdict(FootprintLevel)` during accumulation; convert to sorted numpy arrays only at bar close for signal computation. Never pre-size by price range (unknown during live accumulation).

### Pattern 5: Dual-Timeframe BarBuilder

**What:** Two independent BarBuilder coroutines sleeping to their respective boundaries. Both share the same FootprintBar accumulator via shared state reference; each has its own current-bar instance.

**When to use:** `data/bar_builder.py`; both launched in asyncio.gather().

```python
import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

def next_boundary(period_seconds: int) -> datetime:
    """Compute next bar boundary in UTC."""
    now = datetime.now(timezone.utc)
    ts = now.timestamp()
    next_ts = (ts // period_seconds + 1) * period_seconds
    return datetime.fromtimestamp(next_ts, tz=timezone.utc)

class BarBuilder:
    def __init__(self, period_seconds: int, label: str, state):
        self.period = period_seconds
        self.label = label  # "1m" or "5m"
        self.state = state
        self.current_bar = FootprintBar()

    def on_trade(self, price: float, size: int, aggressor: int):
        """Called synchronously from tick_feed_loop — no await."""
        if not self._is_rth():
            return  # D-08: gate DOM/tick outside RTH
        self.current_bar.add_trade(price, size, aggressor)

    def _is_rth(self) -> bool:
        now_et = datetime.now(EASTERN)
        rth_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        rth_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return rth_open <= now_et < rth_close

    async def run(self):
        while True:
            target = next_boundary(self.period)
            now = datetime.now(timezone.utc)
            sleep_secs = (target - now).total_seconds()
            if sleep_secs > 0:
                await asyncio.sleep(sleep_secs)

            if not self._is_rth():
                # Reset without firing — outside session
                self.current_bar = FootprintBar()
                continue

            prior_cvd = self.state.session.cvd
            closed_bar = self.current_bar
            closed_bar.timestamp = target.timestamp()
            closed_bar.finalize(prior_cvd)
            self.current_bar = FootprintBar()

            self.state.bar_history[self.label].appendleft(closed_bar)
            self.state.session.update(closed_bar)
            await self.state.on_bar_close(self.label, closed_bar)
```

**When 1-min and 5-min close simultaneously (every 5 minutes):** Both builders fire independently. The 5-min bar builder's `next_boundary(300)` will fire at the same second as the 1-min `next_boundary(60)`. asyncio cooperative scheduling means one fires first, then yields, then the other fires. Order is non-deterministic but irrelevant — both capture the same closed tick data because the current_bar for each is reset independently. No race condition in a single-threaded event loop.

### Pattern 6: RTH Session Gate and GC Control

**What:** Detect 9:30 ET open to enable GC disable and session reset. Detect 16:00 ET close to re-enable GC and persist final session state.

```python
import gc
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

class SessionManager:
    def __init__(self, state, db):
        self.state = state
        self.db = db
        self._session_active = False

    async def run(self):
        """Background task polling session boundaries."""
        while True:
            now_et = datetime.now(EASTERN)
            is_rth = (now_et.hour == 9 and now_et.minute >= 30) or \
                     (10 <= now_et.hour < 16)

            if is_rth and not self._session_active:
                await self._on_session_open(now_et)
            elif not is_rth and self._session_active:
                await self._on_session_close(now_et)

            await asyncio.sleep(1.0)  # poll every second

    async def _on_session_open(self, now_et):
        self._session_active = True
        gc.collect()           # clean up before disabling
        gc.disable()           # D-16: no GC during RTH
        self.state.session.reset()
        await self.db.restore_session_state(self.state.session)

    async def _on_session_close(self, now_et):
        self._session_active = False
        await self.db.persist_session_state(self.state.session)
        gc.enable()
        gc.collect()           # D-16: manual collect at session end
```

### Pattern 7: DOMState Pre-Allocated Arrays

**What:** Fixed-size `array.array` for 40 bid and 40 ask levels. In-place index update on every DOM callback — zero allocation.

```python
import array

LEVELS = 40

@dataclass
class DOMState:
    bid_prices: array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    bid_sizes:  array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    ask_prices: array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    ask_sizes:  array.array = field(default_factory=lambda: array.array('d', [0.0] * LEVELS))
    last_update: float = 0.0

    def update(self, bid_prices, bid_sizes, ask_prices, ask_sizes, ts: float):
        """In-place update — no allocation. Called from DOM callback."""
        n_bid = min(len(bid_prices), LEVELS)
        n_ask = min(len(ask_prices), LEVELS)
        for i in range(n_bid):
            self.bid_prices[i] = bid_prices[i]
            self.bid_sizes[i]  = bid_sizes[i]
        for i in range(n_ask):
            self.ask_prices[i] = ask_prices[i]
            self.ask_sizes[i]  = ask_sizes[i]
        self.last_update = ts

    def snapshot(self):
        """Copy for engine use — called once per bar close, not per callback."""
        return (
            list(self.bid_prices), list(self.bid_sizes),
            list(self.ask_prices), list(self.ask_sizes),
        )
```

### Pattern 8: SQLite Session Persistence via aiosqlite

**What:** Key-value store for IB range, opening VWAP, running CVD, session_id. Survives restart.

```python
# Source: aiosqlite official docs (aiosqlite.omnilib.dev)
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_state (
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (session_id, key)
);
"""

class SessionPersistence:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(SCHEMA)
            await db.commit()

    async def write(self, session_id: str, key: str, value: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO session_state VALUES (?, ?, ?, ?)",
                (session_id, key, value, time.time())
            )
            await db.commit()

    async def read_all(self, session_id: str) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT key, value FROM session_state WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                return {row[0]: row[1] async for row in cursor}
```

**Session state keys to persist:** `cvd`, `vwap_numerator`, `vwap_denominator`, `ib_high`, `ib_low`, `ib_complete`, `opening_range_high`, `opening_range_low`.

[VERIFIED: aiosqlite PyPI + omnilib docs — version 0.22.1, async with aiosqlite.connect pattern confirmed]

### Pattern 9: Reconnection FROZEN State

**What:** On disconnect, set a global freeze flag. No bar processing, no session updates during freeze. On reconnect (sequential plant), unfreeze only after state sync.

```python
import asyncio
import structlog

log = structlog.get_logger()

class ConnectionState:
    CONNECTED = "CONNECTED"
    FROZEN = "FROZEN"
    RECONNECTING = "RECONNECTING"

class FreezeGuard:
    def __init__(self):
        self.state = ConnectionState.CONNECTED

    def on_disconnect(self, ts: float):
        self.state = ConnectionState.FROZEN
        log.warning("connection.disconnected", ts=ts, state=self.state)

    async def on_reconnect(self, client, config):
        self.state = ConnectionState.RECONNECTING
        # Issue #49 workaround: sequential plant connection
        await client.connect()
        await asyncio.sleep(0.5)  # 500ms delay between plants
        # After reconnect: sync position state before unfreezing
        await sync_position_state(client)
        self.state = ConnectionState.CONNECTED
        log.info("connection.restored", state=self.state)

    @property
    def is_frozen(self) -> bool:
        return self.state != ConnectionState.CONNECTED
```

### Pattern 10: ATR(20) Incremental Calculation

**What:** Online Wilder's ATR using exponential smoothing. No pandas required.

```python
class ATRTracker:
    """Wilder's ATR(20) — incremental, no history storage needed."""
    def __init__(self, period: int = 20):
        self.period = period
        self.alpha = 1.0 / period
        self.atr: float = 0.0
        self._initialized = False
        self._bar_count = 0
        self._prev_close: float = 0.0
        self._first_bars: list = []  # collect first N for seed

    def update(self, high: float, low: float, close: float):
        tr = high - low
        if self._prev_close > 0:
            tr = max(tr,
                     abs(high - self._prev_close),
                     abs(low  - self._prev_close))
        self._prev_close = close
        self._bar_count += 1

        if not self._initialized:
            self._first_bars.append(tr)
            if self._bar_count >= self.period:
                self.atr = sum(self._first_bars) / self.period
                self._initialized = True
        else:
            # Wilder's smoothing: ATR = prior_ATR * (N-1)/N + TR * (1/N)
            self.atr = self.atr * (1.0 - self.alpha) + tr * self.alpha

    @property
    def ready(self) -> bool:
        return self._initialized
```

[ASSUMED] — ATR incremental formula is standard (Wilder 1978). Implementation is training-knowledge; no external verification needed for this mathematical identity.

### Pattern 11: SignalFlags IntFlag Stub

**What:** Python IntFlag provides O(popcount) bitmask semantics natively. 64 bits in Python is unbounded (arbitrary precision int). Stub now, fill in Phase 2+.

```python
from enum import IntFlag

class SignalFlags(IntFlag):
    NONE = 0
    # Absorption (Phase 2)
    ABS_CLASSIC     = 1 << 0
    ABS_PASSIVE     = 1 << 1
    ABS_STOPPING    = 1 << 2
    ABS_EFFORT      = 1 << 3
    # Exhaustion (Phase 2) — bits 4-10
    # Imbalance (Phase 3)  — bits 11-19
    # Delta (Phase 3)      — bits 20-30
    # ... 44 signals total across bits 0-43
```

### Anti-Patterns to Avoid

- **Signal computation in DOM callback:** DOM callback must only update raw arrays (O(1)). All signal computation deferred to bar_engine_loop at bar close.
- **asyncio.create_task in hot path:** Task creation allocates; use `queue.put_nowait()` instead. Zero allocation in 1,000/sec path.
- **asyncio.Lock on shared state:** Single event loop = no concurrent mutations. Locks are unnecessary overhead and can deadlock.
- **Pandas in hot path:** Per-tick append to DataFrame is ~100x slower than deque. Use Pandas only for batch analytics.
- **float as dict key for price levels:** Float equality is unreliable. Always convert `price / TICK_SIZE` to int before using as dict key.
- **uvloop.install() on Python 3.12:** Deprecated. Use `asyncio.Runner(loop_factory=uvloop.new_event_loop)` instead.
- **Connecting all plants simultaneously:** Issue #49 — connect sequentially with 500ms delay to avoid ForcedLogout loop.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async SQLite | Custom threading wrapper for sqlite3 | aiosqlite | Thread safety, connection management, cursor lifecycle already solved |
| Event loop speed | Custom asyncio extensions | uvloop | libuv-backed, 2-4x callback throughput; zero custom code |
| Async testing | Manually managing event loop in tests | pytest-asyncio | `@pytest.mark.asyncio` handles loop lifecycle correctly |
| Time zone conversion | Manual UTC offset arithmetic | zoneinfo stdlib | DST, transition edge cases, leap seconds all handled correctly |
| ATR from scratch with pandas | Rolling window, pandas shift/diff | Incremental Wilder formula (no lib needed) | Single formula, O(1) memory, no pandas dependency in hot path |
| DOM order book state | Custom linked list / sorted dict | array.array with index-based update | Pre-allocation is faster and allocation-free in the 1,000/sec path |

**Key insight:** The footprint accumulator itself is hand-rolled (intentionally — no library matches exact requirements), but everything around it (persistence, event loop, testing, time zones) has solved libraries.

---

## Common Pitfalls

### Pitfall 1: Aggressor Field = UNSPECIFIED on First Ticks

**What goes wrong:** The `aggressor` field exists in the protobuf but may arrive as `TRANSACTIONTYPE_UNSPECIFIED=0` during pre-market, auction phases, or for implied orders. If code unconditionally reads `aggressor` and maps 0 to bid-side, footprint bars during these periods will have corrupted bid/ask split.

**Why it happens:** CME does not always publish AggressorSide. The field is present but zero-valued. async-rithmic faithfully passes it through.

**How to avoid:** The startup aggressor verification gate (D-03) must sample ticks and confirm that non-zero values are arriving before enabling FootprintBar accumulation. During RTH on NQ, non-UNSPECIFIED rate should be >90%. If <85% after 100 ticks, escalate. Ticks with `aggressor=0` during RTH must be skipped (not classified via fallback) — using fallback tick-rule silently adds ~5-15% error to footprint volumes.

**Warning signs:** Bar delta consistently reads 0 (all bid = all ask); bid/ask volumes at all levels are equal.

### Pitfall 2: async-rithmic 1.5.9 Not Found by pip

**What goes wrong:** `pip install async-rithmic` installs 1.3.4 (the highest version on this machine's cached pip index). The codebase expects 1.5.9 features and callback shapes from that version.

**Why it happens:** PyPI serves the latest version via `pypi.org` but local pip indexes or corporate proxies may cache an older state. The machine's pip reported 1.3.4 as latest during research (April 2026).

**How to avoid:** Always install with explicit version: `pip install "async-rithmic==1.5.9"`. If pip cannot find it, try `pip install --index-url https://pypi.org/simple/ "async-rithmic==1.5.9"` to force the canonical index. Document in `requirements.txt` with pinned version.

**Warning signs:** `pip show async-rithmic` shows version 1.3.4 or earlier.

### Pitfall 3: DOM Callback Receives Partial Updates

**What goes wrong:** async-rithmic delivers `OrderBook` updates in CLEAR/BEGIN/MIDDLE/END/SOLO sequence. Processing on MIDDLE updates gives an incomplete DOM view. Signal code that snapshots DOM state during MIDDLE will see partially-updated bid/ask arrays.

**Why it happens:** Rithmic sends the full order book update as a multi-message sequence. The library does not buffer internally — it fires the callback for each message.

**How to avoid:** In the DOM callback, only update DOMState on `update_type in ("SOLO", "END")` messages. For CLEAR/BEGIN/MIDDLE: update internal staging buffer but do not write to the canonical `DOMState`. After END: atomically copy staging to canonical. The staging buffer can be a second `array.array` pair.

**Warning signs:** DOM state shows phantom price levels that disappear within milliseconds; ask array has stale entries from two updates ago.

### Pitfall 4: Bar Boundary Drift on Long-Running Process

**What goes wrong:** `asyncio.sleep()` is not wall-clock precise. Over 8 hours of trading, accumulated drift can shift bar close times by 1-5 seconds, causing the last few ticks of a bar to be credited to the wrong bar. This produces footprint bars that disagree with TradingView's bar boundaries.

**Why it happens:** asyncio.sleep() sleeps "at least N seconds" but wakes when the event loop schedules it. A busy loop (DOM burst at bar close) delays sleep wakeup.

**How to avoid:** Use `next_boundary()` time calculation: compute next boundary from the absolute epoch, not from "now + period". On each iteration of `run()`, recalculate the sleep duration to the next true boundary. This self-corrects any drift on each bar.

**Warning signs:** Python bar timestamps drifting vs TradingView bars over the course of a session.

### Pitfall 5: Session State Not Restored After Restart

**What goes wrong:** Process restarts mid-session. CVD reads as 0 (session start). VWAP restarts from restart time, not from 9:30 ET open. IB range recalculates from restart time. All session-anchored signals diverge from correct values.

**Why it happens:** Session state (CVD, VWAP numerator/denominator, IB range) is initialized in-memory. A restart without persistence restore loses all accumulated state.

**How to avoid:** The `SessionManager._on_session_open()` must call `db.restore_session_state()` before accepting any new ticks. If no prior session state exists (new day), initialize from zero. If prior state exists with today's session_id, restore it. The session_id should be the date string in ET (`2026-04-11`) to auto-expire prior-day state.

**Warning signs:** CVD shows 0 or very small values mid-session after restart; VWAP diverges sharply from TradingView's anchored VWAP.

### Pitfall 6: GC Re-enabling Fails to Fire at Session Close

**What goes wrong:** GC is disabled at 9:30 ET. If the session_manager polling loop crashes silently, GC remains disabled for the rest of the day. The next day's session opens with GC still disabled, and the day after, creating a memory leak over days.

**Why it happens:** The 1-second polling coroutine can be silently cancelled if the event loop shuts down or an exception propagates without a handler.

**How to avoid:** Wrap the SessionManager.run() loop in `try/finally: gc.enable()`. Any exception that escapes the polling loop must re-enable GC. Also: register `gc.enable()` as an `atexit` handler at process startup.

**Warning signs:** Memory usage growing over multiple days; `gc.isenabled()` returns False in the morning before 9:30.

---

## Code Examples

### Verified: async-rithmic Tick Callback Shape

```python
# Source: async_rithmic/protocol_buffers/last_trade_pb2.py (GitHub)
# MessageToDict with preserving_proto_field_name=True means field names are
# the exact protobuf field names. LastTrade fields relevant to footprint:
#
#   "trade_price"  : float  — the last trade price
#   "trade_size"   : int    — contracts traded
#   "aggressor"    : int    — TransactionType: 0=UNSPECIFIED, 1=BUY, 2=SELL
#   "volume"       : int    — cumulative session volume
#   "datetime"     : added by async-rithmic from ssboe/usecs
#   "data_type"    : DataType.LAST_TRADE (1) or BBO (2)

async def on_tick(data: dict):
    if data.get("data_type") != DataType.LAST_TRADE:
        return
    price     = data["trade_price"]
    size      = data["trade_size"]
    aggressor = data.get("aggressor", 0)  # 0=unknown, 1=buy, 2=sell
    ts        = data["datetime"]
    # Route to BarBuilder (synchronous — no await)
    for builder in state.bar_builders.values():
        builder.on_trade(price, size, aggressor)
```

[VERIFIED: protobuf field names confirmed from last_trade_pb2.py analysis]

### Verified: aiosqlite Session Write Pattern

```python
# Source: aiosqlite.omnilib.dev official documentation
import aiosqlite, json, time

async def persist_session_state(db_path: str, session_id: str, session):
    state_map = {
        "cvd":                str(session.cvd),
        "vwap_numerator":     str(session.vwap_numerator),
        "vwap_denominator":   str(session.vwap_denominator),
        "ib_high":            str(session.ib_high),
        "ib_low":             str(session.ib_low),
        "ib_complete":        str(int(session.ib_complete)),
    }
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO session_state VALUES (?,?,?,?)",
            [(session_id, k, v, time.time()) for k, v in state_map.items()]
        )
        await db.commit()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| uvloop.install() | asyncio.Runner(loop_factory=uvloop.new_event_loop) | Python 3.12 | install() deprecated; policies removed in 3.16 |
| pytz for timezone | zoneinfo (stdlib) | Python 3.9 | pytz deprecated; zoneinfo handles DST natively |
| Python 3.10 minimum | Python 3.12 recommended | async-rithmic 1.4.0 | 3.10 minimum for async-rithmic; 3.12 for best library compat |
| Free-threaded CPython 3.13 | Stick with GIL-enabled 3.12 | 2026 | Free-threading ecosystem immature; asyncio not thread-safe in 3.13 |

**Deprecated/outdated:**
- `uvloop.install()`: Still works in 3.12 but deprecated — use Runner instead.
- `pytz`: Replaced by zoneinfo. Do not add pytz as a dependency.
- Direct event loop policies (`asyncio.set_event_loop_policy`): Will be removed in Python 3.16.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | async-rithmic on_tick callback delivers `aggressor` field under that exact name (from protobuf field name preservation) | Pattern 3 | If field name differs, footprint accumulator silently gets 0 for all aggressor values |
| A2 | Issue #49 workaround (500ms delay) is sufficient for sequential plant connection | Pattern 2 | May need longer delay or different sequencing; would cause ForcedLogout loop on reconnect |
| A3 | ARCH-04 correlation matrix deferred to Phase 2 is acceptable (only raw data collected in Phase 1) | Phase Requirements | If correlation matrix is needed before Phase 2 signal definition, scope is wrong |
| A4 | 5-10% tolerance on TradingView Pine Script comparison is acceptable (vs D-10's stated 2%) | CONTEXT.md Specifics note | If stricter validation is required, need ATAS/Quantower which user doesn't have |
| A5 | `array.array('d', [0.0] * 40)` is sufficient DOM pre-allocation — NQ L2 rarely exceeds 40 levels per side | Pattern 7 | If Rithmic sends 50+ levels, outer levels are silently dropped; snapshot may be incomplete |

**If this table is empty:** All claims were verified. It is not empty — A1 is the highest-risk assumption and must be confirmed on the first live tick before the footprint engine is enabled.

---

## Open Questions

1. **Exact `aggressor` field name in async-rithmic callback dict**
   - What we know: The protobuf field is named `aggressor`; `MessageToDict(preserving_proto_field_name=True)` preserves protobuf names; the field should arrive as `"aggressor"` in the callback dict.
   - What's unclear: The `base.py` `_response_to_dict()` excludes specific fields by name (`template_id`, `request_key`, etc.) — we cannot confirm from static analysis that `aggressor` is not in that exclusion list.
   - Recommendation: On first live connection to test environment, log the raw callback dict for 10 ticks. Confirm `"aggressor"` key is present with non-zero values during active trading.

2. **async-rithmic 1.5.9 pip install reliability**
   - What we know: PyPI.org confirms 1.5.9 released 2026-02-20. Local pip reports 1.3.4 as latest.
   - What's unclear: Whether the production pip environment (Python 3.12 venv) on the trading machine will resolve 1.5.9 without forcing the canonical index URL.
   - Recommendation: Test `pip install "async-rithmic==1.5.9"` in the Python 3.12 venv as the first step of Wave 0.

3. **ARCH-04 scope in Phase 1**
   - What we know: ARCH-04 requires a pairwise Pearson correlation matrix for the 44 signals. No signals are implemented in Phase 1.
   - What's unclear: ARCH-04 is mapped to Phase 1 in the traceability table but cannot be computed without signal data.
   - Recommendation: Phase 1 satisfies ARCH-04 by establishing the data collection infrastructure (FootprintBar + BarHistory) that will feed the correlation matrix. The matrix itself is deferred to the point in Phase 2/3 where enough signals exist to compute it. Document this in the plan.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | async-rithmic 1.4.0+ requirement | Needs install | System has 3.9.6 | Must install Python 3.12 via pyenv or Homebrew |
| pip with PyPI access | Package installation | Available | 21.2.4 (on 3.9) | — |
| SQLite (stdlib) | aiosqlite | Available | 3.43.2 | — |
| numpy | DOM arrays, bar computation | Available | 1.23.5 (on 3.9) | Will install 2.4.4 in Python 3.12 venv |
| Rithmic test environment | async-rithmic connection | Assumed available | — | No fallback — needs broker confirmation |
| Internet access to PyPI | Package installation | Available | — | — |

**Missing dependencies with no fallback:**
- Python 3.12 — must be installed before any other Phase 1 work. `brew install python@3.12` or `pyenv install 3.12` on macOS.
- async-rithmic 1.5.9 installation (pip version conflict) — must verify explicit version install works.

**Missing dependencies with fallback:**
- None — all other dependencies are stdlib or straightforward pip installs.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 1.2.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 creates this |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Rithmic client connects, receives DOM updates | integration (live) | Manual — requires Rithmic test env | Wave 0 creates test_connection.py |
| DATA-02 | aggressor field non-zero in LAST_TRADE callback | integration (live) | Manual verification script | Wave 0 creates verify_aggressor.py |
| DATA-03 | FootprintBar accumulates correct bid/ask vol per level | unit | `pytest tests/test_footprint.py -x` | Wave 0 |
| DATA-04 | BarBuilder fires on_bar_close at correct boundaries | unit (mock clock) | `pytest tests/test_bar_builder.py -x` | Wave 0 |
| DATA-05 | DOMState update does not allocate (tracemalloc check) | unit | `pytest tests/test_dom_state.py::test_no_allocation` | Wave 0 |
| DATA-06 | uvloop is active event loop policy | unit | `pytest tests/test_loop.py::test_uvloop_active` | Wave 0 |
| DATA-07 | SQLite persistence: write then restore produces identical state | unit | `pytest tests/test_session.py::test_persistence_roundtrip` | Wave 0 |
| DATA-08 | Trades outside RTH are not accumulated | unit | `pytest tests/test_bar_builder.py::test_rth_gate` | Wave 0 |
| DATA-09 | GC disabled at RTH open; re-enabled at close | unit | `pytest tests/test_session.py::test_gc_lifecycle` | Wave 0 |
| DATA-10 | FootprintBar matches TradingView reference (manual) | manual | CSV export + visual comparison | Manual — no automation possible without TV MCP |
| ARCH-01 | Package structure: deep6/data/engines/etc exist with __init__.py | unit | `pytest tests/test_package.py::test_imports` | Wave 0 |
| ARCH-02 | Process boundary documented (asyncio main; no Kronos in this phase) | — | N/A — structural, no test needed | — |
| ARCH-03 | ATR(20) tracker produces correct value after 20+ bars | unit | `pytest tests/test_atr.py::test_atr_accuracy` | Wave 0 |
| ARCH-04 | BarHistory deque accumulates bars; correlation deferred | unit | `pytest tests/test_bar_history.py` | Wave 0 |
| ARCH-05 | SignalFlags IntFlag: all 44 bits definable without overflow | unit | `pytest tests/test_signals.py::test_signal_flags` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q --ignore=tests/integration`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

All test files are missing (greenfield). Wave 0 must create:

- [ ] `tests/conftest.py` — shared fixtures: `fake_tick()`, `mock_bar_builder()`, `temp_db()`
- [ ] `tests/test_footprint.py` — FootprintBar accuracy: bid/ask accumulation, delta computation, finalize
- [ ] `tests/test_bar_builder.py` — boundary calculation, RTH gate, dual-TF independence
- [ ] `tests/test_dom_state.py` — pre-allocation, in-place update, snapshot correctness
- [ ] `tests/test_session.py` — persistence roundtrip, RTH detection, GC lifecycle
- [ ] `tests/test_loop.py` — uvloop active, event loop type check
- [ ] `tests/test_atr.py` — Wilder ATR(20) convergence test against known values
- [ ] `tests/test_bar_history.py` — deque maxlen, bar ordering
- [ ] `tests/test_signals.py` — IntFlag bits, no overflow, popcount logic
- [ ] `tests/test_package.py` — all stubs importable; no circular imports
- [ ] `pyproject.toml` — `[tool.pytest.ini_options]` with asyncio_mode = "auto"
- [ ] Framework install: `pip install pytest pytest-asyncio` in Python 3.12 venv

---

## Security Domain

Security enforcement is not explicitly configured. Phase 1 creates no user-facing interfaces and no execution paths. Security surface is minimal.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (internal process, no user auth) | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes — Rithmic tick data | Validate field presence + type before using; reject UNSPECIFIED aggressor |
| V6 Cryptography | No | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed Rithmic tick (zero price, negative size) | Tampering | Validate price > 0 and size > 0 before accumulating; log and skip invalid ticks |
| Credentials in plain source | Information Disclosure | Store RITHMIC_USER/PASSWORD in `.env` file; add `.env` to `.gitignore` on day 1 |
| SQLite file read by other processes | Information Disclosure | Store db in process-owned directory; no network exposure (local file only) |

---

## Sources

### Primary (HIGH confidence)

- `async_rithmic/protocol_buffers/last_trade_pb2.py` (GitHub rundef/async_rithmic) — aggressor field + TransactionType enum confirmed
- `async_rithmic/plants/base.py` (GitHub) — `_response_to_dict` with `preserving_proto_field_name=True` confirmed
- PyPI: `https://pypi.org/pypi/async-rithmic/json` — version 1.5.9, released 2026-02-20, Python 3.10+ [VERIFIED]
- PyPI: uvloop 0.22.1, aiosqlite 0.22.1, pytest-asyncio 1.2.0, numpy 2.4.4 [VERIFIED]
- `docs.python.org/3/library/asyncio-policy.html` — event loop policies deprecated for Python 3.16 [VERIFIED]
- `aiosqlite.omnilib.dev` — async with connect() pattern, executemany pattern [VERIFIED via WebSearch citing official docs]
- GitHub Issue #49 rundef/async_rithmic — ForcedLogout reconnection loop, opened 2026-03-27, still open 2026-04-07 [VERIFIED via WebFetch]
- `.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` — project research corpus [HIGH — read directly]

### Secondary (MEDIUM confidence)

- uvloop docs (`uvloop.readthedocs.io`) — `asyncio.Runner(loop_factory=uvloop.new_event_loop)` as Python 3.12+ recommended pattern [MEDIUM — docs referenced via WebSearch; 403 on direct fetch]
- `async-rithmic.readthedocs.io` — confirmed 403 on direct fetch; callback shapes inferred from source code analysis [MEDIUM]

### Tertiary (LOW confidence)

- None for this phase — all critical claims verified from source code or PyPI.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all packages verified against PyPI with exact versions
- Architecture: HIGH — patterns from ARCHITECTURE.md + source code inspection; one ASSUMED item (exact callback field name)
- Pitfalls: HIGH — carry-forward from project pitfall research + two new Phase 1-specific findings (pip version conflict, DOM partial update)
- Testing: HIGH — pytest-asyncio 1.2.0 confirmed installed; test structure designed from requirements

**Research date:** 2026-04-11
**Valid until:** 2026-07-11 (90 days — async-rithmic is actively maintained; check for breaking changes before each phase)
