# Technology Stack

**Project:** DEEP6 v2.0 — Python Footprint Auto-Trading System
**Researched:** 2026-04-11
**Research Mode:** Ecosystem — Python-specific stack for Rithmic + Kronos + TradingView MCP
**Overall Confidence:** HIGH (all primary sources verified; latency benchmarks MEDIUM)

---

## Context

This is a greenfield Python build replacing NinjaTrader 8 / C#. All v1 domain research
(44 signals, absorption/exhaustion, LVN lifecycle, scoring, ML dimensions) carries forward
unchanged — only the implementation language changes. This document covers the Python-specific
stack for the seven key components identified in project requirements.

---

## Recommended Stack

### 1. Rithmic Data + Execution: async-rithmic

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| async-rithmic | 1.5.9 | Rithmic R\|Protocol via WebSocket + protobuf — L2 DOM, tick data, order execution | HIGH |
| Python | 3.12 | Runtime (async-rithmic requires 3.10+; 3.12 is the sweet spot for library compatibility) | HIGH |

**What async-rithmic provides:**
- Full Order Book (L2) streaming — 40+ price levels per side, identical feed to what NinjaTrader receives
- Live tick data and Best Bid/Offer (BBO) streaming
- Order management: market, limit, stop orders via ORDER_PLANT
- Historical tick and time bar data
- Automatic reconnection with configurable backoff (exponential + jitter via `ReconnectionSettings`)
- Multi-account support
- macOS native — pure Python WebSocket + protobuf, no C DLLs

**Connection setup pattern (from official docs):**

```python
from async_rithmic import RithmicClient, DataType

client = RithmicClient(
    user="your_username",
    password="your_password",
    system_name="Rithmic Test",  # or "Rithmic Paper Trading" or production
    app_name="DEEP6",
    app_version="2.0.0",
    uri="wss://rituz00100.rithmic.com:443",  # test environment
)
await client.connect()
```

**L2 Order Book subscription (dominant pattern for this system):**

```python
from async_rithmic import RithmicClient, DataType

async def on_order_book(update):
    # update.update_type values:
    # CLEAR_ORDER_BOOK  -- clear book state, new snapshot incoming
    # BEGIN             -- first of a set of updates (book not yet complete)
    # MIDDLE            -- middle of a set of updates
    # END               -- last of a set (book is now evaluable)
    # SOLO              -- single atomic update (book evaluable immediately)
    if update.update_type in ("SOLO", "END"):
        # Safe to process the book here
        process_dom_update(update)

client.on_order_book += on_order_book
await client.subscribe_to_market_data(
    security_code="NQM5",   # front month NQ
    exchange="CME",
    data_type=DataType.ORDER_BOOK,
)
```

**Tick data subscription (for footprint construction):**

```python
from async_rithmic import DataType, LastTradePresenceBits, BestBidOfferPresenceBits

async def on_tick(tick):
    if tick.data_type == DataType.LAST_TRADE:
        # tick.last_trade has: price, size, aggressor (buy/sell)
        accumulate_footprint(tick.last_trade.price, tick.last_trade.size,
                             tick.last_trade.aggressor)
    elif tick.data_type == DataType.BBO:
        update_bbo(tick.best_bid_offer.bid_price, tick.best_bid_offer.ask_price)

client.on_tick += on_tick
await client.subscribe_to_market_data("NQM5", "CME", DataType.LAST_TRADE)
await client.subscribe_to_market_data("NQM5", "CME", DataType.BBO)
```

**Order submission:**

```python
from async_rithmic import OrderType, TransactionType

# Market order
await client.submit_order(
    order_id="DEEP6_001",
    security_code="NQM5",
    exchange="CME",
    qty=1,
    order_type=OrderType.MARKET,
    transaction_type=TransactionType.BUY,
)

# Limit order
await client.submit_order(
    order_id="DEEP6_002",
    security_code="NQM5",
    exchange="CME",
    qty=1,
    order_type=OrderType.LIMIT,
    transaction_type=TransactionType.SELL,
    price=21500.00,
)
```

**Reconnection configuration:**

```python
from async_rithmic import ReconnectionSettings

client = RithmicClient(
    ...,
    reconnection_settings=ReconnectionSettings(
        max_retries=10,
        base_delay=1.0,       # seconds
        max_delay=60.0,
        backoff_factor=2.0,   # exponential
        jitter=True,
    )
)
```

