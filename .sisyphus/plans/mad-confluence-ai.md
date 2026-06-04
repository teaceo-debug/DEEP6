# MAD Confluence AI — Institutional-Grade Execution Intelligence for NQ Futures

## TL;DR

> **Quick Summary**: Build a standalone NinjaTrader 8 indicator that combines MAD-style key levels, order flow analysis (absorption, exhaustion, delta, imbalances), liquidity logic (sweeps, traps, failed auctions), market context (regime, trend, session), and statistical confluence scoring into a single execution intelligence system that outputs LONG/SHORT/WAIT/DO NOT TRADE with a 0-100 confidence score for NQ futures.
> 
> **Deliverables**:
> - 5 partial class files comprising the MADConfluenceAI indicator
> - 12 custom signal detectors (highest-alpha subset)
> - Weighted confluence scoring engine with setup classification
> - SharpDX-rendered visual overlay (levels, markers, dashboard, heatmap)
> - Full TDD test suite with JSON fixtures
> - Deploy + compile verification
> 
> **Estimated Effort**: XL (30 tasks across 7 waves)
> **Parallel Execution**: YES — 7 waves, up to 6 concurrent tasks
> **Critical Path**: T1 → T7 → T12 → T18 → T22 → T27 → F1-F4

---

## Context

### Original Request
Build an institutional-grade NinjaTrader 8 indicator called "MAD Confluence AI" — inspired by MAD Levels, Bookmap, ATAS, Sierra Chart Numbers Bars, and Quantower — that acts as a smart execution assistant for NQ futures. The system must determine WHETHER a trader should take a trade when price reaches an important level, combining 5 analysis pillars: Level Quality, Order Flow Confirmation, Market Context, Liquidity Logic, and Trade Filtering into a weighted scoring engine.

