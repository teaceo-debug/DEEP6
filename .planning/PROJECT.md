# DEEP6 v2.0

## What This Is

DEEP6 is an institutional-grade footprint chart auto-trading system for NQ futures, built on NinjaTrader 8 with Rithmic Level 2 DOM data. The core engine processes up to 1,000 callbacks/second and synthesizes 44 independent market microstructure signals into a unified confidence score. A Python + Next.js web backend provides ML-driven analytics, parameter evolution, and regime detection. The system's thesis: absorption and exhaustion are the highest-alpha reversal signals in order flow — everything else exists to confirm or contextualize them.

## Core Value

Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via NT8 ATM Strategy.

## Requirements

### Validated

- ✓ Foundation + WPF Shell — P1
- ✓ E1 FOOTPRINT engine (absorption/exhaustion/stacked imbalances/CVD) — P2
- ✓ E2 TRESPASS engine (DOM queue imbalance + logistic regression) — P2
- ✓ E3 COUNTERSPOOF engine (Wasserstein-1 + cancel detection) — P2
- ✓ E4 ICEBERG engine (native + synthetic iceberg detection) — P2
- ✓ E5 MICRO engine (Naïve Bayes combination) — P2
- ✓ E6 VP+CTX engine (DEX-ARRAY + VWAP + IB + GEX + POC) — P2
- ✓ E7 ML QUALITY engine (Kalman filter + logistic classifier) — P2
- ✓ Header bar (10 live-updating status columns) — P3a
- ✓ Left tab bar (9 tabs) — P3b
- ✓ Status pills (9 live pills) — P3c
- ✓ SharpDX footprint rendering (bid/ask/imbalance/POC/delta) — P3d
- ✓ Signal label boxes (TYPE A/B/C gold/amber bordered) — P3e
- ✓ STKt markers — P3f
- ✓ GEX/LEVELS/LOG right panel tabs — P3g
- ✓ DEX-ARRAY + STKt engine — P3h
- ✓ ML baseline tracking — P3i
- ✓ 7-engine voting system (0-100 unified score, 4+ agreement threshold) — P2
- ✓ 15 price level lines (VWAP/IB/GEX/POC/previous day) — P3d

### Active

- [ ] **44-signal engine expansion** — expand from current 3 signal types to full 44-signal taxonomy across 8 categories (imbalance, delta, absorption, exhaustion, auction theory, trapped traders, volume patterns, POC/VA)
- [ ] **Absorption/exhaustion deep system** — port and enhance Pine Script's narrative candle classification (absorption: wick + balanced delta; exhaustion: wick + one-sided delta + delta trajectory divergence + cooldown)
- [ ] **LVN/HVN sophisticated levels** — volume profile with low/high volume node detection, peak cluster zones, zone scoring (type + volume + touches + recency), zone lifecycle (creation → defense → break → flip → invalidation)
- [ ] **GEX level integration** — commercial API (SpotGamma or similar) for real-time gamma exposure, call/put walls, HVL, gamma flip level
- [ ] **Signal-level interaction algorithm** — sophisticated scoring system where 44 signals, LVN/HVN zones, GEX levels, and VWAP/VA all interact with weighted confluence multipliers
- [ ] **Auto-execution via NT8 ATM** — automated trade entry/exit using NT8 Advanced Trade Management based on signal confluence scores
- [ ] **Python ML backend** — FastAPI service for parameter optimization, signal weighting, entry/exit timing, and regime detection using trade history
- [ ] **Next.js analytics dashboard** — web interface for ML model performance, signal analysis, parameter evolution tracking, regime classification visualization
- [ ] **NT8 ↔ Web data bridge** — real-time data pipeline from NT8 (signals, trades, market state) to Python backend for ML processing
- [ ] **Backtesting framework** — historical replay of 44-signal engine against recorded market data with P&L tracking
- [ ] **E8 CVD Engine** — cumulative volume delta engine with multi-bar divergence detection via linear regression
- [ ] **E9 Auction State Machine** — finite state machine tracking auction theory states (unfinished business, finished auction, poor high/low, volume void)
- [ ] **Volume sequencing detection** — identify institutional accumulation/distribution patterns in real-time
- [ ] **Inverse imbalance trap detection** — highest-alpha trapped trader signal (80-85% win rate per research)
- [ ] **Volatility-adaptive thresholds** — all 44 signal thresholds adjust dynamically to ATR(20)

### Out of Scope

- TradingView Pine Script maintenance — Pine Script is reference architecture only, not a maintained product
- Multi-instrument support (ES, YM, etc.) — perfect on NQ first, expand later
- Full web-based charting platform — NT8 handles charting/execution; web is analytics only
- Direct Rithmic API execution — using NT8 ATM Strategy, not bypassing NT8
- Mobile app — desktop/web only
- Social/community features — single-user institutional tool