**Access requirements:**
- Existing Rithmic broker account (same one used with NinjaTrader) — zero additional cost
- Must sign Rithmic Market Data Subscription Agreement (done via R|Trader once)
- Test environment (wss://rituz00100.rithmic.com) is free for development
- Broker must enable "API/plugin mode" (EdgeClear, Tradovate via Rithmic, AMP Futures all support this)

**Sources:**
- PyPI: https://pypi.org/project/async-rithmic/ (v1.5.9, released 2026-02-20)
- GitHub: https://github.com/rundef/async_rithmic
- Rithmic API page: https://www.rithmic.com/apis

---

### 2. Kronos E10 Bias Engine

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| Kronos-small | 24.7M params | Directional bias prediction from OHLCV (E10 signal) | MEDIUM |
| KronosTokenizer | base tokenizer | Converts OHLCV to hierarchical discrete tokens | MEDIUM |
| PyTorch | >=2.0 (via Kronos requirements) | Model runtime | HIGH |
| transformers | (via requirements.txt) | Model loading utilities | HIGH |

**Note:** Kronos is not pip-installable — it requires cloning the GitHub repo. The HuggingFace model weights (`NeoQuasar/Kronos-small`) are the official release.

**Installation:**

```bash
git clone https://github.com/shiyu-coder/Kronos.git
cd Kronos
pip install -r requirements.txt
```

**Loading and inference:**

```python
from model import Kronos, KronosTokenizer, KronosPredictor
import pandas as pd

# Load from HuggingFace Hub (downloads once, cached locally)
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")  # 24.7M params
predictor = KronosPredictor(model, tokenizer, max_context=512)
```

**OHLCV input format:**

```python
# x_df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume', 'amount']
# Minimum: ['open', 'high', 'low', 'close'] — volume and amount are optional
# Rows: historical K-lines, chronologically ordered, evenly spaced intervals

# For 1-minute NQ bars: 512 bars = ~8.5 hours of context
x_df = nq_bars_df[['open', 'high', 'low', 'close', 'volume']].tail(400)
x_timestamp = nq_bars_df['datetime'].tail(400)
y_timestamp = pd.date_range(start=last_bar_time, periods=10, freq='1min')

pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=10,   # predict 10 bars forward
    T=0.7,         # temperature: lower = more deterministic
    top_p=0.9,
    sample_count=3, # ensemble: average 3 autoregressive paths
)
# pred_df columns: open, high, low, close, volume, amount
# Use pred_df['close'] vs current close for directional bias
```

**Integration into signal pipeline:**

```python
def get_kronos_bias(pred_df, current_close: float) -> float:
    """Returns E10 score in [-1, 1]: positive = bullish bias, negative = bearish."""
    predicted_close = pred_df['close'].iloc[-1]  # end of forecast horizon
    magnitude = abs(predicted_close - current_close) / current_close
    direction = 1.0 if predicted_close > current_close else -1.0
    # Scale: small moves < 0.05% = weak signal; > 0.2% = strong signal
    strength = min(magnitude / 0.002, 1.0)
    return direction * strength
```

**Latency estimates:**

| Hardware | Model | Inference Time (1 prediction) |
|----------|-------|-------------------------------|
| A100 GPU | Kronos-base (102M) | ~50ms |
| RTX 3060 GPU | Kronos-small (24.7M) | ~80-150ms (estimated) |
| Apple Silicon M2 (MPS) | Kronos-small | ~200-400ms (estimated) |
| CPU only (no GPU) | Kronos-small | ~500ms-2s (estimated) |
| CPU only | Kronos-mini (4.1M) | ~100-200ms (estimated) |

**Confidence note:** A100 latency (~50ms for base) is from official article. RTX 3060 / M2 / CPU figures are estimated based on model size ratios and general GPU inference patterns — treat as LOW confidence until benchmarked on your hardware.

**Recommendation for DEEP6:** Use Kronos-small (24.7M) on Apple Silicon with MPS backend. Kronos runs inference once per completed bar (1-minute or 5-minute resolution), not on every tick — so 200-400ms per inference is acceptable. The bottleneck is DOM callbacks, not Kronos.

**Key architecture decision:** Run Kronos in a dedicated asyncio task that wakes up on each bar close, computes the E10 prediction in a thread executor (to avoid blocking the event loop), and updates a shared `E10_bias` value that the signal engine reads.

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

kronos_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kronos")

async def kronos_bar_task(predictor, bar_buffer, e10_state):
    """Wakes on each bar close, updates E10 bias without blocking DOM loop."""
    while True:
        await bar_buffer.bar_close_event.wait()
        loop = asyncio.get_event_loop()
        bias = await loop.run_in_executor(
            kronos_executor,
            run_kronos_inference,  # synchronous call
            bar_buffer.get_recent_bars(400),
        )
        e10_state.update(bias)
```

**Sources:**
- GitHub: https://github.com/shiyu-coder/Kronos
- HuggingFace: https://huggingface.co/NeoQuasar/Kronos-small
- arXiv paper: https://arxiv.org/abs/2508.02739
- BrightCoding guide (2026-04-10): https://www.blog.brightcoding.dev/2026/04/10/kronos-the-revolutionary-ai-model-for-financial-markets

---

### 3. TradingView MCP

| Technology | Stars | Purpose | Confidence |
|------------|-------|---------|------------|
| tradingview-mcp (tradesdontlie) | ~1.7K | Claude Code ↔ TradingView Desktop bridge via CDP | HIGH |
| Chrome DevTools Protocol | — | Underlying mechanism for chart inspection + JS injection | HIGH |

**What it provides (78 tools across categories):**

**Chart reading:**
- `chart_get_state` — symbol, timeframe, all indicator names/IDs (~500 bytes)
- `quote_get` — current OHLC + volume
- `data_get_ohlcv` — full price bars (use `summary: true` for compact mode)
- `data_get_study_values` — read any built-in indicator values (RSI, MACD, EMA, etc.)
- `data_get_pine_lines` — horizontal levels from custom Pine indicators
- `data_get_pine_labels` — text annotations with price from Pine
- `data_get_pine_boxes` — price zones as {high, low} pairs
- `capture_screenshot` — full, chart, or strategy_tester regions

**Pine Script development:**
- `pine_set_source` — inject Pine Script into TradingView editor
- `pine_smart_compile` — compile with auto-detection + error report
- `pine_get_errors` — read compilation errors
- `pine_get_console` — read log.info() output
- `pine_save` — save to TradingView cloud

**Chart control:**
- `chart_set_symbol`, `chart_set_timeframe`, `chart_set_type`
- `chart_scroll_to_date` — jump to date for replay
- `pane_set_layout` — configure multi-pane grid (2x2, etc.)

**Streaming (CLI):**
```bash
tv stream quote       # price tick monitoring
tv stream lines --filter "NY Levels"  # watch specific Pine indicator levels
tv stream tables --filter Profiler    # table data
```

**Claude Code MCP configuration (~/.claude/.mcp.json or .mcp.json in project root):**

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "node",
      "args": ["/path/to/tradingview-mcp/src/server.js"]
    }
  }
}
```

**Setup steps:**

```bash
# 1. Clone and install
git clone https://github.com/tradesdontlie/tradingview-mcp.git
cd tradingview-mcp
npm install

# 2. Launch TradingView Desktop with debugging enabled (macOS)
./scripts/launch_tv_debug_mac.sh
# Equivalent manual: /Applications/TradingView.app/Contents/MacOS/TradingView \
#   --remote-debugging-port=9222

# 3. Verify connection in Claude Code
# "Use tv_health_check to verify TradingView is connected"
```

**How it works:** Chrome DevTools Protocol (CDP) on `localhost:9222`. Same mechanism used by VS Code, Slack, Discord for local debugging. Does NOT connect to TradingView servers — all data stays on your machine. Requires a valid TradingView subscription (it does not bypass paywalls).

**DEEP6 workflow use case:**
1. Claude reads chart state + Pine Script indicator levels from the Bookmap Liquidity Mapper (absorption/exhaustion zones)
2. Claude reads OHLCV history to visually validate signals
3. Claude injects modified Pine Script thresholds during parameter optimization sessions
4. Claude uses replay mode for step-by-step visual review of historical trades

**Sources:**
- GitHub: https://github.com/tradesdontlie/tradingview-mcp
- Setup guide: https://github.com/tradesdontlie/tradingview-mcp/blob/main/SETUP_GUIDE.md
- PulseMCP listing: https://www.pulsemcp.com/servers/hilmituncay-tradingview-mcp

---

### 4. Databento Python SDK (Backtesting Data)

| Technology | Version | Purpose | Cost | Confidence |
|------------|---------|---------|------|------------|
| databento | latest | MBO (L3) historical NQ data for backtesting; live MBO as independent validation feed | $179/mo | HIGH |

**What databento provides for this project:**
- MBO (Market-by-Order, L3) = every individual order event (add, modify, cancel) at every price level
- Full order book reconstructibility from MBO — gives you all 40+ levels in historical replay
- Nanosecond timestamps from CME colocation
- Live and historical APIs share the same interface — one codebase for both
- NQ continuous symbol: `NQ.c.0` (front-month roll handled automatically)

**Live MBO subscription (NQ front month):**

```python
import databento as db

live = db.Live(key="YOUR_API_KEY")

live.subscribe(
    dataset="GLBX.MDP3",   # CME Globex
    schema="mbo",
    stype_in="continuous",
    symbols="NQ.c.0",
    snapshot=True,          # receive initial book state before streaming
)

for record in live:
    if isinstance(record, db.MBOMsg):
        if record.flags & db.RecordFlags.F_SNAPSHOT:
            # Initial book state — rebuild from scratch
            book.process_snapshot(record)
        else:
            # Incremental update
            book.apply(record)
```

**Historical replay (for backtesting):**

```python
import databento as db

client = db.Historical(key="YOUR_API_KEY")
# Equivalent to env var: DATABENTO_API_KEY

data = client.timeseries.get_range(
    dataset="GLBX.MDP3",
    symbols="NQ.c.0",
    stype_in="continuous",
    schema="mbo",
    start="2025-01-02T14:30",
    end="2025-01-02T21:00",
)

# Market replay with callback — identical to live processing
data.replay(callback=process_mbo_message)

# Or convert to DataFrame / ndarray for analysis
df = data.to_df()
```

**Storing locally:**

```python
# Download as binary file for repeated replay (avoids re-downloading)
data.to_file("nq_mbo_20250102.dbn.zst")  # compressed, efficient format

# Later, reload without API call
import databento as db
data = db.DBNStore.from_file("nq_mbo_20250102.dbn.zst")
data.replay(callback=process_mbo_message)
```

**Role in DEEP6 architecture:**

Databento is **backtesting data only** (not the live trading feed). The live trading feed is async-rithmic (same Rithmic connection, zero extra cost). Databento provides:
1. Historical MBO replay for vectorbt parameter sweeps
2. Independent validation that the async-rithmic live data matches expected behavior
3. Deeper history than Rithmic's native historical feed (Rithmic provides ~360 days; Databento has multi-year history from CME colocation)

**Sources:**
- GitHub: https://github.com/databento/databento-python
- Databento blog (live MBO snapshots): https://databento.com/blog/live-MBO-snapshot
- Live API reference: https://databento.com/docs/api-reference-live

---

### 5. Python Async Architecture

**Core constraint:** asyncio single event loop must handle 1,000+ DOM callbacks/sec (async-rithmic) + bar-level Kronos inference + order management + FastAPI SSE streaming + signal computation — without any blocking.

**The pattern that works: three-tier task separation**

```
asyncio event loop (single thread)
├── Task 1: async-rithmic WebSocket receiver (I/O-bound — never blocks)
│           └── hot callback: on_order_book() / on_tick()
│               └── MUST be fast: update shared state + push to asyncio.Queue
│
├── Task 2: signal_engine_task() (CPU-light — reads shared state)
│           └── runs on each queue item; computes 44 signals from DOM snapshot
│           └── if signal computation > ~1ms, offload to ThreadPoolExecutor
│
├── Task 3: kronos_bar_task() (CPU-heavy — runs in ThreadPoolExecutor)
│           └── wakes on bar_close_event; offloads to executor; never blocks loop
│
├── Task 4: order_manager_task() (I/O-bound — awaits order fills)
│           └── reads from signal_queue; submits orders via async-rithmic
│
└── Task 5: FastAPI SSE task (I/O-bound — pushes to dashboard)
            └── reads from sse_queue; pushes signal state to Next.js
```

**Key implementation principles:**

**Rule 1: DOM callbacks must never block**

```python
async def on_order_book(update):
    # WRONG: any computation here starves other tasks
    # score = compute_all_44_signals(update)  # DO NOT DO THIS

    # CORRECT: update shared state atomically, put in queue
    dom_state.apply_update(update)  # O(1) operation only
    if update.update_type in ("SOLO", "END"):
        await dom_queue.put(dom_state.snapshot())  # non-blocking put
```

**Rule 2: Use asyncio.Queue to decouple data ingestion from signal computation**

```python
dom_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
signal_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

async def signal_engine_task():
    while True:
        snapshot = await dom_queue.get()
        signals = compute_signals(snapshot)  # fast if < 1ms
        if signals.has_trigger():
            await signal_queue.put(signals)
        dom_queue.task_done()
```

**Rule 3: CPU-bound work goes to ThreadPoolExecutor**

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

signal_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="signals")