### Interview Summary
**Key Discussions**:
- **Build approach**: Full monolith — all 5 sub-systems in one plan (user chose over phased)
- **Architecture**: Fresh standalone — no dependency on existing DEEP6 AddOns (user chose over building on existing 44-detector infrastructure)
- **Data source**: Raw ticks via OnMarketData — TDD-compatible, proven pattern in DEEP6, more capable than VolumetricBars (user chose after Metis flagged VolumetricBars can't be unit tested)
- **File structure**: 5 partial class files — MADConfluenceAI.cs, .Data.cs, .Signals.cs, .Scoring.cs, .Rendering.cs (user chose after Metis flagged single-file meltdown at 15K+ lines)
- **Signal count**: Top 12 highest-alpha signals — captures ~90% of alpha with ~25% of the code (user chose over all 44)
- **ML approach**: Pure C# classical statistics — Bayesian log-odds, Z-score, simple regime classifier. No HMM (Metis flagged it as a research project)
- **Testing**: TDD — tests first, NUnit 3.14.0, JSON fixtures, NinjaTrader.Stubs simulator
- **Integration**: Standalone — no Python bridge, no DEEP6 backend dependency

**Research Findings**:
- DEEP6 already has 100+ C# files with 44 detectors, ConfluenceScorer, ProfileAnchorLevels, FootprintBar/Cell — but user wants fresh build
- Highest-alpha signals: Liquidity Sweep+Reload (71% win), Stacked Imbalances (67%), Absorption+DeltaDivergence (64%), Iceberg at VP level (61%)
- NinjaScript constraints: .NET 4.8, C# 7.3, no NuGet, data thread vs chart thread separation
- OnMarketDepth real-time only — DOM signals won't fire on historical bars
- MAD Levels = Mechanical Absorption Detection (VWAP bands + absorption zones)
- Bookmap's unique value = L2 heatmap + iceberg detection
- ATAS/Sierra Chart = most granular footprint (55 subgraphs, diagonal imbalances)

### Metis Review
**Identified Gaps** (addressed):
- **VolumetricBars untestable**: Resolved — user chose raw ticks via OnMarketData (testable with existing stubs)
- **Single-file meltdown**: Resolved — user chose 5 partial class files
- **Scope explosion (44 detectors)**: Resolved — user chose top 12 signals
- **HMM rabbit hole**: Auto-resolved — replaced with simple regime classifier (80% value, 5% effort)
- **WAIT vs DO NOT TRADE semantics**: Auto-resolved — WAIT = conditions not yet met (score 40-59), DO NOT TRADE = conditions actively dangerous (score < 40 or conflict/chop detected)
- **Multi-instrument**: Auto-resolved — NQ-only with hardcoded NQ assumptions (tick size 0.25, point value $5)
- **Performance budget**: Auto-resolved — <2ms per OnBarUpdate, 8Hz render throttle, <0.5ms per OnMarketData
- **Rendering performance**: Applied guardrail — mandatory visibility toggles per visual layer
- **Config parameter cap**: Applied guardrail — ≤30 user-facing NinjaScript parameters

---

## Work Objectives

### Core Objective
Build a self-contained NinjaTrader 8 indicator (5 partial class files) that ingests raw tick data and Level 2 DOM to produce institutional-grade trade decisions (LONG/SHORT/WAIT/DO NOT TRADE) with a 0-100 confidence score, specifically optimized for NQ futures scalping and intraday trading.

### Concrete Deliverables
- `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` — Core: state machine, OnStateChange, OnBarUpdate orchestration, user parameters
- `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Data.cs` — Data: OnMarketData tick handler, OnMarketDepth DOM handler, MADFootprintBar/Cell, BBO tracking
- `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Signals.cs` — Signals: 12 detectors (absorption, exhaustion, delta, imbalance, iceberg, sweep, auction, trap, regime)
- `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Scoring.cs` — Scoring: confluence engine, setup classifier, trade filter, market context
- `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` — Rendering: SharpDX level zones, signal markers, confidence dashboard, heatmap, SL/TP projection
- `ninjatrader/tests/MADConfluenceAI/` — Test suite: detector tests, scoring tests, integration tests (JSON fixtures)

### Definition of Done
- [ ] `dotnet test ninjatrader/tests/` → ALL PASS (coverage: every detector, scoring engine, setup classifier)
- [ ] `nt8-deploy.ps1` → deploys all 5 partial class files to NT8 Custom/Indicators
- [ ] `nt8-compile.ps1` → `[COMPILE-RESULT] SUCCESS` with zero errors
- [ ] Indicator loads on NQ 1-minute chart, processes ticks, displays confidence score
- [ ] All 12 detectors fire correctly on known test data
- [ ] Scoring engine produces correct tier classification (Elite/High/Moderate/Avoid)
- [ ] Setup classifier correctly identifies all 7 setup types
- [ ] Visual overlay renders without SharpDX exceptions
- [ ] OnBarUpdate completes in <2ms measured by Stopwatch in test harness
- [ ] Indicator survives 500+ historical bars without crash (graceful DOM degradation)

### Must Have
- 12 signal detectors covering all 5 analysis pillars
- Weighted confluence scoring engine (0-100 scale)
- LONG/SHORT/WAIT/DO NOT TRADE decision output
- Setup type classification (7 types)
- Level Quality calculation (PDH/PDL, VWAP, VP POC/VAH/VAL, session H/L, opening range, psychological)
- Raw tick footprint with bid/ask per price level
- L2 DOM state tracking (real-time)
- SharpDX confidence dashboard overlay
- Signal markers (buy/sell arrows, absorption/exhaustion/sweep)
- Recommended SL/TP with R:R ratio
- TDD test suite with JSON fixture coverage for every detector
- Visibility toggles for every visual layer
- NQ-specific optimization (tick size 0.25, point value $5)

### Must NOT Have (Guardrails)
- **No dependency on DEEP6 AddOns** — completely standalone, no references to `NinjaTrader.NinjaScript.AddOns.DEEP6.*`
- **No NuGet packages** — NinjaScript .NET 4.8 / C# 7.3 constraint
- **No external Python bridge** — all computation in C#
- **No HMM implementation** — use simple regime classifier instead
- **No single .cs file exceeding 1,500 lines** — use partial classes
- **No VolumetricBars dependency** — raw ticks via OnMarketData for TDD compatibility
- **No object allocation in OnMarketData/OnMarketDepth hot paths** — pre-allocate in State.DataLoaded
- **No OnMarketDepth access in historical mode** — graceful degradation (DOM signals disabled)
- **No alerts/sounds/email** — pure visual indicator (no alert integration)
- **No more than 30 user-facing parameters** — hardcode sensible defaults for internal thresholds
- **No "comprehensive debug panel"** — diagnostic output via NinjaTrader Output window only
- **No helper utility files or extension methods** — everything in 5 partial class files + test files
- **No rendering all visual layers simultaneously without toggle** — performance guardrail
- **No Draw.* method calls in hot path** — SharpDX OnRender only for all visuals
- **No generic retail indicator patterns** — no RSI/MACD overlays, no simple moving average crossovers
- **Over-abstraction** — no "AbstractBaseDetectorFactory" patterns; keep detection logic direct and readable
- **Over-commenting** — no JSDoc-style comment blocks; code should be self-explanatory with minimal inline comments

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (NUnit 3.14.0, NinjaTrader.Stubs, 297 existing tests)
- **Automated tests**: TDD (RED → GREEN → REFACTOR per detector/scorer)
- **Framework**: NUnit 3.14.0 targeting net8.0 (test project) + NT8 .NET 4.8 (indicator)
- **If TDD**: Each task follows RED (failing test with JSON fixture) → GREEN (minimal implementation) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Unit Tests**: `dotnet test ninjatrader/tests/` — JSON fixture → detector → assert signal output
- **Compile Verification**: `nt8-deploy.ps1` + `nt8-compile.ps1` → SUCCESS
- **Integration**: Deploy to NT8 → add to NQ chart → verify no crash → screenshot evidence
- **Performance**: Stopwatch measurement in test harness → assert <2ms

---

## Execution Strategy

### The 12 Signals

| ID | Signal | Pillar | Description |
|----|--------|--------|-------------|
| ABS-01 | Classic Absorption | Order Flow | High volume at price level, zero price progress, passive orders reload |
| ABS-02 | Passive Absorption | Order Flow | Aggressive orders consumed by passive wall without breaking |
| EXH-01 | Exhaustion Print | Order Flow | Large volume at extreme, price fails to advance |
| EXH-02 | Fading Momentum | Order Flow | Declining delta on successive pushes in same direction |
| DELT-01 | Delta Divergence | Order Flow | Price direction != delta direction (3.5σ threshold) |
| DELT-02 | CVD Acceleration | Order Flow | CVD curve inflection points (second derivative) |
| IMB-01 | Stacked Imbalance | Order Flow | 3+ consecutive levels with ≥3:1 bid/ask ratio |
| ICE-01 | Iceberg Detection | Liquidity | Traded volume >> displayed DOM size at same price |
| LIQSW-01 | Liquidity Sweep | Liquidity | Price breaks key level → immediate reversal within 15 seconds |
| FAIL-01 | Failed Auction | Liquidity | High volume at extreme + reversal candle + single print |
| TRAP-01 | False Breakout Trap | Liquidity | Breakout beyond level → failure → trapped traders become fuel |
| REG-01 | Regime Classifier | Market Context | Trending/ranging/volatile state via ATR percentile + delta trend + volume regime |

### The 7 Setup Types

| Type | Primary Signals | Entry Logic |
|------|----------------|-------------|
| Reversal | ABS-01/02 + EXH-01 at key level | Absorption confirmed + exhaustion at level |
| Breakout | IMB-01 + volume surge through level | Stacked imbalance in direction + level break |
| Failed Breakout | TRAP-01 + FAIL-01 | Break attempt + immediate failure + trapped traders |
| Absorption Bounce | ABS-01/02 + DELT-01 | Absorption at level + delta shift in bounce direction |
| Trend Continuation | REG-01(trending) + DELT-02 | Pullback to key level + CVD acceleration in trend direction |
| Exhaustion Reversal | EXH-01/02 + DELT-01 at extreme | Exhaustion at extreme + delta divergence |
| Liquidity Sweep Reversal | LIQSW-01 + ABS-01 | Sweep beyond level + immediate absorption + reversal |

### Parallel Execution Waves

```
Wave 1 (Foundation — 6 tasks, MAX PARALLEL):
├── T1:  Project scaffolding + 5 partial class skeletons [quick]
├── T2:  Core data types (MADFootprintBar, MADCell, MADSignalResult) [quick]
├── T3:  Session context + market state tracking [quick]
├── T4:  Test infrastructure setup (NUnit project, fixtures, base classes) [quick]
├── T5:  Level Quality Engine (PDH/PDL, VWAP, OR, psychological, session H/L) [unspecified-high]
├── T6:  Configuration system + user parameters (≤30 inputs) [quick]

Wave 2 (Data Pipeline — 5 tasks, after Wave 1):
├── T7:  Footprint data pipeline (OnMarketData tick handler, bar building) [deep]
├── T8:  DOM data pipeline (OnMarketDepth handler, L2 state array) [deep]
├── T9:  Volume Profile engine (POC/VAH/VAL/HVN/LVN from ticks) [deep]
├── T10: Delta pipeline (per-bar delta, CVD, delta extremes, quality scalar) [unspecified-high]
├── T11: Multi-timeframe bias (AddDataSeries for HTF trend context) [quick]

Wave 3 (Detectors — 6 tasks, MAX PARALLEL after Wave 2):
├── T12: Absorption detector (ABS-01 Classic + ABS-02 Passive) [deep]
├── T13: Exhaustion detector (EXH-01 Print + EXH-02 FadingMomentum) [deep]
├── T14: Delta analysis (DELT-01 Divergence + DELT-02 CVD Acceleration) [deep]
├── T15: Stacked Imbalance + Iceberg (IMB-01 + ICE-01) [deep]
├── T16: Liquidity Sweep + Failed Auction (LIQSW-01 + FAIL-01) [deep]
├── T17: Trap + Regime Classifier (TRAP-01 + REG-01) [unspecified-high]

Wave 4 (Intelligence — 4 tasks, after Wave 3):
├── T18: Confluence scoring engine (weighted categories, tier classification) [deep]
├── T19: Setup classifier (7 setup types, entry/exit conditions) [unspecified-high]
├── T20: Market context engine (trend, time-of-day, session type, momentum) [unspecified-high]
├── T21: Trade filter + decision logic (LONG/SHORT/WAIT/DNT, SL/TP calc) [deep]

Wave 5 (Rendering — 5 tasks, MAX PARALLEL after Wave 4):
├── T22: Level zone rendering (SharpDX rectangles, level quality colors) [visual-engineering]
├── T23: Signal markers (arrows, dots, sweep lines, absorption zones) [visual-engineering]
├── T24: Confidence dashboard (score, tier badge, category breakdown, setup type) [visual-engineering]
├── T25: SL/TP projection + R:R display [visual-engineering]
├── T26: Delta heatmap + visibility toggle system [visual-engineering]

Wave 6 (Integration & Polish — 4 tasks, after Wave 5):
├── T27: Integration test suite (full lifecycle, multi-bar, scoring parity) [unspecified-high]
├── T28: Performance profiling + hot path optimization [deep]
├── T29: Historical mode (graceful DOM degradation, warm-up period) [unspecified-high]
├── T30: Deploy + compile verification + chart load test [quick]

Wave FINAL (Verification — 4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high + nt8-expert skill)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

### Critical Path
T1 → T7 → T12 → T18 → T21 → T22 → T27 → T30 → F1-F4 → user okay

### Parallel Speedup
~65% faster than sequential. Max concurrent: 6 (Waves 1, 3, 5)

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T2-T6, all later tasks | 1 |
| T2 | T1 | T7-T10, T12-T17 | 1 |
| T3 | T1 | T10, T17, T20 | 1 |
| T4 | T1 | T7-T17 (TDD needs test infra) | 1 |
| T5 | T1 | T12, T16, T19 | 1 |
| T6 | T1 | T7, T18, T22-T26 | 1 |
| T7 | T2, T4, T6 | T9-T17 | 2 |
| T8 | T2, T4 | T15, T16 | 2 |
| T9 | T7 | T12, T15, T16, T18 | 2 |
| T10 | T3, T7 | T12-T14, T18 | 2 |
| T11 | T1 | T17, T20 | 2 |
| T12 | T5, T9, T10 | T18, T19 | 3 |
| T13 | T9, T10 | T18, T19 | 3 |
| T14 | T10 | T18, T19 | 3 |
| T15 | T8, T9 | T18, T19 | 3 |
| T16 | T5, T8, T9 | T18, T19 | 3 |
| T17 | T3, T11 | T18, T20 | 3 |
| T18 | T12-T17 | T19, T21 | 4 |
| T19 | T12-T16, T18 | T21, T24 | 4 |
| T20 | T3, T11, T17 | T21 | 4 |
| T21 | T18-T20 | T22-T26 | 4 |
| T22 | T5, T21 | T27 | 5 |
| T23 | T21 | T27 | 5 |
| T24 | T19, T21 | T27 | 5 |
| T25 | T21 | T27 | 5 |
| T26 | T7, T21 | T27 | 5 |
| T27 | T22-T26 | T28-T30 | 6 |
| T28 | T27 | T30 | 6 |
| T29 | T27 | T30 | 6 |
| T30 | T28, T29 | F1-F4 | 6 |
| F1-F4 | T30 | user okay | FINAL |

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|-----------|
| 1 | 6 | T1→`quick`, T2→`quick`, T3→`quick`, T4→`quick`, T5→`unspecified-high`, T6→`quick` |
| 2 | 5 | T7→`deep`, T8→`deep`, T9→`deep`, T10→`unspecified-high`, T11→`quick` |
| 3 | 6 | T12→`deep`, T13→`deep`, T14→`deep`, T15→`deep`, T16→`deep`, T17→`unspecified-high` |
| 4 | 4 | T18→`deep`, T19→`unspecified-high`, T20→`unspecified-high`, T21→`deep` |
| 5 | 5 | T22-T26→`visual-engineering` |
| 6 | 4 | T27→`unspecified-high`, T28→`deep`, T29→`unspecified-high`, T30→`quick` |
| FINAL | 4 | F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep` |

---

## TODOs

### Wave 1: Foundation (Start Immediately — MAX PARALLEL)

- [x] 1. Project Scaffolding + Partial Class Skeletons

  **What to do**:
  - Create directory `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/`
  - Create 5 partial class files with correct namespace, class declaration, and empty method stubs:
    - `MADConfluenceAI.cs` — Core: `partial class MADConfluenceAI : Indicator`, OnStateChange (State.SetDefaults, Configure, DataLoaded, Terminated), OnBarUpdate, user-facing properties
    - `MADConfluenceAI.Data.cs` — Data: OnMarketData, OnMarketDepth, empty bar/tick processing stubs
    - `MADConfluenceAI.Signals.cs` — Signals: empty detector method stubs for all 12 signals
    - `MADConfluenceAI.Scoring.cs` — Scoring: empty scoring/classification method stubs
    - `MADConfluenceAI.Rendering.cs` — Rendering: OnRender, OnRenderTargetChanged, empty visual stubs
  - All files under `namespace NinjaTrader.NinjaScript.Indicators.DEEP6`
  - Include proper `#region NinjaScript generated code` marker at end (NT8 requires this)
  - Verify: `dotnet build` succeeds (compiles with stubs)

  **Must NOT do**:
  - Do NOT reference any DEEP6 AddOn types
  - Do NOT add logic — stubs only (return defaults, empty bodies)
  - Do NOT create helper files outside the 5 partial class files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-new`]
    - `nt8-new`: NinjaScript code generation — knows namespace conventions, state machine, NT8 boilerplate

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3, T4, T5, T6)
  - **Blocks**: T2, T3, T4, T5, T6, and all later tasks
  - **Blocked By**: None (can start immediately)

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:1-80` — Indicator class declaration, namespace, OnStateChange pattern
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs:1-50` — Alternative indicator skeleton with 7-layer architecture comments

  **API/Type References**:
  - `ninjatrader/ninjascript-ai-context.md` — NinjaScript API patterns, namespace rules, state machine, forbidden patterns

  **External References**:
  - NinjaTrader 8 indicator development: namespace must be `NinjaTrader.NinjaScript.Indicators` or sub-namespace

  **WHY Each Reference Matters**:
  - `DEEP6Footprint.cs:1-80`: Copy the exact OnStateChange pattern (SetDefaults → Configure → DataLoaded → Terminated) — this is the lifecycle NT8 requires
  - `ninjascript-ai-context.md`: MUST read before writing any NinjaScript — contains forbidden patterns (no readonly fields, no constructor logic, no generic types)

  **Acceptance Criteria**:
  - [ ] 5 .cs files created in correct directory
  - [ ] All files share `partial class MADConfluenceAI : Indicator`
  - [ ] `dotnet build ninjatrader/simulator/` compiles without errors (may need stub references)
  - [ ] Each file has correct namespace declaration
  - [ ] OnStateChange handles all 4 states

  **QA Scenarios**:
  ```
  Scenario: Scaffold compiles cleanly
    Tool: Bash (dotnet build)
    Preconditions: All 5 files created
    Steps:
      1. Run `dotnet build ninjatrader/simulator/` 
      2. Check exit code
    Expected Result: Exit code 0, zero errors, zero warnings related to MADConfluenceAI
    Failure Indicators: CS0101 (duplicate class), CS0246 (missing type), any error in MADConfluenceAI files
    Evidence: .sisyphus/evidence/task-1-scaffold-compile.txt

  Scenario: Files follow NT8 conventions
    Tool: Bash (grep)
    Preconditions: Files created
    Steps:
      1. Grep all 5 files for `namespace NinjaTrader.NinjaScript.Indicators.DEEP6`
      2. Grep for `partial class MADConfluenceAI : Indicator`
      3. Grep for `#region NinjaScript generated code`
      4. Grep for any `using NinjaTrader.NinjaScript.AddOns.DEEP6` (must NOT exist)
    Expected Result: Lines 1-3 found in all files, line 4 found in ZERO files
    Failure Indicators: Missing namespace, missing partial keyword, AddOns reference found
    Evidence: .sisyphus/evidence/task-1-conventions-check.txt
  ```

  **Commit**: YES (groups with T2, T3, T4, T5, T6 — Wave 1 commit)
  - Message: `feat(mad): scaffold MADConfluenceAI indicator with core types and test infra`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/*.cs`
  - Pre-commit: `dotnet build`

- [x] 2. Core Data Types (MADFootprintBar, MADCell, MADSignalResult)

  **What to do**:
  - In `MADConfluenceAI.Data.cs`, define internal data types (nested classes within the partial class):
    - `MADCell`: `long BidVol, AskVol, NeutralVol` + computed `Delta => AskVol - BidVol`, `TotalVol => BidVol + AskVol + NeutralVol`, `ImbalanceRatio` (ask/bid or bid/ask, whichever > 1)
    - `MADFootprintBar`: `SortedDictionary<double, MADCell> Levels`, `long BarDelta, Cvd`, `double PocPrice, VahPrice, ValPrice`, `long MaxDelta, MinDelta`, `int TradeCount`, `double Open, High, Low, Close`, `DateTime BarTime`, `AddTrade(double price, long volume, bool isBuy)`, `Finalize()` (compute POC, delta quality)
    - `MADSignalResult`: `string SignalId, MADSignalDirection Direction, double Strength (0-1), string Detail`, `enum MADSignalDirection { Long, Short, Neutral }`
    - `MADSessionContext`: `double Atr20, VolEma, double PrevDayHigh, PrevDayLow, PrevDayClose, PrevDayPoc, PrevDayVah, PrevDayVal, double SessionHigh, SessionLow, double OpeningRangeHigh, OpeningRangeLow`, `DateTime SessionDate, bool IsRth`
  - Write TDD test first: create `ninjatrader/tests/MADConfluenceAI/DataTypesTests.cs`
    - Test MADCell.Delta computation
    - Test MADFootprintBar.AddTrade accumulation
    - Test MADFootprintBar.Finalize POC calculation
    - Test MADSignalResult construction

  **Must NOT do**:
  - Do NOT copy FootprintBar.cs from DEEP6 AddOns — reimplement independently
  - Do NOT add rendering logic to data types
  - Do NOT use generic constraints or interfaces for data types — keep them concrete

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Understands NT8 data structures and NinjaScript conventions

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3, T4, T5, T6)
  - **Blocks**: T7, T8, T9, T10, T12-T17
  - **Blocked By**: T1 (needs file skeleton)

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs` — The existing FootprintBar/Cell implementation. Study its `AddTrade`, `Finalize`, and value area computation. Reimplement the same logic independently (no imports)
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs` — The existing SignalResult type. Study its fields (SignalId, Direction, Strength, FlagBit, Detail). Create equivalent MADSignalResult
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — The existing SessionContext. Study what fields it tracks (ATR, vol EMA, session date). Create equivalent MADSessionContext

  **Test References**:
  - `ninjatrader/tests/Detectors/AbsorptionDetectorTests.cs` — How existing tests create FootprintBar fixtures manually. Follow same pattern for MADFootprintBar

  **WHY Each Reference Matters**:
  - `FootprintBar.cs`: The core data structure — your reimplementation must handle the same operations (AddTrade per tick, Finalize per bar, POC/VAH/VAL calculation). Study it to avoid missing edge cases
  - `SignalResult.cs`: Signal output format must be consistent for scoring engine consumption
  - `SessionContext.cs`: Shared state pattern that all detectors will need

  **Acceptance Criteria**:
  - [ ] TDD: Test file `DataTypesTests.cs` written FIRST with ≥8 test cases
  - [ ] `dotnet test --filter "DataTypes"` → PASS (all 8+ tests)
  - [ ] MADCell.Delta returns correct value for known bid/ask volumes
  - [ ] MADFootprintBar.AddTrade accumulates correctly across multiple calls
  - [ ] MADFootprintBar.Finalize computes correct POC (price with highest total volume)

  **QA Scenarios**:
  ```
  Scenario: MADFootprintBar accumulates ticks correctly
    Tool: Bash (dotnet test)
    Preconditions: DataTypesTests.cs created with test cases
    Steps:
      1. Create MADFootprintBar, call AddTrade(20000.0, 5, true) then AddTrade(20000.0, 3, false)
      2. Assert Levels[20000.0].AskVol == 5, BidVol == 3, Delta == 2
      3. Call AddTrade(20000.25, 10, true)
      4. Call Finalize()
      5. Assert PocPrice == 20000.25 (highest total volume = 10 vs 8)
    Expected Result: All assertions pass
    Failure Indicators: Wrong delta sign, wrong POC, missing price level
    Evidence: .sisyphus/evidence/task-2-data-types-test.txt

  Scenario: MADCell edge cases
    Tool: Bash (dotnet test)
    Preconditions: Test cases for edge cases
    Steps:
      1. Test MADCell with zero volumes → Delta == 0
      2. Test MADCell.ImbalanceRatio with one side zero → return double.MaxValue or capped value
      3. Test MADSignalResult with all directions
    Expected Result: No divide-by-zero, no NaN
    Failure Indicators: DivideByZeroException, NaN in ImbalanceRatio
    Evidence: .sisyphus/evidence/task-2-edge-cases.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(mad): scaffold MADConfluenceAI indicator with core types and test infra`
  - Files: `MADConfluenceAI.Data.cs`, `tests/MADConfluenceAI/DataTypesTests.cs`