## Context

**Existing codebase:** DEEP6 v1.0.0 is a working NinjaTrader 8 indicator (~1,010 lines C#) with 7 engines, full SharpDX UI, and a 0-100 scoring system. Phases P1-P3i are complete and functional.

**Reference implementations:**
- Bookmap Liquidity Mapper Pine Script (~900 lines) — sophisticated absorption/exhaustion/momentum/rejection classification with zone scoring, delta trajectory intelligence, regime detection, value area integration, and zone lifecycle (create → defend → break → flip → invalidate). This is the primary reference for signal logic.
- VP Low-TF LVN Levels Pine Script — volume profile LVN detection algorithm with configurable strength parameter and session-based resets.
- Screenshot reference shows TradingView chart with GEX levels (call wall, put wall, gamma flip), session levels, LVN lines, sweeps, and wick zones — the visual target for what DEEP6 v2.0 should display.

**Research-first approach:** The user explicitly wants deep research on each domain before committing to architecture. Each element (footprint signals, absorption/exhaustion theory, LVN/HVN behavior, GEX integration, execution strategies, ML approaches) should be independently researched, findings presented as docs + conversation, then decisions made.

**Signal priority:** Absorption and exhaustion are the highest-priority signals. Everything else exists to confirm or contextualize these two. The Pine Script's "narrative candle classification" (absorption > exhaustion > momentum > rejection > quiet) is the reference hierarchy.

**44-signal taxonomy (from research):**
- Imbalance (9): single, multiple, stacked T1/T2/T3, reverse, inverse, oversized, consecutive, diagonal, reversal
- Delta (11): rise, drop, tail, reversal, divergence, flip, trap, sweep, slingshot, at min/max, CVD multi-bar divergence
- Absorption (4): classic, passive, stopping volume, effort vs result
- Exhaustion (6): zero print, exhaustion print, thin print, fat print, fading momentum, bid/ask fade
- Auction Theory (5): unfinished business, finished auction, poor high/low, volume void, market sweep
- Trapped Traders (5): inverse imbalance, delta trap, false breakout trap, high volume rejection, CVD trap
- Volume Patterns (6): volume sequencing, volume bubble, volume surge, POC momentum wave, delta velocity, big delta per level
- POC/Value Area (8): above/below POC, extreme POC, continuous POC, POC gap, POC delta, engulfing VA, VA gap, bullish/bearish POC

**Academic foundations:** Gould & Bonart (2015) queue imbalance, Zotikov & Antonov (2021) iceberg detection, Tao et al. (2020) spoofing detection, Kalman (1960) filtering, Do & Putniņš (2023) layering detection.

**Andrea Chimmy orderflow framework:** Referenced in Pine Script — absorption as passive limit order defense, exhaustion as aggressor running out of steam, momentum as "toxic orderflow" to market makers. Confirmation logic: absorption confirmed by defense or same-direction momentum within N bars.

## Constraints

- **Platform**: NinjaTrader 8 (.NET Framework 4.8) — indicator must compile and run in NT8's NinjaScript environment
- **Data feed**: Rithmic Level 2 with 40+ DOM levels required for E2/E3/E4 engines
- **Performance**: Must handle 1,000+ callbacks/second without GC pressure or frame drops in SharpDX rendering
- **Rendering**: SharpDX + WPF within NT8 — no external UI frameworks
- **GEX data**: Requires commercial API subscription (SpotGamma or equivalent) — not yet provisioned
- **ML backend**: Python + Next.js — separate from NT8 runtime, communicates via data bridge
- **Development**: macOS dev environment — can edit/plan but cannot compile/run NT8; Windows box required for testing
- **Monolithic risk**: Current DEEP6.cs is 1,010 lines with 7 engines + UI in one file — adding 44 signals + 2 new engines requires careful architecture to avoid maintainability collapse

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| NT8 as trading engine, web for ML/analytics | Keep execution close to data feed; ML doesn't need real-time | — Pending |
| NQ only (no multi-instrument) | Perfect on one instrument before expanding | — Pending |
| Absorption/exhaustion as core priority | Highest-alpha signals per research and user experience | — Pending |
| Pine Script as reference only (not maintained) | One codebase to maintain; port best ideas to C# | — Pending |
| Research-first workflow | Deep research per domain before committing to architecture | — Pending |
| NT8 ATM for execution | Use NT8's built-in trade management rather than direct API | — Pending |
| Commercial GEX API (SpotGamma or similar) | Real-time institutional-grade data vs manual entry or scraping | — Pending |
| Python + Next.js web stack | Python for ML ecosystem; Next.js for modern dashboard | — Pending |
| All ML dimensions (thresholds, weighting, timing, regime) | Comprehensive ML optimization — no premature scope cuts | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-11 after initialization*