async def signal_engine_task():
    loop = asyncio.get_event_loop()
    while True:
        snapshot = await dom_queue.get()
        # Offload if signal computation takes > 1ms
        signals = await loop.run_in_executor(
            signal_executor, compute_all_44_signals, snapshot
        )
        await signal_queue.put(signals)
```

**Rule 4: Use janus for thread-safe queue between sync and async code**

```python
# janus: thread-safe asyncio-aware queue
# Use when Kronos (sync PyTorch) needs to push results to async signal engine
import janus

result_queue = janus.Queue()

# Kronos thread (sync):
result_queue.sync_q.put(bias_value)

# Signal engine (async):
bias = await result_queue.async_q.get()
```

**Rule 5: DOM state must use lock-free shared state**

For 1,000 callbacks/sec, use a pre-allocated array indexed by integer price level:

```python
import numpy as np

PRICE_LEVELS = 2000  # covers NQ's expected range
bid_volume = np.zeros(PRICE_LEVELS, dtype=np.float64)
ask_volume = np.zeros(PRICE_LEVELS, dtype=np.float64)

def apply_dom_update(update):
    idx = price_to_index(update.price)  # O(1): (price - base) / tick_size
    if update.side == 'B':
        bid_volume[idx] = update.size  # NumPy array write is ~atomic for single writer
    else:
        ask_volume[idx] = update.size
