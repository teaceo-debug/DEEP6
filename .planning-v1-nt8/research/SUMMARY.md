# Project Research Summary

**Project:** DEEP6 v2.0 — Institutional Footprint Auto-Trading System
**Domain:** NQ futures footprint analysis with ML-adaptive signal weighting and automated execution
**Researched:** 2026-04-11
**Confidence:** HIGH (NT8 constraints, stack versions); MEDIUM (scoring calibration, GEX API coverage)

---

## Executive Summary

DEEP6 v2.0 is a multi-component trading system built on an existing working NinjaTrader 8 indicator (~1,010 lines, 7 engines, 0-100 scoring). The milestone expands from 3 signal types to a 44-signal taxonomy across 8 categories, adds a Python ML backend for adaptive signal weighting, builds an NT8-to-Python data bridge, integrates GEX options levels via FlashAlpha API, and delivers a Next.js analytics dashboard. The architecture is non-negotiable at the NT8 layer: .NET Framework 4.8, NinjaScript lifecycle, SharpDX rendering. Everything else is a choice.

The recommended approach is strictly sequential and dependency-driven. The NT8 codebase must be refactored into partial classes (Indicators/AddOns pattern) before any signal expansion begins — otherwise the monolith collapses at ~1,800 lines and becomes undebuggable. GC hot-path allocations must be fixed before new signals add to the allocation rate. After those two foundations are in place, signal expansion follows the dependency chain: ATR normalization first (unblocks all thresholds), then absorption/exhaustion (core alpha), then LVN zones and GEX (confluence context), then the execution gate, then ML backend and dashboard in parallel. The data bridge must be stood up early (file-based CSV bridge) to begin collecting the signal history the ML backend needs.

The primary risks are: (1) signal overfitting — 44 signals optimized on a single instrument's historical data will appear to work in backtest and fail live; walk-forward validation with WFE > 70% is mandatory before any ML optimization runs; (2) GC pressure — the hot path already has known allocation issues that will become critical at 44-signal scale; (3) DOM data is structurally unreplayable in NT8 Strategy Analyzer, meaning E2/E3/E4 backtest results are phantom — the first 90 days of live trading are the only valid ground truth for DOM-dependent signals. Risk management (daily loss limits, circuit breakers) must be implemented simultaneously with execution, not after.

---

## Key Findings

### Recommended Stack

The NT8 C# layer is fully constrained: .NET 4.8, NinjaScript, SharpDX, WPF — no alternatives exist within NT8. The file decomposition pattern is `Indicators/DEEP6.cs` as the NT8 facade, with engine logic in `AddOns/` partial class files. This is the only NT8-safe way to modularize without triggering NT8's auto-wrapper compilation errors. Python 3.12 with FastAPI + XGBoost + Optuna + hmmlearn handles the ML backend — all versions verified on PyPI. For the data bridge, a file-based CSV bridge (StreamWriter on NT8 side, watchdog on Python side) is the zero-risk Phase 1; ZeroMQ (NetMQ + pyzmq) is the Phase 2 upgrade for <5ms latency. The Next.js dashboard uses App Router with Tremor for KPI/chart components, TradingView Lightweight Charts v5.1 for OHLC overlays, and SSE (not WebSockets) for one-way real-time signal streaming from FastAPI.

**Core technologies:**
- NinjaScript / .NET 4.8 partial classes (AddOns folder): NT8 modularization — only pattern that compiles safely
- FastAPI 0.135.3 + Uvicorn: Python ML API — async-native, Pydantic v2, 15-20K RPS
- XGBoost 3.2.0 + scikit-learn 1.8.0: Signal classifiers and weight optimization — outperform deep learning on small tabular trading datasets
- Optuna 4.8.0: Hyperparameter optimization — Bayesian HPO, 10-100x more efficient than grid search
- hmmlearn 0.3.3: Regime detection (HMM) — captures temporal state transitions critical for regime stickiness
- SQLAlchemy 2.0.49 + SQLite: Signal/trade history persistence — zero operational overhead, portable to PostgreSQL
- FlashAlpha API (Basic $49/mo): GEX data — only provider with confirmed NQ/NDX coverage and Python SDK
- vectorbt 0.28.5 + NT8 CSV export: Two-layer backtesting — NT8 Strategy Analyzer for signal validation, vectorbt for parameter sweeps
- Next.js 15 (App Router) + Tremor 3.x + Lightweight Charts 5.1: Dashboard — purpose-built for financial data display
- Server-Sent Events (native): Real-time dashboard push — correct for read-only streaming, no WebSocket complexity

