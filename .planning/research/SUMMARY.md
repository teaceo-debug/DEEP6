# Research Summary: DEEP6 v2.0 — Python Footprint Auto-Trading System

**Synthesized:** 2026-04-11
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md
**Consumer:** gsd-roadmapper agent

---

## Executive Summary

DEEP6 v2.0 is a greenfield Python rewrite of a production NQ futures footprint auto-trading system. All domain logic — 44 signals across 8 categories, absorption/exhaustion/imbalance detection, LVN/HVN zone lifecycle, the scoring cascade, and ML dimensions (E7 XGBoost, E10 Kronos) — carries forward from v1 research unchanged. What changes is everything below the domain: NinjaTrader 8 and C# are replaced by Python 3.12, asyncio, and async-rithmic, giving the system proper module structure, macOS-native operation, direct Rithmic execution without NT8 overhead, and a legitimate backtesting pipeline via Databento MBO historical replay.

The architecture answer is clear: a single asyncio event loop (with uvloop) handles 1,000+ DOM callbacks/sec without contention because the event loop is single-threaded -- no locks on shared state needed. Signal computation runs synchronously at bar close (not per tick), completing well under 100ms for all 44 signals on in-memory arrays. Kronos (E10 ML bias) runs in a dedicated subprocess with a persistent GPU model load, communicating over a multiprocessing.Pipe so inference latency (50-400ms) never stalls the event loop. The system critical correctness dependency is tick classification: Rithmic natively provides the aggressor field (TransactionType.BUY/SELL), which must be verified in async-rithmic callback structure before the footprint engine is built -- if absent, all 44 downstream signals are degraded.

The Python pivot eliminates five specific v1 pitfalls (DOM backtesting impossibility, NT8 race conditions, monolithic NinjaScript file limits, Pine Script timing mismatches, ATM Strategy slippage) while introducing three new critical risks: asyncio event loop blocking from CPU work in callbacks, Python GC pauses corrupting DOM state at high callback frequency, and async-rithmic status as a single-maintainer community library with one open production reconnection bug. These risks are well-understood and have documented mitigations; they must be designed around from Phase 1, not retrofitted.

---

## Stack Decisions

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| Data + Execution | async-rithmic | 1.5.9 | Only Python-native Rithmic library; L2 DOM, live ticks, order management via WebSocket + protobuf; macOS native |
| Runtime | Python | 3.12 | async-rithmic requires 3.10+; 3.12 is ecosystem sweet spot; do NOT use 3.13 free-threaded build |
| Event loop | uvloop | latest | 2-4x faster callback throughput, 50%+ tail latency reduction; mandatory for 1,000/sec DOM workload |
| ML E10 Bias | Kronos-small | 24.7M params | Decoder-only Transformer on 45+ exchanges; cloned from GitHub; weights from NeoQuasar/Kronos-small |
| ML E7 Quality | XGBoost | latest | ~0.7ms single-sample inference; run via thread executor (XGBoost releases GIL during C++ traversal) |
| Chart analysis | TradingView MCP | tradesdontlie fork | 78 tools via Chrome DevTools Protocol; NOT in signal pipeline; on-demand only |
| Historical backtest | Databento | latest SDK | MBO (L3) NQ data from CME colocation, nanosecond timestamps; only correct DOM backtesting path |
| API backend | FastAPI + Uvicorn | 0.135.3 / 0.34+ | Runs in same asyncio event loop as trading engine; SSE for signals, WebSocket for footprint bars |
| Dashboard | Next.js + Lightweight Charts | 15.x / 5.1.0 | App Router; Tremor components; Lightweight Charts custom series for footprint rendering |
| Async bridge | janus | latest | Thread-safe asyncio-aware queue; required where sync PyTorch threads hand off to async engine |

Critical version constraint: Standard CPython 3.12 (GIL-enabled) only. Python 3.13 free-threaded build is architecturally immature for asyncio + NumPy in trading contexts as of April 2026.

async-rithmic risk: Single maintainer (rundef). GitHub Issue #49 (ForcedLogout reconnection loop, March 2026) is an open production bug. Mitigation: pin to 1.5.9, maintain local fork, connect plants sequentially with 500ms delay.

---

## Feature Priorities

### Phase 1 Must-Have: Footprint Engine (Foundation)

Getting the footprint bar right is binary. All 44 signals downstream are only as correct as the bid/ask volume split per price level.

