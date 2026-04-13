# Architecture Patterns: DEEP6 v2.0 — Python Footprint Auto-Trading System

**Domain:** Real-time footprint auto-trading system (NQ futures, Python, Rithmic L2)
**Researched:** 2026-04-11
**Overall confidence:** HIGH (asyncio patterns, component design) / MEDIUM (async-rithmic specifics, Kronos latency)
**Milestone context:** Python architecture from scratch — 1,000 DOM callbacks/sec, 44 signals, direct execution

---

## Recommended Architecture

### System Boundary Map

```
┌──────────────────────────────────────────────────────────────────────────┐
│  DEEP6 Python Process (macOS, Python 3.12+, uvloop event loop)           │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  main.py  (asyncio.run entry point)                              │    │
│  │  - Creates RithmicClient, starts event loop                      │    │
│  │  - Launches long-lived tasks via asyncio.gather()                │    │
│  └───┬─────────────────────────────────────────────────────────────┘    │
│      │                                                                    │
│      ├── Task: dom_feed_loop()     ← async-rithmic TickerPlant consumer  │
│      ├── Task: tick_feed_loop()    ← async-rithmic TickerPlant consumer  │
│      ├── Task: bar_engine_loop()   ← bar close + signal computation      │
│      ├── Task: execution_loop()    ← order management + fills            │
│      ├── Task: gex_poll_loop()     ← FlashAlpha HTTP poll (1/min)        │
│      ├── Task: api_server()        ← FastAPI + WebSocket dashboard feed  │
│      └── Task: kronos_result_consumer() ← picks up ML results from pipe │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Shared In-Process State (no locks — single event loop thread)   │    │
│  │                                                                   │    │
│  │  DOMState        — live bid/ask arrays (40+ levels, updated/sec) │    │
│  │  TickBuffer      — ring buffer of last N trades                   │    │
│  │  FootprintBar    — current bar's bid/ask volume per price level   │    │
│  │  BarHistory      — deque of closed FootprintBar objects (N bars)  │    │
│  │  SessionContext  — VWAP, IB, day type, POC, session VP            │    │
│  │  ZoneRegistry    — all active LVN/HVN/absorption/GEX zones        │    │
│  │  PositionState   — current position, fills, risk counters         │    │
│  │  ScorerState     — latest ScorerResult, signal snapshot           │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Signal Engines (plain Python classes, called synchronously       │    │
│  │  inside bar_engine_loop — no threading, no locks needed)          │    │
│  │                                                                   │    │
│  │  E1 FootprintEngine    E2 TrespassEngine   E3 CounterspoofEngine  │    │
│  │  E4 IcebergEngine      E5 MicroEngine      E6 VPCtxEngine         │    │
│  │  E7 MLQualityEngine    E8 CvdEngine        E9 AuctionFSM          │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Scorer → ExecutionGateway                                        │    │
│  │  44-signal weighted cascade → ScorerResult → risk check → order   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
         │ multiprocessing.Pipe (one-way)
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Kronos Process (separate Python process, GPU-capable)               │
│  - Receives OHLCV batch request over pipe                            │
│  - Runs KronosPredictor.predict() (50ms on GPU, 200ms on CPU)        │
│  - Sends E10BiasResult back over pipe                                │
│  - No event loop — pure compute subprocess                           │
└──────────────────────────────────────────────────────────────────────┘
         │ REST + WebSocket (localhost)
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (same process, different uvicorn worker or          │
│  same asyncio event loop via asyncio.create_task)                    │
│  - /api/signals — historical signal feed                             │
│  - /api/regime  — ML regime classification                           │
│  - /ws/live     — WebSocket stream of ScorerResult to dashboard      │
│  - /api/optimize — XGBoost + Optuna parameter sweep trigger          │
└──────────────────────────────────────────────────────────────────────┘
         │ HTTP/WS (localhost:3000)
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Next.js Dashboard (browser)                                         │
│  - Signal performance, regime state, zone map, session replay        │
└──────────────────────────────────────────────────────────────────────┘

         [Separate tool — not integrated into signal pipeline]
┌──────────────────────────────────────────────────────────────────────┐
│  TradingView MCP (Claude Code sidecar, localhost:9222 CDP)           │
│  - Claude reads TV charts via Chrome DevTools Protocol               │
│  - Visual confirmation, Pine Script injection, screenshots           │
│  - Operates on-demand, not in the hot path                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Async Event Loop Design

### Single-Process, Single Event Loop — The Right Answer

**Verdict:** Single asyncio event loop, single Python process (except Kronos), uvloop for speed.

**Why not multi-process for everything:**
- Shared state (DOMState, BarHistory, ZoneRegistry) between processes requires IPC serialization — adds latency and complexity.
- The 1,000 DOM callbacks/sec workload is I/O-bound, not CPU-bound. asyncio handles I/O-bound concurrency without multiprocessing.
- Signal computation (44 signals per bar close) is CPU work, but it happens once per bar (~every few seconds), not 1,000x/sec. Bar close is non-latency-critical at the millisecond level.
- A single event loop means zero shared-state concurrency bugs. No locks. No races. No `asyncio.Lock()` needed for shared state that only the event loop touches.

**Why uvloop:**
- Drop-in replacement for the default asyncio event loop. 2-4x faster callback throughput. Reduces tail latency 50%+. Mandatory for 1,000 callbacks/sec with no measurable cost. Install: `pip install uvloop`. Install at entry: `uvloop.install()` before `asyncio.run()`.

**GIL reality for this workload:**
- 1,000 DOM callbacks/sec: each callback updates a dict/array — pure Python, microseconds of CPU per callback. GIL is held briefly, released, held. No GIL starvation. No contention.
- 44 signal computations at bar close: NumPy operations release the GIL. numpy-heavy engines (CVD regression, VP computations) are effectively parallel with I/O coroutines.
- Kronos inference: must run in a separate process (GPU-bound, blocks for 50-200ms). Use `multiprocessing.Process` + `multiprocessing.Pipe`.
- XGBoost inference: ~0.7ms single sample. Run via `loop.run_in_executor(process_pool, xgb_predict, features)` to avoid blocking the event loop.

**Why not threading for engines:**
- Threads share the GIL and require locking for shared state.
- Asyncio gives the same concurrency for I/O without locking complexity.
- Signal engines are called sequentially inside the bar_engine_loop coroutine — deterministic, no races, easier to debug.

### Long-Lived Task Structure

```python
async def main():
    uvloop.install()

    state = SharedState()  # DOMState, BarHistory, ZoneRegistry, etc.
    rithmic = RithmicClient(credentials)
    await rithmic.connect()

    await asyncio.gather(
        dom_feed_loop(rithmic, state),        # receives DOM updates, mutates DOMState
        tick_feed_loop(rithmic, state),       # receives trades, mutates TickBuffer
        bar_engine_loop(state),               # detects bar close, runs all 44 signals
        execution_loop(rithmic, state),       # watches ScorerResult, sends orders
        gex_poll_loop(state),                 # HTTP polls FlashAlpha every 60s
        api_server(state),                    # FastAPI lifespan task
        kronos_result_consumer(state),        # reads from Kronos pipe when result ready
    )