```

**Expected throughput:** 1,000 DOM callbacks/sec in Python asyncio is well within limits. Python asyncio I/O event loops typically handle 10,000-50,000 simple callbacks/sec. The bottleneck will be signal computation (44 signals, footprint building), not the I/O loop itself.

**Libraries:**

| Library | Purpose | Install |
|---------|---------|---------|
| `asyncio` | Core event loop (stdlib) | stdlib |
| `janus` | Thread-safe asyncio queue | `pip install janus` |
| `numpy` | Lock-free DOM state arrays | `pip install numpy` |
| `concurrent.futures` | ThreadPoolExecutor for CPU work | stdlib |

---

### 6. Footprint Chart Rendering

**Recommendation: Lightweight Charts v5.x via Next.js (primary), with Plotly for analysis/debugging**

The footprint bar itself is custom — no mainstream library provides a built-in footprint chart type. You build the bid/ask volume accumulator in Python and send the aggregated per-bar, per-level data to the frontend.

**Python-side footprint accumulator (the core, no library required):**

```python
from collections import defaultdict
import numpy as np

class FootprintBar:
    def __init__(self, tick_size: float = 0.25):
        self.tick_size = tick_size
        self.levels: dict[float, dict[str, int]] = defaultdict(
            lambda: {'bid_vol': 0, 'ask_vol': 0}
        )

    def on_tick(self, price: float, size: int, is_buy: bool) -> None:
        snapped = round(price / self.tick_size) * self.tick_size
        if is_buy:
            self.levels[snapped]['ask_vol'] += size  # buy = lifted offer
        else:
            self.levels[snapped]['bid_vol'] += size  # sell = hit bid

    def delta(self) -> dict[float, int]:
        return {p: v['ask_vol'] - v['bid_vol'] for p, v in self.levels.items()}

    def to_dict(self) -> dict:
        return {
            'levels': {str(p): v for p, v in self.levels.items()},
            'delta': sum(v['ask_vol'] - v['bid_vol'] for v in self.levels.values()),
        }