- [x] 3. Session Context + Market State Tracking

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement `MADMarketState` class that tracks:
    - **Session tracking**: RTH start/end detection, session date rollover, ETH vs RTH flag
    - **Rolling ATR**: 20-period ATR computed from bar data (no external indicator dependency)
    - **Volatility EMA**: Exponential moving average of bar range for regime context
    - **Session extremes**: Track session high/low as they develop, opening range (first 30 min)
    - **Prior day levels**: Capture prior day H/L/C/POC/VAH/VAL at session rollover
    - `Reset()` method for session boundary reset
    - `Update(double high, double low, double close, DateTime time)` per bar
  - Write TDD tests: `ninjatrader/tests/MADConfluenceAI/SessionContextTests.cs`
    - Test ATR calculation with known bars
    - Test session rollover detection
    - Test opening range capture (first 30 min bars)
    - Test prior day level capture

  **Must NOT do**:
  - Do NOT use NT8's built-in ATR() indicator — compute manually for standalone independence
  - Do NOT hardcode session times — use configurable RTH start/end (default 9:30 ET / 16:00 ET)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T10, T17, T20
  - **Blocked By**: T1

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — Existing session context with ATR20, vol EMA, session date tracking. Study the fields and Reset() pattern

  **WHY Each Reference Matters**:
  - `SessionContext.cs`: Shows exactly what cross-signal shared state is needed. Reimplement independently but ensure same field coverage

  **Acceptance Criteria**:
  - [ ] TDD: `SessionContextTests.cs` with ≥6 test cases
  - [ ] `dotnet test --filter "SessionContext"` → PASS
  - [ ] ATR20 matches manual calculation for known bar sequence
  - [ ] Session rollover correctly captures prior day H/L/C
  - [ ] Opening range captured from first 30 minutes of RTH

  **QA Scenarios**:
  ```
  Scenario: ATR calculation matches known values
    Tool: Bash (dotnet test)
    Preconditions: Test with 25 bars of known H/L/C data
    Steps:
      1. Feed 25 bars through MADMarketState.Update()
      2. Assert Atr20 matches manual ATR(20) calculation within ±0.01
    Expected Result: ATR within tolerance
    Failure Indicators: ATR off by >0.1, NaN, or zero
    Evidence: .sisyphus/evidence/task-3-atr-test.txt

  Scenario: Session rollover captures prior day levels
    Tool: Bash (dotnet test)
    Steps:
      1. Feed bars from Day 1 (session high=20100, low=19900, close=20050)
      2. Trigger session rollover (new session date)
      3. Assert PrevDayHigh==20100, PrevDayLow==19900, PrevDayClose==20050
    Expected Result: Prior day levels correctly captured
    Failure Indicators: Stale values, zeros, values from wrong session
    Evidence: .sisyphus/evidence/task-3-rollover-test.txt
  ```

  **Commit**: YES (groups with Wave 1)

- [x] 4. Test Infrastructure Setup

  **What to do**:
  - Create `ninjatrader/tests/MADConfluenceAI/` directory
  - Create `MADConfluenceAITestBase.cs` — shared base class with:
    - Helper to create MADFootprintBar from JSON fixture
    - Helper to create MADSessionContext with default NQ values
    - Helper to assert MADSignalResult matches expected (SignalId, Direction, Strength range)
    - Helper to load JSON fixture files from `ninjatrader/tests/MADConfluenceAI/fixtures/`
  - Create `fixtures/` directory with example fixture format:
    ```json
    {
      "description": "Classic absorption at support",
      "bar": { "open": 20000, "high": 20005, "low": 19995, "close": 20002, "levels": { "20000.00": { "bid": 150, "ask": 25 } } },
      "session": { "atr20": 45.0, "volEma": 12000, "prevDayLow": 19990 },
      "expected": [{ "signalId": "ABS-01", "direction": "Long", "strengthMin": 0.6, "strengthMax": 1.0 }]
    }
    ```
  - Create `MADConfluenceAIFixtureTests.cs` — verify fixture loading works
  - Ensure test project references NinjaTrader.Stubs for mock types

  **Must NOT do**:
  - Do NOT create abstract base detector test classes — keep test infrastructure minimal
  - Do NOT add MSTest or xUnit — use NUnit 3.14.0 (existing project convention)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T7-T17 (all TDD tasks need test infra)
  - **Blocked By**: T1

  **References**:
  **Pattern References**:
  - `ninjatrader/tests/Detectors/AbsorptionDetectorTests.cs` — How existing tests create FootprintBar fixtures, assert SignalResult output
  - `ninjatrader/tests/Scoring/ConfluenceScorerTests.cs` — How scoring tests feed known signal combinations
  - `ninjatrader/tests/fixtures/` — Existing JSON fixture directory (if exists; check structure)

  **Test References**:
  - `ninjatrader/tests/DEEP6.Tests.csproj` — Project configuration, NUnit version, package references

  **WHY Each Reference Matters**:
  - `AbsorptionDetectorTests.cs`: The gold standard for how detector TDD works in this project — copy the fixture creation pattern
  - `DEEP6.Tests.csproj`: Need to know exact NUnit version, target framework, and NinjaTrader.Stubs reference

  **Acceptance Criteria**:
  - [ ] Test base class created with 3+ helper methods
  - [ ] JSON fixture format defined and example fixture created
  - [ ] `dotnet test --filter "Fixture"` → PASS (fixture loading works)
  - [ ] All helpers return correct types (MADFootprintBar from JSON, MADSessionContext)

  **QA Scenarios**:
  ```
  Scenario: Fixture loading round-trips correctly
    Tool: Bash (dotnet test)
    Steps:
      1. Load example fixture JSON
      2. Assert bar.Open == 20000, bar.Levels["20000.00"].BidVol == 150
      3. Assert session.Atr20 == 45.0
      4. Assert expected[0].SignalId == "ABS-01"
    Expected Result: All fields deserialized correctly
    Failure Indicators: JsonException, null fields, wrong values
    Evidence: .sisyphus/evidence/task-4-fixture-loading.txt
  ```

  **Commit**: YES (groups with Wave 1)

- [x] 5. Level Quality Engine

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement `MADLevelEngine` that computes and classifies key price levels:
    - **Prior Day/Week/Month Levels**: PDH, PDL, PDM (midpoint), PWH, PWL, PMH, PML — captured from session rollovers
    - **VWAP + Bands**: Compute session VWAP from tick data (price × volume accumulation) with ±1σ, ±2σ, ±3σ deviation bands
    - **Volume Profile Levels**: POC, VAH, VAL from developing session profile (from MADFootprintBar data)
    - **Opening Range**: High/low of first 30 minutes of RTH (configurable)
    - **Session H/L**: Current session high and low
    - **Psychological Levels**: Round numbers (00, 25, 50, 75 for NQ at 0.25 tick size — e.g., 20000, 20025, 20050, 20075)
    - **Level Proximity**: Method `GetNearbyLevels(double price, double tolerance)` returns all levels within N ticks of a price
    - **Level Quality Score**: Each level gets a quality score (0-1) based on: number of confluent levels at same price, age (today vs yesterday vs last week), touch count (how many times price has tested this level)
  - Write TDD tests: `ninjatrader/tests/MADConfluenceAI/LevelEngineTests.cs`
    - Test VWAP calculation matches known price×volume sequence
    - Test psychological level detection for NQ tick size
    - Test level proximity search with known level set
    - Test level quality scoring with confluent levels

  **Must NOT do**:
  - Do NOT use NT8's built-in VWAP() indicator — compute from tick data manually
  - Do NOT include GEX levels — separate indicator handles that
  - Do NOT track more than 200 active levels (memory guardrail)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`, `trading-knowledge`]
    - `nt8-expert`: NinjaScript API patterns
    - `trading-knowledge`: Key level theory, value area computation, VWAP math

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T12, T16, T19
  - **Blocked By**: T1

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Levels/ProfileAnchorLevels.cs` — Existing level calculation (PDH/PDL/PDM, POC/VAH/VAL, naked POCs, prior-week POC). Study the full computation — reimplement independently
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs` — Value area computation from volume at price levels (the Finalize method)

  **External References**:
  - VWAP formula: `VWAP = Σ(Price × Volume) / Σ(Volume)`, StdDev bands = `VWAP ± N × √(Σ(Volume × (Price - VWAP)²) / Σ(Volume))`
  - Value area: 68% of volume centered on POC, expanding outward

  **WHY Each Reference Matters**:
  - `ProfileAnchorLevels.cs`: Contains the exact prior-day/week level capture logic and naked POC tracking. Study how it handles session rollovers and level persistence
  - `FootprintBar.cs Finalize()`: The value area calculation logic — how to expand from POC to capture 68% of volume

  **Acceptance Criteria**:
  - [ ] TDD: `LevelEngineTests.cs` with ≥10 test cases
  - [ ] VWAP matches manual calculation within ±0.01 for 100-tick sequence
  - [ ] Psychological levels correctly identified for NQ (0.25 tick)
  - [ ] Level proximity returns correct levels within tolerance
  - [ ] Quality score increases with confluence (2 levels at same price > 1)

  **QA Scenarios**:
  ```
  Scenario: VWAP calculation correctness
    Tool: Bash (dotnet test)
    Steps:
      1. Feed 100 ticks: (price=20000, vol=10), (price=20001, vol=5), (price=19999, vol=15)
      2. Manual VWAP = (20000×10 + 20001×5 + 19999×15) / (10+5+15) = 19999.833...
      3. Assert computed VWAP == 19999.833 ± 0.01
    Expected Result: VWAP within tolerance
    Failure Indicators: VWAP off by >0.1, NaN, zero
    Evidence: .sisyphus/evidence/task-5-vwap-test.txt

  Scenario: Level proximity with confluence
    Tool: Bash (dotnet test)
    Steps:
      1. Set levels: PDL=20000, VWAP-1σ=20001.5, Psych=20000
      2. Call GetNearbyLevels(20000.5, tolerance=2.0)
      3. Assert returns 3 levels (PDL, VWAP-1σ, Psych)
      4. Assert quality score for PDL > single-level quality (confluent with Psych at ~same price)
    Expected Result: 3 levels returned, PDL has elevated quality due to confluence
    Evidence: .sisyphus/evidence/task-5-proximity-test.txt
  ```

  **Commit**: YES (groups with Wave 1)

- [x] 6. Configuration System + User Parameters

  **What to do**:
  - In `MADConfluenceAI.cs` (core), define all user-facing NinjaScript parameters using `[NinjaScriptProperty]` and `[Display]` attributes:
    - **Signal Weights** (7): AbsorptionWeight, ExhaustionWeight, DeltaWeight, ImbalanceWeight, IcebergWeight, LiquidityWeight, TrapWeight (all default 1.0, range 0-3)
    - **Thresholds** (8): MinConfidenceScore (default 60), EliteThreshold (90), HighThreshold (75), AbsorptionVolumeMultiplier (3.0), ImbalanceRatio (3.0), SweepReversalSeconds (15), ExhaustionDeltaDecay (0.7), TrapFailureSeconds (30)
    - **Visual Toggles** (8): ShowLevelZones, ShowSignalMarkers, ShowDashboard, ShowHeatmap, ShowSlTp, ShowAbsorptionZones, ShowSweepMarkers, ShowImbalanceHighlights (all default true)
    - **Session** (4): RthStartTime, RthEndTime, OpeningRangeMinutes (30), WarmupBars (50)
    - **Risk** (3): DefaultStopTicks (20), DefaultTargetTicks (40), MaxRiskRewardRatio (5.0)
    - Total: 30 parameters (at cap)
  - Create internal `MADConfig` helper struct that groups these for passing to engines (avoids long parameter lists)
  - Write TDD test: `ConfigTests.cs` — verify defaults are sensible, weight sum is non-zero

  **Must NOT do**:
  - Do NOT exceed 30 user-facing parameters
  - Do NOT add "advanced" or "debug" parameter categories
  - Do NOT use enum parameters (NinjaScript enum handling is brittle) — use int/double/bool only

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T7, T18, T22-T26
  - **Blocked By**: T1

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` — How existing DEEP6 indicator defines NinjaScript parameters with [Display] groups and categories
  - `ninjatrader/ninjascript-ai-context.md` — NinjaScript parameter attribute syntax, forbidden patterns

  **WHY Each Reference Matters**:
  - `DEEP6Footprint.cs parameters section`: Shows exact attribute syntax for NinjaScript parameters, Display grouping, and PropertyOrder

  **Acceptance Criteria**:
  - [ ] Exactly 30 user-facing parameters defined
  - [ ] All have sensible defaults (non-zero weights, reasonable thresholds)
  - [ ] MADConfig struct groups parameters for internal passing
  - [ ] `dotnet test --filter "Config"` → PASS

  **QA Scenarios**:
  ```
  Scenario: Parameter count exactly 30
    Tool: Bash (grep)
    Steps:
      1. Count [NinjaScriptProperty] attributes in MADConfluenceAI.cs
      2. Assert count == 30
    Expected Result: Exactly 30 parameters
    Failure Indicators: >30 (exceeds cap) or <25 (missing essential controls)
    Evidence: .sisyphus/evidence/task-6-param-count.txt
  ```

  **Commit**: YES (groups with Wave 1)

### Wave 2: Data Pipeline (After Wave 1)

