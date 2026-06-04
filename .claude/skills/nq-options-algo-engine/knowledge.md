# NQ Options Algo Engine

> Build NQ futures algos and indicators from options market data.
> Data sources: **Massive.com** (raw chain/Greeks/OI/trades) + **FlashAlpha** (derived GEX/flow/dealer positioning).

## Identity

This skill transforms options market intelligence into executable NQ trading algorithms and indicators. It bridges two data sources — Massive.com for raw options data and FlashAlpha for derived dealer analytics — into Python signal generators and Pine Script indicators for the DEEP6 system.

**This skill is the IMPLEMENTATION layer.** For options market theory, regime classification, and trade setup logic, load the companion `options-bias-engine/` skill tree. This skill assumes you understand the theory and focuses on *how to build code from it*.

## When to Load This Skill

Load when the task involves ANY of:
- Building Python algos that consume options data for NQ trading decisions
- Creating Pine Script indicators that display options-derived levels/regimes
- Integrating Massive.com or FlashAlpha APIs into the DEEP6 data pipeline
- Converting options market analysis into automated signals
- Backtesting NQ strategies that use options data as inputs
- Designing the real-time data pipeline for options → signal → execution

Do NOT load for:
- Pure options theory questions → load `options-bias-engine/knowledge`
- FlashAlpha API reference only → load `flashalpha-options/SKILL.md`
- NQ trading playbook only → load `flashalpha-nq/SKILL.md`
- GEX reaction indicator for NT8 → load `gex-reaction-sensor/knowledge`

---

## Data Source Architecture

### Two Complementary Feeds

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPTIONS DATA UNIVERSE                         │
│                                                                  │
│  ┌──────────────────────┐    ┌───────────────────────────────┐  │
│  │    MASSIVE.COM        │    │       FLASHALPHA               │  │
│  │    (Raw Data)         │    │       (Derived Analytics)      │  │
│  │                       │    │                                │  │
│  │  • Option chains      │    │  • GEX by strike/expiry       │  │
│  │  • Greeks per contract│    │  • Gamma flip point            │  │
│  │  • IV per strike      │    │  • Call/put walls              │  │
│  │  • OI snapshots       │    │  • Dealer delta hedging est.   │  │
│  │  • Tick-level trades  │    │  • VEX/CHEX/DEX exposure       │  │
│  │  • Quote streams (WS) │    │  • 0DTE pin score + magnet     │  │
│  │  • Historical flat    │    │  • Flow levels + sweep alerts  │  │
│  │    files (S3)         │    │  • Regime classification       │  │
│  │                       │    │  • Expected move boundaries    │  │
│  │  Symbols: QQQ, NDX    │    │  • IV rank/percentile, VRP    │  │
│  │  Tiers: $0–enterprise │    │  • Strategy scores             │  │
│  └──────────┬───────────┘    └──────────────┬────────────────┘  │
│             │                                │                    │
│             └──────────┬─────────────────────┘                   │
│                        ▼                                          │
│              ┌──────────────────┐                                 │
│              │   DATA FUSION    │                                 │
│              │   (Python async) │                                 │
│              │                  │                                 │
│              │  QQQ → NQ proxy  │                                 │
│              │  Unified model   │                                 │
│              │  Conflict res.   │                                 │
│              └────────┬─────────┘                                 │
│                       ▼                                           │
│              ┌──────────────────┐                                 │
│              │  SIGNAL ENGINE   │                                 │
│              │  (44 signals)    │                                 │
│              │                  │                                 │
│              │  Options-derived │                                 │
│              │  signals feed    │                                 │
│              │  into composite  │                                 │
│              │  confidence      │                                 │
│              └────────┬─────────┘                                 │
│                       ▼                                           │
│              ┌──────────────────┐                                 │
│              │  EXECUTION       │                                 │
│              │  (async-rithmic) │                                 │
│              └──────────────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Source Selection Rules

| Data Need | Primary Source | Fallback | Rationale |
|-----------|---------------|----------|-----------|
| GEX, dealer positioning | FlashAlpha | Compute from Massive OI | FA pre-computes; Massive is raw |
| Gamma flip, walls | FlashAlpha | Compute from Massive OI + Greeks | FA updates frequently |
| Raw Greeks per contract | Massive.com | FA `/v1/optionquote/{symbol}` | Massive has tick-level granularity |
| IV surface, skew | Both | — | Massive for raw IV; FA for rank/percentile/VRP |
| Open interest snapshots | Massive.com | FA `/v1/flow/oi/{symbol}` | Massive has contract-level OI |
| Options flow/sweeps | FlashAlpha | Massive tick trades + heuristics | FA classifies flow intent |
| Historical options data | Massive flat files | FA historical API (Alpha $149) | Massive has nanosecond ticks |
| Real-time quotes | Massive WebSocket | FA polling (15s intervals) | Massive is true streaming |
| 0DTE analytics | FlashAlpha | Compute from Massive 0DTE chain | FA has pin score, magnet, charm regime |

---

## File Map

### data-sources/ — API Integration & Data Pipeline

| File | Purpose | Load When |
|------|---------|-----------|
| `massive-api.md` | Massive.com REST/WebSocket/flat-file API reference for QQQ/NDX options | Building Massive.com integration |
| `flashalpha-bridge.md` | FlashAlpha endpoint map optimized for algo consumption patterns | Building FlashAlpha polling/caching layer |
| `data-fusion.md` | Combining Massive raw + FlashAlpha derived into unified options state | Designing the data normalization pipeline |
| `nq-proxy-pipeline.md` | QQQ/NDX → NQ conversion pipeline with real-time recalibration | Converting any options level to NQ price |