```

**Frontend rendering options:**

| Library | Approach | Footprint support | Notes |
|---------|----------|-------------------|-------|
| TradingView Lightweight Charts v5.1 | Custom series via Next.js WebSocket | Manual custom series plugin | Purpose-built for financial data; 45KB bundle; best performance for OHLC overlay |
| Plotly (Python Dash or as static charts) | Python-side rendering | Manual trace construction | Better for analysis/debugging than production real-time UI |
| HTML5 Canvas (custom) | Direct WebGL/Canvas in Next.js | Full control | Maximum performance; significant development effort |

**Recommendation:** Use Lightweight Charts v5.1 in Next.js with a custom series for footprint bars. The canonical approach is:
1. FastAPI sends footprint bar data as JSON over WebSocket to Next.js
2. Next.js custom Lightweight Charts plugin renders bid/ask volume at each price level within the bar
3. Color-code by delta (positive delta = green, negative = red)

For the initial implementation, render footprint data as a Plotly heatmap in a Python Dash panel — simpler to build, adequate for development and parameter tuning. Port to Lightweight Charts custom series when the signal engine is stable.

**Useful reference implementations:**
- OrderflowChart (Plotly-based footprint): https://github.com/murtazayusuf/OrderflowChart
- bmoscon orderbook (C-backed order book state management): https://github.com/bmoscon/orderbook
- py-market-profile (Volume Profile from pandas): https://github.com/bfolkens/py-market-profile

---

### 7. FastAPI + Next.js Web Stack

The v1 research (STACK.md from .planning-v1-nt8/) thoroughly documented this layer. It carries forward unchanged since the Python pivot does not affect the web stack architecture.

**Key decisions (validated, unchanged from v1):**

| Layer | Choice | Version | Rationale |
|-------|--------|---------|-----------|
| Python API | FastAPI | 0.135.3 | Async-native, 15K-20K RPS, Pydantic v2 built-in, SSE via StreamingResponse |
| ASGI server | Uvicorn | 0.34+ | Required by FastAPI; single worker sufficient |
| Real-time push | SSE (native) | — | One-way push from FastAPI → Next.js; simpler than WebSockets; `EventSource` in browser |
| Real-time push (footprint) | WebSocket | — | Footprint bar data is high-frequency; SSE is text-only; use WebSocket for binary efficiency |
| Dashboard framework | Next.js | 15.x (App Router) | RSC reduces client bundle; built-in SSE via Route Handlers |
| UI components | shadcn/ui + Tremor | latest / 3.x | Accessible primitives + production-ready chart components |
| Financial charts | Lightweight Charts | 5.1.0 | Purpose-built OHLC; 45KB bundle; data conflation at v5.1 |
| Dashboard charts | Tremor + Recharts | 3.x / 2.x | AreaChart, KPI cards, scatter plots out of the box |

**SSE endpoint pattern (FastAPI):**

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json

app = FastAPI()

async def signal_event_generator(signal_queue: asyncio.Queue):
    while True:
        signal_state = await signal_queue.get()
        yield f"data: {json.dumps(signal_state)}\n\n"

@app.get("/stream/signals")
async def stream_signals():
    return StreamingResponse(
        signal_event_generator(signal_queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

**WebSocket endpoint (footprint bars):**

```python
from fastapi import WebSocket

