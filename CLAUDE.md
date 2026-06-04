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

### nt8-expert — NinjaTrader 8 Expert Agent

Skill location: `.claude/skills/nt8-expert/`

Invoke this skill for ANY NinjaTrader 8 interaction:
- Deploy indicators/strategies to NT8 (`ninjatrader/scripts/nt8-deploy.ps1`)
- Trigger recompile via UI automation (`ninjatrader/scripts/nt8-compile.ps1`)
- Interact with NT8 UI: focus window, open editor, add indicator/strategy to chart, screenshot (`ninjatrader/scripts/nt8-ui.ps1`)
- Check NT8 status, deployed files, sync state, compile errors (`ninjatrader/scripts/nt8-status.ps1`)
- Answer any NT8 settings, NinjaScript API, namespace, or folder-structure question

Load `.claude/skills/nt8-expert/knowledge.md` for verified paths, compile methods,
common errors, keyboard shortcuts, and DEEP6 file inventory.
Load `.claude/skills/nt8-expert/scripts.md` for script usage reference.

### nt8-fix — NT8 Compile Error Auto-Fixer

Skill location: `.claude/skills/nt8-fix/`

Invoke this skill when:
- NT8 compile fails and you need to fix errors
- User says "fix errors", "fix it", "what's broken"
- `nt8-compile.ps1` returns `[COMPILE-RESULT] FAILED`

Reads full error messages via UIAutomation from the NT8 NinjaScript Editor DataGrid,
then applies targeted fixes using NT8-specific error patterns.
See `nt8-errors-full.ps1` for the UIAutomation error reader.

### nt8-new — NinjaScript Code Generator

Skill location: `.claude/skills/nt8-new/`

Invoke this skill when:
- User wants to create a new indicator, strategy, or AddOn
- User describes a trading concept and wants NinjaScript code
- User says "write an indicator that...", "create a strategy for..."

Generates valid NinjaScript C# code from a description, deploys it, compiles it,
and fixes any errors automatically.

### nt8-backtesting-expert — NinjaTrader 8 Backtesting Expert

Skill location: `.claude/skills/nt8-backtesting-expert/`

Invoke this skill when:
- Running backtests in NT8 Strategy Analyzer (backtest, optimization, walk-forward)
- Downloading or importing historical data for backtesting
- Writing NinjaScript strategies that backtest accurately
- Debugging backtest vs live discrepancies
- Understanding Strategy Analyzer settings, metrics, or output
- Setting up Tick Replay, OrderFillResolution, or intrabar fill accuracy

Load `.claude/skills/nt8-backtesting-expert/knowledge.md` for the complete backtesting encyclopedia
covering Strategy Analyzer (all tabs), historical data acquisition, NinjaScript code patterns,
fill accuracy mechanisms, performance metrics, optimization-ready templates, and troubleshooting.

### nt8-architect — DEEP6 Architecture Map

Skill location: `.claude/skills/nt8-architect/`

Invoke this skill when:
- User asks about file dependencies, what's broken, what namespace is where
- Investigating a CS0234/CS0246 missing type error
- Planning a new file that needs to know what types already exist
- Checking deployment state

Maintains a live map of all DEEP6 files, their namespaces, exports, and dependency graph.

### nt8-visual-design — NT8 Visual Design Bible

Skill location: `.claude/skills/nt8-visual-design/`

Invoke this skill when:
- Building or modifying NinjaTrader 8 indicator visuals (SharpDX rendering)
- Designing footprint charts, HUDs, dashboards, or signal markers
- Choosing colors, fonts, or layout for any NT8 chart overlay
- Need SharpDX code patterns for gradients, rounded panels, custom shapes, text rendering

Load `.claude/skills/nt8-visual-design/knowledge.md` for the complete NT8 visual design system
including institutional color palettes, typography specs, SharpDX technique catalog,
footprint cell rendering patterns, and performance optimization rules.

### trading-knowledge — Trading Knowledge Center

Skill location: `.claude/skills/trading-knowledge/`

Invoke this skill when:
- User asks about trading concepts, order flow, microstructure, strategy discovery, or trade setup documentation
- User asks "What is [trading concept]?," "Find strategies for [condition]," "What does DEEP6 signal [X] detect?," "How do I find NinjaTrader strategies?," "Document this trade setup," "What academic research supports [pattern]?," or "Explain [order flow concept]"

Load `.claude/skills/trading-knowledge/knowledge.md` first, then route to the relevant domain, catalog, or reference file as needed.

### display-topology — Multi-Monitor Display Map

Skill location: `.claude/skills/display-topology/`

Invoke this skill when:
- Taking screenshots or interacting with UI across multiple monitors
- Finding which screen NinjaTrader, TradingView, or any application is on
- Doing UI automation that needs to know monitor positions and coordinates
- Debugging window positioning or display layout issues