asyncio.run(main())
```

Each long-lived task runs as a coroutine. Tasks yield control with `await asyncio.sleep(0)` or `await queue.get()` — this is the cooperative scheduling point.

---

## Data Pipeline: Rithmic to Execution

### async-rithmic Plants (MEDIUM confidence — docs blocked, confirmed from search)

async-rithmic structures connections around Rithmic's four WebSocket plants:

| Plant | Responsibility | Key callbacks |
|-------|---------------|---------------|
| TickerPlant | Live tick data, L2 DOM streaming, time bars | `on_tick`, `on_best_bid_ask`, `on_order_book_update` |
| OrderPlant | Order submission, modification, cancellation | `on_order_update`, `on_order_fill` |
| HistoryPlant | Historical bars and ticks | `get_historical_time_bars()` |
| PnlPlant | Account P&L, position tracking | `on_pnl_update` |

Each plant = a separate WebSocket connection, multiplexed by asyncio concurrently.

### Hot Path: DOM Feed (1,000 callbacks/sec)

```
async-rithmic DOM callback fires
  → dom_feed_loop receives update (coroutine resumes)
  → DOMState.update(bid_prices, bid_volumes, ask_prices, ask_volumes)
       [array.array or numpy array, in-place update, no allocation]
  → DOMState.snapshot_for_engine()  [only on bar close, not every callback]
  → yield control (loop handles next callback)