- [x] 7. Footprint Data Pipeline (OnMarketData Tick Handler)

  **What to do**:
  - In `MADConfluenceAI.Data.cs`, implement the core tick-to-footprint pipeline:
    - **BBO Tracking**: Track `_bestBid` and `_bestAsk` from MarketDataType.Bid/Ask updates
    - **Trade Classification**: On MarketDataType.Last — classify as buy (price >= ask) or sell (price <= bid), neutral if between
    - **Bar Accumulation**: Route classified trades into current `MADFootprintBar.AddTrade(price, volume, isBuy)`
    - **Bar Finalization**: On OnBarUpdate (BarsInProgress == 0), call Finalize() on completed bar, push to rolling `_bars` list (cap at 500 bars)
    - **CVD Tracking**: Maintain running cumulative delta from session start, reset on session rollover
    - **VWAP Accumulation**: Feed price×volume into level engine's VWAP calculator
    - Thread safety: `lock(_dataLock)` for all shared state between OnMarketData (data thread) and OnBarUpdate (chart thread)
  - Write TDD tests: `ninjatrader/tests/MADConfluenceAI/DataPipelineTests.cs`
    - Test BBO tracking with simulated bid/ask ticks
    - Test trade classification (at bid, at ask, between spread)
    - Test bar accumulation across 50 simulated ticks
    - Test CVD reset on session boundary
    - Test bar list trimming at 500 cap

  **Must NOT do**:
  - Do NOT allocate new objects in OnMarketData — pre-allocate MADFootprintBar pool in State.DataLoaded
  - Do NOT call any Draw.* methods from OnMarketData (wrong thread)
  - Do NOT process MarketDataType.Last if CurrentBar < WarmupBars

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`, `trading-knowledge`]
    - `nt8-expert`: NinjaScript threading model, OnMarketData patterns
    - `trading-knowledge`: Trade classification, delta computation

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T9, T10, T11)
  - **Blocks**: T9, T10, T12-T17
  - **Blocked By**: T2, T4, T6

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:200-245` — OnMarketData pattern: BBO tracking, trade classification, AddTrade routing. THIS IS THE GOLD STANDARD — study every line
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:OnMarketData` — Alternative OnMarketData implementation with lock pattern
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs:AddTrade` — How AddTrade accumulates volume into cells

  **API/Type References**:
  - `ninjatrader/ninjascript-ai-context.md` — Threading model section: data thread vs chart thread rules

  **WHY Each Reference Matters**:
  - `DEEP6FootprintV7.cs:200-245`: The proven pattern for NQ tick processing at 1000+ ticks/sec. Copy the lock pattern, BBO update logic, and trade classification exactly
  - `ninjascript-ai-context.md threading section`: OnMarketData runs on data thread — MUST NOT touch Draw.*, indicator plots, or chart objects

  **Acceptance Criteria**:
  - [ ] TDD: `DataPipelineTests.cs` with ≥10 test cases
  - [ ] BBO tracks correctly (bestBid/bestAsk update on Bid/Ask ticks)
  - [ ] Trade classification: at-ask → buy, at-bid → sell, between → neutral
  - [ ] 50-tick accumulation produces correct bar delta
  - [ ] CVD resets to 0 on session boundary
  - [ ] Bar list trimmed at 500 (oldest removed when cap reached)
  - [ ] No object allocation in OnMarketData (verified by code review — no `new` keywords in method body)

  **QA Scenarios**:
  ```
  Scenario: 50-tick accumulation produces correct footprint
    Tool: Bash (dotnet test)
    Steps:
      1. Simulate 50 ticks: 30 buys at prices 20000-20005, 20 sells at 19998-20002
      2. Finalize bar
      3. Assert BarDelta == (30 buy volume) - (20 sell volume) for overlapping levels
      4. Assert POC is at price level with highest total volume
    Expected Result: Delta and POC match hand calculations
    Failure Indicators: Wrong delta sign, wrong POC, missing levels
    Evidence: .sisyphus/evidence/task-7-accumulation-test.txt

  Scenario: Thread safety under concurrent access
    Tool: Bash (dotnet test)
    Steps:
      1. Spawn 2 threads: Thread A calls AddTrade 1000 times, Thread B reads BarDelta 1000 times
      2. Run for 1 second
      3. Assert no exceptions thrown, no deadlocks (test completes within 5 seconds)
    Expected Result: Zero exceptions, test completes
    Failure Indicators: InvalidOperationException, deadlock (timeout), torn reads
    Evidence: .sisyphus/evidence/task-7-thread-safety.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(mad): implement data pipeline — footprint bars, DOM state, volume profile, delta`