Load `.claude/skills/display-topology/knowledge.md` for the complete 4-screen monitor map,
coordinate system, DPI scaling reference, and runtime window detection commands.

### trader-dale-footprint — Trader Dale Order Flow Mastery

Skill location: `.claude/skills/trader-dale-footprint/`

Invoke this skill when:
- Reading footprint/order flow charts (bid/ask, delta, imbalances, volume clusters)
- Using Trader Dale's 5 standalone trading setups (Volume Clusters, Multiple Nodes, Trades Filter, Stacked Imbalances, Unfinished Business)
- Using Trader Dale's 4 confirmation setups (Big Limit Orders, Absorption, Aggressive Orders & Delta, Cumulative Delta Divergence)
- Setting up Order Flow workspace (4-chart layout, timeframes, cell content modes)
- Placing take profit, stop loss, or trailing with order flow
- Combining Volume Profile with Order Flow for S/R identification
- Understanding passive vs active market participants
- Any question about TDO Bars software or Trader Dale's methodology

Load `.claude/skills/trader-dale-footprint/knowledge.md` for the master index and routing map.
27 files across 7 subdirectories: foundations/, reading/, setups/, confirmations/, risk/, volume-profile/, workspace/.

### rithmic-networking — Rithmic API Networking Reference

Skill location: `.claude/skills/rithmic-networking/`

Invoke this skill when:
- Connecting to Rithmic via async-rithmic (test, paper, live, prop firm)
- Debugging Rithmic connection errors (SYSTEM_NAME, ForcedLogout, authentication)
- Setting up a new Rithmic service or configuring environment variables
- Working with gateway discovery, system names, or conformance testing
- Troubleshooting DOM/tick data feed issues from Rithmic

Load `.claude/skills/rithmic-networking/knowledge.md` for verified gateway URLs,
system names, connection patterns, error troubleshooting, and DEEP6-specific patterns.

### tradingview-machine-profile — TradingView Platform + Routing Profile

Skill location: `.claude/skills/tradingview-machine-profile/`

Invoke this skill when:
- Starting any TradingView or Pine Script task and you need platform context first
- Connecting to TradingView Desktop or reasoning about MCP/tool routing
- Determining whether a task is platform/setup, build, debugging, MCP operation, or strategy backtesting

Load `.claude/skills/tradingview-machine-profile/knowledge.md` first for the platform model,
DEEP6-specific role of TradingView, and the routing table Hermes or any implementation agent should follow.

### tradingview-pinescript-builder-doctor — DEEP6 Pine Builder

Skill location: `.claude/skills/tradingview-pinescript-builder-doctor/`

Invoke this skill when:
- Building Pine indicators, strategies, libraries, alert scripts, or webhook bridges
- Designing TradingView studies for DEEP6 visual analysis or signal surfacing
- Extending Pine-side DEEP6 logic such as anchors, overlays, or backend-facing alert payloads

Load `.claude/skills/tradingview-pinescript-builder-doctor/knowledge.md` first, then route to
the smallest matching article under `patterns/`, `strategies/`, or `deep6/`.

### tradingview-pinescript-error-doctor — Pine Error Encyclopedia + Repair Playbooks

Skill location: `.claude/skills/tradingview-pinescript-error-doctor/`

Invoke this skill when:
- Pine compile errors, runtime errors, repainting bugs, MTF bugs, or object lifecycle bugs need fixing
- The user asks for Pine error diagnosis, deep debugging, or a trusted repair workflow
- Strategy behavior is suspicious and you need to separate compile-silent logic bugs from platform issues

Load `.claude/skills/tradingview-pinescript-error-doctor/knowledge.md` first.
It routes to official error-code notes, common compile errors, and focused repair playbooks.

### tradingview-mcp-trading-operator — TradingView MCP Operations

Skill location: `.claude/skills/tradingview-mcp-trading-operator/`

Invoke this skill when:
- Reading or replacing Pine source through MCP
- Compiling on chart, checking Pine errors/console, inspecting labels/lines/boxes/tables
- Taking TradingView screenshots, querying study values, or managing alerts through the bridge

Load `.claude/skills/tradingview-mcp-trading-operator/knowledge.md` for the canonical MCP tool sequences.

### tradingview-strategy-backtesting-operator — Strategy Tester Specialist

Skill location: `.claude/skills/tradingview-strategy-backtesting-operator/`

Invoke this skill when:
- Evaluating Pine strategies in Strategy Tester
- Interpreting trades, equity, settings realism, or why a strategy takes bad/no trades
- Tightening strategy assumptions before trusting backtest output

Load `.claude/skills/tradingview-strategy-backtesting-operator/knowledge.md` for the backtesting checklist,
tester interpretation rules, and routing to builder/error-doctor skills when the issue is upstream.