```

Critical rule: **no signal computation in the DOM callback**. DOM callback only updates raw arrays. Signal computation is deferred to bar_engine_loop.

For E2 (TrespassEngine / DOM queue imbalance) and E3 (CounterspoofEngine): these engines read DOMState snapshots taken at the moment of bar close, not from inside the DOM callback. This is the correct Python equivalent of NT8's volatile double pattern — a shared in-process value that the event loop writes sequentially without races.

### Tick Path: Trade Feed

```
async-rithmic tick callback fires
  → tick_feed_loop receives trade (price, size, side, timestamp)
  → TickBuffer.append(trade)  [collections.deque(maxlen=N) — O(1) append]
  → FootprintBar.add_trade(trade)  [accumulate bid/ask vol at price level]
  → IcebergTracker.observe(trade, dom_state)  [update E4 iceberg state]
  → yield control
```

FootprintBar is the central per-bar accumulator. It holds a dict `{price_level: (bid_vol, ask_vol)}`. Updated in-place on every trade.

### Bar Close Path: Signal Computation

Bar close is detected one of two ways:
1. Subscribe to async-rithmic time bar feed — the library fires a callback when a bar closes.
2. Detect it from tick timestamps (bar boundary = seconds since midnight % bar_seconds == 0).

Prefer option 1 (time bar subscription) — cleaner, less edge-case code.

```
bar_engine_loop detects bar close:
  bar = FootprintBar.close_and_reset()   ← atomically captures, resets for next bar
  BarHistory.appendleft(bar)             ← deque of last 200 bars

  session = SessionContext.update(bar, BarHistory)
  dom_snap = DOMState.snapshot()         ← single read for all DOM engines

  # Engine cascade (sequential, synchronous — no await needed)
  e1 = E1FootprintEngine.run(bar, BarHistory, session)
  e2 = E2TrespassEngine.run(dom_snap)
  e3 = E3CounterspoofEngine.run(dom_snap)
  e4 = E4IcebergEngine.run(TickBuffer, dom_snap)
  e5 = E5MicroEngine.run(e1, e2, e4)
  e6 = E6VPCtxEngine.run(session, ZoneRegistry, e1)
  e7 = E7MLQualityEngine.run(bar, BarHistory)
  e8 = E8CvdEngine.run(BarHistory)
  e9 = E9AuctionFSM.transition(bar, BarHistory, session)
  e10 = state.latest_kronos_result        ← pre-computed, read from state

  ZoneRegistry.update(bar, e1, gex_levels)

  result = Scorer.score(e1,e2,e3,e4,e5,e6,e7,e8,e9,e10, ZoneRegistry, session)
  state.latest_scorer_result = result

  # Async hand-off to execution and dashboard (non-blocking)
  execution_queue.put_nowait(result)
  dashboard_broadcast(result)            ← asyncio.create_task or queue

  await asyncio.sleep(0)                 ← yield to other tasks