@app.websocket("/ws/footprint")
async def footprint_ws(websocket: WebSocket):
    await websocket.accept()
    while True:
        bar = await footprint_queue.get()
        await websocket.send_json(bar.to_dict())
```

**Architecture boundary:**

```
macOS (dev machine + trading machine)
├── async-rithmic process (Python 3.12)
│   ├── WebSocket → Rithmic infrastructure
│   ├── DOM state (NumPy arrays, lock-free)
│   ├── Footprint builder (per-bar tick accumulator)
│   ├── 44-signal engine (asyncio tasks + ThreadPoolExecutor)
│   ├── Kronos E10 (ThreadPoolExecutor, wakes on bar close)
│   ├── Order manager (async-rithmic ORDER_PLANT)
│   └── FastAPI (Uvicorn) serving SSE + WebSocket
│       ├── GET  /stream/signals  → SSE to Next.js
│       ├── WS   /ws/footprint   → WebSocket to Next.js
│       ├── POST /orders          → order management API
│       └── GET  /backtest        → vectorbt parameter sweeps
│
├── Databento (Python client, separate process)
│   └── Historical MBO replay → vectorbt backtesting
│
├── Kronos inference (ThreadPoolExecutor within main process)
│   └── NeoQuasar/Kronos-small on MPS or CPU
│
└── Next.js dashboard (Node.js, localhost:3000)
    ├── EventSource → /stream/signals (signal state, scores)
    ├── WebSocket   → /ws/footprint   (live footprint bars)
    └── Lightweight Charts + Tremor rendering