### tradingview-pine-converter — Pine→Python Conversion Specialist

Skill location: `.claude/skills/tradingview-pine-converter/`

Invoke this skill when:
- Converting Pine Script indicators or strategies to Python for VectorBT PRO
- Porting Pine trading logic to BaseSignalGenerator format
- Mapping Pine functions to pandas/numpy equivalents
- Validating converted code for repainting and parameter format compliance

Load `.claude/skills/tradingview-pine-converter/knowledge.md` for the banned parameter table,
mapping reference, anti-repainting rules, and quality checklist.

### hermes-backtest-discovery — DEEP6 Autonomous Backtest Discovery

Skill location: `.claude/skills/hermes-backtest-discovery/`

Invoke this skill when:
- Running the backtest discovery loop
- Discovering entry models targeting MBO levels
- Evolving strategies via iteration
- Reading backtest loop state or progress

Load `.claude/skills/hermes-backtest-discovery/knowledge.md` first for complete iteration protocol, data paths, CLI commands, and guardrails.

### nq-options-algo-engine — NQ Options Market Algo Builder

Skill location: `.claude/skills/nq-options-algo-engine/`

Invoke this skill when:
- Building Python algos or Pine indicators that consume options data for NQ trading
- Integrating Massive.com or FlashAlpha APIs into the DEEP6 data pipeline
- Converting options market analysis (GEX, flow, volatility) into automated signals
- Designing the real-time options data pipeline (async clients, data fusion, proxy conversion)
- Backtesting NQ strategies that use options-derived inputs
- Building any of: regime detection, wall reaction, vol surface, or 0DTE gamma algos

Load `.claude/skills/nq-options-algo-engine/knowledge.md` first for the master router,
data source architecture, file map, and cross-references to companion skills
(options-bias-engine for theory, flashalpha-options for API reference).

17 files across 4 subdirectories: data-sources/, algo-patterns/, strategies/, implementation/.
5 deep-expertise files: dealer mechanics formulas, vol surface quantitative, institutional flow taxonomy,
academic foundations (8 papers), GEX model validation with honest limitations.

### volume-profile-lvn — Volume Profile & LVN Institutional Price Structure

Skill location: `.claude/skills/volume-profile-lvn/`

Invoke this skill when:
- User asks about Volume Profile shapes, LVN, HVN, POC, VAH, VAL, or value area
- User asks about Low Volume Nodes as entry zones, acceleration zones, or rejection levels
- User asks about profile-based NQ trading strategies (breakout, fade, gap-fill, retest)
- User asks about combining Volume Profile with order flow (absorption, delta, imbalances at LVN)
- User asks about combining Volume Profile with GEX/options (gamma regime + LVN behavior)
- User asks about Market Profile, TPO, auction market theory, or Dalton/Steidlmayer methodology
- User asks about composite profiles, value migration, naked VPOC, or structural LVN
- User asks about implementing Volume Profile in Python or Pine Script
- User says "LVN setup", "volume profile strategy", "where is support/resistance from VP", "profile shapes"

Load `.claude/skills/volume-profile-lvn/knowledge.md` first for the 5-step decision framework,
strategy summary table, and query routing map.
24 files across 6 subdirectories: foundations/, reading/, setups/, confluence/, implementation/, risk/.
Covers: AMT theory, 6 codified LVN strategies, order flow + GEX confluence rules,
Python/Pine implementation patterns, DEEP6 engine integration points, and academic evidence review.

### unusual-whales — Unusual Whales API & Dark Pool Intelligence

Skill location: `.claude/skills/unusual-whales/`

Invoke this skill when:
- User asks about Unusual Whales API, endpoints, authentication, or rate limits
- User wants dark pool levels from QQQ/SPY as NQ support/resistance
- User wants to build options flow alerts, screening, or sweep detection using UW data
- User asks about GEX/gamma exposure from Unusual Whales (independent from FlashAlpha)
- User wants real-time WebSocket streaming of dark pool, flow, or GEX data
- User asks about building a Python async client for the UW API
- User asks about congressional trading, insider trading, or institutional 13F data from UW
- User says "unusual whales", "dark pool levels", "UW API", "institutional flow", "off-lit trades"

Load `.claude/skills/unusual-whales/knowledge.md` first for the master router,
NQ proxy strategy, DEEP6 integration architecture, and sub-skill routing table.
8 files: knowledge.md (router), api-reference.md (100+ endpoints, anti-hallucination),
dark-pool.md (levels as S/R, clustering, NQ proxy), options-flow.md (alerts, 6-component scoring),
gex-greeks.md (GEX, IV, vol surface), websocket.md (real-time streaming, production patterns),
implementation.md (Python async client, rate limiting, DEEP6 pipeline),
institutional.md (13F, congressional, insider data).