```

Bar close computation budget: all 44 signals must complete within ~100ms to leave headroom before the next bar's ticks arrive. With sequential Python and NumPy, 44 signals computed on in-memory arrays will finish in well under 10ms. The budget is not a concern for bar-close computation.

### Execution Path

```
execution_loop:
  result = await execution_queue.get()
  
  if result.score >= THRESHOLD and result.direction != 0:
    if not PositionState.has_open_position():
      risk_check = RiskGateway.check(result, PositionState)
      if risk_check.approved:
        order = build_order(result, risk_check)
        await rithmic.submit_order(order)    ← async-rithmic OrderPlant
        PositionState.pending_order = order
  
  # Fill updates come via on_order_fill callback → update PositionState
  # Stop/target management happens in execution_loop on each fill event
```

Latency budget for execution: async-rithmic order submission is a WebSocket write + protocol buffer encode — effectively network-latency-bound (~1-5ms round trip to Rithmic gateway). Python overhead adds < 1ms. Total signal-to-order latency: ~5-20ms. This is acceptable for footprint trading (not HFT tick-scalping).

---

## State Management

### Thread Safety Is a Non-Issue

Because all state lives in a single asyncio event loop, there is no concurrent mutation. The event loop runs one coroutine at a time. State transitions are atomic at the coroutine-switch boundary (every `await`). No `asyncio.Lock()` is needed for any of the state objects listed below.

**Exception:** The Kronos subprocess communicates via `multiprocessing.Pipe`. This is the one true concurrency boundary. Use `loop.run_in_executor(thread_pool, pipe.recv)` to await pipe data without blocking the event loop.

### State Objects

| State Object | Type | Updated By | Read By | Notes |
|---|---|---|---|---|
| `DOMState` | dataclass with `array.array` fields | `dom_feed_loop` | `bar_engine_loop` (snapshot) | In-place array update, no allocation |
| `TickBuffer` | `collections.deque(maxlen=1000)` | `tick_feed_loop` | `bar_engine_loop` | Ring buffer, O(1) append |
| `FootprintBar` (current) | dataclass with `dict[int, tuple]` | `tick_feed_loop` | `bar_engine_loop` | Reset on bar close |
| `BarHistory` | `collections.deque(maxlen=200)` | `bar_engine_loop` | All engines, Kronos feeder | Closed bars only |
| `SessionContext` | dataclass | `bar_engine_loop` | E6, Scorer | VWAP, IB, POC, day type |
| `ZoneRegistry` | custom class with list[Zone] | `bar_engine_loop` | E6, Scorer, dashboard | 5-state FSM per zone |
| `PositionState` | dataclass | `execution_loop` | `execution_loop`, risk | Fills, P&L, open position |
| `ScorerResult` (latest) | dataclass | `bar_engine_loop` | `execution_loop`, API | Written after each bar |
| `KronosResult` (latest) | dataclass | `kronos_result_consumer` | `bar_engine_loop` as e10 | May be 1+ bars stale — fine |
| `GEXLevels` | dataclass | `gex_poll_loop` | `bar_engine_loop` | Updated every 60s |

### FootprintBar Design

```python
@dataclass
class FootprintBar:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    # Per-price-level bid/ask volumes — use dict for sparse storage
    bid_vol: dict[int, float]   # key = price in ticks (int avoids float key errors)
    ask_vol: dict[int, float]
    total_vol: float
    delta: float                # ask_vol_total - bid_vol_total
    vpoc: int                   # price tick with highest total vol

    def add_trade(self, price_tick: int, size: float, is_ask: bool):
        if is_ask:
            self.ask_vol[price_tick] = self.ask_vol.get(price_tick, 0.0) + size
        else:
            self.bid_vol[price_tick] = self.bid_vol.get(price_tick, 0.0) + size
        self.total_vol += size
        self.delta += size if is_ask else -size
        if price_tick > self.high: self.high = price_tick
        if price_tick < self.low: self.low = price_tick
        self.close = price_tick