- [x] 8. DOM Data Pipeline (OnMarketDepth Handler)

  **What to do**:
  - In `MADConfluenceAI.Data.cs`, implement Level 2 DOM state tracking:
    - **DOM State Array**: Pre-allocate 2 arrays (bid side, ask side) of 50 levels each. Each level: `{ double Price, long Volume }`
    - **OnMarketDepth Handler**: Process MarketDepthEventArgs — update bid/ask arrays on Add/Update/Remove operations
    - **Liquidity Wall Detection**: Method `GetLiquidityWalls(double threshold)` scans DOM for levels with volume > threshold × average level volume
    - **DOM Imbalance**: Method `GetDomImbalance()` returns ratio of total bid volume / total ask volume (top 10 levels)
    - **Refill Tracking** (for iceberg detection): Track when a level's volume drops to 0 and immediately reloads — maintain refill counter per price level (rolling 30-second window)
    - Thread safety: `lock(_domLock)` separate from `_dataLock` (different contention profile)
    - **Historical Mode Guard**: All DOM methods return neutral/default values when `_isDomAvailable == false` (set in OnMarketDepth first call)

  **Must NOT do**:
  - Do NOT allocate in OnMarketDepth hot path — pre-allocate arrays in State.DataLoaded
  - Do NOT store more than 50 levels per side (memory guardrail)
  - Do NOT assume DOM data exists on historical bars

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`, `trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T15, T16 (detectors that need DOM data)
  - **Blocked By**: T2, T4

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:OnMarketDepth` — L2 depth intake pattern for liquidity wall detection
  - `ninjatrader/Custom/Indicators/DEEP6/GEXGammaOverlay.cs:OnMarketDepth` — Alternative DOM handling pattern
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6LiquidityImbalance.cs` — DOM state management with Kalman filtering

  **WHY Each Reference Matters**:
  - `DEEP6FootprintV7.cs:OnMarketDepth`: Shows the exact pattern for processing L2 updates on NQ with 40+ levels. Critical for understanding Position, Operation, and level indexing
  - `DEEP6LiquidityImbalance.cs`: Shows how to compute DOM imbalance and detect liquidity walls — advanced pattern with Kalman filter (we'll simplify but study the approach)

  **Acceptance Criteria**:
  - [ ] TDD: `DomPipelineTests.cs` with ≥8 test cases
  - [ ] DOM state tracks 50 levels per side correctly
  - [ ] GetLiquidityWalls returns correct wall levels for known DOM state
  - [ ] GetDomImbalance returns correct ratio
  - [ ] Refill tracking detects 3+ refills at same price within 30 seconds
  - [ ] Historical mode returns defaults without error

  **QA Scenarios**:
  ```
  Scenario: DOM state tracks level updates
    Tool: Bash (dotnet test)
    Steps:
      1. Simulate: Add bid at 20000 vol=100, Add bid at 19999 vol=50
      2. Assert bid[0] = {20000, 100}, bid[1] = {19999, 50}
      3. Simulate: Update bid at position 0, vol=200
      4. Assert bid[0] = {20000, 200}
    Expected Result: DOM state reflects all operations
    Evidence: .sisyphus/evidence/task-8-dom-tracking.txt

  Scenario: Historical mode graceful degradation
    Tool: Bash (dotnet test)
    Steps:
      1. Do NOT call OnMarketDepth (simulating historical mode)
      2. Call GetLiquidityWalls(threshold=2.0)
      3. Assert returns empty list (not exception)
      4. Call GetDomImbalance()
      5. Assert returns 1.0 (neutral)
    Expected Result: No exceptions, neutral defaults
    Evidence: .sisyphus/evidence/task-8-historical-mode.txt
  ```

  **Commit**: YES (groups with Wave 2)

- [x] 9. Volume Profile Engine (POC/VAH/VAL/HVN/LVN)

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement `MADVolumeProfile` that builds developing session volume profile:
    - **Accumulation**: Each finalized MADFootprintBar adds its levels to the session profile: `SessionProfile[price] += totalVol`
    - **POC Calculation**: Track price with highest cumulative session volume
    - **Value Area**: Expand outward from POC until 68% of session volume captured → VAH (upper bound), VAL (lower bound)
    - **HVN/LVN Detection**: After computing profile, identify High Volume Nodes (local maxima with volume > 1.5× surrounding average) and Low Volume Nodes (local minima with volume < 0.5× surrounding average)
    - **Naked Levels**: Track POC levels from previous sessions that price hasn't revisited — these act as magnets
    - `Reset()` on session rollover (save previous session's POC as naked level)
    - `AddBar(MADFootprintBar bar)` called per finalized bar
    - `GetProfileLevels()` returns current POC, VAH, VAL, HVNs, LVNs

  **Must NOT do**:
  - Do NOT use NT8's Volume Profile indicator (not exposed in NinjaScript)
  - Do NOT store profile for more than 5 previous sessions (memory cap)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`trading-knowledge`]
    - `trading-knowledge`: Volume profile theory, value area computation, auction market theory

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T12, T15, T16, T18
  - **Blocked By**: T7 (needs finalized footprint bars)

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Levels/ProfileAnchorLevels.cs` — Value area computation, naked POC tracking, session rollover handling
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs:Finalize` — Bar-level POC and value area calculation

  **WHY Each Reference Matters**:
  - `ProfileAnchorLevels.cs`: The complete algorithm for session-level volume profile with naked POCs. This is the reference implementation to study and independently replicate

  **Acceptance Criteria**:
  - [ ] TDD: `VolumeProfileTests.cs` with ≥8 test cases
  - [ ] POC correctly identifies highest-volume price from 20-bar session
  - [ ] Value area captures 68% ± 2% of total session volume
  - [ ] HVN detection finds correct local maxima
  - [ ] LVN detection finds correct local minima
  - [ ] Naked POC preserved across session rollover

  **QA Scenarios**:
  ```
  Scenario: Value area captures 68% of volume
    Tool: Bash (dotnet test)
    Steps:
      1. Create 20 bars with known volume distribution (bell curve centered at 20050)
      2. AddBar for all 20
      3. Assert POC == 20050 (highest volume)
      4. Assert VAH-VAL range contains 68% ± 2% of total volume
    Expected Result: POC correct, value area within tolerance
    Evidence: .sisyphus/evidence/task-9-value-area.txt
  ```

  **Commit**: YES (groups with Wave 2)

- [x] 10. Delta Pipeline (Per-Bar Delta, CVD, Delta Extremes)

  **What to do**:
  - In `MADConfluenceAI.Data.cs`, implement delta tracking beyond basic bar delta:
    - **Intrabar Delta Tracking**: Track MaxDelta and MinDelta within each bar (updated on each tick via AddTrade)
    - **Delta Quality Scalar**: `DeltaQuality = Close_Delta / Max(|MaxDelta|, |MinDelta|)` — measures how much of the intrabar extreme delta survives to bar close (range 0-1.15, clamped)
    - **CVD Series**: Maintain array of CVD values per bar (for divergence detection): `_cvdSeries[barIndex] = cumDelta`
    - **Delta Rate of Change**: `DeltaRoC = (CVD[0] - CVD[N]) / N` — slope of CVD over last N bars
    - **Delta Acceleration**: Second derivative of CVD — `DeltaAccel = DeltaRoC[0] - DeltaRoC[1]`
    - These feed into DELT-01 (divergence) and DELT-02 (acceleration) detectors in Wave 3
  - Write TDD tests: `DeltaPipelineTests.cs`

  **Must NOT do**:
  - Do NOT compute delta from OrderFlowCumulativeDelta indicator — compute from raw tick accumulation

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T12-T14, T18
  - **Blocked By**: T3, T7

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs:DeltaQualityScalar()` — Delta quality computation (conviction measure 0.7-1.15)
  - `.claude/skills/trading-knowledge/domains/order-flow.md` — Delta signals: DELT-01 through DELT-11 definitions

  **WHY Each Reference Matters**:
  - `FootprintBar.cs:DeltaQualityScalar()`: The exact formula for measuring delta conviction. Critical for absorption/exhaustion confidence scoring
  - `order-flow.md`: Defines what delta divergence and CVD acceleration mean in trading terms — needed to implement correct detection logic

  **Acceptance Criteria**:
  - [ ] TDD: `DeltaPipelineTests.cs` with ≥6 test cases
  - [ ] MaxDelta/MinDelta track correctly across 50 ticks within a bar
  - [ ] DeltaQuality returns ~1.0 when close delta equals max delta (strong conviction)
  - [ ] DeltaQuality returns ~0.5 when close delta is half of max delta (weak conviction)
  - [ ] CVD series accumulates correctly across bar boundaries
  - [ ] DeltaRoC and DeltaAccel compute correct derivatives

  **QA Scenarios**:
  ```
  Scenario: Delta quality matches conviction
    Tool: Bash (dotnet test)
    Steps:
      1. Build bar: 40 buy ticks, then 10 sell ticks (delta peaks mid-bar, partially reverses)
      2. Assert MaxDelta reflects peak, MinDelta reflects trough
      3. Assert DeltaQuality < 1.0 (close delta < max delta due to late sells)
    Expected Result: Quality reflects partial reversal
    Evidence: .sisyphus/evidence/task-10-delta-quality.txt
  ```

  **Commit**: YES (groups with Wave 2)

- [x] 11. Multi-Timeframe Bias (AddDataSeries for HTF Trend)

  **What to do**:
  - In `MADConfluenceAI.cs` (core OnStateChange), add secondary data series:
    - `AddDataSeries(BarsPeriodType.Minute, 5)` — 5-minute bars for medium-term trend (BarsInProgress == 1)
    - `AddDataSeries(BarsPeriodType.Minute, 15)` — 15-minute bars for higher-timeframe trend (BarsInProgress == 2)
  - In OnBarUpdate, when BarsInProgress == 1 or 2:
    - Compute simple trend: compare Close[0] vs SMA(20) — above = bullish, below = bearish
    - Compute momentum: rate of change of Close over last 10 bars
    - Store in `MADMarketState.HtfBias` (enum: Bullish/Bearish/Neutral) and `HtfMomentum` (double)
  - This feeds into REG-01 (regime classifier) and T20 (market context engine) in later waves
  - Write TDD test with simulated multi-series bar data

  **Must NOT do**:
  - Do NOT add more than 2 secondary data series (3 total including primary)
  - Do NOT use NT8's built-in SMA() — compute 20-period simple average manually
  - Do NOT process detector logic on secondary series — only capture trend/momentum

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T17, T20
  - **Blocked By**: T1

  **References**:
  **Pattern References**:
  - `ninjatrader/ninjascript-ai-context.md` — AddDataSeries usage, BarsInProgress filtering, multi-series synchronization rules
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6MarketInternals.cs` — How existing DEEP6 handles secondary data series

  **WHY Each Reference Matters**:
  - `ninjascript-ai-context.md multi-series section`: CRITICAL — AddDataSeries has strict rules (hardcoded arguments only, BarsInProgress guard mandatory). Missing this causes runtime exceptions

  **Acceptance Criteria**:
  - [ ] TDD: `MultiTimeframeTests.cs` with ≥4 test cases
  - [ ] 5-minute and 15-minute series correctly added
  - [ ] HtfBias correctly reflects trend relative to SMA(20)
  - [ ] Momentum computed as rate of change
  - [ ] BarsInProgress guards prevent detector logic on secondary series

  **QA Scenarios**:
  ```
  Scenario: HTF bias correctly identifies uptrend
    Tool: Bash (dotnet test)
    Steps:
      1. Simulate 25 five-minute bars with ascending closes (19900 to 20100)
      2. Assert HtfBias == Bullish (close > SMA20)
      3. Assert HtfMomentum > 0
    Expected Result: Correct bullish identification
    Evidence: .sisyphus/evidence/task-11-htf-bias.txt
  ```

  **Commit**: YES (groups with Wave 2)

### Wave 3: Detectors (MAX PARALLEL After Wave 2)

- [x] 12. Absorption Detector (ABS-01 Classic + ABS-02 Passive)

  **What to do**:
  - In `MADConfluenceAI.Signals.cs`, implement 2 absorption variants:
  - **ABS-01 Classic Absorption**: High volume at a single price level with zero/minimal price progress. Detection: `totalVol(level) > AbsorptionVolumeMultiplier × avgLevelVol AND |priceChange| < 2 ticks`. Direction: if mostly bid volume absorbed → Long (passive buyers), if ask absorbed → Short (passive sellers). Strength: `min(1.0, totalVol / (AbsorptionVolumeMultiplier × 2 × avgVol))`. Level proximity bonus: +0.15 if at key level (from Level Engine T5).
  - **ABS-02 Passive Absorption**: Aggressive orders hit a passive wall repeatedly without breaking through. Detection: examine 3+ consecutive bars where delta strongly favors one direction but price doesn't break the level. `|cumDelta(3bars)| > 3 × avgBarDelta AND |priceRange(3bars)| < 3 ticks`. Direction: opposite to aggressor (aggressor fails → passive side wins).
  - Both variants: return `MADSignalResult` with SignalId, Direction, Strength (0-1), and Detail string
  - Each detector gets its own JSON fixture file: `fixtures/abs-01-classic.json`, `fixtures/abs-02-passive.json`

  **Must NOT do**:
  - Do NOT import AbsorptionDetector from DEEP6 AddOns — reimplement
  - Do NOT add VA-Extreme bonus (that's part of the scoring engine T18)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`, `trading-knowledge`]
    - `trading-knowledge`: Absorption theory — what constitutes institutional absorption, lead times, false positive filters

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T13-T17)
  - **Blocks**: T18, T19
  - **Blocked By**: T5, T9, T10

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` — The 5 absorption variants (ABS-01 through ABS-07). Study detection logic, thresholds, and strength calculation. Reimplement top 2 independently
  - `.claude/skills/trading-knowledge/domains/order-flow.md` — Absorption signal definitions with conditions and entry rules

  **Test References**:
  - `ninjatrader/tests/Detectors/AbsorptionDetectorTests.cs` — How existing tests create fixture bars for absorption, what assertions they make

  **WHY Each Reference Matters**:
  - `AbsorptionDetector.cs`: Contains the battle-tested detection logic — thresholds, delta gate, cooldown, strength formula. Study this carefully to get the same quality in the reimplementation
  - `AbsorptionDetectorTests.cs`: Shows what edge cases to test (low volume bars, absorption at session extremes, conflicting signals)

  **Acceptance Criteria**:
  - [ ] TDD: `AbsorptionDetectorTests.cs` with ≥6 test cases per variant (12 total)
  - [ ] ABS-01 fires on bar with volume > 3× average at a single level AND price stalls
  - [ ] ABS-01 does NOT fire on normal high-volume bar where price moves
  - [ ] ABS-02 fires on 3+ bars with cumulative delta > 3× avg AND price unchanged
  - [ ] Both return correct Direction (opposite to aggressive side)
  - [ ] Strength scales with volume magnitude

  **QA Scenarios**:
  ```
  Scenario: ABS-01 detects classic absorption at support
    Tool: Bash (dotnet test)
    Preconditions: JSON fixture with bar at 20000, bid volume 150 (3x average 50), ask volume 25, price change < 2 ticks
    Steps:
      1. Load fixture, create MADFootprintBar
      2. Run ABS-01 detection
      3. Assert fires with Direction=Long (sellers absorbed by passive buyers)
      4. Assert Strength >= 0.6
    Expected Result: Signal fires correctly
    Evidence: .sisyphus/evidence/task-12-abs01-detection.txt

  Scenario: ABS-01 does NOT fire on normal volume bar
    Tool: Bash (dotnet test)
    Preconditions: Bar with volume 1.5x average (below 3x threshold)
    Steps:
      1. Run ABS-01 detection
      2. Assert no signal returned
    Expected Result: No false positive
    Evidence: .sisyphus/evidence/task-12-abs01-no-fire.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(mad): implement 12 signal detectors with TDD coverage`

- [x] 13. Exhaustion Detector (EXH-01 Print + EXH-02 Fading Momentum)

  **What to do**:
  - In `MADConfluenceAI.Signals.cs`, implement 2 exhaustion variants:
  - **EXH-01 Exhaustion Print**: Large volume at bar extreme (high or low) with price failing to advance beyond. Detection: `volumeAtExtreme > ExhaustionVolumeThreshold AND bar closes away from extreme by > 50% of bar range`. Direction: if volume at high and close below midpoint → Short (buying exhaustion), vice versa → Long. Strength: proportional to close distance from extreme.
  - **EXH-02 Fading Momentum**: Declining delta on successive pushes in same direction over 3+ bars. Detection: `delta[0] < ExhaustionDeltaDecay × delta[1] AND delta[1] < ExhaustionDeltaDecay × delta[2] AND price[0] extremes same direction`. Direction: opposite to fading momentum direction. Strength: magnitude of delta decay.
  - Both need delta quality scalar gate: only fire if DeltaQuality > 0.5 (reject noise)

  **Must NOT do**:
  - Do NOT import ExhaustionDetector from DEEP6 AddOns

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`, `trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T18, T19
  - **Blocked By**: T9, T10

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs` — 6 exhaustion variants. Study EXH-01, EXH-05 (FadingMomentum) — these map to our 2 variants
  - `ninjatrader/tests/Detectors/ExhaustionDetectorTests.cs` — Test patterns for exhaustion

  **Acceptance Criteria**:
  - [ ] TDD: ≥6 test cases per variant (12 total)
  - [ ] EXH-01 fires at bar with high volume at extreme + close away from extreme
  - [ ] EXH-02 fires when delta decays > 30% per bar across 3+ bars
  - [ ] Delta quality gate prevents firing on low-quality bars
  - [ ] Direction correctly identifies fading side

  **QA Scenarios**:
  ```
  Scenario: EXH-01 detects exhaustion at high
    Tool: Bash (dotnet test)
    Steps:
      1. Create bar: high volume at 20100 (bar high), close at 20090 (below midpoint)
      2. Run EXH-01
      3. Assert Direction=Short (buying exhaustion), Strength > 0.5
    Expected Result: Correctly identifies buying exhaustion
    Evidence: .sisyphus/evidence/task-13-exh01-detection.txt
  ```

  **Commit**: YES (groups with Wave 3)

- [x] 14. Delta Analysis (DELT-01 Divergence + DELT-02 CVD Acceleration)

  **What to do**:
  - **DELT-01 Delta Divergence**: Price makes new high/low but CVD fails to confirm. Detection: `price[0] > price[N] (new high) BUT cvd[0] < cvd[N] (CVD declining)` over lookback N bars. Use Z-score normalization: divergence must exceed 3.5σ from recent delta-price correlation. Direction: opposite to price direction (bearish divergence → Short, bullish divergence → Long). Strength: Z-score magnitude / 5.0, clamped to [0, 1].
  - **DELT-02 CVD Acceleration**: Detect inflection points in CVD curve via second derivative. Detection: `cvdAccel changes sign AND magnitude > threshold`. Positive-to-negative acceleration while CVD still rising = deceleration warning. Direction: opposite to CVD direction at inflection. Strength: magnitude of acceleration change.
  - Both require minimum 10 bars of CVD history

  **Must NOT do**:
  - Do NOT use linear regression for divergence — use Z-score of price-CVD correlation
  - Do NOT fire within first 10 bars (insufficient history)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T18, T19
  - **Blocked By**: T10

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs` — Delta divergence logic, CVD analysis
  - `.claude/skills/trading-knowledge/domains/order-flow.md` — DELT-01 through DELT-11 definitions

  **Acceptance Criteria**:
  - [ ] TDD: ≥6 test cases per variant
  - [ ] DELT-01 fires on bearish divergence (price up, CVD down) exceeding 3.5σ
  - [ ] DELT-01 does NOT fire on normal price-CVD correlation
  - [ ] DELT-02 detects CVD inflection points
  - [ ] Both respect 10-bar minimum history

  **QA Scenarios**:
  ```
  Scenario: DELT-01 detects bearish divergence
    Tool: Bash (dotnet test)
    Steps:
      1. Create 15 bars: price ascending (20000→20075), CVD descending (1000→-500)
      2. Run DELT-01
      3. Assert fires with Direction=Short, Detail contains "bearish divergence"
    Expected Result: Bearish divergence detected
    Evidence: .sisyphus/evidence/task-14-divergence.txt
  ```

  **Commit**: YES (groups with Wave 3)

- [x] 15. Stacked Imbalance + Iceberg (IMB-01 + ICE-01)

  **What to do**:
  - **IMB-01 Stacked Imbalance**: 3+ consecutive price levels where bid/ask ratio > ImbalanceRatio (default 3:1). Detection: scan footprint bar levels from low to high. For each level, compute `askVol/bidVol` (or inverse). If ratio > threshold for 3+ consecutive levels, flag as stacked imbalance. Direction: if ask-dominant stack → Long (aggressive buying), bid-dominant → Short. Strength: `(consecutiveLevels - 2) / 5`, clamped to [0, 1]. Diagonal variant: compare ask(N) vs bid(N+1) for diagonal imbalance.
  - **ICE-01 Iceberg Detection**: Detect hidden orders via DOM + tick comparison. Detection: `tradedVolumeAtPrice > 3 × displayedDomSize AND refillCount >= 3 within 30 seconds`. Uses refill tracking from DOM pipeline (T8). Direction: if iceberg is on bid side (passive buyer) → Long, ask side → Short. Strength: `min(1.0, hiddenRatio / 10.0)` where hiddenRatio = tradedVol / displayedSize.
  - ICE-01 requires DOM data — gracefully returns empty results in historical mode

  **Must NOT do**:
  - Do NOT fire ICE-01 on historical bars (DOM unavailable)
  - Do NOT count imbalances where total level volume < 5 contracts (noise filter)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T18, T19
  - **Blocked By**: T8, T9

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs` — Stacked imbalance detection (IMB-01..03)
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/IcebergDetector.cs` — Iceberg detection from DOM clustering

  **Acceptance Criteria**:
  - [ ] TDD: ≥6 test cases per signal
  - [ ] IMB-01 detects 3+ consecutive levels with 3:1 ratio
  - [ ] IMB-01 ignores levels with < 5 total contracts
  - [ ] ICE-01 detects 3+ refills at same price with hidden volume > 3× displayed
  - [ ] ICE-01 returns empty in historical mode (no DOM)

  **QA Scenarios**:
  ```
  Scenario: IMB-01 detects 4-level stacked imbalance
    Tool: Bash (dotnet test)
    Steps:
      1. Create bar with 4 consecutive levels: ask=100/bid=25 at each (ratio 4:1)
      2. Run IMB-01
      3. Assert fires with Direction=Long, Strength=(4-2)/5=0.4
    Expected Result: Stacked imbalance detected with correct strength
    Evidence: .sisyphus/evidence/task-15-imbalance.txt
  ```

  **Commit**: YES (groups with Wave 3)

- [x] 16. Liquidity Sweep + Failed Auction (LIQSW-01 + FAIL-01)

  **What to do**:
  - **LIQSW-01 Liquidity Sweep**: Price breaks a key level (PDH/PDL, session H/L, swing H/L) then reverses within SweepReversalSeconds (default 15). Detection: `price breaks level by ≥ 1 tick AND reverses back through level within timeWindow AND volume spike on break (> 2× average)`. Uses Level Engine (T5) for key levels. Direction: opposite to break direction (sweep above → Short, sweep below → Long). Strength: speed of reversal (faster = stronger).
  - **FAIL-01 Failed Auction**: High volume at bar extreme with immediate reversal candle and optional single print (isolated volume). Detection: `volumeAtExtreme > 2× avgBarVol AND next bar reverses > 50% of current bar range AND (optional) single print at extreme (only 1 level with volume)`. Direction: opposite to failed extreme. Strength: reversal magnitude / bar range.
  - Both require at least 2 bars of context (current + next/previous)

  **Must NOT do**:
  - Do NOT detect sweeps in first 5 minutes of session (opening volatility noise)
  - Do NOT require DOM data for sweep detection — use price action + volume only

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T18, T19
  - **Blocked By**: T5, T8, T9

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Trap/TrapDetector.cs` — False breakout and trap detection — related concept
  - `.claude/skills/trading-knowledge/domains/order-flow.md` — Trap signals and failed breakout definitions

  **Acceptance Criteria**:
  - [ ] TDD: ≥6 test cases per signal
  - [ ] LIQSW-01 detects break + reversal within time window
  - [ ] LIQSW-01 does NOT fire during first 5 minutes of session
  - [ ] FAIL-01 detects high volume at extreme + reversal candle
  - [ ] Strength scales with reversal speed/magnitude

  **QA Scenarios**:
  ```
  Scenario: LIQSW-01 detects sweep below PDL
    Tool: Bash (dotnet test)
    Steps:
      1. Set PDL=20000 in level engine
      2. Create bar that breaks to 19998 with 3× avg volume, then reverses to 20005
      3. Time between break and reversal: 10 seconds (< 15 threshold)
      4. Assert fires Direction=Long, Detail contains "sweep below PDL"
    Expected Result: Liquidity sweep reversal detected
    Evidence: .sisyphus/evidence/task-16-sweep.txt
  ```

  **Commit**: YES (groups with Wave 3)

- [x] 17. Trap + Regime Classifier (TRAP-01 + REG-01)

  **What to do**:
  - **TRAP-01 False Breakout Trap**: Breakout beyond key level → failure → trapped traders become fuel. Detection: `price breaks level by ≥ 3 ticks AND holds for ≥ 2 bars AND reverses back inside by > bar range within TrapFailureSeconds (30)`. Additional confirmation: CVD diverges from breakout direction (trapped longs/shorts). Direction: opposite to failed breakout. Strength: number of bars trapped × volume magnitude.
  - **REG-01 Regime Classifier**: Classify market as Trending/Ranging/Volatile based on:
    - ATR percentile: current ATR vs 50-period ATR percentile (> 75th = volatile, < 25th = quiet)
    - Delta trend: consistent positive/negative delta over 10 bars = trending
    - Volume regime: volume > 1.5× average = active, < 0.5× = thin
    - HTF bias from T11: aligned = trending, conflicting = ranging
    - Output: `enum MADRegime { Trending, Ranging, Volatile, Thin }` + confidence
  - REG-01 is meta-signal — used by scoring engine to adjust weights, not for direct trade signals

  **Must NOT do**:
  - Do NOT implement full HMM — use the threshold-based classifier described above
  - Do NOT make regime a trade signal — it's a context modifier only

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T18, T20
  - **Blocked By**: T3, T11

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Trap/TrapDetector.cs` — Trap detection logic (false breakout, CVD trap)
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs` — L4 Regime layer (HmmForward + Bocpd) — study the concept but implement simplified version

  **Acceptance Criteria**:
  - [ ] TDD: ≥4 test cases per signal
  - [ ] TRAP-01 detects breakout + failure + reversal pattern
  - [ ] REG-01 correctly classifies trending market (consistent delta + HTF alignment)
  - [ ] REG-01 correctly classifies ranging market (low ATR + conflicting HTF)
  - [ ] REG-01 correctly classifies volatile market (high ATR percentile)

  **QA Scenarios**:
  ```
  Scenario: REG-01 classifies trending market
    Tool: Bash (dotnet test)
    Steps:
      1. Set ATR percentile=60 (moderate), delta trend positive over 10 bars, HTF bias=Bullish
      2. Run REG-01
      3. Assert regime=Trending, confidence > 0.6
    Expected Result: Trending correctly identified
    Evidence: .sisyphus/evidence/task-17-regime.txt
  ```

  **Commit**: YES (groups with Wave 3)

### Wave 4: Intelligence (After Wave 3)

- [x] 18. Confluence Scoring Engine

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement the core weighted confluence scorer:
  - **Category Weights** (from user config): Absorption, Exhaustion, Delta, Imbalance, Iceberg, Liquidity, Trap — each default 1.0, configurable 0-3
  - **Scoring Formula**: `rawScore = Σ(signal.Strength × categoryWeight × directionAgreement) / maxPossibleScore × 100`
    - `directionAgreement`: +1.0 if signal direction matches majority, -0.5 if conflicts (penalty for conflicting signals)
    - `maxPossibleScore`: sum of all category weights (for normalization to 0-100)
  - **Category Agreement Bonus**: +10 points if ≥3 different categories agree on direction (cross-pillar confluence)
  - **Level Proximity Bonus**: +5 points if signal fires at/near a key level (within 3 ticks)
  - **Regime Modifier**: 
    - Trending: +10 for continuation setups, -10 for reversal setups
    - Ranging: +10 for reversal setups, -10 for breakout setups
    - Volatile: -5 for all setups (higher uncertainty)
    - Thin: -15 for all setups (low liquidity = dangerous)
  - **Tier Classification**:
    - 90-100 = Elite (S tier)
    - 75-89 = High Probability (A tier)
    - 60-74 = Moderate (B tier)
    - 40-59 = WAIT (C tier) — conditions not yet clear
    - < 40 = DO NOT TRADE (Q tier) — actively dangerous
  - **Output**: `MADScorerResult { double Score, MADTier Tier, MADSignalDirection Direction, string SetupType, List<MADSignalResult> ContributingSignals }`

  **Must NOT do**:
  - Do NOT implement Bayesian updating between bars — keep each bar's score independent
  - Do NOT allow score > 100 or < 0 after all modifiers
  - Do NOT weight historical signals (only current bar signals count)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T19, T20, T21)
  - **Blocks**: T19, T21
  - **Blocked By**: T12-T17 (all detectors must exist)

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs` — Two-layer scoring (engine-level + category-level), R3 attribution weights, multiplier cascade. Study the full 30KB implementation for architecture inspiration
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/SignalTier.cs` — Tier classification (Q/C/B/A/S) with thresholds

  **Test References**:
  - `ninjatrader/tests/Scoring/ConfluenceScorerTests.cs` — How scoring tests feed known signal combinations and assert exact scores

  **WHY Each Reference Matters**:
  - `ConfluenceScorer.cs`: The gold standard for how to combine 44 signals into a single score. Study the two-layer approach (engine agreement first, then category confluence) and the multiplier cascade pattern
  - `SignalTier.cs`: Tier thresholds and classification logic — reimplement with our 5-tier system

  **Acceptance Criteria**:
  - [ ] TDD: `ScoringEngineTests.cs` with ≥12 test cases
  - [ ] Single-signal scoring: ABS-01 at strength 0.8 with weight 1.0 → score in correct range
  - [ ] Multi-signal confluence: 3 agreeing signals → higher score than single signal
  - [ ] Category agreement bonus: +10 when ≥3 categories agree
  - [ ] Level proximity bonus: +5 when signal at key level
  - [ ] Regime modifier correctly adjusts score
  - [ ] Tier classification: score 92 → Elite, 80 → High, 65 → Moderate, 50 → WAIT, 30 → DNT
  - [ ] Conflicting signals reduce score (direction penalty)
  - [ ] Score always 0-100 after all modifiers

  **QA Scenarios**:
  ```
  Scenario: Full confluence produces Elite score
    Tool: Bash (dotnet test)
    Steps:
      1. Feed 5 signals: ABS-01(Long,0.9), EXH-01(Long,0.8), DELT-01(Long,0.7), LIQSW-01(Long,0.9), at key level
      2. Set regime=Ranging (reversal bonus)
      3. Assert score >= 90, tier=Elite, direction=Long
    Expected Result: Elite setup with full confluence
    Evidence: .sisyphus/evidence/task-18-elite-score.txt

  Scenario: Conflicting signals produce WAIT
    Tool: Bash (dotnet test)
    Steps:
      1. Feed: ABS-01(Long,0.8), DELT-01(Short,0.7), EXH-02(Short,0.6)
      2. Assert score < 60 (conflicting signals penalized)
      3. Assert tier=WAIT or lower
    Expected Result: Conflicting signals correctly penalized
    Evidence: .sisyphus/evidence/task-18-conflicting.txt
  ```

  **Commit**: YES (groups with Wave 4)
  - Message: `feat(mad): implement confluence scoring, setup classification, and trade filtering`