1. Tick classification -- Verify aggressor field in async-rithmic LAST_TRADE callback. Use it directly. Do NOT implement Lee-Ready. For Databento MBO backtesting, use native side field (F=buyer, A=seller from CME).
2. FootprintBar accumulator -- defaultdict(FootprintLevel) keyed by integer tick index (round(price / 0.25)). Never float keys. Compute derived fields only at bar close.
3. BarBuilder -- Time-based bar close using async-rithmic native time bar subscription.
4. DOMState -- Pre-allocated array.array (40 levels per side). In-place index assignment. Zero allocation in hot path.

### Phase 2 Must-Have: Signal Engine Cascade (Sequential at Bar Close)

Implement in dependency order:
- E1 FootprintEngine: absorption variants, stopping volume, effort vs result, zero/thin/fat prints, bid/ask fade, imbalance (diagonal + stacked + inverse), bar narrative
- E9 AuctionFSM: driven by zero/thin prints from E1; unfinished auction levels persist cross-session to SQLite
- E8 CVDEngine: linear regression slope on rolling delta deque; divergence detection
- E6 VPCtxEngine: LVN/HVN via scipy.signal.find_peaks, VWAP, IB, POC, GEX proximity; zone lifecycle FSM (5 states)
- E2 TrespassEngine: DOM queue imbalance from DOMSnapshot
- E3 CounterspoofEngine: Wasserstein-1 distance on DOM distributions; cancel detection
- E4 IcebergEngine: native/synthetic iceberg detection from TickBuffer + DOMSnapshot
- E5 MicroEngine: Naive Bayes combination of E1/E2/E4 outputs
- E7 MLQualityEngine: XGBoost quality multiplier; returns 1.0 (neutral) when model not yet trained
- E10 KronosBiasEngine: directional bias from ensemble Kronos samples; every 5 bars; confidence decay between updates

### Phase 3 Must-Have: Scorer + Backtesting Framework

- 44-signal weighted cascade to ScorerResult; zone bonuses; confluence gating
- Databento MBO replay engine generating ground-truth signal labels per bar (vectorbt cannot replay DOM state)
- vectorbt portfolio simulation on labeled signal DataFrame (portfolio sim only)
- Initial XGBoost E7 training pipeline with purged walk-forward validation (6-month train / 2-month test)

### Phase 4 Must-Have: Execution + Risk Layer

- ExecutionGateway: order build + submit via async-rithmic OrderPlant
- Rithmic server-side bracket order submission (stop + target at Rithmic, not managed client-side)
- RiskGateway: daily loss limit, max 1 open position, consecutive-loss cooldown
- asyncio.Lock() on entry logic; TRADING_FROZEN reconnection state; position persistence to disk
- 30-day paper trading minimum before live capital

### Defer to v2+

- Multi-instrument support
- ZoneRegistry in Redis (currently in-memory)
- TradingView MCP to DEEP6 signal annotation bridge
- Lightweight Charts custom footprint series (Plotly/Dash initially)
- Free-threaded CPython (Python 3.15 era)

---

## Architecture Approach

Single-process, single asyncio event loop (uvloop). All live trading logic in one Python process.

Shared state (DOMState, TickBuffer, FootprintBar, BarHistory, ZoneRegistry, PositionState, ScorerState) is written and read sequentially by the event loop. Zero locks needed. Zero races possible at await boundaries.

Long-lived tasks via asyncio.gather:
- dom_feed_loop: receives DOM updates, mutates DOMState in-place
- tick_feed_loop: receives trades, updates TickBuffer + current FootprintBar
- bar_engine_loop: detects bar close, runs all 9 engines sequentially, writes ScorerResult
- execution_loop: reads ScorerResult queue, submits orders, manages fills
- gex_poll_loop: HTTP polls FlashAlpha every 60s
- api_server: FastAPI/Uvicorn as asyncio coroutine (loop=none)
- kronos_result_consumer: awaits pipe results from Kronos subprocess via thread executor

Two true process boundaries:
1. Kronos subprocess: persistent multiprocessing.Process, model loaded once in GPU/MPS memory, receives OHLCV batch via multiprocessing.Pipe, sends KronosResult back. Main process reads pipe via loop.run_in_executor(thread_pool, pipe.recv).
2. Databento backtesting: separate process; does not touch the live architecture.

Non-negotiable hot path rules:
- DOM callback: update arrays in-place only. No signal computation. No allocation. No asyncio.create_task().
- Tick callback: TickBuffer.append() + FootprintBar.add_trade(). Both O(1), sub-microsecond.
- Signal computation: runs once at bar close synchronously inside bar_engine_loop. Budget: under 10ms actual; 100ms allocated.
- XGBoost (E7): loop.run_in_executor(thread_executor) -- GIL released during C++ tree traversal.
- Kronos: dedicated subprocess only. Never in event loop. Never in thread executor.

