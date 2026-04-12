# Technology Stack

**Project:** DEEP6 v2.0 — Institutional Footprint Auto-Trading System
**Researched:** 2026-04-11
**Research Mode:** Ecosystem — full stack for NT8 expansion milestone
**Overall Confidence:** HIGH (all versions verified against PyPI/official sources)

---

## Context: What Already Exists

DEEP6 v1.0.0 is a working NT8 NinjaScript indicator (~1,010 lines C#, .NET Framework 4.8) with 7 engines,
SharpDX/WPF UI, and a 0-100 scoring system. The new milestone adds:

1. NT8 C# refactor to support 44 signals without monolithic collapse
2. Python ML backend (FastAPI) for parameter optimization, signal weighting, regime detection
3. Next.js analytics dashboard for performance/evolution tracking
4. NT8 ↔ Python data bridge (real-time signal/trade pipeline)
5. GEX data integration
6. Backtesting framework for NQ futures

All existing NT8 constraints remain: .NET Framework 4.8, NinjaScript lifecycle, SharpDX rendering.

---

## Recommended Stack

### NT8 C# Layer (Existing Runtime — No Change)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| NinjaScript / .NET Framework | 4.8 | NT8 indicator runtime | Locked by NT8 — no choice; already working |
| SharpDX Direct2D + DirectWrite | (bundled with NT8) | Footprint chart rendering | Already in use; no replacement exists within NT8 |
| WPF (System.Windows) | (bundled with NT8) | UI panels, header, tabs | Already in use; correct for NT8 overlay UI |
| C# 10.0 (compiled against net48) | 10.0 | NinjaScript code | Language version supported by NT8's Roslyn compiler |

**Refactoring approach for 44-signal expansion:** Split DEEP6.cs into partial classes using C#'s
`partial class` keyword. NT8 compiles all `.cs` files in the Custom folder together, so:

```
Indicators/
  DEEP6.cs              -- Core lifecycle, Scorer, WPF UI
  DEEP6.E1.Footprint.cs -- E1 engine (partial class DEEP6)
  DEEP6.E2.Trespass.cs  -- E2 engine
  ...
  DEEP6.Signals.cs      -- 44-signal taxonomy, enums, constants
  DEEP6.Render.cs       -- SharpDX rendering layer
```

This is the standard pattern for large NinjaScript projects. NT8 compiles the full partial class set
as one unit. Zero runtime overhead vs monolith.

**Confidence: HIGH** — NT8 partial class support is documented; pattern used in production NT8 add-ons.

---

### Python ML Backend

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12 | Runtime | 3.12 is the recommended stable target; 3.13 available but ecosystem compatibility still catching up as of Q1 2026 |
| FastAPI | 0.135.3 | REST API framework | De facto standard for Python ML APIs; async-native; 15K-20K RPS; Pydantic v2 built in |
| Uvicorn | 0.34+ | ASGI server | Required by FastAPI; single-worker sufficient for this use case (not web-scale) |
| scikit-learn | 1.8.0 | Signal classifiers, logistic regression, ensemble models | Standard ML library; Py 3.11+ required — use Python 3.12 |
| XGBoost | 3.2.0 | Gradient boosted trees for signal weight prediction | Faster training than scikit-learn for tabular data; GPU acceleration available; outperforms random forest on small tabular datasets like trading signal history |
| Optuna | 4.8.0 | Hyperparameter optimization | Best-in-class for Bayesian HPO; native XGBoost/scikit-learn integration via `optuna-integration`; replaces grid search |
| hmmlearn | 0.3.3 | Hidden Markov Model for regime detection | scikit-learn API; standard tool for low/high volatility regime labeling; 2-4 states sufficient for NQ regime classification |
| NumPy | 2.x | Array math | Foundation for all ML libs |
| Pandas | 2.x | Trade history DataFrames, signal logs | Standard tabular data; use with PyArrow backend for performance |
| SQLAlchemy | 2.0.49 | ORM for signal/trade database | Async-compatible with FastAPI; maps to SQLite (dev) and PostgreSQL (if scaling needed) |
| SQLite | (stdlib) | Local time-series storage for signals, trades, parameter history | No operational overhead; sufficient for single-machine single-user system; upgrade to TimescaleDB/PostgreSQL only if multi-day query performance becomes an issue |
| APScheduler | 3.x | Background job scheduling | Run nightly parameter optimization sweeps without a separate task queue (Celery is overkill here) |

**What NOT to use:**

- **Flask**: No async support; FastAPI strictly better for ML APIs with streaming endpoints
- **Ray / Dask**: Overkill; single-machine optimization with Optuna is sufficient
- **Celery + Redis**: Overkill for nightly HPO jobs; APScheduler with SQLite job store is sufficient
- **PyTorch / TensorFlow**: Overkill for tabular signal classification; XGBoost + scikit-learn outperform deep learning on small tabular datasets
- **TimescaleDB (immediately)**: Operational overhead not justified until query patterns on SQLite prove limiting; design schema to be portable

**Confidence: HIGH** — All versions verified against PyPI official release pages.

---

### Next.js Dashboard

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Next.js | 15.x (App Router) | Dashboard framework | App Router with React Server Components reduces client bundle for data-heavy dashboards; built-in SSE support via Route Handlers |
| React | 19.x | UI layer | Required by Next.js 15; concurrent rendering improves chart update performance |
| TypeScript | 5.x | Type safety | Non-negotiable for a system passing financial signals; catches data schema drift |
| Tailwind CSS | 4.x | Styling | Zero-config for dashboard layouts; pairs with shadcn/ui |
| shadcn/ui | latest | Component primitives | Radix-based accessible components; no lock-in (source-available); pairs with Tremor |
| Tremor | 3.x | Chart dashboard components | Built on Recharts + Radix + Tailwind; provides AreaChart, LineChart, BarChart, KPI cards out of the box; ideal for signal performance tracking |
| TradingView Lightweight Charts | 5.1.0 | Candlestick / line charts for signal overlay visualization | Purpose-built for financial data; 45KB bundle; data conflation at v5.1 handles large tick datasets; the correct choice for any OHLC display |
| Recharts | 2.x | Supporting charts (scatter plots, distribution histograms) | Already a Tremor dependency; use directly for custom chart types Tremor doesn't expose |
| Server-Sent Events (native) | — | Real-time signal push from FastAPI → dashboard | One-way push from Python backend; no WebSocket complexity; correct for dashboard read-only updates; native to Next.js App Router Route Handlers with `force-dynamic` |

**What NOT to use:**

- **D3.js / visx directly**: Too low-level for dashboard; use Recharts/Lightweight Charts as the D3 abstraction
- **WebSockets (Socket.io) for the dashboard**: Bidirectional not needed; SSE is simpler and sufficient for one-way signal streaming
- **Chart.js**: Less TypeScript-friendly than Recharts; worse React integration
- **Electron**: Not needed; browser-based dashboard is sufficient; NT8 handles the native window

**Confidence: HIGH** — Next.js 15, Tremor 3.x, and Lightweight Charts v5.1 verified against official release pages/GitHub.

---

### NT8 ↔ Python Data Bridge

This is the highest-risk architectural decision. Three viable patterns exist. Recommendation is the file-based bridge for Phase 1, upgrading to TCP socket for Phase 2.

#### Phase 1 Recommendation: File-Based Bridge (CSV append + filesystem watch)

**NT8 side (C#):**
```csharp
// In OnBarUpdate or OnMarketData, after Scorer():
using var sw = File.AppendText(@"C:\deep6\bridge\signals.csv");
sw.WriteLine($"{DateTime.Now:O},{_total},{_sigDir},{_sigTyp},{_fpSc},{_trSc},...");
```

**Python side:**
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
# Tail signals.csv; parse new rows; push to FastAPI; write back optimized params
```

**Why file-first:**
- Zero dependencies on NT8 internals; does not require NT8's TCP port to be open
- Works regardless of NT8 version or permissions
- StreamWriter-based CSV export is explicitly documented in NT8 support forums with working code samples
- Debug-friendly: CSV is human-readable audit trail
- **Latency:** 50-500ms depending on poll interval — acceptable for ML batch processing (not HFT)

**Confidence: HIGH** — StreamWriter CSV export is a documented, production-used NT8 pattern.

#### Phase 2 Upgrade: TCP Socket Bridge (ZeroMQ PUB/SUB)

**NT8 side (C#):** Add `NetMQ` (the .NET ZeroMQ binding) to the Custom folder. NT8 can load external DLLs placed in `Documents\NinjaTrader 8\bin\Custom`.

**Python side:**
```python
import zmq
ctx = zmq.Context()
sock = ctx.socket(zmq.SUB)
sock.connect("tcp://localhost:5555")
sock.setsockopt_string(zmq.SUBSCRIBE, "")
```

**Why ZeroMQ over raw TCP or named pipes:**
- ZeroMQ handles reconnection, framing, and backpressure automatically
- PUB/SUB pattern: NT8 publishes, Python subscribes — multiple Python consumers possible
- pyzmq (27.1.0) is stable; clrzmq4 / NetMQ is the .NET binding
- Latency: ~1-5ms — sufficient for ML signal processing
- Named pipes are Windows-only and require matching .NET pipe client; more complex than ZeroMQ

**What NOT to use for the bridge:**
- **HTTP polling from Python → NT8**: NT8 doesn't run an HTTP server natively; would require a full NT8 Add-On
- **COM/DDE**: Legacy Windows IPC; fragile; no Python support without pywin32 hacks
- **Shared memory**: Complex synchronization; not worth it for signal rates (~1-10 signals/minute)
- **WebSocket from NT8**: NT8 NinjaScript doesn't have a native WebSocket server; requires third-party NT8 Add-On

**Confidence: MEDIUM** — ZeroMQ pattern is documented in NT8 community. NetMQ DLL loading inside NT8 Custom folder requires validation on target Windows environment. File bridge is confirmed HIGH confidence.

---

### GEX Data Integration

GEX for NQ is uniquely complex because NQ futures options exist on CME (not CBOE), and the mainstream GEX analytics providers focus on equity index options (SPX, NDX) and ETF proxies (QQQ).

#### Primary Recommendation: FlashAlpha API

| Criterion | Detail |
|-----------|--------|
| API access | YES — REST API with Python SDK (`pip install flashalpha`) |
| NQ coverage | QQQ proxy (NQ is mapped from QQQ option chain by convention); NDX available at Basic+ |
| GEX endpoint | `/v1/exposure/gex/{symbol}` — returns net GEX, gamma flip, call/put walls, regime |
| Pricing | Free: 5 req/day — dev only. Basic: $49/mo, 100 req/day — sufficient for end-of-day GEX updates. Growth: $299/mo, 2,500 req/day — for real-time polling |
| Python SDK | Official: `pip install flashalpha`. Typed responses, retry logic |
| C# SDK | Official: `dotnet add package FlashAlpha` — could be used directly from NT8 if needed |

**Recommended tier:** Basic ($49/mo) for initial integration. GEX levels change slowly (meaningful moves happen at major option strikes); polling once per minute is sufficient. 100 req/day = ~6-second poll interval during RTH (6.5 hours × 60 min = 390 minutes), so hourly polling fits comfortably. Upgrade to Growth if you want 1-minute resolution.

#### Secondary Option: GEXStream

- $29.50/mo (Basic) or $99.50/mo (Flow)
- Covers QQQ, SPY, SPX, and major ETFs — NQ proxy via QQQ
- API access not clearly documented (requires account/docs review)
- Use as a manual cross-reference until API access is confirmed

#### What NOT to use:

- **SpotGamma:** No programmatic API access — confirmed. Web-only subscription. Cannot be integrated into an automated pipeline.
- **Barchart.com GEX charts:** No API; web scraping is against ToS and fragile
- **Manual GEX entry (current E6 approach):** Sufficient for v1.0.0 but blocks automated regime detection in v2.0
- **Building your own GEX calculator:** Requires options chain data feed (OPRA), which costs $500-2,000/month for CME options data; not cost-effective

**NQ-specific note:** NQ futures themselves are not equity options. True NQ gamma exposure requires CME futures options data. QQQ is the best available proxy at retail/institutional-API price points. The mapping (NQ price → QQQ × 40 scaling factor) introduces basis risk but is the standard approach used by MenthorQ, TanukiTrade, and GEXStream for retail NQ GEX.

**Confidence: MEDIUM** — FlashAlpha API coverage for NQ/NDX confirmed at pricing page; QQQ-as-NQ-proxy confirmed as industry standard. Exact QQQ→NQ mapping accuracy requires live validation.

---

### Backtesting Framework

NT8's built-in Strategy Analyzer is the authoritative backtesting environment for NT8-native signals,
but it is Windows-only and cannot be called from Python. The recommended approach is a two-layer architecture:

#### Layer 1: NT8 Strategy Analyzer (Signal Validation)

Use NT8's native tick replay to validate signal logic correctness. NT8 Tick Replay mode replays historical
market data events in the exact sequence they occurred, including `OnMarketDepth` callbacks — critical
for E2/E3/E4 engines that depend on DOM data.

**NT8 data export for backtesting:**
1. Write a thin NT8 Strategy that calls the same engine methods as the indicator
2. In `OnBarUpdate`, write bar-level signal outputs to CSV via `StreamWriter`
3. Export: timestamp, OHLCV, all engine scores, signal direction, signal type, P&L
4. Import CSV into Python for statistical analysis and parameter optimization

**NT8 backtesting constraints:**
- Tick Replay cannot be used in Strategy Analyzer simultaneously with Market Replay data
- Historical tick data: 360 days on NT8 servers; use Rithmic historical tick export for deeper history
- VolumetricBarsType requires Tick Replay enabled for accurate footprint backtesting

#### Layer 2: vectorbt 0.28.5 (Python-Side Statistical Analysis)

Use vectorbt to run portfolio simulations, parameter sweeps, and signal attribution analysis on the
exported NT8 CSV data — NOT to re-implement the signal logic.

| Criterion | Detail |
|-----------|--------|
| Version | 0.28.5 (Mar 2026) — actively maintained |
| Python support | 3.10-3.13 |
| Tick support | Native tick-level resolution (added in 0.28.x) |
| Speed | Numba-compiled; handles millions of bars without memory issues |
| Use case | Sweep Optuna-selected parameters across historical signal CSVs; plot equity curves |

**What NOT to use:**

- **Backtrader:** Slower event-loop architecture; fine for strategy logic testing but not parameter sweeps
- **Zipline:** Effectively unmaintained for futures; equity-centric
- **QuantConnect LEAN:** Full platform with licensing complexity; overkill for CSV-based parameter analysis
- **Re-implementing signal logic in Python for backtesting:** The NT8 C# implementation IS the signal logic; reimplementing it in Python creates two sources of truth that will diverge

**Confidence: MEDIUM** — vectorbt 0.28.5 confirmed active on PyPI. NT8 tick replay + CSV export pattern is documented in NT8 forums. The two-layer approach is a pragmatic workaround for NT8's closed runtime.

---

## Full Installation Reference

### Python Environment

```bash
# Create virtual environment (use Python 3.12)
python3.12 -m venv .venv
source .venv/bin/activate  # macOS/Linux dev
# .venv\Scripts\activate   # Windows production

# Core API
pip install fastapi==0.135.3 uvicorn[standard]

# ML stack
pip install scikit-learn==1.8.0 xgboost==3.2.0 optuna==4.8.0 hmmlearn==0.3.3

# Optuna integrations
pip install optuna-integration[xgboost]

# Data
pip install numpy pandas pyarrow

# Database / ORM
pip install sqlalchemy==2.0.49 aiosqlite

# Scheduling
pip install apscheduler

# NT8 bridge (Phase 2 ZeroMQ)
pip install pyzmq==27.1.0

# File bridge watching (Phase 1)
pip install watchdog

# GEX data
pip install flashalpha

# Backtesting
pip install vectorbt==0.28.5
```

### Next.js Dashboard

```bash
npx create-next-app@latest deep6-dashboard --typescript --tailwind --app
cd deep6-dashboard

# Component library
npx shadcn@latest init
npm install @tremor/react

# Charting
npm install lightweight-charts@5.1.0
npm install recharts

# Utilities
npm install swr  # for data fetching with revalidation
```

### NT8 C# (No New Dependencies)

The NT8 refactor uses partial classes — no new NuGet packages. For Phase 2 ZeroMQ bridge,
place `NetMQ.dll` and `AsyncIO.dll` in `Documents\NinjaTrader 8\bin\Custom\` and reference
via the NinjaScript Editor's assembly reference list.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Python API | FastAPI 0.135.3 | Flask 3.x | No async; inferior for ML streaming endpoints |
| Python API | FastAPI | Django REST | Too heavyweight; ORM coupling; not needed |
| HPO | Optuna 4.8.0 | Ray Tune | Multi-machine overkill; complex setup for single-machine HPO |
| HPO | Optuna | GridSearchCV | Exponential search space; Bayesian optimization 10-100x more efficient |
| ML models | XGBoost + scikit-learn | PyTorch | Deep learning underperforms on small tabular datasets; training complexity not justified |
| Regime detection | hmmlearn (HMM) | K-Means clustering | HMM captures temporal state transitions — critical for regime "stickiness" detection |
| Bridge Phase 1 | File + watchdog | ZeroMQ immediately | ZeroMQ requires NetMQ DLL validation in NT8 environment; file bridge is zero-risk |
| Bridge Phase 2 | ZeroMQ (NetMQ) | Named pipes | Named pipes require matching .NET pipe client; ZeroMQ handles framing/reconnect |
| Bridge Phase 2 | ZeroMQ | Raw TCP | ZeroMQ adds reconnection, backpressure, multi-subscriber at no cost |
| Database | SQLite + SQLAlchemy | TimescaleDB | No operational overhead justified for single-user system; portable to TimescaleDB later |
| Dashboard charts | Tremor + Lightweight Charts | D3.js | D3 is 200+ hours of custom charting; Tremor provides production-ready components |
| Dashboard charts | Lightweight Charts v5 | Recharts for OHLC | Recharts is not designed for financial OHLC; Lightweight Charts is purpose-built |
| Real-time push | SSE (native) | WebSockets / Socket.io | SSE is read-only push — correct for dashboard; no bidirectional complexity |
| Backtesting | vectorbt + NT8 CSV export | Backtrader | vectorbt 10-100x faster for parameter sweeps; Backtrader event-loop too slow |
| GEX data | FlashAlpha API | SpotGamma | SpotGamma has NO API; web-only subscription |
| GEX data | FlashAlpha | Build from OPRA | OPRA CME options data costs $500-2,000/month; not cost-effective |

---

## Architecture Boundary: What Runs Where

```
Windows Trading Box (NT8)
├── DEEP6.cs (partial classes)  ← C# / .NET 4.8 / NinjaScript
│   ├── 44 signals + engines
│   ├── SharpDX renderer
│   ├── WPF UI panels
│   └── Bridge writer (StreamWriter CSV or ZeroMQ PUB)
│
├── bridge/
│   └── signals.csv             ← Shared file (Phase 1 bridge)
│
└── Python ML Backend (FastAPI)  ← Python 3.12 / Windows or macOS
    ├── POST /signals            ← Receives NT8 signal stream
    ├── GET  /params             ← Returns optimized parameters
    ├── SSE  /stream             ← Pushes to Next.js dashboard
    └── SQLite                   ← Persists signal history + trade logs

Any Machine (macOS dev or same Windows box)
└── Next.js Dashboard            ← Node.js + browser
    ├── Signal performance charts (Tremor/Recharts)
    ├── OHLC + signal overlay (Lightweight Charts)
    └── Regime classification panel
```

---

## Phase-Specific Stack Notes

| Phase | Stack Element | Note |
|-------|---------------|------|
| 44-signal expansion | C# partial classes | Refactor DEEP6.cs before adding signals — otherwise unmaintainable |
| GEX integration | FlashAlpha API Basic tier | Provision API key before building E6 GEX regime logic |
| Bridge Phase 1 | StreamWriter CSV + watchdog | Implement this before any ML work — data collection must start first |
| ML backend | FastAPI + SQLite + XGBoost + Optuna | Build after 2+ weeks of signal data collection |
| Dashboard | Next.js 15 + Tremor + Lightweight Charts | Build after ML backend has endpoints; use SSE for live signal feed |
| Bridge Phase 2 | ZeroMQ (NetMQ + pyzmq) | Upgrade if file bridge latency proves limiting for real-time parameter feedback |
| Backtesting | vectorbt + NT8 CSV export | Requires NT8 Strategy implementation; separate from indicator refactor |

---

## Sources

- FastAPI 0.135.3: [https://pypi.org/project/fastapi/](https://pypi.org/project/fastapi/)
- scikit-learn 1.8.0: [https://pypi.org/project/scikit-learn/](https://pypi.org/project/scikit-learn/)
- XGBoost 3.2.0: [https://pypi.org/project/xgboost/](https://pypi.org/project/xgboost/)
- Optuna 4.8.0: [https://pypi.org/project/optuna/](https://pypi.org/project/optuna/)
- hmmlearn 0.3.3: [https://pypi.org/project/hmmlearn/](https://pypi.org/project/hmmlearn/)
- SQLAlchemy 2.0.49: [https://pypi.org/project/SQLAlchemy/](https://pypi.org/project/SQLAlchemy/)
- pyzmq 27.1.0: [https://pypi.org/project/pyzmq/](https://pypi.org/project/pyzmq/)
- vectorbt 0.28.5: [https://pypi.org/project/vectorbt/](https://pypi.org/project/vectorbt/)
- Lightweight Charts v5.1.0: [https://github.com/tradingview/lightweight-charts/releases](https://github.com/tradingview/lightweight-charts/releases)
- FlashAlpha API pricing: [https://flashalpha.com/pricing](https://flashalpha.com/pricing)
- GEXStream pricing: [https://gexstream.com/](https://gexstream.com/)
- SpotGamma (no API confirmed): [https://spotgamma.com/subscribe-to-spotgamma/](https://spotgamma.com/subscribe-to-spotgamma/)
- NinjaTrader StreamWriter pattern: [https://forum.ninjatrader.com/forum/ninjascript-educational-resources/reference-samples/3581-indicator-using-streamwriter-to-write-to-a-text-file](https://forum.ninjatrader.com/forum/ninjascript-educational-resources/reference-samples/3581-indicator-using-streamwriter-to-write-to-a-text-file)
- NT8 Tick Replay: [https://ninjatrader.com/support/helpguides/nt8/tick_replay.htm](https://ninjatrader.com/support/helpguides/nt8/tick_replay.htm)
- ZeroMQ NT8 pattern: [https://basicsoftradingstocks.wordpress.com/2020/03/28/quick-way-of-setting-up-zeromq-ipc-messaging-inside-of-ninjatrader-8-stream-data-and-signals-in-out-of-nt8/](https://basicsoftradingstocks.wordpress.com/2020/03/28/quick-way-of-setting-up-zeromq-ipc-messaging-inside-of-ninjatrader-8-stream-data-and-signals-in-out-of-nt8/)
- MenthorQ NQ GEX via QQQ proxy: [https://menthorq.com/guide/gamma-levels-on-futures-options/](https://menthorq.com/guide/gamma-levels-on-futures-options/)
- Next.js 15 SSE: [https://damianhodgkiss.com/tutorials/real-time-updates-sse-nextjs](https://damianhodgkiss.com/tutorials/real-time-updates-sse-nextjs)
- Tremor: [https://www.tremor.so/](https://www.tremor.so/)

---

*Stack research: 2026-04-11 | All library versions verified against PyPI official release pages*
