# DEEP6 v2.0 — NinjaScript Edition (Python reference-only)

## What This Is

DEEP6 is an institutional-grade footprint chart auto-trading system for NQ futures, built on NinjaTrader 8 via NinjaScript C#. The validated Python engine (Phases 1–15) is retained as the reference implementation and source-of-truth for signal logic being ported to NinjaScript. Execution runs through NT8 native Rithmic orders on Apex (APEX-262674) and Lucid (LT-45N3KIV8) funded prop accounts. 44 independent market microstructure signals (minus Kronos E10, which is deferred) are synthesized into a unified confidence score. The system's thesis is unchanged: absorption and exhaustion are the highest-alpha reversal signals in order flow — everything else exists to confirm or contextualize them.

## Core Value

Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via NT8 Rithmic orders on Apex/Lucid funded accounts — with the Python engine kept as the validated reference specification.

## Requirements

### Validated

- ✓ 44-signal taxonomy researched and categorized (8 categories, all signal types defined) — v1 research
- ✓ Absorption/exhaustion deep research complete (4 absorption variants, 6 exhaustion variants) — v1 research
- ✓ LVN zone lifecycle designed (5-state FSM: Created→Defended→Broken→Flipped→Invalidated) — v1 research
- ✓ Scoring architecture designed (two-layer consensus + category confluence multiplier) — v1 research
- ✓ GEX integration approach defined (massive.com API + regime classification) — v1 research
- ✓ ML stack selected (XGBoost + Optuna + walk-forward validation) — v1 research
- ✓ Pine Script reference architecture analyzed (Bookmap Liquidity Mapper + VP LVN Levels) — v1 analysis
- ✓ Python reference signal engine validated through Phase 15 (LevelBus + Confluence Rules + Trade Decision FSM, 757 tests green) — Phases 1–15

### Active

- [ ] **NT8 footprint indicator** — NinjaScript C# footprint indicator with absorption/exhaustion + massive.com GEX overlay (Phase 16, built)
- [ ] **NT8 detector refactor + remaining signals port** — ISignalDetector registry; IMB/DELT/AUCT/TRAP/VOLP/ENG signals ported from Python reference to NinjaScript (Phase 17)
- [ ] **Two-layer confluence scorer in NinjaScript** — Two-layer confluence scorer with matching weights and thresholds (Phase 18)
- [ ] **Replay harness for C#↔Python parity validation** — Manual replay harness validates signal parity on ≥5 recorded NQ sessions (Phase 18)
- [ ] **Apex + Lucid 30-day paper-trade gate** — DEEP6Strategy running on funded prop accounts before live capital (Phase 19)
- [ ] **massive.com GEX overlay live in NT8** — Call/put wall, gamma flip, HVL via massive.com API (Phase 16, built)
- [ ] **NT8 native OnMarketData + OnMarketDepth aggregation** — Tick-level footprint accumulation via NT8 data feed (Phase 16, built)
- [ ] **NT8 OrderPlant execution via ATM strategy templates** — Direct Rithmic execution on Apex + Lucid (Phase 19)

### Out of Scope

- **Python as live runtime** — reference-only source-of-truth for C# porting; not the live system
- **async-rithmic live runtime** — blocked by Apex refusing API/plugin mode (2026-04-15); NT8 native Rithmic connection replaces it on the live path
- **Kronos E10 bias engine** — deferred post-v1; revisit after NT8 paper-trade gate
- **FastAPI backend** — reference-only; deferred post-v1
- **TradingView MCP** — reference-only; deferred post-v1
- **Next.js dashboard** — reference-only; deferred post-v1
- **Databento live feed** — reference-only; NT8 Market Replay + recorded fixtures used for backtest/parity validation
- **EventStore** — reference-only; deferred post-v1
- Multi-instrument support — NQ only for v1
- Mobile app — desktop + web dashboard
- Social/community features — single-user institutional tool
- Options trading execution — futures only; options data for GEX context only

## Context