### algo-patterns/ — Signal Building Templates

| File | Purpose | Load When |
|------|---------|-----------|
| `python-signal-templates.md` | BaseSignalGenerator patterns for options-derived signals | Writing a new Python signal class |
| `pine-indicator-templates.md` | Pine Script patterns for TradingView options overlays | Building Pine indicators that show options data |
| `gex-to-signal.md` | Converting GEX regime/levels/walls to entry/exit signals | Building GEX-based algo signals |
| `flow-to-signal.md` | Converting institutional flow to momentum/reversal signals | Building flow-based algo signals |
| `composite-scoring.md` | Multi-source signal fusion into unified confidence score | Integrating options signals into 44-signal engine |

### strategies/ — Automated Trading Strategies

| File | Purpose | Load When |
|------|---------|-----------|
| `regime-algo.md` | Automated regime detection + playbook switching | Building the regime classification engine |
| `wall-reaction-algo.md` | Automated wall bounce/break detection and entry | Building wall-proximity trade logic |
| `vol-surface-algo.md` | Vanna/charm/VRP-driven directional algo | Building volatility-surface-based signals |
| `zero-dte-algo.md` | 0DTE gamma acceleration + pin risk exploitation | Building 0DTE-specific intraday algos |

### implementation/ — Production Architecture

| File | Purpose | Load When |
|------|---------|-----------|
| `async-pipeline.md` | Python async architecture for dual-API data ingestion | Designing the data pipeline |
| `api-clients.md` | Async HTTP/WebSocket client patterns for both APIs | Writing API client code |
| `backtesting-with-options.md` | Historical replay using Massive flat files + FA historical | Building options-aware backtesting |

### deep-expertise/ — Institutional-Grade Quantitative Knowledge

| File | Purpose | Load When |
|------|---------|-----------|
| `dealer-mechanics-quantitative.md` | Hedging formulas, rebalancing triggers, inventory dynamics, amplification loops, gamma exhaustion | Need the math behind dealer behavior |
| `volatility-surface-quantitative.md` | SVI/SSVI parameterization, vanna/charm formulas, RV estimators, VRP computation, vol regime classification | Building vol-surface-based signals |
| `institutional-flow-taxonomy.md` | 7 institutional player types, sweep/dark pool mechanics, flow metrics, conviction scoring frameworks | Reading institutional flow for NQ signals |
| `academic-foundations.md` | 8 peer-reviewed papers with findings and algo implications (Hu, Pan, Barbon, Avellaneda, etc.) | Need academic evidence for signal design |
| `gex-model-validation.md` | 8-year GEX backtest results, reliability matrix, edge cases, 0DTE structural shift, honest limitations | Assessing what GEX can and cannot predict |

> **These files go deeper than the options-bias-engine domains.** The domains cover theory at expert level; these files add quantitative formulas, academic evidence, institutional mechanics, and honest model validation. Load when building algo logic that needs the underlying math, or when evaluating whether a signal has real edge.

---

## Cross-Reference: Companion Skills

This skill does NOT duplicate theory. Load these companions when needed:

| Skill | Load For | Key Files |
|-------|----------|-----------|
| `options-bias-engine/knowledge` | 7-step decision framework (regimes → setups → risk → output) | Master index routes to 48 files |
| `options-bias-engine/domains/*` | GEX theory, DEX/VEX/CHEX, volatility, 0DTE, dealer mechanics | 8 domain files |
| `options-bias-engine/step1-regimes/*` | Regime classification logic (A-G) | 9 regime files |
| `options-bias-engine/step5-setups/*` | Trade setup specifications (wall bounce, flip cross, etc.) | 8 setup files |
| `options-bias-engine/step4-cross-validation/*` | Conviction matrix, divergence patterns | 3 validation files |
| `options-bias-engine/order-book/*` | Rithmic MBO signals (absorption, iceberg, spoofs) | 6 order book files |
| `flashalpha-options/api-reference` | Complete FlashAlpha endpoint reference (all tiers) | 840-line API doc |
| `flashalpha-options/concepts/*` | Greeks, volatility, exposure analytics, 0DTE concepts | 4 concept files |
| `flashalpha-nq/SKILL` | NQ-specific FlashAlpha trading playbook | Entry + 4 references |
| `gex-reaction-sensor/knowledge` | NT8 indicator bridging GEX + order flow | 1 design pattern file |

---

## NQ Proxy Conversion (Quick Reference)

All options data arrives in **QQQ** (or NDX) price space. Convert to NQ:

```
ratio = NQ_spot / QQQ_spot     # Typically 84x–87x
nq_level = qqq_level × ratio   # Apply to every wall, flip, magnet, expected move boundary

# Recalibrate:
# - At session open (mandatory)
# - After NQ moves 100+ points intraday
# - After major macro event
```

For detailed conversion pipeline: load `data-sources/nq-proxy-pipeline.md`.

---

## Algo Development Workflow

```
1. IDENTIFY what options data drives the signal
   → Load relevant data-sources/ file

2. DESIGN the signal extraction logic
   → Load relevant algo-patterns/ file

3. IMPLEMENT the strategy using the signal
   → Load relevant strategies/ file

4. BUILD the data pipeline to feed it
   → Load relevant implementation/ file

5. BACKTEST with historical options data
   → Load implementation/backtesting-with-options.md

6. VALIDATE against options-bias-engine decision framework
   → Load options-bias-engine/step4-cross-validation/conviction-matrix.md
```