```

Use integer tick keys (price / tick_size rounded to int). Avoids float equality bugs. NQ tick size = 0.25, so price 18500.25 → tick key 74001. Store `tick_size` as class constant.

### DOMState Design

```python
@dataclass
class DOMState:
    # Pre-allocated arrays — no allocation on update
    bid_prices: array.array   # 'd' type, 40 levels
    bid_sizes: array.array
    ask_prices: array.array
    ask_sizes: array.array
    timestamp: float

    def snapshot(self) -> DOMSnapshot:
        # Copy for engine use — called once per bar, not per callback
        return DOMSnapshot(
            bid_prices=list(self.bid_prices),
            bid_sizes=list(self.bid_sizes),
            ask_prices=list(self.ask_prices),
            ask_sizes=list(self.ask_sizes),
            timestamp=self.timestamp,
        )
```

Pre-allocated `array.array` with 40 slots per side. Updates are in-place index assignments: `self.bid_prices[i] = price`. Zero allocation per callback — critical for the 1,000/sec hot path.

---

## Component Boundaries (Python Package Structure)

```
deep6/
├── __main__.py                  ← asyncio.run(main()), uvloop.install()
├── config.py                    ← all thresholds, instrument params, credentials
├── state/
│   ├── dom.py                   ← DOMState, DOMSnapshot
│   ├── footprint.py             ← FootprintBar, BarHistory
│   ├── session.py               ← SessionContext
│   ├── zones.py                 ← ZoneRegistry, Zone, ZoneType, ZoneFSM
│   └── position.py              ← PositionState, Fill, RiskCounters
├── data/
│   ├── rithmic.py               ← RithmicClient wrapper (async-rithmic)
│   ├── dom_feed.py              ← dom_feed_loop coroutine
│   ├── tick_feed.py             ← tick_feed_loop coroutine
│   ├── bar_builder.py           ← bar close detection, FootprintBar management
│   └── gex.py                   ← FlashAlpha HTTP poll coroutine
├── engines/
│   ├── base.py                  ← EngineResult dataclass, SignalFlags IntFlag
│   ├── e1_footprint.py          ← absorption, exhaustion, imbalance signals
│   ├── e2_trespass.py           ← DOM queue imbalance, logistic regression
│   ├── e3_counterspoof.py       ← Wasserstein-1, cancel detection
│   ├── e4_iceberg.py            ← native/synthetic iceberg detection
│   ├── e5_micro.py              ← Naive Bayes combination
│   ├── e6_vpctx.py              ← VP context, VWAP/IB/POC/GEX scoring
│   ├── e7_ml_quality.py         ← Kalman filter quality multiplier
│   ├── e8_cvd.py                ← multi-bar CVD divergence, linear regression
│   └── e9_auction.py            ← auction theory FSM
├── scoring/
│   ├── scorer.py                ← 44-signal cascade, zone bonuses, confluence
│   └── signals.py               ← SignalFlags (IntFlag enum, 64-bit compatible)
├── execution/
│   ├── gateway.py               ← ExecutionGateway (order build + submit)
│   ├── risk.py                  ← RiskGateway (checks, circuit breakers)
│   └── execution_loop.py        ← execution_loop coroutine
├── ml/
│   ├── kronos_process.py        ← Kronos subprocess (KronosPredictor)
│   ├── kronos_bridge.py         ← Pipe interface, kronos_result_consumer
│   ├── xgboost_regime.py        ← XGBoost regime classifier (run in executor)
│   └── feature_builder.py       ← feature vector construction from bar history
├── api/
│   ├── server.py                ← FastAPI app, lifespan, WebSocket endpoint
│   ├── routes.py                ← REST endpoints (signals, regime, optimize)
│   └── broadcaster.py           ← asyncio broadcast to WebSocket connections
└── backtesting/
    ├── databento_replay.py      ← MBO stream → FootprintBar reconstruction
    └── vectorbt_adapter.py      ← vectorbt integration, parameter sweep
```

### SignalFlags in Python

Python's `enum.IntFlag` is the equivalent of C#'s `[Flags] enum SignalFlags : ulong`. 64 bits is native in Python (no overflow).

```python
from enum import IntFlag

