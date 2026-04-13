# DEEP6 v2.0 — Python Edition

## What This Is

DEEP6 is an institutional-grade footprint chart auto-trading system for NQ futures, built entirely in Python. The system connects directly to Rithmic via `async-rithmic` for real-time Level 2 DOM data (40+ levels, 1,000 callbacks/sec) and trade execution — eliminating the NinjaTrader dependency. 44 independent market microstructure signals are synthesized into a unified confidence score. Kronos (foundation model for financial K-lines) provides directional bias as E10. TradingView MCP enables Claude-in-the-loop visual analysis. A FastAPI + Next.js web stack provides ML optimization, analytics, and a session replay dashboard. The system's thesis: absorption and exhaustion are the highest-alpha reversal signals in order flow — everything else exists to confirm or contextualize them.

## Core Value

Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via direct Rithmic orders — all in Python, running on macOS.

## Requirements

### Validated

- ✓ 44-signal taxonomy researched and categorized (8 categories, all signal types defined) — v1 research
- ✓ Absorption/exhaustion deep research complete (4 absorption variants, 6 exhaustion variants) — v1 research
- ✓ LVN zone lifecycle designed (5-state FSM: Created→Defended→Broken→Flipped→Invalidated) — v1 research
- ✓ Scoring architecture designed (two-layer consensus + category confluence multiplier) — v1 research
- ✓ GEX integration approach defined (FlashAlpha API + regime classification) — v1 research
- ✓ ML stack selected (XGBoost + Optuna + walk-forward validation) — v1 research
- ✓ Python L2 DOM feasibility confirmed (async-rithmic provides identical Rithmic feed) — pivot research
- ✓ Pine Script reference architecture analyzed (Bookmap Liquidity Mapper + VP LVN Levels) — v1 analysis

### Active

- [ ] **Rithmic data pipeline** — async-rithmic connection for real-time L2 DOM (40+ levels) + tick trade data on NQ
- [ ] **Footprint chart engine** — build bid/ask volume per price level per bar from raw L2/tick data in Python
- [ ] **44-signal engine** — all signals from 8 categories detecting correctly from Python data pipeline
- [ ] **Absorption/exhaustion core** — all 4 absorption + 6 exhaustion variants with narrative cascade
- [ ] **LVN/HVN volume profile** — session VP with zone lifecycle FSM and scoring
- [ ] **GEX integration** — FlashAlpha API for call/put walls, gamma flip, HVL, regime
- [ ] **E8 CVD engine** — cumulative volume delta with multi-bar divergence via linear regression
- [ ] **E9 Auction State Machine** — FSM tracking auction theory states
- [ ] **E10 Kronos bias engine** — foundation model directional prediction from OHLCV
- [ ] **Zone registry** — centralized zone manager for all level types
- [ ] **Scoring/confluence** — two-layer consensus with category multiplier and zone bonus
- [ ] **Auto-execution** — direct Rithmic order submission from signal confluence (execution approach TBD — needs research)
- [ ] **Risk management** — circuit breakers, daily loss limits, position sizing
- [ ] **Backtesting** — Databento MBO historical replay + vectorbt parameter sweeps
- [ ] **ML backend** — FastAPI + XGBoost + Optuna for parameter optimization and regime detection
- [ ] **Next.js dashboard** — signal performance, regime viz, parameter evolution, session replay
- [ ] **TradingView MCP** — Claude reads/controls TV charts for visual confirmation and Pine Script signals
- [ ] **Volatility-adaptive thresholds** — all 44 thresholds scale with ATR(20)
- [ ] **Signal correlation analysis** — pairwise matrix to identify redundant signals

### Out of Scope

- NinjaTrader 8 / C# — replaced by Python + async-rithmic (v1 C# code archived in .planning-v1-nt8/)
- Multi-instrument support — NQ only for v1
- Mobile app — desktop + web dashboard
- Social/community features — single-user institutional tool
- Options trading execution — futures only; options data for GEX context only

## Context

**Architecture pivot (2026-04-13):** Originally built as NT8/C# indicator. Discovered `async-rithmic` provides identical Rithmic L2 DOM access in Python, eliminating NT8 dependency entirely. All v1 research (44 signals, absorption/exhaustion, LVN lifecycle, scoring architecture, ML stack) carries forward unchanged — only the implementation language changes.

**v1 C# work archived:** The NT8 decomposition (12 AddOns/ partial class files + GC fixes) is preserved in `.planning-v1-nt8/` for reference. The engine logic, signal definitions, and scoring formulas from those files inform the Python implementation.

**Key technology stack:**
- **async-rithmic** — Direct Rithmic R|Protocol via WebSocket + Protocol Buffers. Same feed NT8 uses. 40+ DOM levels, execution capability. macOS native.
- **Kronos** (16K GitHub stars, AAAI 2026) — Foundation model for K-line prediction. Tokenizes OHLCV into hierarchical discrete tokens, autoregressive Transformer predicts future candles. Models: mini (4.1M), small (24.7M), base (102.3M).
- **TradingView MCP** (1.7K stars) — Bridges Claude Code to TradingView Desktop via Chrome DevTools Protocol. Read charts, inject Pine Script, navigate, screenshots.
- **Databento** ($179/mo) — MBO (Market-by-Order) L3 data from CME colocation. Historical replay with identical API to live. Python SDK.
- **vectorbt** — Backtesting framework. User has existing vectorbt expert agent at `/Users/teaceo/Documents/coding/tapsuite/.claude/agents/vectorbt-backtesting-expert.md`.

**Reference implementations (carry forward from v1):**
- Bookmap Liquidity Mapper Pine Script (~900 lines) — absorption/exhaustion/momentum/rejection + zone scoring
- VP Low-TF LVN Levels Pine Script — LVN detection algorithm
- FutTrader/footprint-system (Sierra Chart C++) — 4-condition reversal (relative volume + unfinished auctions + diagonal imbalances + P/B profile)
- JumpstartTrading footprint methodology — signal hierarchy validation
- Andrea Chimmy orderflow framework — absorption as passive limit defense, confirmation logic

**44-signal taxonomy (unchanged from v1):**
- Imbalance (9), Delta (11), Absorption (4), Exhaustion (6), Auction Theory (5), Trapped Traders (5), Volume Patterns (6), POC/Value Area (8)

## Constraints

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

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Drop NT8/C# for Python | async-rithmic provides identical L2 DOM; eliminates Windows dependency | — Pending |
| async-rithmic for data + execution | Same Rithmic feed NT8 uses, zero extra cost, macOS native | — Pending |
| Kronos as E10 bias engine | 16K star foundation model, AAAI 2026, trained on 45+ exchanges | — Pending |
| TradingView MCP for visual analysis | Claude-in-the-loop reads charts, bridges to existing Pine Scripts | — Pending |
| Databento MBO for backtesting | Full L3 order book replay, nanosecond timestamps, $179/mo | — Pending |
| Absorption/exhaustion as core priority | Highest-alpha signals per research and user experience | ✓ Good (carried from v1) |
| NQ only for v1 | Perfect on one instrument first | ✓ Good (carried from v1) |
| Research-first workflow | Deep research per domain before architecture | ✓ Good (carried from v1) |
| Python + Next.js web stack | Python for ML + data; Next.js for dashboard | — Pending |
| All ML dimensions (thresholds, weighting, timing, regime) | Comprehensive optimization | ✓ Good (carried from v1) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-13 after Python pivot*