### dark-pool-nq-charting — Doctorate-Level Dark Pool Expertise for NQ Futures

Skill location: `.claude/skills/dark-pool-nq-charting/`

Invoke this skill when:
- User asks about dark pool theory, market microstructure, or price discovery at an academic level
- User wants to chart dark pool levels on NQ futures (QQQ proxy conversion, visualization methods)
- User asks about DIX (Dark Index), dark pool z-scores, or quantitative dark pool signals
- User asks about GEX + dark pool confluence (gamma walls + institutional levels interaction)
- User asks about FINRA data mechanics, ATS venues, reporting latency, or data biases
- User wants Python code for dark pool clustering (DBSCAN, KDE, premium-weighted merge)
- User wants Pine Script indicators for dark pool level overlays on NQ
- User asks about Kyle lambda, Glosten-Milgrom, Zhu sorting mechanism, or Comerton-Forde tipping point
- User says "chart dark pools on NQ", "dark pool PhD", "institutional levels", "dark pool microstructure"

Load `.claude/skills/dark-pool-nq-charting/knowledge.md` first for the information hierarchy,
critical numbers, NQ proxy architecture, and sub-skill routing table.
6 files: knowledge.md (router), foundations.md (FINRA mechanics, venues, biases),
microstructure-theory.md (Kyle/Glosten-Milgrom/Zhu/Comerton-Forde at PhD level),
charting-methodology.md (visualization, QQQ→NQ conversion, patterns, daily workflow),
quantitative-models.md (DIX formula, z-scores, aggression, GEX confluence, Bayesian),
implementation.md (Python clustering, Pine Script, real-time pipeline).

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



<!-- GSD:hermes-operator-start -->
## HERMES Operator Directive (MANDATORY)

**Claude writes code. HERMES executes on the computer. No exceptions.**

Any time you need to do something on this machine — compile, deploy, inject code into TradingView, start services, run tests, take screenshots, verify things work — you MUST invoke HERMES via WSL. Do NOT use TradingView MCP tools, clipboard paste, or any direct computer operations yourself.

### How to invoke HERMES

```bash
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'TASK_DESCRIPTION' -s SKILL1,SKILL2 -Q --yolo --max-turns N 2>&1"
```

### Key flags
- `-q "TASK"` — single query, non-interactive
- `-s SKILLS` — preload skills (comma-separated)
- `-Q` — quiet/programmatic mode
- `--yolo` — auto-approve tool calls
- `--max-turns N` — limit turns (6-12 for most tasks)

### Available HERMES skills
- `deep6-deployment-operator` — deploy Pine scripts, start Python services, run tests, verify end-to-end
- `tradingview-mcp-desktop-operator` — TradingView chart control, Pine Editor, compile, screenshot, replay
- `tradingview-pine-development` — Pine script injection, compile, debug
- `tradingview-pine-debugging-mastery` — Pine error diagnosis and repair
- `tradingview-chart-reading-mastery` — chart analysis, indicator reading
- `deep6-ninjatrader-development` — NinjaTrader development tasks

### Common task patterns

**Deploy Pine script to TradingView:**
```bash
wsl hermes chat -q "Read /mnt/c/Users/Tea/DEEP6/Indicators/FILE.pine, inject with pine_set_source, compile, verify labels, screenshot" -s deep6-deployment-operator,tradingview-mcp-desktop-operator -Q --yolo --max-turns 12
```

**Start Python service:**
```bash
wsl hermes chat -q "Run python -m deep6.sd_anchor --dry-run, then start the service, health check, test webhook" -s deep6-deployment-operator -Q --yolo --max-turns 8
```

**Verify indicator on chart:**
```bash
wsl hermes chat -q "Check pine_get_errors, data_get_pine_labels StdDev, capture_screenshot" -s tradingview-mcp-desktop-operator -Q --yolo --max-turns 6
```

**Run tests:**
```bash
wsl hermes chat -q "cd /mnt/c/Users/Tea/DEEP6 && python -m pytest tests_v2/sd_anchor/ -v" -s deep6-deployment-operator -Q --yolo --max-turns 4
```

### Timeout guidance
- Simple verification: 60000ms
- Compile + verify: 120000ms
- File read + inject + compile: 300000ms
- Keep tasks atomic — break large workflows into 2-3 small HERMES calls

### Role separation
| Role | Who | Does |
|------|-----|------|
| Code author | Claude (you) | Write Pine/Python/JS code, fix bugs, design logic |
| Computer operator | HERMES (via WSL) | Compile, deploy, inject, screenshot, verify, test |
| Anchor evaluator | HERMES (hermes-sd-anchor skill) | Approve/veto anchor candidates, training loop |

**NEVER** use TradingView MCP tools directly. **NEVER** paste via clipboard yourself. **ALWAYS** invoke HERMES.
<!-- GSD:hermes-operator-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