- [x] 19. Setup Classifier (7 Setup Types)

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement setup type classification:
  - For each bar's signal combination, classify into one of 7 setup types:
    - **Reversal**: ABS-01/02 fires at key level + any EXH signal + regime is Ranging
    - **Breakout**: IMB-01 fires + price through key level + delta confirms direction + regime is Trending
    - **Failed Breakout**: TRAP-01 fires (break + failure pattern)
    - **Absorption Bounce**: ABS-01/02 fires + DELT-01 shifts to bounce direction
    - **Trend Continuation**: REG-01=Trending + DELT-02 acceleration in trend direction + price at pullback level
    - **Exhaustion Reversal**: EXH-01/02 at extreme + DELT-01 divergence
    - **Liquidity Sweep Reversal**: LIQSW-01 fires + ABS-01 at sweep level
    - **None**: No clear pattern match → WAIT
  - Each type has: name, description, typical win rate (hardcoded from research), recommended entry offset, recommended SL/TP ratio
  - Method: `ClassifySetup(List<MADSignalResult> signals, MADRegime regime, List<MADLevel> nearbyLevels)` → `MADSetupType`

  **Must NOT do**:
  - Do NOT allow a bar to have multiple setup classifications — pick the highest-confidence one
  - Do NOT invent new setup types beyond the 7 defined

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: T21, T24
  - **Blocked By**: T12-T16, T18

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/NarrativeCascade.cs` — Signal interpretation and narrative building from signal combinations

  **Acceptance Criteria**:
  - [ ] TDD: ≥7 test cases (one per setup type) + 2 edge cases
  - [ ] Each setup type correctly identified from its required signal combination
  - [ ] "None" returned when no pattern matches
  - [ ] Only highest-confidence setup returned per bar

  **QA Scenarios**:
  ```
  Scenario: Reversal setup correctly classified
    Tool: Bash (dotnet test)
    Steps:
      1. Signals: ABS-01(Long,0.8) at PDL + EXH-01(Long,0.7), regime=Ranging
      2. Assert ClassifySetup returns Reversal with Direction=Long
    Expected Result: Reversal correctly identified
    Evidence: .sisyphus/evidence/task-19-reversal-setup.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [x] 20. Market Context Engine

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement market context assessment:
  - **Trend Direction**: From HTF bias (T11) + 20-bar close vs SMA on primary series → `Bullish/Bearish/Neutral`
  - **Time of Day Modifier**: Score modifier based on NQ session behavior:
    - 9:30-10:00 ET: Opening drive (-5 reversal, +5 breakout — high volatility, directional)
    - 10:00-11:30 ET: Prime trading (+5 all setups — best setups here)
    - 11:30-13:30 ET: Midday chop (-10 all setups — avoid)
    - 13:30-15:00 ET: Afternoon session (+3 continuation — institutional rebalancing)
    - 15:00-16:00 ET: Close (-5 all — unpredictable)
    - ETH: -15 all setups (thin liquidity)
  - **Session Type**: From regime (T17) + time-of-day + volume → `TrendDay / RotationalDay / BreakoutDay / ChopDay`
  - **Momentum**: Rate of price change over last 10 bars normalized by ATR → `Strong/Moderate/Weak/Reversing`
  - Output: `MADMarketContext { TrendDirection, TimeModifier, SessionType, Momentum }` — fed into scoring engine as modifiers

  **Must NOT do**:
  - Do NOT add market internals (TICK, ADD, VOLD) — that would require AddDataSeries for those instruments
  - Do NOT hardcode ET timezone — use NQ trading hours from TradingHours object

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: T21
  - **Blocked By**: T3, T11, T17

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6MarketInternals.cs` — Market context and session type analysis

  **Acceptance Criteria**:
  - [ ] TDD: ≥6 test cases
  - [ ] Time-of-day modifier correct for each session window
  - [ ] Session type correctly identified (trend day vs chop day)
  - [ ] Trend direction matches HTF bias + primary SMA

  **QA Scenarios**:
  ```
  Scenario: Midday chop correctly penalized
    Tool: Bash (dotnet test)
    Steps:
      1. Set time to 12:00 ET, regime=Ranging, low volume
      2. Assert TimeModifier == -10
      3. Assert SessionType == ChopDay
    Expected Result: Midday correctly identified as low-quality
    Evidence: .sisyphus/evidence/task-20-midday-chop.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [x] 21. Trade Filter + Decision Logic (LONG/SHORT/WAIT/DNT + SL/TP)

  **What to do**:
  - In `MADConfluenceAI.Scoring.cs`, implement the final decision layer:
  - **Decision Logic**: Combine scorer result (T18) + market context (T20) → final output:
    - Score ≥ 90 AND setup classified AND context not hostile → LONG or SHORT (Elite)
    - Score 75-89 AND setup classified → LONG or SHORT (High)
    - Score 60-74 AND setup classified → LONG or SHORT (Moderate — with caution flag)
    - Score 40-59 OR no setup match → WAIT (conditions unclear)
    - Score < 40 OR conflicting signals > agreeing OR regime=Thin → DO NOT TRADE
    - Midday chop override: WAIT regardless of score between 11:30-13:30 ET unless score ≥ 90
  - **SL/TP Calculation**:
    - Stop Loss: Nearest level on wrong side of entry + 2 ticks buffer. Min: DefaultStopTicks. Max: ATR × 1.5.
    - Take Profit: Next key level in direction + R:R ratio adjustment. Min R:R: 1.5:1.
    - If R:R < 1.5:1 with nearest levels → downgrade tier by 1 (Elite→High, etc.)
  - **Final Output**: `MADDecision { Action (Long/Short/Wait/DNT), Score, Tier, SetupType, StopPrice, TargetPrice, RiskRewardRatio, Detail }`
  - Store in indicator's plot values for strategy consumption: `Values[0][0] = Score`, `Values[1][0] = DirectionCode` (+1=Long, -1=Short, 0=Wait/DNT)

  **Must NOT do**:
  - Do NOT place actual orders — this is an indicator, not a strategy
  - Do NOT bypass the midday chop filter for non-Elite setups
  - Do NOT allow R:R below 1.0 (reject setup entirely)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (last in Wave 4)
  - **Blocks**: T22-T26 (all rendering), T27
  - **Blocked By**: T18, T19, T20

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerEntryGate.cs` — Entry gate logic for execution decisions
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/TradeSetupState.cs` — Trade setup state tracking with SL/TP

  **Acceptance Criteria**:
  - [ ] TDD: ≥10 test cases covering all 5 decision outcomes
  - [ ] Elite setup (score 92) → LONG or SHORT action
  - [ ] Low score (35) → DO NOT TRADE
  - [ ] Midday with score 75 → WAIT (override)
  - [ ] Midday with score 95 → LONG/SHORT (Elite overrides chop filter)
  - [ ] SL/TP calculated with R:R ≥ 1.5
  - [ ] R:R < 1.5 → tier downgraded
  - [ ] Values[0] and Values[1] correctly populated for strategy consumption

  **QA Scenarios**:
  ```
  Scenario: Full decision pipeline — Elite Long
    Tool: Bash (dotnet test)
    Steps:
      1. Score=92, SetupType=Reversal, Direction=Long, PDL nearby=20000
      2. Current price=20005, nearest support=19995 (5 ticks), nearest target=20040 (35 ticks)
      3. Assert Action=Long, StopPrice=19993 (support - 2 ticks), TargetPrice=20040
      4. Assert R:R = 35/12 ≈ 2.9:1
    Expected Result: Clean Elite Long decision with favorable R:R
    Evidence: .sisyphus/evidence/task-21-elite-long.txt

  Scenario: R:R too low downgrades tier
    Tool: Bash (dotnet test)
    Steps:
      1. Score=85 (High), but nearest support 15 ticks away, target 20 ticks → R:R 1.33
      2. Assert tier downgraded from High to Moderate
    Expected Result: Tier downgraded due to poor R:R
    Evidence: .sisyphus/evidence/task-21-rr-downgrade.txt
  ```

  **Commit**: YES (groups with Wave 4)