**Architecture pivot (2026-04-15):** Apex refused to enable Rithmic API/plugin mode on the APEX-262674 user id, blocking the async-rithmic live-runtime track. Committing to a full C# port into NinjaScript running inside NT8. Python engine (Phases 1–15) is preserved as the validated reference specification — all research (44-signal taxonomy, absorption/exhaustion, LVN lifecycle, scoring architecture) carries forward unchanged; only the runtime and language change. Prior 2026-04-13 Python pivot rationale is archived in this doc's history.

**v1 C# work archived:** The NT8 decomposition (12 AddOns/ partial class files + GC fixes) is preserved in `.planning-v1-nt8/` for reference. The engine logic, signal definitions, and scoring formulas from those files inform the NinjaScript implementation.

**Key technology stack:**
- **NinjaScript C# / .NET Framework 4.8** — NT8 8.1.x native. OnMarketData + OnMarketDepth for L2 DOM. SharpDX Direct2D for rendering.
- **massive.com API** (MASSIVE_API_KEY in .env) — GEX overlay: call wall, put wall, gamma flip, HVL via QQQ/NDX proxy. NOTE: CLAUDE.md GEX provider reference is stale — massive.com is the live provider (confirmed Phase 16).
- **Python reference engine** — Phases 1–15 validated 44-signal stack (757 tests green); retained as port source-of-truth, not live runtime.
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

- **Language**: NinjaScript C# / .NET Framework 4.8 (NT8 8.1.x)
- **Data feed**: NT8 native OnMarketData + OnMarketDepth (Rithmic via NT8 connection, not async-rithmic)
- **Execution**: NT8 OrderPlant via ATM strategy templates on Apex + Lucid funded accounts
- **GEX data**: massive.com API (MASSIVE_API_KEY in .env — CLAUDE.md GEX provider entry is stale; massive.com is correct)
- **Historical data**: NT8 Market Replay + recorded tick/depth fixtures
- **Reference runtime**: Python 3.12 engine retained for parity validation, not live
- **Dashboard**: reference-only (Next.js + FastAPI deferred post-v1)
- **Development**: NT8 runs on Windows VM / dedicated box; planning and C# authoring on macOS
- **Research-first**: Deep research per domain before committing to architecture

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Drop NT8/C# for Python (2026-04-13) | async-rithmic provides identical L2 DOM; eliminates Windows dependency | Superseded 2026-04-15 |
| async-rithmic for data + execution | Same Rithmic feed NT8 uses, zero extra cost, macOS native | Shelved — Apex refused API mode |
| Kronos as E10 bias engine | 16K star foundation model, AAAI 2026, trained on 45+ exchanges | Deferred post-v1 |
| TradingView MCP for visual analysis | Claude-in-the-loop reads charts, bridges to existing Pine Scripts | Deferred post-v1 |
| Databento MBO for backtesting | Full L3 order book replay, nanosecond timestamps, $179/mo | Reference-only; NT8 Market Replay for v1 |
| Absorption/exhaustion as core priority | Highest-alpha signals per research and user experience | ✓ Good (carried from v1) |
| NQ only for v1 | Perfect on one instrument first | ✓ Good (carried from v1) |
| Research-first workflow | Deep research per domain before architecture | ✓ Good (carried from v1) |
| All ML dimensions (thresholds, weighting, timing, regime) | Comprehensive optimization | ✓ Good (carried from v1) |
| Pivot to NT8-only runtime (2026-04-15) | Apex refused Rithmic API/plugin mode | Pending |
| Python engine reference-only | Preserve validated Phase 1–15 logic as port source | Pending |
| massive.com for GEX | CLAUDE.md GEX provider entry is stale — massive.com confirmed | ✓ Confirmed (live in Phase 16) |
| NT8 execution via ATM strategy templates on Apex + Lucid | Funded accounts already active | Pending (Phase 19) |
| Kronos E10 deferred post-v1 | Not required for absorption/exhaustion thesis | Pending |

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
*Last updated: 2026-04-15 after NT8 pivot (Apex refused Rithmic API mode)*