class SignalFlags(IntFlag):
    # Imbalance (bits 0-8)
    ImbSingle       = 1 << 0
    ImbStackedT1    = 1 << 1
    # ... (all 44 signals, same bit layout as v1 C# design)
    # Python int is arbitrary precision — no bit limit concern
```

### EngineResult in Python

```python
@dataclass(slots=True)
class EngineResult:
    score: float           # 0 to category max
    direction: int         # +1 bull, -1 bear, 0 neutral
    fired: SignalFlags     # bitmask of which signals fired
    category_mask: int     # which of 8 categories contributed
```

`slots=True` reduces per-instance memory 40-60% versus default `__dict__`. Matters when creating EngineResults at bar frequency across thousands of bars in backtesting.

---

## Kronos Integration Point

### Architecture Decision: Separate Process

Kronos inference blocks for 50ms (GPU) to 200ms (CPU). Running inside the asyncio event loop would stall all other coroutines for 50-200ms per inference — unacceptable (blocks DOM updates, kills execution responsiveness).

**Correct pattern:** Separate `multiprocessing.Process` with a bidirectional `multiprocessing.Pipe`.

```
Main Process                          Kronos Process
────────────────                      ──────────────────────
bar_engine_loop sees bar close        [idle, waiting on pipe.recv()]
  → if bar_count % KRONOS_INTERVAL == 0:
      → pipe.send(ohlcv_batch)       →  pipe.recv() → DataFrame
                                         predictor.predict(df)  [50-200ms]
                                     ←  pipe.send(BiasResult)
kronos_result_consumer:
  await loop.run_in_executor(
      thread_pool, pipe.recv         ← unblocks when result arrives
  )
  state.latest_kronos_result = result
```

`KRONOS_INTERVAL` = every N bars (e.g., every 5 bars). Kronos provides directional bias for the session, not a per-tick signal — staleness of 1-3 bars is acceptable.

Kronos subprocess uses `KronosPredictor(model, tokenizer, max_context=512).predict(df)`. The DataFrame format: `['open', 'high', 'low', 'close', 'volume']` from the last 512 bars. Use Kronos-small (24.7M params) for CPU, Kronos-base (102M) with GPU.

**Do NOT use `run_in_executor(process_pool, predict)` for Kronos.** ProcessPoolExecutor serializes arguments via pickle across processes on every call — inefficient for large tensors. A persistent subprocess with a Pipe keeps the model loaded in GPU memory permanently.

### Kronos Result as E10

```python
@dataclass
class KronosResult:
    bar_timestamp: float      # bar that triggered this inference
    direction: int            # +1 bullish, -1 bearish, 0 neutral
    confidence: float         # 0.0 to 1.0
    predicted_close: float    # Kronos predicted next-bar close
    freshness_bars: int       # how many bars ago this was computed