### Wave 5: Rendering (MAX PARALLEL After Wave 4)

- [x] 22. Level Zone Rendering (SharpDX)

  **What to do**:
  - In `MADConfluenceAI.Rendering.cs`, implement level zone visualization:
  - **OnRenderTargetChanged**: Create and cache SharpDX brushes for each level type:
    - PDH/PDL: Red/Green with 30% opacity fill
    - VWAP bands: Blue with decreasing opacity (1σ=25%, 2σ=15%, 3σ=10%)
    - VP POC: Yellow solid line, VAH/VAL: Yellow dashed
    - Opening range: Purple zone
    - Session H/L: White dashed
    - Psychological: Gray dotted
  - **OnRender**: For each visible level within chart price range:
    - Draw zone rectangle (±1 tick height) with type-specific color
    - Draw label text (e.g., "PDH 20100") at right edge
    - Level quality affects opacity: higher quality = more opaque
  - **Visibility guard**: Only render if `ShowLevelZones == true`
  - **Performance**: Skip levels outside visible chart range, maximum 50 rendered levels

  **Must NOT do**:
  - Do NOT use Draw.* methods — SharpDX OnRender only
  - Do NOT recreate brushes on every OnRender call — cache in OnRenderTargetChanged
  - Do NOT render more than 50 levels simultaneously

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T23-T26)
  - **Blocks**: T27
  - **Blocked By**: T5, T21

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:OnRender` — SharpDX rendering pattern: brush caching, chart coordinate conversion, text layout
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:OnRenderTargetChanged` — Brush creation/disposal lifecycle
  - `ninjatrader/Custom/AddOns/DEEP6/Levels/ProfileAnchorLevels.cs` — How levels are drawn on chart

  **WHY Each Reference Matters**:
  - `DEEP6Footprint.cs:OnRender`: The proven SharpDX rendering loop — coordinate conversion (ChartControl.GetXByBarIndex, ChartScale.GetYByValue), text layout creation, dispose patterns. MUST follow this exactly to avoid GDI leaks
  - `OnRenderTargetChanged`: Critical lifecycle hook — brushes MUST be created here, not in OnRender. Missing this causes crashes on RenderTarget changes (monitor switch, DPI change)

  **Acceptance Criteria**:
  - [ ] Level zones render with correct colors per type
  - [ ] Labels display at right edge with level name and price
  - [ ] Visibility toggle correctly hides/shows all level zones
  - [ ] No SharpDX brush leak (Dispose in OnRenderTargetChanged and Terminated)
  - [ ] Performance: render 50 levels without chart lag

  **QA Scenarios**:
  ```
  Scenario: Level zones render on NQ chart
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1)
    Steps:
      1. Deploy indicator to NT8
      2. Compile successfully
      3. Add to NQ 1-min chart
      4. Verify no SharpDX exceptions in Output window
    Expected Result: Indicator loads and renders without error
    Failure Indicators: SharpDX.SharpDXException, NullReferenceException in OnRender
    Evidence: .sisyphus/evidence/task-22-level-render.png (screenshot)
  ```

  **Commit**: YES (groups with Wave 5)
  - Message: `feat(mad): implement SharpDX rendering — levels, markers, dashboard, heatmap`

- [x] 23. Signal Markers (Arrows, Dots, Sweep Lines)

  **What to do**:
  - In `MADConfluenceAI.Rendering.cs`, render signal markers on chart:
  - **Buy/Sell Arrows**: Triangle up (green) below bar for Long signals, triangle down (red) above bar for Short signals. Size proportional to confidence score (larger = higher score).
  - **Absorption Markers**: Cyan dots at the price level where absorption was detected. Dot size proportional to absorption strength.
  - **Exhaustion Markers**: Orange dots at exhaustion price levels.
  - **Sweep Lines**: Horizontal line from sweep point extending 3 bars to the right, with arrow showing reversal direction. Color: magenta.
  - **Imbalance Highlights**: Small colored rectangles on the footprint bar at imbalance levels (blue for ask-dominant, red for bid-dominant). Only on current bar + last 5 bars.
  - **Visibility guards**: Each marker type controlled by respective toggle (ShowSignalMarkers, ShowAbsorptionZones, ShowSweepMarkers, ShowImbalanceHighlights)

  **Must NOT do**:
  - Do NOT render markers on bars older than 50 bars back (performance)
  - Do NOT use Draw.ArrowUp/Down — use SharpDX triangle paths

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5
  - **Blocks**: T27
  - **Blocked By**: T21

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:OnRender` — Signal marker rendering (cyan triangles for absorption, yellow/orange arrows for exhaustion)

  **Acceptance Criteria**:
  - [ ] Buy/sell arrows render at correct positions relative to bar
  - [ ] Arrow size scales with confidence score
  - [ ] Absorption dots render at correct price levels
  - [ ] Visibility toggles work independently for each marker type
  - [ ] Maximum 50 bars of markers rendered (performance cap)

  **QA Scenarios**:
  ```
  Scenario: Signal markers render without crash
    Tool: Bash (nt8-compile.ps1)
    Steps:
      1. Deploy + compile
      2. Add to chart with known signal conditions
      3. Verify no exceptions in Output window
    Expected Result: Markers render, no exceptions
    Evidence: .sisyphus/evidence/task-23-markers.png
  ```

  **Commit**: YES (groups with Wave 5)

- [x] 24. Confidence Dashboard (Score, Tier, Category Breakdown)

  **What to do**:
  - In `MADConfluenceAI.Rendering.cs`, render an overlay dashboard panel:
  - **Position**: Top-right corner of chart (configurable), semi-transparent background
  - **Dashboard Elements**:
    - **Score Display**: Large number (0-100) with color: Green (≥75), Yellow (60-74), Orange (40-59), Red (<40)
    - **Tier Badge**: "ELITE" / "HIGH" / "MOD" / "WAIT" / "DNT" with corresponding color
    - **Action Display**: "LONG" / "SHORT" / "WAIT" / "DO NOT TRADE" in large text
    - **Setup Type**: Current setup classification (e.g., "Reversal" / "Absorption Bounce")
    - **Category Breakdown**: 7 small bars showing contribution of each signal category (Abs, Exh, Dlt, Imb, Ice, Liq, Trp) with fill proportional to signal strength
    - **Regime Badge**: "TREND" / "RANGE" / "VOL" / "THIN" indicator
    - **Session Info**: RTH/ETH, time, ATR
  - **Background**: Dark semi-transparent rectangle behind all dashboard elements
  - **Visibility**: Controlled by `ShowDashboard` toggle

  **Must NOT do**:
  - Do NOT make dashboard cover more than 25% of chart area
  - Do NOT animate dashboard elements (no transitions — instant updates)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5
  - **Blocks**: T27
  - **Blocked By**: T19, T21

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs:OnRender` — HUD rendering with SharpDX: background panel, text layout, corner positioning

  **Acceptance Criteria**:
  - [ ] Dashboard renders in top-right corner
  - [ ] Score number updates per bar
  - [ ] Tier badge shows correct color
  - [ ] Category breakdown shows 7 bars
  - [ ] Toggle hides entire dashboard

  **QA Scenarios**:
  ```
  Scenario: Dashboard displays all elements
    Tool: Bash (nt8-compile.ps1)
    Steps:
      1. Deploy + compile + add to chart
      2. Verify dashboard visible with score, tier, action, setup type, regime
    Expected Result: All dashboard elements visible and formatted
    Evidence: .sisyphus/evidence/task-24-dashboard.png
  ```

  **Commit**: YES (groups with Wave 5)

- [x] 25. SL/TP Projection + R:R Display

  **What to do**:
  - In `MADConfluenceAI.Rendering.cs`, render trade projection when action is LONG or SHORT:
  - **Entry Zone**: Highlighted current price zone (±1 tick, semi-transparent green/red background)
  - **Stop Loss Line**: Horizontal dashed red line at calculated StopPrice. Label: "SL: {price} ({ticks} ticks)"
  - **Take Profit Line**: Horizontal dashed green line at calculated TargetPrice. Label: "TP: {price} ({ticks} ticks)"
  - **R:R Label**: Text showing "R:R {ratio}:1" between entry and SL/TP
  - **Risk Zone**: Semi-transparent red rectangle between entry and SL
  - **Reward Zone**: Semi-transparent green rectangle between entry and TP
  - Only render when decision Action is Long or Short (not WAIT/DNT)
  - Visibility: `ShowSlTp` toggle

  **Must NOT do**:
  - Do NOT draw SL/TP if action is WAIT or DO NOT TRADE

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5
  - **Blocks**: T27
  - **Blocked By**: T21

  **Acceptance Criteria**:
  - [ ] SL/TP lines render at correct prices
  - [ ] Risk/reward zones correctly colored
  - [ ] R:R label shows correct ratio
  - [ ] Hidden when action is WAIT/DNT
  - [ ] Toggle works correctly

  **QA Scenarios**:
  ```
  Scenario: SL/TP renders for Long signal
    Tool: Bash (nt8-compile.ps1)
    Steps:
      1. Ensure indicator produces Long action with SL/TP calculated
      2. Verify green entry zone, red SL line below, green TP line above
    Expected Result: Complete trade projection visible
    Evidence: .sisyphus/evidence/task-25-sltp.png
  ```

  **Commit**: YES (groups with Wave 5)