**What NOT to use:** Flask (no async), PyTorch/TensorFlow (overkill for tabular data), Celery/Redis (APScheduler sufficient), D3.js directly (Tremor/Recharts abstract it), WebSockets for dashboard (SSE sufficient), SpotGamma (no API), Backtrader (too slow for parameter sweeps), ZeroMQ in Phase 1 (validate file bridge first).

### Expected Features

Absorption and exhaustion are the core value proposition — table stakes, not differentiators. Without all 4 absorption variants and all 6 exhaustion variants, DEEP6 is inferior to TradeDevils and ATAS. ATR normalization is a prerequisite for all signal thresholds.

**Must have (table stakes):**
- Absorption: all 4 variants (classic, passive, stopping volume, effort vs result)
- Exhaustion: all 6 variants (zero print, exhaustion print, thin/fat print, fading momentum, bid/ask fade)
- LVN/HVN zone detection with lifecycle FSM (create/defend/break/flip/invalidate)
- Signal confluence scoring: 44-signal taxonomy with zone proximity bonuses and category agreement multiplier
- GEX level integration (call wall, put wall, gamma flip, HVL) via FlashAlpha API — replaces current manual entry
- Volatility-adaptive ATR normalization for all signal thresholds
- Auto-execution via NT8 ATM with risk gates (TypeB minimum, circuit breakers mandatory)

**Should have (differentiators — absent from all commercial platforms):**
- Narrative candle classification hierarchy (Absorption > Exhaustion > Momentum > Rejection > Quiet)
- Inverse imbalance trap detection — 80-85% win rate per research; no commercial platform classifies this
- E8 CVD multi-bar divergence engine — fires 1-3 bars before single-bar exhaustion
- E9 Auction State Machine (poor high/low, unfinished business, volume void, market sweep)
- ML backend: adaptive signal weighting per regime with human review gate
- Next.js analytics dashboard: personalized signal effectiveness heatmap (signal x regime x context)

**Defer to v2+:**
- Multi-instrument support (ES, YM, MNQ) — NQ must be proven profitable first
- Fully autonomous ML weight deployment — human review gate is permanent, not temporary
- Intrabar execution — bar-close execution is correct and safe
- Real-time web footprint chart replication — NT8 handles this; months of engineering for zero benefit
- Pine Script/TradingView maintenance — archive the reference implementation, never update it

### Architecture Approach