State design rules:
- DOMState: array.array pre-allocated to 40 levels per side; in-place index assignment only
- FootprintBar: defaultdict for live accumulation; convert to NumPy after bar close for vectorized signal detection
- All hot-path dataclasses: @dataclass(slots=True) to eliminate __dict__ allocation
- Disable CPython cyclic GC during market hours (gc.disable() at session open)

TradingView MCP: Separate Claude Code sidecar. Never in signal pipeline. CDP on localhost:9222. 100ms-1s round-trip -- correct for human workflow, unacceptable in signal path.

Package structure: deep6/ with state/, data/, engines/, scoring/, execution/, ml/, api/, backtesting/ subdirectories. Nine engine modules (e1_footprint.py through e9_auction.py). SignalFlags as Python IntFlag enum (64-bit native, no overflow).

---

## Critical Pitfalls (Top 5 That Could Kill the Project)

### Pitfall 1: asyncio Event Loop Blocked by CPU Work (CRITICAL -- Phase 1)
Any blocking call inside a coroutine freezes all DOM callbacks and order management. At 1,000 DOM callbacks/sec, a 10ms block loses 10 DOM updates. System appears correct in slow markets; fails precisely when NQ is moving fastest.

Prevention: 100-microsecond CPU budget for anything in DOM callbacks. Signal computation deferred to bar_engine_loop (once per bar). Kronos in dedicated subprocess. XGBoost in thread executor. Instrument event loop lag on day one.

### Pitfall 2: Tick Classification Silent Error (CRITICAL -- Phase 1)
If async-rithmic does not surface the aggressor field (or surfaces UNKNOWN values), the footprint accumulator silently uses the wrong bid/ask split. All 44 signals downstream are degraded. Absorption signals fire on bars where no absorption occurred.

Prevention: Inspect async-rithmic on_trade callback structure before writing any footprint code. Track a classification confidence metric. Compare live footprint bars to Bookmap as ground truth.

### Pitfall 3: Python GC Pauses at Peak Volatility (CRITICAL -- Phase 1)
At 1,000 DOM callbacks/sec, allocating new Python objects per callback triggers CPython cyclic GC at exactly the highest-volume moments. GC pauses of 5-50ms produce stale DOM snapshots with incorrect price level sizes.

Prevention: Pre-allocate DOMState as fixed array.array. Use __slots__ on all hot-path dataclasses. Disable cyclic GC during market hours. Monitor allocation rate with tracemalloc in development (target: under 1KB/sec in DOM loop).

### Pitfall 4: Reconnection During Open Position -- Position Desync (CRITICAL -- Phase 4)
async-rithmic Issue #49 (March 2026): simultaneous plant connections cause ForcedLogout reconnection loop. During any reconnection gap, fills and stop executions at the exchange are not replayed. Python system shows FLAT while exchange holds open position. System re-enters, doubling exposure.

Prevention: Connect plants sequentially with 500ms delay. On every ORDER_PLANT reconnection: query Rithmic position API before resuming. Set TRADING_FROZEN = True during reconnection. Use Rithmic server-side bracket orders so stops/targets persist at exchange independent of client connection.

### Pitfall 5: Signal Correlation Masquerading as Independent Confirmation (CRITICAL -- Phase 2)
44 signals from the same bid/ask volume data are naturally correlated. XGBoost + Optuna will discover that weighting correlated signals together maximizes backtest Sharpe -- which is in-sample overfitting amplified by the optimizer.

Prevention: Compute pairwise Pearson correlation matrix before finalizing signal taxonomy. Collapse or drop any pair with r > 0.7. L1 regularization on XGBoost. Cap any single signal weight at 3x baseline without manual override. Require 200+ OOS trades per signal in purged walk-forward validation.

---

## v1 Pitfalls Eliminated by the Python Pivot

| v1 Pitfall | Why Eliminated |
|-----------|---------------|
| DOM backtesting impossible in NT8 | Databento MBO replay provides true L3 DOM history with nanosecond timestamps and exchange aggressor flags |
| NT8 race conditions between DOM and bar threads | asyncio is single-threaded; event loop serializes all state mutations at await boundaries |
| Monolithic NinjaScript file (partial class limits) | Python allows proper module/package structure from day one |
| Pine Script to C# execution timing mismatch | No Pine Script port; Python feeds directly from Rithmic data stream |
| ATM Strategy slippage and order routing overhead | Direct async-rithmic OrderPlant bypass; 5-20ms signal-to-order vs 50-200ms through NT8 ATM |