- [x] 26. Delta Heatmap + Visibility Toggle System

  **What to do**:
  - In `MADConfluenceAI.Rendering.cs`, implement two final visual components:
  - **Delta Heatmap**: For the last 20 bars, color each price level's background based on delta intensity:
    - Green (buy dominant): intensity proportional to positive delta / max delta in bar
    - Red (sell dominant): intensity proportional to negative delta / max delta in bar
    - Opacity: 20-60% (light enough to see candles through)
    - Cell size: 1 tick height × bar width
    - Only render levels between bar's High and Low
  - **Master Visibility Toggle System**: Implement `UpdateVisibility()` method called in OnRender:
    - Check each toggle (ShowLevelZones, ShowSignalMarkers, ShowDashboard, ShowHeatmap, ShowSlTp, ShowAbsorptionZones, ShowSweepMarkers, ShowImbalanceHighlights)
    - Skip rendering for disabled layers (early return in each section)
    - Render budget: if total OnRender time exceeds 12ms (targeting 60fps with margin), skip lowest-priority layers (heatmap first, then imbalance highlights)
  - **Performance monitoring**: Track OnRender time with Stopwatch. If average > 8ms over last 10 frames, auto-disable heatmap

  **Must NOT do**:
  - Do NOT render heatmap for more than 20 bars (performance)
  - Do NOT render at > 60 FPS — throttle to 8Hz (125ms minimum between renders)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5
  - **Blocks**: T27
  - **Blocked By**: T7, T21

  **References**:
  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:OnRender` — Per-cell footprint rendering with delta-based coloring. This is the exact pattern needed for the heatmap

  **Acceptance Criteria**:
  - [ ] Heatmap colors correctly (green=buy, red=sell) with intensity proportional to delta
  - [ ] Only last 20 bars rendered
  - [ ] All 8 visibility toggles independently control their layer
  - [ ] Render budget: auto-disable heatmap if OnRender > 8ms average
  - [ ] 8Hz throttle (no renders within 125ms of each other)

  **QA Scenarios**:
  ```
  Scenario: Heatmap renders with correct colors
    Tool: Bash (nt8-compile.ps1)
    Steps:
      1. Deploy + compile + add to chart
      2. Verify green cells at buy-dominant levels, red at sell-dominant
      3. Verify candles visible through semi-transparent heatmap
    Expected Result: Heatmap visible, candles readable
    Evidence: .sisyphus/evidence/task-26-heatmap.png

  Scenario: Visibility toggles work
    Tool: Bash (nt8-compile.ps1)
    Steps:
      1. Toggle ShowHeatmap=false
      2. Verify heatmap disappears but levels/markers/dashboard remain
      3. Toggle ShowDashboard=false
      4. Verify dashboard disappears
    Expected Result: Independent toggle control
    Evidence: .sisyphus/evidence/task-26-toggles.png
  ```

  **Commit**: YES (groups with Wave 5)

### Wave 6: Integration & Polish (After Wave 5)

- [x] 27. Integration Test Suite

  **What to do**:
  - Create `ninjatrader/tests/MADConfluenceAI/IntegrationTests.cs`:
  - **Full Lifecycle Test**: Simulate 100 bars through MADConfluenceAI:
    - Create NinjaScriptRunner-style lifecycle (SetDefaults → Configure → DataLoaded → Historical → Realtime)
    - Feed 100 bars with known data (mix of absorption setups, exhaustion, sweeps, trending bars, choppy bars)
    - Assert: at least 3 signals fire, at least 1 Elite/High setup detected, at least 1 DO NOT TRADE during chop
  - **Scoring Parity Test**: Feed identical signal combinations and assert exact score matches for 10 known scenarios
  - **Edge Case Tests**:
    - First bar (insufficient history) → no signals, WAIT
    - Session rollover → prior day levels captured, session state reset
    - All 12 detectors produce signals simultaneously → scoring handles without crash
    - Empty bar (zero volume) → graceful handling, WAIT
    - NQ-specific: tick size 0.25 used throughout calculations
  - **Cross-Component Test**: Verify data flows correctly from Data → Signals → Scoring → Decision

  **Must NOT do**:
  - Do NOT test rendering in integration tests (separate concern, verified via deployment)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 6 (with T28, T29, T30)
  - **Blocks**: T28, T29, T30
  - **Blocked By**: T22-T26

  **References**:
  **Test References**:
  - `ninjatrader/tests/Strategy/DEEP6StrategySimulatorTests.cs` — Full lifecycle simulation pattern
  - `ninjatrader/simulator/Lifecycle/NinjaScriptRunner.cs` — NinjaScript lifecycle runner

  **Acceptance Criteria**:
  - [ ] 100-bar lifecycle test passes
  - [ ] Scoring parity: 10 known scenarios produce expected scores ± 0.01
  - [ ] All edge cases handled gracefully (no exceptions)
  - [ ] `dotnet test --filter "Integration"` → ALL PASS

  **QA Scenarios**:
  ```
  Scenario: Full 100-bar integration
    Tool: Bash (dotnet test)
    Steps:
      1. Run `dotnet test --filter "MADConfluenceAI.Integration"`
      2. Assert all tests pass
    Expected Result: ALL PASS
    Evidence: .sisyphus/evidence/task-27-integration.txt
  ```

  **Commit**: YES (groups with Wave 6)
  - Message: `feat(mad): integration tests, performance profiling, historical mode, deploy verification`

- [x] 28. Performance Profiling + Hot Path Optimization

  **What to do**:
  - Create `ninjatrader/tests/MADConfluenceAI/PerformanceTests.cs`:
  - **OnBarUpdate Latency Test**: Simulate 500 bars with realistic tick data. Measure Stopwatch elapsed per OnBarUpdate call. Assert: average < 2ms, 99th percentile < 5ms.
  - **OnMarketData Latency Test**: Simulate 10,000 ticks. Measure per-tick processing time. Assert: average < 0.5ms.
  - **Memory Allocation Test**: Use GC.GetAllocatedBytesForCurrentThread() before/after 1000 OnMarketData calls. Assert: < 1KB per call (minimal allocation).
  - **Optimization pass**: If any threshold exceeded, profile and optimize:
    - Replace dictionary lookups with array indexing where price range is known
    - Pre-compute expensive calculations in Finalize() not in detector methods
    - Cache Z-score lookups instead of recomputing per detector

  **Must NOT do**:
  - Do NOT micro-optimize before measuring — profile first
  - Do NOT add caching that changes signal results (correctness > speed)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 6
  - **Blocks**: T30
  - **Blocked By**: T27

  **Acceptance Criteria**:
  - [ ] OnBarUpdate < 2ms average
  - [ ] OnMarketData < 0.5ms average
  - [ ] Memory allocation < 1KB per tick
  - [ ] `dotnet test --filter "Performance"` → ALL PASS

  **QA Scenarios**:
  ```
  Scenario: Performance within budget
    Tool: Bash (dotnet test)
    Steps:
      1. Run performance tests
      2. Assert all latency/memory assertions pass
    Expected Result: ALL PASS
    Evidence: .sisyphus/evidence/task-28-performance.txt
  ```

  **Commit**: YES (groups with Wave 6)

- [x] 29. Historical Mode (Graceful DOM Degradation + Warm-up)

  **What to do**:
  - In `MADConfluenceAI.Data.cs` and `MADConfluenceAI.Signals.cs`:
  - **Historical Mode Detection**: Set `_isHistorical = true` until first OnMarketDepth call (then `false`)
  - **DOM Signal Degradation**: When historical:
    - ICE-01 (Iceberg) → returns empty (no DOM data available)
    - DOM imbalance → returns neutral (1.0)
    - Liquidity walls → returns empty
    - All other detectors work normally (they use footprint bar data, not DOM)
  - **Warm-up Period**: First `WarmupBars` bars (default 50) → suppress all signals and decisions. Reason: ATR, CVD, value area need history to be meaningful.
  - **Indicator Status**: During warm-up, dashboard shows "WARMING UP ({N} bars remaining)" instead of score
  - Test: load indicator on 500-bar historical chart → no crash, warm-up displays, then normal operation

  **Must NOT do**:
  - Do NOT crash or throw when OnMarketDepth is never called (historical mode)
  - Do NOT output signals during warm-up period

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 6
  - **Blocks**: T30
  - **Blocked By**: T27

  **Acceptance Criteria**:
  - [ ] ICE-01 returns empty on historical bars (no crash)
  - [ ] DOM methods return defaults when _isHistorical == true
  - [ ] First 50 bars show "WARMING UP" in dashboard
  - [ ] Bar 51+ shows normal scores
  - [ ] 500-bar historical load completes without exception

  **QA Scenarios**:
  ```
  Scenario: Historical mode doesn't crash
    Tool: Bash (dotnet test)
    Steps:
      1. Simulate 500 bars without any OnMarketDepth calls
      2. Assert zero exceptions
      3. Assert ICE-01 never fires
      4. Assert other detectors fire normally after warm-up
    Expected Result: Graceful degradation
    Evidence: .sisyphus/evidence/task-29-historical.txt
  ```

  **Commit**: YES (groups with Wave 6)

- [x] 30. Deploy + Compile Verification + Chart Load Test

  **What to do**:
  - **Run full test suite**: `dotnet test ninjatrader/tests/ --filter "MADConfluenceAI"` — assert ALL PASS
  - **Deploy to NT8**: Run `nt8-deploy.ps1` — verify all 5 .cs files copied to NT8 Custom/Indicators/DEEP6/MADConfluenceAI/
  - **Compile in NT8**: Run `nt8-compile.ps1` — assert `[COMPILE-RESULT] SUCCESS`
  - **Chart Load Test**: Add MADConfluenceAI to NQ 1-minute chart:
    - Verify indicator loads without error
    - Verify it processes 500+ historical bars (warm-up → normal operation)
    - Verify dashboard appears with score
    - Verify level zones render
    - Verify no exceptions in NT8 Output window
    - Take screenshot evidence
  - **File Size Verification**: Assert no .cs file exceeds 1,500 lines
  - **Parameter Count Verification**: Assert ≤30 NinjaScriptProperty attributes
  - **AddOn Reference Check**: Grep for `AddOns.DEEP6` — assert zero matches

  **Must NOT do**:
  - Do NOT proceed to Final Verification if compile fails — fix first

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (last in Wave 6)
  - **Blocks**: F1-F4
  - **Blocked By**: T28, T29

  **Acceptance Criteria**:
  - [ ] `dotnet test --filter "MADConfluenceAI"` → ALL PASS (every single test)
  - [ ] `nt8-deploy.ps1` → 5 files deployed
  - [ ] `nt8-compile.ps1` → `[COMPILE-RESULT] SUCCESS`
  - [ ] Indicator loads on NQ chart without error
  - [ ] Dashboard visible with score after warm-up period
  - [ ] No file > 1,500 lines
  - [ ] ≤ 30 NinjaScriptProperty attributes
  - [ ] Zero references to NinjaTrader.NinjaScript.AddOns.DEEP6

  **QA Scenarios**:
  ```
  Scenario: Full deployment pipeline
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1)
    Steps:
      1. dotnet test --filter "MADConfluenceAI" → capture output
      2. nt8-deploy.ps1 → capture output
      3. nt8-compile.ps1 → capture output
      4. Assert all three succeed
    Expected Result: Tests pass, deploy succeeds, compile succeeds
    Evidence: .sisyphus/evidence/task-30-deploy.txt

  Scenario: Guardrail verification
    Tool: Bash (grep + wc)
    Steps:
      1. For each of 5 .cs files: count lines → assert < 1500
      2. Count NinjaScriptProperty attributes → assert ≤ 30
      3. Grep for "AddOns.DEEP6" → assert 0 matches
    Expected Result: All guardrails pass
    Evidence: .sisyphus/evidence/task-30-guardrails.txt
  ```

  **Commit**: YES (final commit before verification)
  - Message: `feat(mad): integration tests, performance profiling, historical mode, deploy verification`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run test command). For each "Must NOT Have": search codebase for forbidden patterns (AddOns.DEEP6 references, NuGet packages, files >1500 lines, object allocations in hot path, Draw.* calls in hot path). Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `dotnet test ninjatrader/tests/` + `nt8-compile.ps1`. Review all 5 partial class files for: `as any`/cast abuse, empty catches, Console.Write in prod code, commented-out code, unused using directives. Check AI slop: excessive comments, over-abstraction (no AbstractBaseDetectorFactory), generic names (data/result/item/temp), unnecessary interfaces. Verify thread safety: all shared state has `lock()`, no allocations in OnMarketData.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `nt8-expert` skill)
  Deploy to NinjaTrader 8 via `nt8-deploy.ps1` + `nt8-compile.ps1`. Add MADConfluenceAI to NQ 1-minute chart. Verify: indicator loads without error, processes historical bars (500+), transitions to real-time, displays confidence score, shows level zones, signal markers appear on known patterns, visibility toggles work, no SharpDX exceptions in Output window. Screenshot evidence for each check.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual implementation. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT Have" compliance: no DEEP6 AddOn references, no NuGet, no files >1500 lines, no HMM, no alerts/sounds. Verify exactly 12 detectors implemented (no more, no fewer). Count user-facing parameters (must be ≤30). Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Detectors [12/12] | Params [N/30] | Creep [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Wave | Commit | Files | Pre-commit |
|------|--------|-------|-----------|
| 1 | `feat(mad): scaffold MADConfluenceAI indicator with core types and test infra` | MADConfluenceAI.cs, .Data.cs (types only), .Signals.cs (empty), .Scoring.cs (empty), .Rendering.cs (empty), test project files | `dotnet build` |
| 2 | `feat(mad): implement data pipeline — footprint bars, DOM state, volume profile, delta` | .Data.cs (full), test fixtures | `dotnet test` |
| 3 | `feat(mad): implement 12 signal detectors with TDD coverage` | .Signals.cs (full), test fixtures per detector | `dotnet test` |
| 4 | `feat(mad): implement confluence scoring, setup classification, and trade filtering` | .Scoring.cs (full), MADConfluenceAI.cs (orchestration), test fixtures | `dotnet test` |
| 5 | `feat(mad): implement SharpDX rendering — levels, markers, dashboard, heatmap` | .Rendering.cs (full) | `dotnet build` + `nt8-compile.ps1` |
| 6 | `feat(mad): integration tests, performance profiling, historical mode, deploy verification` | test files, .Data.cs (historical fallback) | `dotnet test` + `nt8-compile.ps1` |

---

## Success Criteria

### Verification Commands
```bash
dotnet test ninjatrader/tests/ --filter "MADConfluenceAI"  # Expected: ALL PASS
powershell ninjatrader/scripts/nt8-deploy.ps1              # Expected: all files copied
powershell ninjatrader/scripts/nt8-compile.ps1              # Expected: [COMPILE-RESULT] SUCCESS
```

### Final Checklist
- [ ] All 12 detectors implemented and tested (ABS-01, ABS-02, EXH-01, EXH-02, DELT-01, DELT-02, IMB-01, ICE-01, LIQSW-01, FAIL-01, TRAP-01, REG-01)
- [ ] Confluence scoring produces correct tier: Elite (90-100), High (75-89), Moderate (60-74), Avoid (<60)
- [ ] Setup classifier identifies all 7 types correctly
- [ ] LONG/SHORT/WAIT/DO NOT TRADE decision logic with SL/TP
- [ ] Level Quality engine calculates PDH/PDL, VWAP bands, VP POC/VAH/VAL, opening range, session H/L, psychological levels
- [ ] SharpDX rendering: level zones, signal markers, confidence dashboard, heatmap, SL/TP projection
- [ ] All visual layers have visibility toggles
- [ ] No file exceeds 1,500 lines
- [ ] No references to NinjaTrader.NinjaScript.AddOns.DEEP6.*
- [ ] ≤30 user-facing parameters
- [ ] OnBarUpdate < 2ms, OnMarketData < 0.5ms
- [ ] Indicator loads on NQ chart with 500+ historical bars without crash
- [ ] Zero SharpDX exceptions in NT8 Output window
- [ ] All tests pass: `dotnet test` AND `nt8-compile.ps1` SUCCESS