The system decomposes into three runtime boundaries: the NT8 process (C#, bar/depth/data/render threads), the Python ML backend (FastAPI, separate process), and the Next.js dashboard (browser). Within NT8, the facade pattern keeps DEEP6.cs as the sole NT8 lifecycle owner; engine logic lives in AddOns partial class files as testable standalone classes that receive inputs by argument and return `EngineResult` structs. The scoring algorithm has three distinct layers: signal-layer weighted category scoring (100 points, absorption highest at 22), zone interaction bonuses (+8 LVN proximity, capped at +20 total), and a confluence multiplier applied last (1.10 at 4 categories, 1.30 at 6+ categories). Engine voting (existing 4-of-9 agreement) remains as an independent consensus layer.

**Major components:**
1. DEEP6.cs facade (Indicators/) — NT8 lifecycle owner; routes all callbacks to engine partial classes
2. Engine partial classes (AddOns/) — E1 through E9, each a testable standalone class + thin partial DEEP6 connector
3. ZoneRegistry — LVN/HVN zone lifecycle FSM; bar-thread write, snapshot-and-swap for render thread reads
4. Scorer — 44-signal cascade: category weights → zone bonuses → confluence multiplier → 0-100 score
5. ExecutionLayer — NT8 ATM with risk gates; bar-close execution only; circuit breakers from day one
6. IpcBridge — ConcurrentQueue + background thread; file-based CSV Phase 1, ZeroMQ Phase 2
7. Python ML Backend (FastAPI) — signal ingestion, HMM regime detection, XGBoost weight optimization, human-gated deployment
8. Next.js Dashboard — SSE consumer; signal heatmap, regime timeline, parameter drift, live signal feed

**Thread safety rules:** E2/E3 results shared across depth/bar threads use `volatile double` fields. ZoneRegistry uses snapshot-and-swap for render reads. IpcBridge uses `ConcurrentQueue<T>`. Never use `lock()` on NT8 internal objects — confirmed deadlock risk per NT8 forums.

### Critical Pitfalls

1. **GC hot-path allocations will become critical at 44-signal scale** — Fix Std() LINQ allocations (Welford's online algorithm), SolidColorBrush per render cell (32-color palette), and List<T>.RemoveAll() in E3/E4 (circular buffer) BEFORE adding any signals. Target: zero allocations in OnMarketDepth hot path.

2. **DOM data is structurally unreplayable in NT8 Strategy Analyzer** — E2 (Trespass), E3 (Counterspoof), and E4 (Iceberg) cannot be backtested. Enable Market Replay Recorder immediately. Accept that the first 90 days of live trading are the only valid DOM signal ground truth.

3. **44-signal overfitting produces strong backtests and losing live systems** — Walk-forward validation with WFE > 70% is mandatory before any ML optimization. Minimum 200 out-of-sample trades per signal class. A 44-signal system needs 26,400 OOS trades for full statistical validity.

4. **Monolithic file collapse** — DEEP6.cs will reach 1,860+ lines during expansion. Partial class decomposition must happen before signal expansion. Enforce a 1,200-line warning threshold.

5. **GEX data becomes stale intraday** — Refresh at market open and noon only. Add staleness indicator to header bar. Reduce GEX weight after 1 hour, zero after 3 hours. Never use GEX as an entry trigger — only as a filter.

**Additional high-severity:**
- Pine Script execution mismatch: enforce `Calculate.OnBarClose` guards on every ported construct; each signal must fire exactly once per bar
- ATM slippage: model 1 tick average in all backtests; use limit orders; track actual slippage from live day one
- Signal correlation: compute pairwise correlation matrix before finalizing taxonomy; any pair with r > 0.7 must be collapsed
- Risk management as afterthought: daily loss limits, position sizing, circuit breakers must ship in the same phase as execution

---

## Implications for Roadmap

### Phase 1: Architecture Foundation
**Rationale:** GC issues and monolith collapse are production blockers. Nothing else proceeds safely without this.
**Delivers:** Partial class decomposition (AddOns folder pattern); GC hot-path fixes (Welford, pre-allocated brushes, circular buffers); integer tick-index price utility; VolumetricBarsType startup guard; Kalman NaN guard; session mid-load IB detection fix.
**Avoids:** Pitfalls 2 (GC), 8 (monolith), 9 (race conditions), 12 (floating point), 14 (Kalman NaN), 15 (session detection)
**Research flag:** Standard NT8 patterns — skip research phase. Validate AddOns folder partial class compilation on target Windows NT8 environment before committing.

### Phase 2: Signal Core — Absorption and Exhaustion
**Rationale:** Core alpha and primary value proposition. ATR normalization is the prerequisite for all threshold-based signals. Narrative classification must happen before more signals are added — avoids a second refactor.
**Delivers:** ATR normalization; all 4 absorption variants; 4 non-CVD exhaustion variants; narrative candle classification hierarchy; inverse imbalance trap detection.
**Avoids:** Pitfall 5 (Pine → C# execution timing — enforce bar-close guards for every ported construct)
**Research flag:** HIGH confidence on definitions. Inverse imbalance trap detection is novel — validate against live data before including in execution gate.

### Phase 3: LVN Zone Registry and GEX Integration
**Rationale:** LVN zones and GEX are required inputs to the confluence scorer and the TypeA execution gate. Must be stable before execution is enabled.
**Delivers:** LVN/HVN detection from volume profile; zone lifecycle FSM; ZoneRegistry with SharpDX rendering; FlashAlpha GEX API (call wall, put wall, gamma flip, HVL); GEX staleness decay; E9 Auction State Machine.
**Uses:** FlashAlpha Basic tier — provision API key before this phase begins
**Avoids:** Pitfall 7 (GEX staleness — staleness indicator and weight decay designed in, not retrofitted)
**Research flag:** FlashAlpha QQQ-to-NQ proxy accuracy requires live validation. Zone FSM scoring calibration constants need live data.

### Phase 4: E8 CVD, 44-Signal Scorer, and Execution Gate
**Rationale:** E8 CVD enables fading momentum exhaustion (the highest-alpha exhaustion variant). Confluence scorer requires LVN + GEX from Phase 3. Correlation analysis must happen before this phase. Execution requires a stable scorer.
**Delivers:** E8 CVD multi-bar divergence engine; 44-signal SignalFlags bitmask taxonomy; Scorer refactor (category weights, zone bonuses, confluence multiplier); auto-execution via NT8 ATM with full risk gate (TypeB minimum, TypeA preferred, daily loss limit, blackout periods, volatility sizing); circuit breakers.
**Avoids:** Pitfalls 1 (overfitting — correlation matrix before taxonomy finalized), 4 (signal correlation), 6 (ATM slippage), 11 (risk as afterthought)
**Research flag:** Scorer calibration constants need empirical validation against live data. Start conservative and increase based on results.

### Phase 5a: NT8-to-Python Data Bridge + Signal Collection
**Rationale:** ML backend cannot be trained without signal history. File-based bridge must be live 6-8 weeks before ML backend has sufficient data. Can start in parallel with Phase 3 or 4.
**Delivers:** StreamWriter CSV export of ScorerResult + SignalSnapshot per bar; Python watchdog consumer; FastAPI /signals ingestion; SQLAlchemy + SQLite schema; APScheduler nightly validation job; Market Replay Recorder enabled.
**Avoids:** Pitfall 3 (DOM backtesting — document which signals are and are not replayable; enable recorder immediately)
**Research flag:** Standard patterns — skip research phase.

### Phase 5b: Python ML Backend
**Rationale:** Requires 6-8 weeks of signal history from Phase 5a. Walk-forward validation gate (WFE > 70%) must clear before any weight optimization reaches the live system.
**Delivers:** HMM regime classifier (TrendBull/TrendBear/Balance/HighVol/LowVol); signal effectiveness tracker; XGBoost weight optimizer (portfolio Sharpe target); purged walk-forward validation; human review gate (operator approves weight candidates); FastAPI /params endpoint returning weights to NT8.
**Uses:** XGBoost 3.2.0 + scikit-learn 1.8.0 + Optuna 4.8.0 + hmmlearn 0.3.3 + vectorbt 0.28.5
**Avoids:** Pitfalls 1 (overfitting — purged walk-forward, WFE gate, 200 OOS trades minimum), 10 (regime ML curve-fitting — regime-aware training), Anti-Feature 2 (no autonomous weight deployment)
**Research flag:** Needs deeper research: purged walk-forward cross-validation implementation for trading signals; WFE computation for multi-signal ensembles; ZeroMQ Phase 2 bridge upgrade (NetMQ DLL validation required on target Windows environment).

### Phase 6: Next.js Analytics Dashboard
**Rationale:** Last — requires both data bridge (Phase 5a) and ML backend (Phase 5b) to have stable endpoints. Build after ML backend has been live at least 2 weeks.
**Delivers:** Signal effectiveness heatmap (signal × regime × context → win_rate); P&L attribution by engine and signal category; regime timeline with P&L overlay; parameter drift tracker; live signal feed via SSE.
**Uses:** Next.js 15 App Router + Tremor 3.x + Lightweight Charts 5.1 + Recharts + SSE native
**Avoids:** Anti-Feature 5 (no real-time footprint chart replication — analytics only)
**Research flag:** Standard Next.js 15 App Router + SSE patterns — skip research phase.

### Phase Ordering Rationale

- Phase 1 before everything: GC and monolith issues are production blockers, not tech debt
- Phase 2 before Phase 3: Absorption/exhaustion signals are inputs to LVN zone defense detection
- Phase 3 before Phase 4: LVN and GEX are required inputs to confluence scorer and TypeA execution gate
- Phase 5a in parallel with Phases 3-4: 6-8 week lead time for signal data accumulation before ML training
- Phase 5b after 5a: Cannot train ML without data; WFE gate must clear before any optimization goes live
- Phase 6 last: Dashboard visualizes ML state that does not exist until Phase 5b is complete

### Research Flags

Phases needing deeper research during planning:
- **Phase 5b (ML Backend):** Purged walk-forward cross-validation implementation; WFE computation for multi-signal ensembles; ZeroMQ NetMQ DLL validation in NT8 on Windows
- **Phase 3 (LVN + GEX):** FlashAlpha QQQ-to-NQ proxy accuracy (live API validation); zone scoring calibration constants
- **Phase 4 (Scorer + Execution):** Confluence multiplier and zone bonus calibration — requires live trading data

Phases with standard, well-documented patterns:
- **Phase 1:** NT8 partial class AddOns pattern is documented; GC fixes are standard .NET patterns
- **Phase 5a:** StreamWriter CSV + watchdog is a documented NT8 production pattern (HIGH confidence)
- **Phase 6:** Next.js 15 App Router + SSE is well-documented with official examples

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library versions verified against PyPI official release pages; NT8 constraints are hard facts |
| Features | HIGH | Absorption/exhaustion/LVN definitions confirmed across ATAS, TradeDevils, Orderflows, Bookmap |
| Architecture | HIGH (NT8) / MEDIUM (scoring) | AddOns partial class pattern: MEDIUM confidence (community evidence, not official docs); scoring calibration needs live validation |
| Pitfalls | HIGH (NT8-specific) / MEDIUM (ML specifics) | NT8 pitfalls confirmed via forum posts; ML overfitting guidance from academic literature |

**Overall confidence:** HIGH for build sequence and technology choices; MEDIUM for calibration constants (scoring weights, zone bonus magnitudes, confluence multiplier thresholds).

### Gaps to Address

- **FlashAlpha QQQ-to-NQ proxy accuracy:** Scaling factor is industry standard but introduces basis risk. Validate GEX level alignment with actual NQ price behavior in Phase 3 before using GEX for execution gating.
- **AddOns folder partial class compilation:** MEDIUM confidence (community evidence). Validate on target Windows NT8 environment before committing to this decomposition.
- **ZeroMQ / NetMQ in NT8:** Phase 2 bridge upgrade. Loading NetMQ.dll + AsyncIO.dll in NT8 Custom folder requires environment-specific validation. File bridge is safe fallback.
- **Scorer calibration:** Zone bonus magnitudes and confluence multiplier values are derived from Pine Script reference and research logic — not empirically validated on NQ. Treat as starting estimates; plan a calibration pass after first 30 days of live trading with execution disabled.
- **DOM signal ground truth:** E2/E3/E4 P&L attribution unmeasurable until 90+ days of live Market Replay data accumulates. Enable recorder before Phase 5a.

---

## Sources

### Primary (HIGH confidence)
- PyPI official release pages: FastAPI 0.135.3, scikit-learn 1.8.0, XGBoost 3.2.0, Optuna 4.8.0, hmmlearn 0.3.3, SQLAlchemy 2.0.49, pyzmq 27.1.0, vectorbt 0.28.5
- NinjaTrader StreamWriter pattern: https://forum.ninjatrader.com/forum/ninjascript-educational-resources/reference-samples/3581-indicator-using-streamwriter-to-write-to-a-text-file
- NT8 Tick Replay documentation: https://ninjatrader.com/support/helpguides/nt8/tick_replay.htm
- NinjaTrader Forum: Level 2 DOM backtesting limitation (structural, not configurable)
- NinjaTrader Forum: Deadlock threading patterns — lock() on NT8 internals confirmed deadlock risk
- ATAS, TradeDevils, Orderflows, Bookmap platform documentation

### Secondary (MEDIUM confidence)
- FlashAlpha API pricing and NQ/NDX coverage: https://flashalpha.com/pricing
- MenthorQ NQ GEX via QQQ proxy: https://menthorq.com/guide/gamma-levels-on-futures-options/
- NT8 AddOns folder partial class pattern: community forum evidence
- ZeroMQ NT8 pattern: https://basicsoftradingstocks.wordpress.com/2020/03/28/quick-way-of-setting-up-zeromq-ipc-messaging-inside-of-ninjatrader-8-stream-data-and-signals-in-out-of-nt8/
- Walk-forward validation methodology: QuantInsti, Build Alpha, arxiv Dec 2025
- Backtest overfitting in ML era: ScienceDirect 2024

### Tertiary (LOW confidence — requires live validation)
- FlashAlpha QQQ-to-NQ proxy accuracy (basis risk not quantified)
- Scoring calibration constants (zone bonuses, confluence multiplier thresholds)
- DOM-dependent signal (E2/E3/E4) P&L attribution — no valid backtest possible

---

*Research completed: 2026-04-11*
*Ready for roadmap: yes*