```

E10 degrades gracefully: if `freshness_bars > MAX_FRESHNESS` (e.g., > 10), treat direction as 0 (neutral). System operates without Kronos if GPU is unavailable.

---

## XGBoost Integration Point

XGBoost serves two different functions:

1. **E7 MLQualityEngine (real-time):** quality multiplier on bar close. Single-sample XGBoost prediction. ~0.7ms latency. Run via `loop.run_in_executor(thread_executor, xgb_model.predict, features)` — thread executor is correct here (XGBoost releases the GIL during C++ tree traversal).

2. **Regime classifier (background):** regime updates every few minutes from FastAPI trigger. Not in the hot path. Can use `ProcessPoolExecutor` or run synchronously in a background task.

---

## TradingView MCP — Architecture Decision

**TradingView MCP is NOT integrated into the signal pipeline.**

Rationale:
- MCP bridge operates via Chrome DevTools Protocol to TradingView Desktop. Round-trip latency is 100ms-1s (CDP screenshot, parse, respond).
- Signal pipeline requires deterministic, sub-100ms bar-close computation.
- TV charts reflect market data but lag behind the direct Rithmic feed.
- TV MCP is a human-workflow tool: Claude reads charts for visual confirmation, injects Pine Scripts, captures screenshots for analysis sessions.

**Correct integration point:** TV MCP is a separate Claude Code session. The human operator calls it for analysis. It does not receive callbacks from DEEP6. It does not feed into scoring.

**Possible future bridge (not v1):** DEEP6 could write signal snapshots to a file/Redis, and a TV MCP session could read them to annotate charts. Keep architecturally separate.

---

## FastAPI + Dashboard Architecture

FastAPI runs **inside the same process** as the trading engine, as an asyncio task. This is the correct pattern — no subprocess needed for the web server.

```python
# In main():
app = create_fastapi_app(state)
config = uvicorn.Config(app, host="127.0.0.1", port=8000, loop="none")
server = uvicorn.Server(config)
# server.serve() is an asyncio coroutine — add to gather()
await asyncio.gather(
    ...,
    server.serve(),  # FastAPI shares the same event loop
)
```

WebSocket broadcast pattern for dashboard:

```python
# broadcaster.py
class DashboardBroadcaster:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except:
                dead.add(ws)
        self._connections -= dead