```

---

## Full Installation Reference

```bash
# Python environment (Python 3.12 required)
python3.12 -m venv .venv
source .venv/bin/activate

# Core data + execution
pip install async-rithmic==1.5.9

# Async utilities
pip install janus                    # thread-safe asyncio queue

# FastAPI stack
pip install fastapi==0.135.3 "uvicorn[standard]"

# ML backend (from v1 — unchanged)
pip install scikit-learn==1.8.0 xgboost==3.2.0 optuna==4.8.0 hmmlearn==0.3.3
pip install optuna-integration[xgboost]

# Data processing
pip install numpy pandas pyarrow

# Database / ORM
pip install sqlalchemy==2.0.49 aiosqlite

# Scheduling
pip install apscheduler

# GEX data
pip install flashalpha

# Backtesting data + engine
pip install databento vectorbt

# Kronos (not on PyPI — install from source)
git clone https://github.com/shiyu-coder/Kronos.git
cd Kronos && pip install -r requirements.txt && cd ..

# Order book state management (optional C-backed)
pip install orderbook

# TradingView MCP (Node.js, not Python)
git clone https://github.com/tradesdontlie/tradingview-mcp.git
cd tradingview-mcp && npm install
```

```bash
# Next.js dashboard
npx create-next-app@latest deep6-dashboard --typescript --tailwind --app
cd deep6-dashboard
npx shadcn@latest init
npm install @tremor/react lightweight-charts@5.1.0 recharts swr
```

---

## What NOT to Use

| Category | Avoid | Why |
|----------|-------|-----|
| Rithmic data | pyrithmic | Older, less maintained; async-rithmic is the better fork |
| Rithmic data | NautilusTrader | Full trading engine adds complexity not needed when async-rithmic already covers the use case |
| Kronos model | Kronos-base (102M) | 4x larger than small; inference latency on CPU/MPS grows proportionally; overkill for single-asset directional bias |
| Kronos model | Kronos-large (499M, closed-source) | Not open-source; unavailable |
| Async | threading.Thread for DOM | DOM callbacks must stay in asyncio to avoid lock overhead at 1,000/sec |
| Async | multiprocessing for signals | Process overhead > signal computation time for 44 signals; ThreadPoolExecutor is sufficient |
| Footprint viz | Bokeh | Less maintained than Plotly; worse integration with modern dashboards |
| Footprint viz | D3.js directly | 200+ hours of custom charting; use Lightweight Charts custom series instead |
| Charts | Chart.js | Worse TypeScript + React integration than Lightweight Charts |
| Real-time | Socket.io (Python) | python-socketio adds complexity; FastAPI WebSocket is sufficient |
| Backtesting | Re-implementing signals in Python from scratch separately from live engine | Creates two sources of truth; use same engine code with Databento replay |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Rithmic Python | async-rithmic 1.5.9 | pyrithmic | async-rithmic is a complete rewrite with better architecture and active maintenance |
| Rithmic Python | async-rithmic | Databento live | Databento adds $179/mo and doesn't provide execution; async-rithmic is $0 extra |
| Foundation model | Kronos-small (24.7M) | Chronos (Amazon) | Chronos is generic time series; Kronos is specifically trained on financial K-lines from 45+ exchanges; higher directional accuracy on OHLCV |
| Foundation model | Kronos | TimeGPT / Nixtla | Commercial API with cost-per-call; Kronos is fully open-source and runs locally |
| DOM state | dict-based LOB | C-backed `orderbook` lib | At 1,000 updates/sec, NumPy array indexing by price level outperforms dict; implement custom for hot path, use `orderbook` for reference implementation |
| Async queue | asyncio.Queue only | janus | asyncio.Queue is not thread-safe; janus needed when Kronos (sync PyTorch) pushes results into the async event loop |
| Footprint viz (dev) | Plotly Dash | Lightweight Charts custom series | LW Charts custom series requires significant JS development; Plotly is faster to build for development iteration |
| Footprint viz (prod) | Lightweight Charts v5.1 | Plotly in browser | LW Charts handles high-frequency updates without DOM thrashing; Plotly re-renders entire chart on update |

---

## Phase-Specific Stack Notes

| Phase | Component | Stack Element | Critical Note |
|-------|-----------|---------------|---------------|
| Phase 1 | Rithmic connection | async-rithmic 1.5.9 | Start with test environment (wss://rituz00100.rithmic.com) — free, no broker approval needed |
| Phase 1 | DOM state | NumPy arrays | Pre-allocate bid/ask arrays covering NQ price range; avoid dict in hot path |
| Phase 1 | Footprint builder | Custom Python | Build this before any signal code — data pipeline must be verified correct first |
| Phase 2 | 44-signal engine | asyncio + ThreadPoolExecutor | Profile each signal; only offload to executor if > 0.5ms |
| Phase 3 | Kronos E10 | Kronos-small + ThreadPoolExecutor | Test inference latency on your hardware before committing to per-bar invocation frequency |
| Phase 3 | Kronos fine-tuning | Qlib pipeline (optional) | Only fine-tune on NQ data if zero-shot directional accuracy < 52%; pre-trained weights may be sufficient |
| Phase 4 | Auto-execution | async-rithmic ORDER_PLANT | Research Rithmic's order types and bracket order support before implementing risk management |
| Phase 5 | Backtesting | databento + vectorbt | Use MBO schema for historical replay; vectorbt for parameter sweeps via Optuna |
| Phase 5 | TradingView MCP | tradingview-mcp + Claude Code | Use for visual trade review, not signal computation; data stays local |
| Phase 6 | Web dashboard | FastAPI SSE + WebSocket + Next.js | SSE for signals (low frequency); WebSocket for footprint bars (high frequency) |

---

## Open Questions Requiring Phase-Specific Research

1. **async-rithmic order types:** Does it expose bracket orders, OCO, and native stop-loss on the ORDER_PLANT? The docs mention market/limit/stop, but bracket order support needs verification before building the risk management layer.

2. **Kronos inference on Apple Silicon MPS:** MPS (Metal Performance Shaders) backend for PyTorch is not CUDA. Kronos was benchmarked on A100. MPS compatibility with Kronos's specific model architecture (especially the tokenizer's quantization operations) needs verification on the target macOS machine.

3. **async-rithmic DOM level count:** The library claims "40+ levels" matching NinjaTrader. This needs live validation — connect to test environment and log how many bid/ask levels arrive per book update to confirm parity with NT8's observed 40+ levels.

4. **Rithmic "API/plugin mode" broker approval:** The current broker must explicitly enable Rithmic API access (separate from the standard trading account). Confirm this before starting Phase 1 development.

5. **Databento MBO historical data cost:** The $179/mo plan covers live data. Historical MBO for NQ backtesting may incur additional per-download charges. Verify the historical data pricing model before committing to Databento for deep historical replay.

---

## Sources

| Source | URL | Confidence |
|--------|-----|------------|
| async-rithmic PyPI | https://pypi.org/project/async-rithmic/ | HIGH |
| async-rithmic GitHub | https://github.com/rundef/async_rithmic | HIGH |
| Rithmic API page | https://www.rithmic.com/apis | HIGH |
| Kronos GitHub | https://github.com/shiyu-coder/Kronos | HIGH |
| Kronos arXiv paper | https://arxiv.org/abs/2508.02739 | HIGH |
| Kronos HuggingFace | https://huggingface.co/NeoQuasar/Kronos-small | HIGH |
| Kronos BrightCoding guide | https://www.blog.brightcoding.dev/2026/04/10/kronos-the-revolutionary-ai-model-for-financial-markets | MEDIUM |
| tradingview-mcp GitHub | https://github.com/tradesdontlie/tradingview-mcp | HIGH |
| tradingview-mcp setup | https://github.com/tradesdontlie/tradingview-mcp/blob/main/SETUP_GUIDE.md | HIGH |
| databento-python GitHub | https://github.com/databento/databento-python | HIGH |
| Databento live MBO blog | https://databento.com/blog/live-MBO-snapshot | HIGH |
| Databento live API ref | https://databento.com/docs/api-reference-live | HIGH |
| vectorbt PyPI | https://pypi.org/project/vectorbt/ | HIGH |
| janus (asyncio queue) | https://github.com/aio-libs/janus | HIGH |
| bmoscon orderbook | https://github.com/bmoscon/orderbook | HIGH |
| OrderflowChart (Plotly footprint) | https://github.com/murtazayusuf/OrderflowChart | MEDIUM |
| Lightweight Charts v5.1 | https://github.com/tradingview/lightweight-charts | HIGH |

---

*Stack research: 2026-04-11 | Supersedes v1 NT8/C# stack for Python pivot components*