---

## Open Questions Requiring Live Validation

1. Does async-rithmic surface the aggressor field? Inspect on_trade callback in paper trading. Confirm data[aggressor] exists with TransactionType.BUY/SELL (not UNKNOWN). Must be answered before any footprint code is written.

2. What is Kronos-small inference latency on the actual target hardware? M2 Mac MPS estimate (200-400ms) is extrapolated. Run KronosPredictor.predict() with 400 bars on production machine before committing to bar type and inference cadence.

3. Does async-rithmic Issue #49 affect the specific broker setup? Test sequential plant connection in paper trading. Verify no ForcedLogout loop with specific broker Rithmic endpoint.

4. What is the actual DOM callback rate for NQ during peak volatility? The 1,000/sec figure is from general research. Instrument live callback rate in paper trading. If peak exceeds 2,000/sec, pre-allocation sizes and GC thresholds need recalibration.

5. Does Databento MBO live feed match async-rithmic footprint bars? After footprint engine is built, subscribe both feeds simultaneously and compare FootprintBar.bar_delta, POC, and bid/ask volumes bar-for-bar. Divergence over 2% indicates aggressor classification issue.

---

## Recommended Phase Ordering

### Phase 1: Data Pipeline Foundation
Delivers: async-rithmic connection, DOMState pre-allocated arrays, tick classification verification, FootprintBar accumulator, BarBuilder, session context, session state persistence to disk.

Rationale: Nothing else can be built until tick classification is confirmed correct and bars close with accurate bid/ask volumes. Resolves the highest-uncertainty item (async-rithmic aggressor field) before any signal logic is written.

Pitfalls addressed: Event loop blocking budget (100us rule), DOM pre-allocation (no per-callback allocation), integer tick keys from line 1, WebSocket zombie detection (data watchdog task), session persistence (IB/CVD anchors every minute).

Research flag: NEEDS PHASE RESEARCH -- async-rithmic callback API must be tested hands-on before footprint engine design is finalized. Kronos hardware benchmark also belongs here.

### Phase 2: Signal Engine Cascade
Delivers: All 9 signal engines (E1-E9) tested on Databento MBO data, correct signal flags and scores per bar, ZoneRegistry operational, AuctionFSM cross-session persistence, pairwise correlation audit completed.

Rationale: Engines implemented in dependency order. Signal taxonomy carries forward from v1 -- implementation, not design, is the work here.

Pitfalls addressed: Signal correlation overfitting (Pearson audit before Scorer finalized), float comparison errors, zero-print edge cases.

Research flag: Standard patterns -- no additional research phase needed.

### Phase 3: Scorer + Backtesting Framework
Delivers: 44-signal weighted cascade, ScorerResult, Databento MBO replay engine generating ground-truth signal labels, vectorbt portfolio simulation, initial XGBoost E7 training pipeline.

Rationale: Scorer cannot be calibrated without a backtesting framework. MBO replay is the correct backbone. E7 XGBoost training requires labeled signal output from this phase.

Pitfalls addressed: vectorbt used for signal logic (portfolio sim only), Optuna reinforcing overfit signals (L1 + CPCV from day one), MBO replay/live divergence from mid-session crash.

Research flag: NEEDS PHASE RESEARCH -- Databento MBO replay engine design; CPCV implementation via mlfinlab.

### Phase 4: Execution + Risk Layer
Delivers: ExecutionGateway, RiskGateway (circuit breakers), Rithmic server-side bracket orders, asyncio.Lock() entry guard, TRADING_FROZEN reconnection state, position state persistence, 30-day paper trading validation.

Rationale: Risk infrastructure must be built simultaneously with execution. Direct Rithmic execution has none of NT8 built-in safety layers. Reconnection-during-open-position must be tested before any live capital.

Pitfalls addressed: Concurrent asyncio entries without Lock, risk as afterthought, position state desync on reconnection.

Research flag: Standard patterns -- reconnection handling is main new design challenge.

### Phase 5: ML Integration (Kronos E10 + XGBoost Refinement)
Delivers: Kronos subprocess with persistent GPU model load, multiprocessing.Pipe bridge, kronos_result_consumer coroutine, E10 ensemble confidence scoring, XGBoost E7 retrained on Phase 3 labeled data, walk-forward validation framework.

