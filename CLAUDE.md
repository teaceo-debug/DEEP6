<!-- GSD:project-start source:PROJECT.md -->
## Project

**DEEP6 v2.0 — Python Edition**

DEEP6 is an institutional-grade footprint chart auto-trading system for NQ futures, built entirely in Python. The system connects directly to Rithmic via `async-rithmic` for real-time Level 2 DOM data (40+ levels, 1,000 callbacks/sec) and trade execution — eliminating the NinjaTrader dependency. 44 independent market microstructure signals are synthesized into a unified confidence score. Kronos (foundation model for financial K-lines) provides directional bias as E10. TradingView MCP enables Claude-in-the-loop visual analysis. A FastAPI + Next.js web stack provides ML optimization, analytics, and a session replay dashboard. The system's thesis: absorption and exhaustion are the highest-alpha reversal signals in order flow — everything else exists to confirm or contextualize them.

**Core Value:** Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via direct Rithmic orders — all in Python, running on macOS.

### Constraints

- **Language**: Python 3.12+ (entire system)
- **Data feed**: Rithmic via async-rithmic (broker must enable API/plugin mode)
- **Performance**: Must handle 1,000+ DOM callbacks/sec in Python async event loop
- **Execution**: Direct Rithmic orders (approach TBD — needs research on order types, risk controls)
- **GEX data**: FlashAlpha API ($49/mo) — NQ via QQQ/NDX proxy
- **Historical data**: Databento MBO ($179/mo) for backtesting
- **Kronos**: Requires GPU for inference (RTX 3060+ recommended) or CPU with larger latency
- **Dashboard**: Next.js 15 + FastAPI backend
- **Development**: macOS native (no Windows dependency)
- **Research-first**: Deep research per domain before committing to architecture
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Context
## Recommended Stack
### 1. Rithmic Data + Execution: async-rithmic
| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| async-rithmic | 1.5.9 | Rithmic R\|Protocol via WebSocket + protobuf — L2 DOM, tick data, order execution | HIGH |
| Python | 3.12 | Runtime (async-rithmic requires 3.10+; 3.12 is the sweet spot for library compatibility) | HIGH |
- Full Order Book (L2) streaming — 40+ price levels per side, identical feed to what NinjaTrader receives
- Live tick data and Best Bid/Offer (BBO) streaming
- Order management: market, limit, stop orders via ORDER_PLANT
- Historical tick and time bar data
- Automatic reconnection with configurable backoff (exponential + jitter via `ReconnectionSettings`)
- Multi-account support
- macOS native — pure Python WebSocket + protobuf, no C DLLs
# Market order
# Limit order
- Existing Rithmic broker account (same one used with NinjaTrader) — zero additional cost
- Must sign Rithmic Market Data Subscription Agreement (done via R|Trader once)
- Test environment (wss://rituz00100.rithmic.com) is free for development
- Broker must enable "API/plugin mode" (EdgeClear, Tradovate via Rithmic, AMP Futures all support this)
- PyPI: https://pypi.org/project/async-rithmic/ (v1.5.9, released 2026-02-20)
- GitHub: https://github.com/rundef/async_rithmic
- Rithmic API page: https://www.rithmic.com/apis
### 2. Kronos E10 Bias Engine
| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| Kronos-small | 24.7M params | Directional bias prediction from OHLCV (E10 signal) | MEDIUM |
| KronosTokenizer | base tokenizer | Converts OHLCV to hierarchical discrete tokens | MEDIUM |
| PyTorch | >=2.0 (via Kronos requirements) | Model runtime | HIGH |
| transformers | (via requirements.txt) | Model loading utilities | HIGH |
# Load from HuggingFace Hub (downloads once, cached locally)
# x_df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume', 'amount']
# Minimum: ['open', 'high', 'low', 'close'] — volume and amount are optional
# Rows: historical K-lines, chronologically ordered, evenly spaced intervals
# For 1-minute NQ bars: 512 bars = ~8.5 hours of context
# pred_df columns: open, high, low, close, volume, amount
# Use pred_df['close'] vs current close for directional bias
| Hardware | Model | Inference Time (1 prediction) |
|----------|-------|-------------------------------|
| A100 GPU | Kronos-base (102M) | ~50ms |
| RTX 3060 GPU | Kronos-small (24.7M) | ~80-150ms (estimated) |
| Apple Silicon M2 (MPS) | Kronos-small | ~200-400ms (estimated) |
| CPU only (no GPU) | Kronos-small | ~500ms-2s (estimated) |
| CPU only | Kronos-mini (4.1M) | ~100-200ms (estimated) |
- GitHub: https://github.com/shiyu-coder/Kronos
- HuggingFace: https://huggingface.co/NeoQuasar/Kronos-small
- arXiv paper: https://arxiv.org/abs/2508.02739
- BrightCoding guide (2026-04-10): https://www.blog.brightcoding.dev/2026/04/10/kronos-the-revolutionary-ai-model-for-financial-markets
### 3. TradingView MCP
| Technology | Stars | Purpose | Confidence |
|------------|-------|---------|------------|
| tradingview-mcp (tradesdontlie) | ~1.7K | Claude Code ↔ TradingView Desktop bridge via CDP | HIGH |
| Chrome DevTools Protocol | — | Underlying mechanism for chart inspection + JS injection | HIGH |
- `chart_get_state` — symbol, timeframe, all indicator names/IDs (~500 bytes)
- `quote_get` — current OHLC + volume
- `data_get_ohlcv` — full price bars (use `summary: true` for compact mode)
- `data_get_study_values` — read any built-in indicator values (RSI, MACD, EMA, etc.)
- `data_get_pine_lines` — horizontal levels from custom Pine indicators
- `data_get_pine_labels` — text annotations with price from Pine
- `data_get_pine_boxes` — price zones as {high, low} pairs
- `capture_screenshot` — full, chart, or strategy_tester regions
- `pine_set_source` — inject Pine Script into TradingView editor
- `pine_smart_compile` — compile with auto-detection + error report
- `pine_get_errors` — read compilation errors
- `pine_get_console` — read log.info() output
- `pine_save` — save to TradingView cloud
- `chart_set_symbol`, `chart_set_timeframe`, `chart_set_type`
- `chart_scroll_to_date` — jump to date for replay
- `pane_set_layout` — configure multi-pane grid (2x2, etc.)
# 1. Clone and install
# 2. Launch TradingView Desktop with debugging enabled (macOS)
# Equivalent manual: /Applications/TradingView.app/Contents/MacOS/TradingView \
#   --remote-debugging-port=9222
# 3. Verify connection in Claude Code
# "Use tv_health_check to verify TradingView is connected"
- GitHub: https://github.com/tradesdontlie/tradingview-mcp
- Setup guide: https://github.com/tradesdontlie/tradingview-mcp/blob/main/SETUP_GUIDE.md
- PulseMCP listing: https://www.pulsemcp.com/servers/hilmituncay-tradingview-mcp
### 4. Databento Python SDK (Backtesting Data)
| Technology | Version | Purpose | Cost | Confidence |
|------------|---------|---------|------|------------|
| databento | latest | MBO (L3) historical NQ data for backtesting; live MBO as independent validation feed | $179/mo | HIGH |
- MBO (Market-by-Order, L3) = every individual order event (add, modify, cancel) at every price level
- Full order book reconstructibility from MBO — gives you all 40+ levels in historical replay
- Nanosecond timestamps from CME colocation
- Live and historical APIs share the same interface — one codebase for both
- NQ continuous symbol: `NQ.c.0` (front-month roll handled automatically)
# Equivalent to env var: DATABENTO_API_KEY
# Market replay with callback — identical to live processing
# Or convert to DataFrame / ndarray for analysis
# Download as binary file for repeated replay (avoids re-downloading)
# Later, reload without API call
- GitHub: https://github.com/databento/databento-python
- Databento blog (live MBO snapshots): https://databento.com/blog/live-MBO-snapshot
- Live API reference: https://databento.com/docs/api-reference-live
### 5. Python Async Architecture
# janus: thread-safe asyncio-aware queue
# Use when Kronos (sync PyTorch) needs to push results to async signal engine
# Kronos thread (sync):
# Signal engine (async):
| Library | Purpose | Install |
|---------|---------|---------|
| `asyncio` | Core event loop (stdlib) | stdlib |
| `janus` | Thread-safe asyncio queue | `pip install janus` |
| `numpy` | Lock-free DOM state arrays | `pip install numpy` |
| `concurrent.futures` | ThreadPoolExecutor for CPU work | stdlib |
### 6. Footprint Chart Rendering
| Library | Approach | Footprint support | Notes |
|---------|----------|-------------------|-------|
| TradingView Lightweight Charts v5.1 | Custom series via Next.js WebSocket | Manual custom series plugin | Purpose-built for financial data; 45KB bundle; best performance for OHLC overlay |
| Plotly (Python Dash or as static charts) | Python-side rendering | Manual trace construction | Better for analysis/debugging than production real-time UI |
| HTML5 Canvas (custom) | Direct WebGL/Canvas in Next.js | Full control | Maximum performance; significant development effort |
- OrderflowChart (Plotly-based footprint): https://github.com/murtazayusuf/OrderflowChart
- bmoscon orderbook (C-backed order book state management): https://github.com/bmoscon/orderbook
- py-market-profile (Volume Profile from pandas): https://github.com/bfolkens/py-market-profile
### 7. FastAPI + Next.js Web Stack
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
## Full Installation Reference
# Python environment (Python 3.12 required)
# Core data + execution
# Async utilities
# FastAPI stack
# ML backend (from v1 — unchanged)
# Data processing
# Database / ORM
# Scheduling
# GEX data
# Backtesting data + engine
# Kronos (not on PyPI — install from source)
# Order book state management (optional C-backed)
# TradingView MCP (Node.js, not Python)
# Next.js dashboard
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
## Open Questions Requiring Phase-Specific Research
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
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