```

Called from `bar_engine_loop` after each bar: `asyncio.create_task(broadcaster.broadcast(result.to_dict()))`. Non-blocking — task is scheduled but doesn't stall bar computation.

---

## Scalability Considerations

| Concern | Now (single NQ session) | Future (multi-instrument) |
|---------|------------------------|--------------------------|
| DOM callbacks | 1,000/sec handled by uvloop | Multiple instruments: still single loop, separate DOMState per instrument |
| Bar computation | <10ms sequential, no issue | Parallel via executor if needed |
| ZoneRegistry | In-memory dict, fast | Could migrate to Redis for persistence/replay |
| Kronos inference | 1 subprocess, 1 instrument | 1 subprocess per instrument (GPU memory permitting) |
| WebSocket clients | Broadcast to N connections | Add asyncio.Queue per client if fan-out becomes slow |
| Backtesting | Sequential replay | vectorbt vectorizes — does not use the live architecture |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking the Event Loop

**What:** Calling any blocking function (time.sleep, requests.get, synchronous file I/O, model.predict) directly inside a coroutine without executor wrapping.

**Why bad:** Freezes the entire event loop. All DOM callbacks stall. Orders don't fire. 50ms Kronos inference would block 50 bar ticks.

**Instead:** `await asyncio.sleep(0)` to yield. `await loop.run_in_executor(executor, blocking_fn, args)` for CPU work. `await asyncio.to_thread(fn, args)` for simple thread offload (Python 3.9+).

### Anti-Pattern 2: Signal Computation Inside DOM Callback

**What:** Running imbalance detection, E2/E3 engine logic inside the DOM callback coroutine (1,000x/sec).

**Why bad:** Signal computation takes 1-10ms. At 1,000 callbacks/sec you'd need 1,000-10,000ms of CPU per second — impossible. Destroys latency for everything else.

**Instead:** DOM callback only updates raw arrays. Signal computation runs once per bar close.

### Anti-Pattern 3: asyncio.Lock for Shared State

**What:** Wrapping shared state (DOMState, BarHistory, ZoneRegistry) in `asyncio.Lock()` out of habit.

**Why bad:** Unnecessary. The event loop is single-threaded. There are no concurrent mutations. Locks add overhead and can cause accidental deadlocks.

**Instead:** Design state mutations to occur only in designated loops (dom_feed_loop writes DOMState, bar_engine_loop writes everything else). Document ownership. No locks needed.

### Anti-Pattern 4: Creating Coroutines in Hot Path

**What:** `asyncio.create_task()` inside the DOM callback (1,000x/sec).

**Why bad:** Task creation allocates memory. 1,000 task objects per second adds GC pressure. GC pauses during trading sessions.

**Instead:** `put_nowait()` on a queue. Single consumer task processes queue items. Zero allocation in callback.

### Anti-Pattern 5: Kronos in the Event Loop

**What:** Running `predictor.predict(df)` directly as an asyncio task or via thread executor.

**Why bad:** Thread executor doesn't give Kronos GPU access correctly. 50-200ms blocks the thread. Async thread pool is still shared with other work.

**Instead:** Dedicated subprocess with permanent GPU model load, pipe-based communication.

### Anti-Pattern 6: Pandas DataFrames in the Hot Path

**What:** Using Pandas for per-tick accumulation (TickBuffer, DOMState updates).

**Why bad:** Pandas has ~10-100x overhead vs native Python structures for single-row operations. DataFrame append is especially slow.

**Instead:** `collections.deque`, `array.array`, plain `dict`, or `numpy` arrays for hot-path state. Use Pandas only for batch analytics (bar history aggregation, regime features, backtesting).

---

## Phase-Specific Architecture Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Rithmic connection | async-rithmic reconnection logic may require custom event handling during market hours | Implement exponential backoff wrapper, log all disconnects |
| Bar close detection | Off-by-one errors on bar boundary if detecting from ticks vs library time bars | Use async-rithmic's native time bar subscription |
| DOM array synchronization | async-rithmic may deliver partial DOM updates (not all 40 levels on every callback) | Track `last_seen_levels` per side, fill missing levels from previous state |
| Footprint accumulation | Trade side (bid hit vs ask lift) may require inference from price vs best bid/ask, not always explicit in tick data | Implement aggressor side detection: trade at ask price = ask-side aggression |
| Kronos subprocess crash | Subprocess dies on CUDA OOM or model load error — main process doesn't notice | Heartbeat ping from main process, auto-restart subprocess on failure |
| E7 XGBoost model not trained yet | E7 MLQualityEngine needs historical labeled data before first use | Design E7 to return neutral quality multiplier (1.0) when model not loaded |
| FastAPI in same process | Uvicorn startup may conflict with asyncio.gather if not configured for external event loop | Use `uvicorn.Config(loop="none")` and `server.serve()` as a coroutine |
| ZoneRegistry in backtesting | Live ZoneRegistry uses real-time state; backtesting needs deterministic replay | Separate ZoneRegistry class for backtesting that accepts replayed bar data |

---

## Sources

- async-rithmic library: https://github.com/rundef/async_rithmic (MEDIUM confidence — docs return 403, structure inferred from search results and library description)
- Rithmic plant architecture: https://www.quantlabsnet.com/post/deep-dive-into-high-frequency-trading-iquant-development-nfrastructure-api-constraints-a (MEDIUM confidence)
- Asyncio for trading patterns: https://medium.com/@trademamba/asyncio-for-algorithmic-trading-part-1-93327929aef6 (MEDIUM confidence)
- uvloop performance: https://github.com/MagicStack/uvloop (HIGH confidence — official repo)
- Python GIL and asyncio: https://shanechang.com/p/python-gil-asyncio-relationship/ (HIGH confidence — well-established Python behavior)
- XGBoost inference latency: https://medium.com/@kaige.yang0110/methods-to-boost-xgboost-model-inference-latency-94540cb170eb (MEDIUM confidence)
- Kronos inference API: https://github.com/shiyu-coder/Kronos (HIGH confidence — official repo, fetched successfully)
- Kronos latency benchmark (50ms A100): https://www.blog.brightcoding.dev/2026/04/10/kronos-the-revolutionary-ai-model-for-financial-markets (LOW confidence — single non-official source)
- FastAPI WebSocket patterns: https://fastapi.tiangolo.com/advanced/websockets/ (HIGH confidence — official docs)
- TradingView MCP bridge: https://github.com/tradesdontlie/tradingview-mcp (HIGH confidence — official repo)
- v1 NT8 architecture (carries forward — scoring, zones, signal flags): .planning-v1-nt8/research/ARCHITECTURE.md