Rationale: Kronos and XGBoost degrade gracefully when unavailable (E10 returns neutral, E7 returns 1.0). Integrate after signal cascade is validated without them.

Pitfalls addressed: Kronos inference blocking event loop (subprocess + pipe only), CPU inference exceeding bar duration (measure on hardware first), XGBoost overfitting via Optuna.

Research flag: NEEDS PHASE RESEARCH -- Kronos subprocess architecture must be verified against actual KronosPredictor API; pipe.recv via thread executor pattern needs validation on target hardware.

### Phase 6: Dashboard + FastAPI API Layer
Delivers: FastAPI in same asyncio event loop (loop=none), WebSocket broadcaster for ScorerResult, SSE for signal state, Next.js dashboard (Tremor KPIs, Plotly footprint initially), optimization trigger endpoint.

Rationale: Dashboard is observability infrastructure. Implement after trading engine is validated and paper-traded.

Pitfalls addressed: FastAPI startup conflicting with asyncio.gather (uvicorn.Config(loop=none)), WebSocket broadcaster creating tasks in hot path (put_nowait() on queue instead).

Research flag: Standard patterns -- well-documented.

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Stack -- async-rithmic | HIGH capability / MEDIUM API specifics | v1.5.9 on PyPI + GitHub; docs partially 403; callback data structure unverified hands-on |
| Stack -- Kronos | MEDIUM | Official GitHub + arXiv paper; CPU/MPS latency extrapolated, not measured on target hardware |
| Stack -- Databento | HIGH | Official docs confirmed; one known live vs historical exception documented |
| Stack -- FastAPI/Next.js | HIGH | Official docs; unchanged from v1 research |
| Features -- footprint engine | HIGH | All algorithms confirmed; aggressor field in async-rithmic is the one unverified dependency |
| Features -- 44-signal implementations | HIGH | Python implementations for all 8 categories with working code; validated v1 domain research |
| Architecture -- asyncio design | HIGH | Well-documented Python fundamentals |
| Architecture -- Kronos subprocess | MEDIUM | Pattern is clear; KronosPredictor API specifics need hands-on verification |
| Pitfalls -- async-rithmic reconnection | MEDIUM | Issue #49 confirmed; full production behavior unverified |
| Pitfalls -- GC behavior | HIGH | CPython cyclic GC well-documented; mitigations are standard |

Overall: HIGH confidence for design decisions. MEDIUM confidence for async-rithmic callback specifics and Kronos hardware latency.

---

## Gaps to Address in Planning

1. async-rithmic aggressor field verification -- First task of Phase 1. If absent or unreliable, footprint engine design forks significantly.
2. Kronos CPU/MPS latency benchmark -- Must be measured on actual macOS M2 machine before Phase 5 inference architecture locks.
3. Databento MBO replay performance -- 2M+ events per NQ day at full fidelity takes minutes per historical day. Plan for overnight batch replay jobs.
4. Walk-forward validation implementation -- CPCV via mlfinlab for XGBoost adds complexity. Needs dedicated design before Phase 3 locks.
5. Session state persistence format -- SQLite vs flat file for IB anchor, CVD baseline, unfinished auction levels. Must be decided in Phase 1.

---

## Sources Aggregated from Research Files

async-rithmic: https://github.com/rundef/async_rithmic | https://async-rithmic.readthedocs.io/ | https://pypi.org/project/async-rithmic/ | Issue #49: https://github.com/rundef/async_rithmic/issues/49
Kronos: https://github.com/shiyu-coder/Kronos | https://arxiv.org/abs/2508.02739 | https://huggingface.co/NeoQuasar/Kronos-small
Databento: https://github.com/databento/databento-python | https://databento.com/docs/api-reference-live
uvloop: https://github.com/MagicStack/uvloop
TradingView MCP: https://github.com/tradesdontlie/tradingview-mcp
FastAPI WebSocket: https://fastapi.tiangolo.com/advanced/websockets/
CME MDP 3.0 AggressorSide: https://ref.onixs.biz/net-cme-mdp3-market-data-handler-guide/f-onixs-cmemdhandler-tags-aggressorside.html
Python asyncio docs: https://docs.python.org/3/library/asyncio-dev.html
Free-threaded Python (Optiver 2025): https://optiver.com/working-at-optiver/career-hub/choosing-between-free-threading-and-async-in-python/
asyncio for algo trading: https://medium.com/@trademamba/asyncio-for-algorithmic-trading-part-1-93327929aef6
v1 NT8 research (carries forward): .planning-v1-nt8/research/
