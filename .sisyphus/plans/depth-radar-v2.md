# Deep Six Depth Radar v2 — Intelligent DOM Wall Classification

## TL;DR

> **Quick Summary**: Upgrade the DEEP6 Depth Radar from a passive DOM visualizer into an intelligent wall classification system with price-aware freshness, rule-based spoof detection, and ML-powered wall classification (GENUINE/SPOOF/ICEBERG/STALE) — all color-coded on the NinjaTrader chart.
> 
> **Deliverables**:
> - `DEEP6DepthRadarV2.cs` — standalone NinjaTrader indicator with 4-color classification rendering
> - Rule-based spoof detection engine (C#, zero Python dependency)
> - Price-aware order freshness scoring (detects when price trades through a level)
> - Python ML service for wall classification via LightGBM (reusing existing infrastructure)
> - IPC integration via extended DataBridgeServer for ML classification delivery
> - Direction + confidence prediction (Phase C stretch goal, TLOB only if LightGBM ceiling hit)
> 
> **Estimated Effort**: Large (3 gated phases)
> **Parallel Execution**: YES — 5 waves across 3 phases
> **Critical Path**: T1 → T3 → T5 → T6 → Gate A → T10 → T12 → T13 → Gate B → T17

---

## Context

### Original Request
Build a v2 of the Deep Six Depth Radar indicator with three enhancements: (1) order freshness scoring to filter stale orders that price has traded through, (2) spoofing detection and filtration, (3) ML/AI to learn order patterns and identify high-probability setups. v1 must remain untouched.

### Interview Summary
**Key Discussions**:
- User currently "guesses" when watching DOM walls — no formal setup definition. ML will replace intuitive pattern-matching with systematic classification.
- Architecture: NinjaTrader C# indicator + Python ML service via IPC. Fully standalone (not wired into DetectorRegistry).
- Visual: Same line-based rendering as v1 but color-coded by classification — GENUINE=green, SPOOF=red, ICEBERG=blue, STALE=gray.
- Hardware: RTX 3060 for ML inference (~100ms estimated).
- Training data: 1 month Databento MBO NQ (minimum viable).
- Tests after implementation using existing NinjaTrader.Stubs.

**Research Findings**:
- Spoofing detection consensus: Six-filter framework (cancellation ratio >95%, time-in-book <500ms, order size >5× avg). Hawkes process for self-excitation. ML models achieving F1 0.95+.
- ML architectures: TLOB (dual attention), LightGBM (existing pipeline in codebase). TLOB designed for mid-price prediction; LightGBM may be better fit for wall classification.
- IPC: Named pipes <1ms, TCP 1-5ms. DataBridgeServer.cs already runs TCP NDJSON on port 9200 — proven infrastructure.

### Metis Review
**Identified Gaps** (addressed):

- **Existing IPC infrastructure ignored**: DataBridgeServer.cs + bridge_client.py already provide TCP NDJSON IPC. → Plan now reuses/extends this instead of building new.
- **Existing Databento reconstruction ignored**: databento_live.py + mbo_adapter.py already reconstruct order books from MBO. → Plan now reuses these.
- **TLOB may be wrong architecture**: TLOB designed for LOB→price prediction, not wall classification. → Plan now starts with LightGBM (existing pipeline), TLOB only as Phase C upgrade if LightGBM ceiling is hit.
- **No graceful degradation**: What happens when Python ML service is down? → Plan now requires rule-based classification in C# that works with zero Python dependency (Phase A).
- **Latency defeats spoof detection**: Spoofs cancel in 200-500ms; ML inference takes 100ms+ → Rule-based spoof detection runs in C# hot path (<1ms). ML is additive/confirmatory.
- **Dual codebase state divergence**: C# and Python both process DOM data. → C# is single source of truth for wall state; Python receives wall snapshots for classification, doesn't maintain independent DOM state.
- **No accuracy exit criteria for ML**: → Binary SPOOF detection must achieve F1 > 0.80 before progressing to 4-class.
- **Insufficient spoof training data**: 1 month may have too few spoof events. → Start with synthetic + real data; use class weighting and oversampling.

---

## Work Objectives

### Core Objective
Transform the Depth Radar from a passive DOM liquidity visualizer into an intelligent wall classification system that automatically identifies genuine walls, spoofs, icebergs, and stale levels — first through rule-based heuristics (immediate value), then enhanced by ML (systematic accuracy).

### Concrete Deliverables
- `DEEP6DepthRadarV2.cs` — standalone C# indicator with 4-color classification
- `L2LevelStateV2` — enhanced per-level state with classification, freshness, spoof scoring
- Rule-based classification engine — works Day 1 with zero Python dependency
- Extended DataBridgeServer — bidirectional IPC for ML classifications
- Python wall classification service — LightGBM on existing feature infrastructure
- Retrospective labeling pipeline — automated from Databento MBO replay
- Unit tests for C# components + Python ML pipeline

### Definition of Done
- [ ] v2 compiles in NT8 NinjaScript Editor with zero errors
- [ ] v2 renders color-coded walls on live NQ chart within 10 seconds of loading
- [ ] v1 and v2 run simultaneously on same chart for 30 minutes without crash
- [ ] Rule-based spoof detection flags synthetic spoofs in unit tests
- [ ] Python ML service responds to health check within 100ms
- [ ] IPC round-trip p99 < 50ms (1000 round-trip timing test)
- [ ] Binary SPOOF classifier achieves F1 > 0.80 on hold-out test set
- [ ] Graceful degradation: kill Python service → indicator continues rendering in rule-based mode within 5s

### Must Have
- Separate indicator file (v2). v1 untouched.
- 4-color classification: GENUINE=green, SPOOF=red, ICEBERG=blue, STALE=gray
- Price-aware freshness (detect price trading through a resting level)
- Rule-based spoof detection in C# hot path (<1ms latency)
- Works standalone without Python service (graceful degradation)
- Unit tests using existing NinjaTrader.Stubs

### Must NOT Have (Guardrails)
- **DO NOT** modify `DEEP6DepthRadar.cs` (v1) — verify with `ast_grep_search` after each wave
- **DO NOT** wire into `DetectorRegistry`, `SessionContext`, or `ConfluenceScorer` — fully standalone
- **DO NOT** rebuild Databento MBO order book reconstruction — reuse `databento_live.py` and `mbo_adapter.py`
- **DO NOT** rebuild IPC from scratch — extend existing `DataBridgeServer.cs`
- **DO NOT** add volume profile overlays, delta panels, or features beyond the spec
- **DO NOT** attempt 4-class ML classification until binary SPOOF achieves F1 > 0.80
- **DO NOT** use TLOB architecture unless LightGBM ceiling is demonstrated with evidence
- **DO NOT** add emojis to code or comments
- **DO NOT** use "visually confirm" as acceptance criteria — use programmatic assertions or screenshot capture

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES — `ninjatrader/tests/ninjatrader.tests.csproj` (net8.0), NinjaTrader.Stubs simulator, JSON fixtures
- **Automated tests**: Tests after implementation
- **Framework**: dotnet test (C#), pytest (Python)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **C# Indicator**: Compile via `nt8-compile.ps1`, verify output, screenshot chart
- **Python Service**: pytest + curl health check + timing harness
- **IPC**: Automated round-trip latency measurement
- **ML Model**: Training metrics output, F1/precision/recall on hold-out set

---

## Execution Strategy

### Three-Phase Architecture with Gates

> Each phase delivers independent value. Phase A works alone. Phase B upgrades Phase A. Phase C is a stretch goal.

```
PHASE A — Rule-Based v2 (C# only, zero Python dependency)
├── Wave 1 (Foundation — 4 tasks, parallel):
│   ├── T1: Create DEEP6DepthRadarV2.cs skeleton [quick]
│   ├── T2: Define WallClassification enum + L2LevelStateV2 [quick]
│   ├── T3: Order lifecycle tracker (per-order event history) [deep]
│   └── T4: Price-crossing detector (detect when price trades through level) [quick]
│
├── Wave 2 (Core Logic + Rendering — 5 tasks, parallel after Wave 1):
│   ├── T5: Rule-based spoof scoring engine [deep]
│   ├── T6: Price-aware freshness scoring [quick]
│   ├── T7: Classification priority resolver [quick]
│   ├── T8: 4-color rendering with classification-based glow [visual-engineering]
│   └── T9: Enhanced HUD + Phase A unit tests [unspecified-high]
│
└── GATE A: v2 compiles, renders, classifies by rules, v1 untouched, tests pass

PHASE B — ML Classification Service (Python + IPC)
├── Wave 3 (ML Pipeline — 5 tasks, parallel):
│   ├── T10: Retrospective wall labeling from MBO replay [deep]
│   ├── T11: Wall feature engineering (extend feature_builder.py) [unspecified-high]
│   ├── T12: LightGBM wall classifier (binary SPOOF first) [deep]
│   ├── T13: Extend DataBridgeServer for classification messages [unspecified-high]
│   └── T14: Python classification service + health endpoint [unspecified-high]
│
├── Wave 4 (Integration — 4 tasks, parallel after Wave 3):
│   ├── T15: v2 IPC client (receive + apply ML classifications) [unspecified-high]
│   ├── T16: Graceful degradation (fallback to rule-based) [quick]
│   ├── T17: 4-class classifier upgrade [deep]
│   └── T18: Phase B integration tests [unspecified-high]
│
└── GATE B: ML classifies walls, IPC delivers in <50ms, F1>0.80, graceful degradation works

PHASE C — Direction Prediction (Stretch Goal)
├── Wave 5 (Direction — 3 tasks):
│   ├── T19: Direction + confidence model [deep]
│   ├── T20: Direction overlay rendering + ML confidence HUD [visual-engineering]
│   └── T21: End-to-end integration test [unspecified-high]
│
└── GATE C: Direction predictions visible on chart, TLOB only if LightGBM ceiling hit

WAVE FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T5,T6,T7,T8,T9 | 1 |
| T2 | — | T3,T5,T7,T8 | 1 |
| T3 | T2 | T5 | 1 |
| T4 | — | T6 | 1 |
| T5 | T1,T2,T3 | T7,T9 | 2 |
| T6 | T1,T4 | T7,T9 | 2 |
| T7 | T2,T5,T6 | T8,T9 | 2 |
| T8 | T1,T2,T7 | T9 | 2 |
| T9 | T5,T6,T7,T8 | Gate A | 2 |
| T10 | Gate A | T12 | 3 |
| T11 | Gate A | T12 | 3 |
| T12 | T10,T11 | T15,T17 | 3 |
| T13 | Gate A | T15 | 3 |
| T14 | T12,T13 | T15,T16 | 3 |
| T15 | T13,T14 | T18 | 4 |
| T16 | T14,T15 | T18 | 4 |
| T17 | T12 (F1>0.80) | T18 | 4 |
| T18 | T15,T16,T17 | Gate B | 4 |
| T19 | Gate B | T20 | 5 |
| T20 | T19 | T21 | 5 |
| T21 | T19,T20 | Gate C | 5 |

### Agent Dispatch Summary

- **Wave 1**: **4 tasks** — T1 → `quick`, T2 → `quick`, T3 → `deep`, T4 → `quick`
- **Wave 2**: **5 tasks** — T5 → `deep`, T6 → `quick`, T7 → `quick`, T8 → `visual-engineering`, T9 → `unspecified-high`
- **Wave 3**: **5 tasks** — T10 → `deep`, T11 → `unspecified-high`, T12 → `deep`, T13 → `unspecified-high`, T14 → `unspecified-high`
- **Wave 4**: **4 tasks** — T15 → `unspecified-high`, T16 → `quick`, T17 → `deep`, T18 → `unspecified-high`
- **Wave 5**: **3 tasks** — T19 → `deep`, T20 → `visual-engineering`, T21 → `unspecified-high`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

### PHASE A — Rule-Based v2 (C# Only, Zero Python Dependency)

- [ ] 1. Create DEEP6DepthRadarV2 Indicator Skeleton

  **What to do**:
  - Copy `DEEP6DepthRadar.cs` to `DEEP6DepthRadarV2.cs` in the same directory
  - Rename class to `DEEP6DepthRadarV2`, update `Name` property to `"DEEP6 Depth Radar V2"`
  - Rename `Description` to distinguish from v1
  - Replace `L2LevelState` with `L2LevelStateV2` reference (Task 2 will define it)
  - Keep all v1 rendering and DOM intake logic intact as starting point — later tasks will modify
  - Verify the file compiles independently in NT8

  **Must NOT do**:
  - Modify `DEEP6DepthRadar.cs` (v1) in any way
  - Reference `DetectorRegistry`, `SessionContext`, or any signal engine types
  - Change namespace — keep `NinjaTrader.NinjaScript.Indicators.DEEP6`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Needed for NT8 indicator structure, NinjaScript state machine, compilation

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 5, 6, 7, 8, 9
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs` — v1 source. Copy this entire file. Understand every method before renaming.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:1-13` — Header comments describing carbon-copy relationship with FootprintV7. Update these for v2.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:41-47` — `L2LevelState` class. Will be replaced by `L2LevelStateV2` (Task 2).

  **WHY Each Reference Matters**:
  - v1 is the exact starting point. Every line must be understood to safely fork without breaking.
  - The header comments explain the v1→FootprintV7 relationship. v2 needs its own header explaining its relationship to v1.

  **Acceptance Criteria**:
  - [ ] File exists: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs`
  - [ ] Class name is `DEEP6DepthRadarV2`
  - [ ] v1 file `DEEP6DepthRadar.cs` has zero modifications: `git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs` returns empty

  **QA Scenarios**:

  ```
  Scenario: v2 file created with correct class name
    Tool: Bash (grep)
    Preconditions: DEEP6DepthRadarV2.cs exists
    Steps:
      1. grep "class DEEP6DepthRadarV2" ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs
      2. grep "DEEP6DepthRadar[^V]" ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs (should find zero class references to v1 name)
      3. git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs
    Expected Result: Class name found, no v1 class references, git diff empty
    Evidence: .sisyphus/evidence/task-1-skeleton-created.txt

  Scenario: v1 remains completely untouched
    Tool: Bash (git)
    Steps:
      1. git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs
    Expected Result: Empty output (zero changes)
    Failure Indicators: Any diff output means v1 was modified
    Evidence: .sisyphus/evidence/task-1-v1-integrity.txt
  ```

  **Commit**: YES (groups with T2, T3, T4 at Gate A)
  - Message: `feat(depth-radar): create v2 indicator skeleton`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs`

- [ ] 2. Define WallClassification Enum + L2LevelStateV2

  **What to do**:
  - Create a new file `DEEP6DepthRadarV2Types.cs` in the same indicator directory
  - Define `WallClassification` enum: `Unknown = 0, Genuine = 1, Spoof = 2, Iceberg = 3, Stale = 4`
  - Define `L2LevelStateV2` sealed class extending v1's `L2LevelState` concept with new fields:
    - All v1 fields: `CurrentSize` (long), `MaxSize` (long), `LastUpdate` (DateTime), `RefillCount` (int)
    - New: `Classification` (WallClassification) — current classification
    - New: `Confidence` (float, 0-1) — classification confidence
    - New: `LastClassificationTime` (DateTime) — when classification was last updated
    - New: `PriceTradedThrough` (bool) — whether price has crossed this level
    - New: `PriceCrossTime` (DateTime) — when price first crossed this level
    - New: `FirstSeenTime` (DateTime) — when this level first appeared on DOM
    - New: `ModificationCount` (int) — how many times this order has been modified
    - New: `OriginalSize` (long) — size when first placed
    - New: `CancellationEvents` (int) — times size dropped to zero then reappeared
    - New: `SpoofScore` (float, 0-100) — rule-based spoof score
    - New: `FreshnessScore` (float, 0-1) — freshness score (1=fresh, 0=stale)
    - New: `IsMLClassified` (bool) — whether ML has classified this level (false = rule-based only)
  - Define classification priority: SPOOF > STALE > ICEBERG > GENUINE (safety-first — flag risks before confirming quality)

  **Must NOT do**:
  - Modify v1's `L2LevelState` class
  - Add fields not listed above — no "bonus" tracking

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 type definition patterns, namespace conventions

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Tasks 3, 5, 7, 8
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:41-47` — v1's `L2LevelState`. Understand these 4 fields — v2 extends them.
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs` — Example of enum + data class pattern in DEEP6 codebase. Follow naming/style conventions.

  **WHY Each Reference Matters**:
  - v1's L2LevelState is the foundation — v2 must be a superset (all v1 fields + new ones)
  - SignalResult shows how the codebase structures enums and result types — match the style

  **Acceptance Criteria**:
  - [ ] File exists: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2Types.cs`
  - [ ] `WallClassification` enum has exactly 5 values: Unknown, Genuine, Spoof, Iceberg, Stale
  - [ ] `L2LevelStateV2` has all 15 fields listed above
  - [ ] No modifications to v1 files

  **QA Scenarios**:

  ```
  Scenario: Types file compiles and contains correct definitions
    Tool: Bash (grep + dotnet build)
    Steps:
      1. grep -c "enum WallClassification" ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2Types.cs
      2. grep -c "class L2LevelStateV2" ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2Types.cs
      3. grep "PriceTradedThrough\|SpoofScore\|FreshnessScore\|IsMLClassified\|Classification" ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2Types.cs
    Expected Result: 1 enum, 1 class, all 5 key fields present
    Evidence: .sisyphus/evidence/task-2-types-defined.txt

  Scenario: Classification priority order is correct
    Tool: Bash (grep)
    Steps:
      1. Check enum values: Unknown=0, Genuine=1, Spoof=2, Iceberg=3, Stale=4
    Expected Result: Priority documented in comments: SPOOF > STALE > ICEBERG > GENUINE
    Evidence: .sisyphus/evidence/task-2-priority-order.txt
  ```

  **Commit**: YES (groups at Gate A)
  - Message: `feat(depth-radar): define v2 types and classification enum`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2Types.cs`

- [ ] 3. Order Lifecycle Tracker (Per-Order Event History)

  **What to do**:
  - In `DEEP6DepthRadarV2.cs`, build an order lifecycle tracking system within `OnMarketDepth`:
    - Track per-price-level event history: when size first appeared, each modification (size change), each cancellation (size → 0), each reappearance
    - Compute per-level metrics in real-time:
      - `TimeInBook`: `DateTime.UtcNow - FirstSeenTime`
      - `ModificationCount`: increment on every size change that isn't a full cancel
      - `CancellationEvents`: increment when `CurrentSize` drops to 0 then reappears at same price
      - `OriginalSize`: capture size on first appearance
      - `CancelRatio`: `CancellationEvents / (CancellationEvents + 1)` (0 if never cancelled)
    - These metrics feed into `L2LevelStateV2` fields defined in Task 2
  - Use v1's existing lock pattern (`_l2Lock`) for thread safety
  - Keep allocation-free on hot path — no LINQ, no string allocation in `OnMarketDepth`

  **Must NOT do**:
  - Store full event history per level (memory explosion at 1,000 callbacks/sec). Only store aggregate metrics.
  - Break v1's threading model (lock → update → set dirty → timer invalidates)
  - Add new locks — reuse `_l2Lock`

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: OnMarketDepth threading model, MarketDepthEventArgs structure, lock patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES (but depends on T2 for type definitions)
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Task 5
  - **Blocked By**: Task 2 (needs L2LevelStateV2 type)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:120-190` — v1's `OnMarketDepth` handler. Study the lock pattern, dictionary update logic, iceberg detection, and prune cycle. v2 extends this, doesn't replace it.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:163-165` — v1's iceberg detection (50% refill threshold). v2 keeps this AND adds cancellation tracking.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:183-190` — v1's prune logic (30s cadence, 270s cutoff). v2 extends with classification-aware pruning.

  **API References**:
  - `MarketDepthEventArgs`: Properties — `MarketDataType` (bid/ask), `Price`, `Volume`, `Operation` (Insert/Update/Remove), `Position` (DOM level index)

  **WHY Each Reference Matters**:
  - OnMarketDepth is THE hot path (1,000 callbacks/sec). Every line added here affects system performance. Study v1's zero-allocation approach before modifying.
  - The iceberg detection shows how v1 tracks refills — v2 adds cancellation tracking using the same pattern.

  **Acceptance Criteria**:
  - [ ] `L2LevelStateV2` fields populated correctly: `FirstSeenTime`, `ModificationCount`, `CancellationEvents`, `OriginalSize` all updated in `OnMarketDepth`
  - [ ] Zero heap allocations on hot path (no new objects, no LINQ, no string formatting in `OnMarketDepth`)
  - [ ] Existing iceberg detection (RefillCount) still works identically to v1

  **QA Scenarios**:

  ```
  Scenario: Lifecycle metrics computed correctly from synthetic DOM events
    Tool: Bash (dotnet test)
    Preconditions: Unit test created with synthetic MarketDepthEventArgs sequence
    Steps:
      1. Create test: 5 events at price 21025 — appear(100 lots) → modify(150) → cancel(0) → reappear(120) → modify(80)
      2. Assert: FirstSeenTime = time of event 1, ModificationCount = 3, CancellationEvents = 1, OriginalSize = 100
      3. Run: dotnet test --filter "OrderLifecycleTracker"
    Expected Result: All assertions pass
    Evidence: .sisyphus/evidence/task-3-lifecycle-tracking.txt

  Scenario: No heap allocations on hot path
    Tool: Bash (grep)
    Steps:
      1. grep -n "new \|\.Select\|\.Where\|\.ToList\|\.ToArray\|string\." OnMarketDepth section of DEEP6DepthRadarV2.cs
    Expected Result: Zero matches within OnMarketDepth method body
    Failure Indicators: Any LINQ or object creation in the hot path
    Evidence: .sisyphus/evidence/task-3-allocation-free.txt
  ```

  **Commit**: YES (groups at Gate A)
  - Message: `feat(depth-radar): add order lifecycle tracking in v2`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs`

- [ ] 4. Price-Crossing Detector

  **What to do**:
  - In `DEEP6DepthRadarV2.cs`, add logic to `OnBarUpdate` (or `OnMarketData` for tick-level) that detects when the current price crosses a resting order level:
    - For each tracked bid level: if `Close` or `last trade price` drops below the bid price → set `PriceTradedThrough = true`, record `PriceCrossTime`
    - For each tracked ask level: if `Close` or `last trade price` rises above the ask price → set `PriceTradedThrough = true`, record `PriceCrossTime`
    - Once `PriceTradedThrough` is true, the level's `FreshnessScore` begins decaying rapidly
    - If the level survives the price cross (order still resting after price moved through), it may be behind the queue — mark as STALE after configurable timeout (default 30s post-cross)
  - Add configurable parameter: `StaleCrossTimeoutSec` (default 30) — seconds after price crosses a level before marking it STALE

  **Must NOT do**:
  - Check price crossing on every OnMarketDepth callback (too expensive at 1,000/sec). Use OnBarUpdate or a throttled check.
  - Remove levels immediately on price cross — they may still be valid (behind queue). Use timeout.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: OnBarUpdate vs OnMarketData, price comparison with tick size, NinjaScript property attributes

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 6
  - **Blocked By**: None (uses L2LevelStateV2 but can be coded against the interface)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:105-118` — v1's `OnBarUpdate`. Currently only does session reset. v2 adds price-crossing check here.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:314-322` — v1's wall filtering (size, staleness, visibility). v2 adds `PriceTradedThrough` filter.

  **WHY Each Reference Matters**:
  - OnBarUpdate is the right place for price-crossing checks — runs once per bar (not 1,000x/sec like OnMarketDepth). 
  - The existing filter logic shows where `PriceTradedThrough` status will be consumed during rendering.

  **Acceptance Criteria**:
  - [ ] Price crossing detected correctly for both bid and ask sides
  - [ ] `PriceTradedThrough` flag set with `PriceCrossTime` recorded
  - [ ] `StaleCrossTimeoutSec` configurable as NinjaScriptProperty
  - [ ] Levels not immediately removed on cross — timeout respected

  **QA Scenarios**:

  ```
  Scenario: Price crossing detected for bid wall
    Tool: Bash (dotnet test)
    Steps:
      1. Create test: bid wall at 21025.00 with size 100
      2. Simulate price dropping from 21026 to 21024 (crosses through bid wall)
      3. Assert: PriceTradedThrough = true, PriceCrossTime is set
      4. Simulate waiting 29 seconds: level still visible (not yet STALE)
      5. Simulate waiting 31 seconds: level marked STALE
    Expected Result: All assertions pass with correct timing
    Evidence: .sisyphus/evidence/task-4-price-crossing.txt

  Scenario: Ask wall price crossing
    Tool: Bash (dotnet test)
    Steps:
      1. Create test: ask wall at 21050.00 with size 200
      2. Simulate price rising from 21049 to 21051
      3. Assert: PriceTradedThrough = true
    Expected Result: Ask-side crossing detected correctly
    Evidence: .sisyphus/evidence/task-4-ask-crossing.txt
  ```

  **Commit**: YES (groups at Gate A)
  - Message: `feat(depth-radar): add price-crossing detector in v2`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs`

- [ ] 5. Rule-Based Spoof Scoring Engine

  **What to do**:
  - Create a `SpoofScorer` static class (or private method in v2) that computes a spoof score (0-100) per wall based on lifecycle metrics from Task 3:
    - **Cancellation ratio** (40 points): `CancellationEvents / (CancellationEvents + 1)` > 0.5 → 40 pts. Scaled linearly 0-40 from 0% to 95% cancel ratio.
    - **Time-in-book** (25 points): `TimeInBook` < 500ms at any cancellation → 25 pts. Scaled 0-25 from 5s to 500ms.
    - **Size anomaly** (20 points): `OriginalSize / AverageWallSize` > 5× → 20 pts. Scaled 0-20 from 1× to 5× average.
    - **Distance from inside market** (10 points): Price is > 10 ticks from current BBO → 10 pts. Scaled 0-10 from 1 to 10+ ticks.
    - **Modification frequency** (5 points): `ModificationCount / TimeInBook` > 10/sec → 5 pts. Scaled 0-5 from 0 to 10+/sec.
  - Score thresholds: `SpoofScore >= 70` → classify as SPOOF, `>= 40` → suspicious (show warning color), `< 40` → not spoof
  - Run scoring on prune cycle (30s cadence, matching v1) — NOT on every OnMarketDepth callback
  - Update `L2LevelStateV2.SpoofScore` and feed into Task 7's classification resolver

  **Must NOT do**:
  - Run scoring on the hot path (OnMarketDepth). Use the existing 30s prune cycle.
  - Compute average wall size per callback — cache it and update on prune cycle.
  - Use LINQ or allocations in the scoring path.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Threading constraints, NinjaScript timing, DOM data patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8, 9)
  - **Blocks**: Tasks 7, 9
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:183-190` — v1's prune cycle (30s cadence). Spoof scoring piggybacks on this cycle.
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/CounterSpoofDetector.cs` — Existing counter-spoof detector using Wasserstein-1 distance. Read for reference only — v2 is standalone, but the Wasserstein approach is interesting context for understanding DEEP6's existing spoof thinking.

  **External References**:
  - Spoofing six-filter framework (Do & Putniņš, 2023): cancellation ratio, time-in-book, size anomaly, distance from mid, imbalance impact, opposite-side execution. We implement 5 of 6 (skip imbalance impact — requires full book state).

  **WHY Each Reference Matters**:
  - The prune cycle is the right place for scoring — runs every 30s, not 1,000x/sec. Understand v1's pruning to know where to hook in.
  - CounterSpoofDetector shows DEEP6's existing thinking on spoof detection. v2 takes a different approach (lifecycle metrics vs Wasserstein distance) but should be aware of what exists.

  **Acceptance Criteria**:
  - [ ] SpoofScore computed correctly for each of 5 components
  - [ ] Threshold at 70 → SPOOF classification
  - [ ] Scoring runs on 30s prune cycle, not on hot path
  - [ ] Zero allocations in scoring path

  **QA Scenarios**:

  ```
  Scenario: Known spoof pattern scores high
    Tool: Bash (dotnet test)
    Steps:
      1. Create synthetic wall: size=500 (10× avg), placed 8 ticks from BBO, cancelled after 200ms, reappeared, cancelled again after 300ms
      2. Run SpoofScorer
      3. Assert: SpoofScore >= 70 (cancellation=40 + time-in-book=25 + size=16 = 81)
    Expected Result: SpoofScore >= 70, classified as SPOOF
    Evidence: .sisyphus/evidence/task-5-spoof-detection.txt

  Scenario: Genuine wall scores low
    Tool: Bash (dotnet test)
    Steps:
      1. Create synthetic wall: size=80 (1.6× avg), placed 2 ticks from BBO, resting for 45 seconds, 1 modification, 0 cancellations
      2. Run SpoofScorer
      3. Assert: SpoofScore < 40
    Expected Result: SpoofScore < 40, not classified as spoof
    Evidence: .sisyphus/evidence/task-5-genuine-passes.txt
  ```

  **Commit**: YES (groups at Gate A)
  - Message: `feat(depth-radar): add rule-based spoof scoring engine`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs`

- [ ] 6. Price-Aware Freshness Scoring

  **What to do**:
  - Create freshness scoring that combines time-based decay (v1's approach) with price-awareness (v2's innovation):
    - **Time decay** (exponential): `exp(-0.02 * minutes_since_last_update)` — half-life ~35 minutes
    - **Price-cross penalty**: If `PriceTradedThrough == true`, multiply freshness by `exp(-0.1 * seconds_since_cross)` — rapid decay after price crosses
    - **Modification penalty**: `exp(-0.05 * ModificationCount)` — heavily modified orders are less fresh
    - **Distance penalty**: `1 / (1 + 0.05 * ticks_from_BBO)` — orders far from inside market are less relevant
    - **Final formula**: `FreshnessScore = time_decay × price_cross_penalty × mod_penalty × distance_penalty`
    - Clamp to [0, 1]
  - Update `L2LevelStateV2.FreshnessScore` on the prune cycle (30s cadence)
  - Freshness < 0.1 → auto-classify as STALE regardless of other scores

  **Must NOT do**:
  - Compute freshness on every OnMarketDepth callback
  - Remove levels based on freshness alone — let the classification resolver (Task 7) handle it

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 7, 8, 9)
  - **Blocks**: Tasks 7, 9
  - **Blocked By**: Tasks 1, 4

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:314-322` — v1's freshness filter (`LastUpdate >= fresh`). v2 replaces this binary check with the continuous freshness score.
  - Task 4 output — `PriceTradedThrough` and `PriceCrossTime` fields drive the price-cross penalty.

  **Acceptance Criteria**:
  - [ ] FreshnessScore computed with all 4 components
  - [ ] Price-crossed levels decay rapidly (FreshnessScore < 0.1 within 30s of cross)
  - [ ] Un-crossed, recently-updated levels maintain FreshnessScore > 0.8
  - [ ] FreshnessScore < 0.1 triggers STALE classification

  **QA Scenarios**:

  ```
  Scenario: Fresh wall scores high
    Tool: Bash (dotnet test)
    Steps:
      1. Create wall: updated 5s ago, no price cross, 0 modifications, 2 ticks from BBO
      2. Compute FreshnessScore
      3. Assert: FreshnessScore > 0.85
    Expected Result: High freshness for recently updated, uncrossed wall
    Evidence: .sisyphus/evidence/task-6-fresh-wall.txt

  Scenario: Price-crossed wall decays rapidly
    Tool: Bash (dotnet test)
    Steps:
      1. Create wall: price crossed 20s ago, still resting
      2. Compute FreshnessScore
      3. Assert: FreshnessScore < 0.2 (price cross dominates decay)
    Expected Result: Rapid decay after price cross
    Evidence: .sisyphus/evidence/task-6-crossed-decay.txt
  ```

  **Commit**: YES (groups at Gate A)

- [ ] 7. Classification Priority Resolver

  **What to do**:
  - Create a `ClassifyWall` method that takes `L2LevelStateV2` and resolves to a single `WallClassification`:
    - Priority order (safety-first): **SPOOF > STALE > ICEBERG > GENUINE**
    - Rules:
      1. If `SpoofScore >= 70` → SPOOF (confidence = SpoofScore / 100)
      2. Else if `FreshnessScore < 0.1` OR (`PriceTradedThrough && TimesSinceCross > StaleCrossTimeoutSec`) → STALE (confidence = 1 - FreshnessScore)
      3. Else if `RefillCount >= 2` → ICEBERG (confidence = min(1, RefillCount * 0.2))
      4. Else if `MaxSize >= WallMinSize` → GENUINE (confidence = FreshnessScore)
      5. Else → UNKNOWN (not displayed)
    - If `IsMLClassified == true`, ML classification takes priority over rule-based (for Phase B integration)
    - Update `Classification`, `Confidence`, `LastClassificationTime` on L2LevelStateV2
  - Run on the prune cycle after spoof scoring (Task 5) and freshness scoring (Task 6)

  **Must NOT do**:
  - Allow multi-label classification — single label only, priority resolves conflicts
  - Run on hot path

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (after T5 and T6 complete)
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 8, 9)
  - **Blocks**: Tasks 8, 9
  - **Blocked By**: Tasks 2, 5, 6

  **References**:

  **Pattern References**:
  - Task 2 output — `WallClassification` enum and `L2LevelStateV2` fields
  - Task 5 output — `SpoofScore` field
  - Task 6 output — `FreshnessScore` field

  **Acceptance Criteria**:
  - [ ] Priority order enforced: SPOOF > STALE > ICEBERG > GENUINE
  - [ ] ML classification overrides rule-based when `IsMLClassified == true`
  - [ ] Confidence values are reasonable (0-1 range, not always 1.0)

  **QA Scenarios**:

  ```
  Scenario: Priority resolution — spoof beats iceberg
    Tool: Bash (dotnet test)
    Steps:
      1. Create wall with SpoofScore=75 AND RefillCount=3 (qualifies as both SPOOF and ICEBERG)
      2. Run ClassifyWall
      3. Assert: Classification == WallClassification.Spoof (spoof wins)
    Expected Result: SPOOF priority overrides ICEBERG
    Evidence: .sisyphus/evidence/task-7-priority-spoof.txt

  Scenario: ML override takes precedence
    Tool: Bash (dotnet test)
    Steps:
      1. Create wall with rule-based Classification == GENUINE, then set IsMLClassified=true, Classification=ICEBERG from ML
      2. Run ClassifyWall
      3. Assert: Classification == ICEBERG (ML override)
    Expected Result: ML classification takes priority over rule-based
    Evidence: .sisyphus/evidence/task-7-ml-override.txt
  ```

  **Commit**: YES (groups at Gate A)

- [ ] 8. 4-Color Rendering with Classification-Based Glow

  **What to do**:
  - Replace v1's single-color-per-side rendering with classification-based colors:
    - **GENUINE**: Bright green — `ARGB(220, 46, 204, 113)` — bid and ask both green when genuine
    - **SPOOF**: Alert red — `ARGB(220, 231, 76, 60)` — immediate visual warning
    - **ICEBERG**: Deep blue — `ARGB(220, 52, 152, 219)` — hidden size indicator
    - **STALE**: Dim gray — `ARGB(100, 149, 165, 166)` — faded, low alpha to visually recede
    - **UNKNOWN**: Not rendered (skip in DrawWallsForSide)
  - Glow bloom adapts to classification:
    - GENUINE: Standard 3-pass glow (same as v1 but green)
    - SPOOF: Red pulse effect — outer glow at higher alpha (0.15, 0.30, 0.50) for urgency
    - ICEBERG: Blue shimmer — slightly wider glow (16px, 10px, 6px) to suggest depth
    - STALE: No glow (just the line, dim)
  - Label format updates:
    - v1: `"BID 21025.50  150 ICE×3"`
    - v2: `"BID 21025.50  150 [GENUINE 87%]"` or `"ASK 21050.25  300 [SPOOF 92%]"` or `"BID 21025.50  150 [ICE×3 78%]"`
    - Classification name + confidence percentage in brackets
  - All color brushes configurable as NinjaScriptProperties (4 brush properties: GenuineBrush, SpoofBrush, IcebergBrush, StaleBrush)
  - Dispose all SharpDX resources properly in `OnRenderTargetChanged` and `DisposeDx`

  **Must NOT do**:
  - Change v1's rendering — v2 has completely separate brushes
  - Use more than 4 colors (no gradient between classifications)
  - Allocate brushes in OnRender — all allocation in OnRenderTargetChanged

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]
    - `nt8-expert`: SharpDX rendering pipeline, OnRenderTargetChanged lifecycle
    - `nt8-visual-design`: Color palette, glow effects, institutional visual design patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES (after T7 provides classification)
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 7, 9)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 1, 2, 7

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:210-246` — v1's `OnRenderTargetChanged` (brush allocation + glow arrays). v2 needs 4× the brushes (4 classifications × 3 glow passes each + main brush = 16 brushes).
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:333-379` — v1's `DrawWallsForSide` (glow + line + label rendering). v2 switches brush based on `Classification` field.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:340-352` — v1's glow bloom (3-pass, 14/8/5px, 0.08/0.18/0.35 alpha). v2 varies per classification.

  **WHY Each Reference Matters**:
  - v1's rendering is the template. v2's core change is: instead of selecting brush by side (bid/ask), select brush by classification.
  - The glow parameters show v1's proven visual approach — v2 adapts per classification for differentiated visual language.

  **Acceptance Criteria**:
  - [ ] 4 distinct colors render correctly on chart
  - [ ] Glow bloom varies by classification (SPOOF brighter, STALE no glow)
  - [ ] Labels show classification name + confidence percentage
  - [ ] All SharpDX resources disposed correctly (no memory leak)
  - [ ] 4 brush properties configurable in indicator settings

  **QA Scenarios**:

  ```
  Scenario: Correct colors render for each classification
    Tool: Bash (nt8-compile.ps1 + screenshot)
    Preconditions: v2 loaded on NQ chart with synthetic DOM data
    Steps:
      1. Compile v2 indicator
      2. Load on chart
      3. Verify GENUINE walls render green, SPOOF red, ICEBERG blue, STALE gray
      4. Capture screenshot
    Expected Result: 4 distinct colors visible, matching spec
    Evidence: .sisyphus/evidence/task-8-color-rendering.png

  Scenario: SPOOF glow is visually distinct from GENUINE glow
    Tool: Bash (screenshot comparison)
    Steps:
      1. Create two walls: one GENUINE, one SPOOF side by side
      2. Capture screenshot
      3. Verify SPOOF glow is brighter/more urgent than GENUINE glow
    Expected Result: Visual distinction clear in screenshot
    Evidence: .sisyphus/evidence/task-8-glow-difference.png
  ```

  **Commit**: YES (groups at Gate A)

- [ ] 9. Enhanced HUD + Phase A Unit Tests

  **What to do**:
  - **Enhanced HUD**: Replace v1's simple HUD (`DEPTH RADAR | B:4 A:3 | cb: 1,234,567`) with classification-aware telemetry:
    - Format: `DEPTH RADAR V2 | G:3 S:1 I:2 X:1 | ML:OFF | cb: 1,234,567`
    - `G:N` = genuine count, `S:N` = spoof count, `I:N` = iceberg count, `X:N` = stale count
    - `ML:OFF` when Python service not connected, `ML:ON [45ms]` when connected (showing last IPC latency)
    - Keep same position (bottom-left pill) and styling (Consolas 10pt, dark semi-transparent background)
  - **Unit tests**: Create comprehensive test file `DEEP6DepthRadarV2Tests.cs` in `ninjatrader/tests/`:
    - Test L2LevelStateV2 field initialization
    - Test order lifecycle tracking (Task 3): modification count, cancellation events
    - Test price-crossing detection (Task 4): bid cross, ask cross, timeout
    - Test spoof scoring (Task 5): known spoof → high score, genuine → low score
    - Test freshness scoring (Task 6): fresh → high, crossed → decaying, stale → low
    - Test classification priority (Task 7): SPOOF > STALE > ICEBERG > GENUINE
    - Test all 5 spoof score components individually
  - Use existing test infrastructure: NinjaTrader.Stubs, JSON fixtures pattern

  **Must NOT do**:
  - Add mini-dashboards, loss curves, or training metrics to HUD — keep it one-line
  - Create test dependencies on live market data — use synthetic fixtures only
  - Test rendering (SharpDX mocking is fragile) — test logic only

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on all Wave 2 tasks
  - **Parallel Group**: Sequential (after T5, T6, T7, T8)
  - **Blocks**: Gate A
  - **Blocked By**: Tasks 5, 6, 7, 8

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:384-405` — v1's HUD rendering. Same style, expanded content.
  - `ninjatrader/tests/Detectors/AbsorptionDetectorTests.cs` — Existing test pattern. Follow same structure: arrange (create fixture), act (call method), assert.
  - `ninjatrader/tests/ninjatrader.tests.csproj` — Test project. Add v2 tests here.
  - `ninjatrader/simulator/NinjaTrader.Stubs/` — Stubs for NinjaScript base classes.

  **WHY Each Reference Matters**:
  - v1's HUD is the visual template — v2 keeps same look but with classification counts.
  - AbsorptionDetectorTests shows THE test pattern used across the codebase — follow it exactly for consistency.

  **Acceptance Criteria**:
  - [ ] HUD shows classification counts (G, S, I, X)
  - [ ] HUD shows ML status (OFF/ON with latency)
  - [ ] All unit tests pass: `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "DepthRadarV2" → 0 failures`
  - [ ] Test coverage includes: lifecycle tracking, price crossing, spoof scoring, freshness scoring, classification priority
  - [ ] v2 compiles in NT8 with zero errors

  **QA Scenarios**:

  ```
  Scenario: All Phase A unit tests pass
    Tool: Bash (dotnet test)
    Steps:
      1. dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "DepthRadarV2" -v normal
    Expected Result: All tests pass, 0 failures, 0 skipped
    Evidence: .sisyphus/evidence/task-9-unit-tests.txt

  Scenario: v2 compiles in NT8
    Tool: Bash (nt8-compile.ps1)
    Steps:
      1. Run nt8-compile.ps1
      2. Check output for [COMPILE-RESULT]
    Expected Result: [COMPILE-RESULT] SUCCESS
    Evidence: .sisyphus/evidence/task-9-compilation.txt

  Scenario: v1 integrity check
    Tool: Bash (git diff)
    Steps:
      1. git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs
    Expected Result: Empty output (zero changes to v1)
    Evidence: .sisyphus/evidence/task-9-v1-integrity.txt
  ```

  **Commit**: YES
  - Message: `feat(depth-radar): complete Phase A — rule-based wall classification v2`
  - Files: All v2 files + test file
  - Pre-commit: `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "DepthRadarV2"`

> **GATE A CHECKPOINT**: After Task 9, verify: v2 compiles, renders 4 colors, classifies by rules, v1 untouched, all tests pass. Phase A is independently useful — the indicator works without Python.

---

### PHASE B — ML Classification Service (Python + IPC)

- [ ] 10. Retrospective Wall Labeling from MBO Replay

  **What to do**:
  - Create `deep6/ml/depth_radar/labeler.py` — processes historical Databento MBO data to automatically label resting orders:
    - **Reuse** existing `deep6/data/databento_live.py` for MBO parsing and `deep6/backtest/mbo_adapter.py` for replay
    - **Reuse** existing `deep6/state/dom.py` (`DOMState`) for order book state management
    - For each "significant wall" (resting order with size ≥ threshold for ≥ N seconds):
      - Track its full lifecycle: appearance, modifications, cancellation, fills
      - **Label SPOOF**: Cancelled within 500ms AND size > 5× average AND not filled
      - **Label ICEBERG**: RefillCount ≥ 2 (size dropped below 50%, recovered 2+ times)
      - **Label STALE**: Price traded through the level AND order cancelled or disappeared within 60s of price cross
      - **Label GENUINE**: Survived ≥ 30s, not cancelled before fill, price either bounced or order absorbed market flow
    - Output: Parquet file with columns: `timestamp, price, side, original_size, max_size, label, features...`
  - Include configurable thresholds for wall significance (min size, min duration)
  - Add a `--dry-run` mode that reports label distribution without writing output

  **Must NOT do**:
  - Rebuild MBO parsing from scratch — use existing `databento_live.py`
  - Rebuild order book reconstruction — use existing `DOMState`
  - Manually label data — everything is automated from lifecycle outcomes

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12, 13, 14)
  - **Blocks**: Task 12
  - **Blocked By**: Gate A (Phase A must be complete before Phase B starts)

  **References**:

  **Pattern References**:
  - `deep6/data/databento_live.py` — Existing MBO event processing (385 lines). Reuse for parsing MBO events.
  - `deep6/backtest/mbo_adapter.py` — Existing MBO replay adapter. Reuse for replaying historical data through callbacks.
  - `deep6/state/dom.py` — `DOMState` class with pre-allocated arrays for 40 bid/ask levels. Reuse for order book state.
  - `deep6/ml/triple_barrier.py` — Existing labeling approach (triple barrier). Reference for labeling methodology patterns.

  **WHY Each Reference Matters**:
  - These three files (databento_live, mbo_adapter, dom.py) are the existing data pipeline that v2's labeler MUST reuse — not rebuild.
  - triple_barrier.py shows how the codebase approaches ML labeling — follow the same patterns.

  **Acceptance Criteria**:
  - [ ] Labeler produces Parquet output with correct columns
  - [ ] Label distribution is reasonable (GENUINE should dominate, SPOOF should be rare)
  - [ ] `--dry-run` mode works and reports distribution
  - [ ] Reuses existing Databento + DOMState infrastructure (no new MBO parser)

  **QA Scenarios**:

  ```
  Scenario: Labeler processes sample MBO data correctly
    Tool: Bash (python)
    Steps:
      1. python -m deep6.ml.depth_radar.labeler --input sample_mbo.dbn --dry-run
      2. Check output: label distribution (GENUINE: N, SPOOF: N, ICEBERG: N, STALE: N)
    Expected Result: Labels generated, GENUINE > 60%, SPOOF < 10%, distribution printed
    Evidence: .sisyphus/evidence/task-10-label-distribution.txt

  Scenario: Known spoof pattern labeled correctly
    Tool: Bash (pytest)
    Steps:
      1. Create synthetic MBO fixture: large order appears, cancels in 200ms
      2. Run labeler on fixture
      3. Assert label == SPOOF
    Expected Result: Synthetic spoof correctly labeled
    Evidence: .sisyphus/evidence/task-10-spoof-label.txt
  ```

  **Commit**: YES (groups at Gate B)
  - Message: `feat(depth-radar-ml): add retrospective wall labeler`
  - Files: `deep6/ml/depth_radar/labeler.py`, `tests_v2/depth_radar/test_labeler.py`

- [ ] 11. Wall Feature Engineering (Extend feature_builder.py)

  **What to do**:
  - Create `deep6/ml/depth_radar/wall_features.py` that extracts per-wall features for ML classification:
    - **Reuse/extend** existing `deep6/ml/feature_builder.py` patterns (47-feature matrix)
    - Per-wall features (minimum set — do NOT add "bonus" features):
      1. `time_in_book` — seconds since first appearance
      2. `modification_count` — total modifications
      3. `cancellation_count` — times cancelled and reappeared
      4. `original_size` — size when first placed
      5. `max_size` — peak size observed
      6. `current_size` — current resting size
      7. `size_ratio` — `max_size / average_wall_size` (relative to market)
      8. `distance_from_mid` — ticks from current mid price
      9. `distance_from_bbo` — ticks from best bid/offer
      10. `spread_at_placement` — spread when order was placed
      11. `book_imbalance` — `(bid_vol - ask_vol) / (bid_vol + ask_vol)` at top 10 levels
      12. `side` — 0 for bid, 1 for ask
      13. `refill_count` — iceberg refill counter
      14. `price_crossed` — 1 if price has traded through this level, 0 otherwise
      15. `modification_rate` — modifications per second
    - Output: numpy array or pandas DataFrame, one row per wall
  - Feature normalization: z-score using rolling statistics (mean/std over last 1000 walls)

  **Must NOT do**:
  - Add more than 15 features without explicit justification
  - Use features that require full order book history (memory explosion)
  - Compute features that need L3 individual order IDs (L2 aggregated data only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 10, 12, 13, 14)
  - **Blocks**: Task 12
  - **Blocked By**: Gate A

  **References**:

  **Pattern References**:
  - `deep6/ml/feature_builder.py` — Existing 47-feature builder. Follow naming and output conventions.
  - `deep6/state/dom.py` — DOMState for computing book_imbalance feature.

  **Acceptance Criteria**:
  - [ ] 15 features extracted per wall
  - [ ] Feature normalization working (z-score)
  - [ ] Output is numpy array compatible with sklearn/LightGBM input

  **QA Scenarios**:

  ```
  Scenario: Features extracted from synthetic wall data
    Tool: Bash (pytest)
    Steps:
      1. Create synthetic wall with known properties
      2. Extract features
      3. Assert: 15 features, correct values for known inputs
    Expected Result: Feature vector matches expected values
    Evidence: .sisyphus/evidence/task-11-feature-extraction.txt
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 12. LightGBM Wall Classifier (Binary SPOOF → 4-class)

  **What to do**:
  - Create `deep6/ml/depth_radar/classifier.py`:
    - **Phase 1 (binary)**: Train LightGBM on SPOOF vs NOT-SPOOF
      - Reuse existing `deep6/ml/lgbm_trainer.py` training patterns
      - Class weighting to handle imbalance (SPOOF is rare)
      - Walk-forward validation (train on first 80% of data, test on last 20%)
      - **EXIT GATE**: Must achieve F1 > 0.80 on binary SPOOF before proceeding to 4-class
    - **Phase 2 (4-class)**: Only after binary F1 > 0.80
      - Extend to 4-class: GENUINE, SPOOF, ICEBERG, STALE
      - Use one-vs-rest LightGBM or native multiclass
      - Weighted F1 target: > 0.75
    - Model persistence: save/load via joblib to `deep6/models/depth_radar_classifier.joblib`
    - Inference function: `classify(features: np.ndarray) → (label: str, confidence: float)`
  - Include training script with CLI: `python -m deep6.ml.depth_radar.train --data labeled_walls.parquet --output model.joblib`

  **Must NOT do**:
  - Use TLOB or any transformer architecture — LightGBM first (existing infrastructure)
  - Skip binary phase — must hit F1 > 0.80 before 4-class
  - Train without walk-forward validation (no random split — time series data requires temporal ordering)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T10 for labels, T11 for features)
  - **Parallel Group**: Wave 3 (starts after T10 + T11 complete)
  - **Blocks**: Tasks 15, 17
  - **Blocked By**: Tasks 10, 11

  **References**:

  **Pattern References**:
  - `deep6/ml/lgbm_trainer.py` — Existing LightGBM training pipeline. Reuse patterns for hyperparameters, class weighting, model persistence.
  - `deep6/ml/feature_builder.py` — Feature pipeline that feeds into training. Wall features (Task 11) follow same output convention.

  **Acceptance Criteria**:
  - [ ] Binary SPOOF classifier trained and achieves F1 > 0.80 on hold-out set
  - [ ] Model saved to `deep6/models/depth_radar_classifier.joblib`
  - [ ] `classify(features)` returns `(label, confidence)` tuple
  - [ ] Walk-forward validation used (not random split)
  - [ ] 4-class only attempted after binary gate passes

  **QA Scenarios**:

  ```
  Scenario: Binary classifier meets F1 threshold
    Tool: Bash (python training script)
    Steps:
      1. python -m deep6.ml.depth_radar.train --data labeled_walls.parquet --output model.joblib --mode binary
      2. Check output: classification report with F1, precision, recall
    Expected Result: F1(SPOOF) > 0.80
    Evidence: .sisyphus/evidence/task-12-binary-f1.txt

  Scenario: Model inference returns correct format
    Tool: Bash (pytest)
    Steps:
      1. Load trained model
      2. Create feature vector for known spoof pattern
      3. Call classify(features)
      4. Assert: returns (label="SPOOF", confidence > 0.7)
    Expected Result: Correct label and confidence format
    Evidence: .sisyphus/evidence/task-12-inference-format.txt
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 13. Extend DataBridgeServer for Classification Messages

  **What to do**:
  - Extend the existing `DataBridgeServer.cs` (`ninjatrader/Custom/AddOns/DEEP6/Bridge/`) to support a **bidirectional classification channel** for Depth Radar v2:
    - **Outbound (NT8 → Python)**: v2 sends wall snapshots to Python for ML classification
      - Message type: `"wall_snapshot"` — includes price, side, size, lifecycle metrics (time_in_book, modification_count, etc.)
      - Sent on the 30s prune cycle (not every DOM callback)
    - **Inbound (Python → NT8)**: Python sends back classifications
      - Message type: `"wall_classification"` — includes price, side, classification (GENUINE/SPOOF/ICEBERG/STALE), confidence (0-1)
      - v2 receives these and updates `L2LevelStateV2.Classification`, `.Confidence`, `.IsMLClassified = true`
    - Use existing NDJSON protocol (one JSON object per line) on a **separate port** (9201) to avoid interfering with existing DataBridgeServer traffic on port 9200
    - Include heartbeat messages every 5s for connection health monitoring
  - Create a lightweight TCP listener class `DepthRadarBridge` inside `DEEP6DepthRadarV2.cs` (private inner class) — NOT modifying DataBridgeServer.cs

  **Must NOT do**:
  - Modify `DataBridgeServer.cs` — create a separate, lightweight bridge for v2
  - Use port 9200 (already used by DataBridgeServer)
  - Send wall snapshots on every OnMarketDepth callback (would flood the channel at 1,000/sec)
  - Use WebSocket, gRPC, or named pipes — stick with TCP NDJSON for consistency with existing patterns

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NinjaTrader threading, async patterns in NT8, state machine lifecycle

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 10, 11, 12, 14)
  - **Blocks**: Task 15
  - **Blocked By**: Gate A

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Bridge/DataBridgeServer.cs` — Existing TCP NDJSON server on port 9200. Study its listener pattern, NDJSON protocol, and shutdown lifecycle. v2's bridge follows the same patterns but on port 9201.
  - `deep6/copilot/bridge_client.py` — Existing Python client with auto-reconnection and exponential backoff. v2's Python classification service should follow the same connection pattern.

  **WHY Each Reference Matters**:
  - DataBridgeServer is the PROVEN IPC pattern in this codebase. v2 creates a parallel instance, not a modification of the original.
  - bridge_client.py shows how Python connects to NT8 TCP — the classification service uses the same approach.

  **Acceptance Criteria**:
  - [ ] `DepthRadarBridge` listens on port 9201
  - [ ] Outbound wall snapshots sent as NDJSON on 30s cycle
  - [ ] Inbound classifications parsed and applied to L2LevelStateV2
  - [ ] Heartbeat every 5s for health monitoring
  - [ ] DataBridgeServer.cs (port 9200) completely unmodified

  **QA Scenarios**:

  ```
  Scenario: Bridge accepts connection and receives classification
    Tool: Bash (python test client)
    Preconditions: v2 indicator loaded and bridge listening on 9201
    Steps:
      1. Python test client connects to localhost:9201
      2. Client sends: {"type":"wall_classification","price":21025.0,"side":"bid","classification":"SPOOF","confidence":0.92}
      3. Verify wall at 21025 updates to SPOOF classification in indicator
    Expected Result: Classification applied, IsMLClassified=true
    Evidence: .sisyphus/evidence/task-13-ipc-receive.txt

  Scenario: IPC round-trip latency under budget
    Tool: Bash (python timing harness)
    Steps:
      1. Run 1000 round-trips: send wall snapshot → receive classification
      2. Measure p50, p95, p99 latency
    Expected Result: p99 < 50ms
    Evidence: .sisyphus/evidence/task-13-ipc-latency.txt
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 14. Python Classification Service + Health Endpoint

  **What to do**:
  - Create `deep6/services/depth_radar_service.py` — async TCP client that:
    - Connects to v2's DepthRadarBridge on port 9201 (auto-reconnect with exponential backoff)
    - Receives wall snapshot messages from NT8
    - Extracts features (using Task 11's `wall_features.py`)
    - Runs LightGBM inference (using Task 12's trained model)
    - Sends classification results back to NT8
    - Logs all classifications for analysis
  - Add FastAPI health endpoint on port 9202:
    - `GET /health` → `{"status": "ok", "model_loaded": true, "last_classification_ms": 45, "walls_classified": 1234}`
    - `GET /metrics` → classification distribution, average inference time, IPC latency
  - CLI entry point: `python -m deep6.services.depth_radar_service --model deep6/models/depth_radar_classifier.joblib --port 9201 --health-port 9202`

  **Must NOT do**:
  - Maintain independent DOM state — receive wall snapshots from NT8 (C# is the state authority)
  - Block the event loop during inference — run LightGBM in thread pool executor
  - Crash on model load failure — log error and run in "passthrough" mode (send UNKNOWN for all walls)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (depends on T12 for model, T13 for IPC protocol)
  - **Parallel Group**: Wave 3 (starts after T12 + T13 complete)
  - **Blocks**: Tasks 15, 16
  - **Blocked By**: Tasks 12, 13

  **References**:

  **Pattern References**:
  - `deep6/copilot/bridge_client.py` — Existing Python async TCP client. Reuse connection pattern, auto-reconnect, backoff.
  - `deep6/ml/lgbm_trainer.py` — Model loading and inference patterns.

  **Acceptance Criteria**:
  - [ ] Service connects to port 9201 and processes wall snapshots
  - [ ] Health endpoint responds within 100ms: `curl http://localhost:9202/health`
  - [ ] Inference runs without blocking event loop
  - [ ] Graceful handling when model file is missing (passthrough mode)

  **QA Scenarios**:

  ```
  Scenario: Health endpoint responds correctly
    Tool: Bash (curl)
    Steps:
      1. Start service: python -m deep6.services.depth_radar_service --model model.joblib
      2. curl http://localhost:9202/health
    Expected Result: {"status": "ok", "model_loaded": true, ...} with 200 status
    Evidence: .sisyphus/evidence/task-14-health-check.txt

  Scenario: Service handles missing model gracefully
    Tool: Bash (python)
    Steps:
      1. Start service with nonexistent model path
      2. curl http://localhost:9202/health
      3. Send wall snapshot via TCP
    Expected Result: Health shows model_loaded=false, classifications return UNKNOWN
    Evidence: .sisyphus/evidence/task-14-passthrough-mode.txt
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 15. v2 IPC Client (Receive + Apply ML Classifications)

  **What to do**:
  - In `DEEP6DepthRadarV2.cs`, integrate the `DepthRadarBridge` (Task 13) to:
    - On startup (State.Realtime): attempt connection to Python service on port 9201
    - On 30s prune cycle: serialize current wall snapshots → send via bridge
    - On receive: parse classification response → update matching `L2LevelStateV2`:
      - Set `Classification` to ML value (overrides rule-based)
      - Set `Confidence` to ML confidence
      - Set `IsMLClassified = true`
      - Set `LastClassificationTime = DateTime.UtcNow`
    - Track IPC latency for HUD display
    - If connection drops: set `IsMLClassified = false` on all walls, fall back to rule-based
  - Add NinjaScriptProperty: `EnableML` (bool, default true) — allows user to disable ML and use rule-based only

  **Must NOT do**:
  - Block the rendering thread waiting for ML response — process asynchronously
  - Overwrite rule-based classification while ML is unavailable
  - Make ML required for the indicator to function

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 16, 17, 18)
  - **Blocks**: Task 18
  - **Blocked By**: Tasks 13, 14

  **References**:

  **Pattern References**:
  - Task 13 output — `DepthRadarBridge` class for TCP communication
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs:194-206` — v1's invalidation timer pattern. ML response handling should trigger invalidation similarly.

  **Acceptance Criteria**:
  - [ ] ML classifications received and applied to wall state
  - [ ] `IsMLClassified` correctly set to true when ML active, false when disconnected
  - [ ] `EnableML` property toggles ML on/off
  - [ ] IPC latency tracked and available for HUD

  **QA Scenarios**:

  ```
  Scenario: ML classifications applied to chart rendering
    Tool: Bash (nt8-compile + screenshot)
    Steps:
      1. Start Python classification service
      2. Load v2 indicator on NQ chart
      3. Wait 30s for first classification cycle
      4. Verify HUD shows "ML:ON [XXms]"
      5. Capture screenshot showing ML-classified walls
    Expected Result: Walls show ML classifications, HUD shows ML:ON
    Evidence: .sisyphus/evidence/task-15-ml-active.png

  Scenario: Graceful fallback when ML disconnected
    Tool: Bash (kill service + screenshot)
    Steps:
      1. Kill Python service while v2 is running
      2. Wait 10 seconds
      3. Verify HUD shows "ML:OFF"
      4. Verify walls still render with rule-based classification
    Expected Result: Indicator continues rendering, HUD shows ML:OFF
    Evidence: .sisyphus/evidence/task-15-ml-fallback.png
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 16. Graceful Degradation (Fallback to Rule-Based)

  **What to do**:
  - Implement robust fallback behavior in `DEEP6DepthRadarV2.cs`:
    - **On Python service disconnect**: Within 5 seconds, all walls revert to rule-based classification (`IsMLClassified = false`)
    - **On reconnect**: Walls transition back to ML classification on next 30s cycle
    - **On startup without Python service**: Indicator works immediately with rule-based classification. No error, no warning beyond HUD showing "ML:OFF"
    - **Classification transition**: When switching between ML and rule-based, do NOT flash/flicker — smooth transition by keeping current classification until new one arrives
    - **HUD status**: `ML:OFF` (disconnected), `ML:ON [45ms]` (connected with latency), `ML:STALE` (connected but no response in >60s)
  - Add logging (via NT8 Output Window): connection events, fallback triggers, reconnection attempts

  **Must NOT do**:
  - Throw exceptions when Python service is unavailable
  - Show error popups or alert dialogs — this is expected operational state
  - Clear all wall classifications on disconnect (keep the last known rule-based classification)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 15, 17, 18)
  - **Blocks**: Task 18
  - **Blocked By**: Tasks 14, 15

  **References**:

  **Pattern References**:
  - `deep6/copilot/bridge_client.py` — Python reconnection pattern with exponential backoff. The C# side should handle disconnection similarly (detect, log, retry).

  **Acceptance Criteria**:
  - [ ] Indicator works with zero Python dependency on startup
  - [ ] Fallback completes within 5 seconds of disconnect
  - [ ] Reconnection automatic on Python service restart
  - [ ] No exceptions or error dialogs during disconnect/reconnect cycles

  **QA Scenarios**:

  ```
  Scenario: Cold start without Python service
    Tool: Bash (nt8-compile + screenshot)
    Steps:
      1. Ensure Python service is NOT running
      2. Load v2 on NQ chart
      3. Verify: walls render with rule-based classification within 10s
      4. Verify: HUD shows "ML:OFF"
    Expected Result: Indicator fully functional in rule-based mode
    Evidence: .sisyphus/evidence/task-16-cold-start.png

  Scenario: Disconnect-reconnect cycle
    Tool: Bash (script)
    Steps:
      1. Start Python service, load v2, verify ML:ON
      2. Kill Python service, wait 10s, verify ML:OFF + walls still visible
      3. Restart Python service, wait 35s, verify ML:ON restored
    Expected Result: Clean transition through all 3 states
    Evidence: .sisyphus/evidence/task-16-disconnect-reconnect.txt
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 17. 4-Class Classifier Upgrade

  **What to do**:
  - **GATE CHECK FIRST**: Verify binary SPOOF classifier achieved F1 > 0.80. If not, do NOT proceed — iterate on binary model instead.
  - Extend `deep6/ml/depth_radar/classifier.py` to support 4-class classification:
    - Classes: GENUINE, SPOOF, ICEBERG, STALE
    - Use LightGBM native multiclass (`objective='multiclass'`, `num_class=4`)
    - Class weighting to handle imbalance (GENUINE will dominate)
    - Walk-forward validation
    - Weighted F1 target: > 0.75
  - Update inference function: `classify(features) → (label: str, confidence: float, all_probs: dict)`
    - `all_probs` returns probability for each class (useful for ambiguous cases)
  - Update Python service to use 4-class model when available, binary when not

  **Must NOT do**:
  - Proceed if binary F1 < 0.80 — iterate on binary model first
  - Use TLOB or any transformer — LightGBM only at this stage
  - Train without walk-forward validation

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (after binary gate passes)
  - **Parallel Group**: Wave 4 (with Tasks 15, 16, 18)
  - **Blocks**: Task 18
  - **Blocked By**: Task 12 (binary F1 > 0.80 gate)

  **References**:

  **Pattern References**:
  - Task 12 output — binary classifier. Extend, don't replace.
  - `deep6/ml/lgbm_trainer.py` — Existing multiclass LightGBM patterns.

  **Acceptance Criteria**:
  - [ ] Binary F1 > 0.80 gate verified before proceeding
  - [ ] 4-class model trained with weighted F1 > 0.75
  - [ ] `classify()` returns all class probabilities
  - [ ] Python service auto-selects 4-class model when available

  **QA Scenarios**:

  ```
  Scenario: 4-class model meets weighted F1 threshold
    Tool: Bash (python training)
    Steps:
      1. Verify binary F1 > 0.80 (gate check)
      2. python -m deep6.ml.depth_radar.train --mode multiclass
      3. Check weighted F1 in output
    Expected Result: Weighted F1 > 0.75
    Evidence: .sisyphus/evidence/task-17-multiclass-f1.txt
  ```

  **Commit**: YES (groups at Gate B)

- [ ] 18. Phase B Integration Tests

  **What to do**:
  - Create end-to-end integration test suite that verifies the full Phase B pipeline:
    - **Test 1: Full pipeline**: MBO data → labeler → features → train → classify → IPC → v2 rendering
    - **Test 2: IPC latency benchmark**: 1000 round-trips, assert p99 < 50ms
    - **Test 3: Graceful degradation cycle**: start service → classify → kill service → verify fallback → restart → verify recovery
    - **Test 4: v1 + v2 coexistence**: Both indicators on same NQ chart for 5 minutes, no crash
    - **Test 5: v1 integrity**: `git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs` returns empty
  - Python tests in `tests_v2/depth_radar/`
  - C# tests in `ninjatrader/tests/`

  **Must NOT do**:
  - Require live market data for integration tests — use synthetic/replay data
  - Skip the v1 integrity check

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on all Wave 4 tasks
  - **Parallel Group**: Sequential (after T15, T16, T17)
  - **Blocks**: Gate B
  - **Blocked By**: Tasks 15, 16, 17

  **Acceptance Criteria**:
  - [ ] All 5 integration tests pass
  - [ ] v1 integrity verified (zero diff)
  - [ ] IPC p99 < 50ms
  - [ ] No crash during v1+v2 coexistence

  **QA Scenarios**:

  ```
  Scenario: Full pipeline integration test
    Tool: Bash (pytest + dotnet test)
    Steps:
      1. pytest tests_v2/depth_radar/test_integration.py -v
      2. dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "DepthRadarV2Integration"
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-18-integration.txt
  ```

  **Commit**: YES
  - Message: `feat(depth-radar): complete Phase B — ML wall classification with IPC`
  - Pre-commit: `dotnet test && pytest tests_v2/depth_radar/`

> **GATE B CHECKPOINT**: ML classifies walls via LightGBM, IPC delivers classifications in <50ms, binary F1>0.80, graceful degradation verified, v1 untouched.

---

### PHASE C — Direction Prediction (Stretch Goal)

- [ ] 19. Direction + Confidence Model

  **What to do**:
  - Create `deep6/ml/depth_radar/direction_model.py`:
    - Input: classified wall features + market context (regime from HMM, session time, spread, book imbalance)
    - Output: direction (LONG/SHORT/NEUTRAL) + confidence (0-1)
    - Labeling: Use existing `deep6/ml/triple_barrier.py` — upper barrier +8 ticks, lower barrier -4 ticks, time barrier 5 minutes
    - Architecture: **Start with LightGBM** — only upgrade to TLOB if LightGBM ceiling is demonstrated
    - Walk-forward validation, same patterns as classifier
    - Minimum accuracy target: directional accuracy > 55% (above random for binary UP/DOWN on filtered walls)
  - This model runs AFTER classification — only scored walls with Classification != STALE and != SPOOF are candidates

  **Must NOT do**:
  - Use TLOB without first demonstrating LightGBM ceiling with concrete metrics
  - Skip triple barrier labeling — use it (it's already in the codebase)
  - Train on ALL walls — only train on GENUINE + ICEBERG classified walls

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Tasks 20, 21
  - **Blocked By**: Gate B

  **References**:

  **Pattern References**:
  - `deep6/ml/triple_barrier.py` — Existing triple barrier labeling. Reuse for direction labels.
  - `deep6/ml/hmm_regime.py` — HMM regime detection. Regime is a critical input feature for direction prediction.

  **Acceptance Criteria**:
  - [ ] Direction model trained with accuracy > 55% on hold-out set
  - [ ] Triple barrier labeling used (8 tick / 4 tick / 5 min)
  - [ ] Only GENUINE + ICEBERG walls used for training (SPOOF and STALE excluded)

  **Commit**: YES (groups at Gate C)

- [ ] 20. Direction Overlay Rendering + ML Confidence HUD

  **What to do**:
  - Add direction visualization to v2 indicator:
    - For walls with direction prediction: draw small arrow (▲ or ▼) next to the wall label
    - Arrow color matches classification color but with higher alpha
    - Label format update: `"BID 21025.50  150 [GENUINE 87%] ▲72%"` — direction arrow + confidence
    - Only show direction arrow when confidence > 50% (configurable: `DirectionConfidenceThreshold`)
  - Enhance HUD for Phase C:
    - Add: `DIR:▲72%` or `DIR:—` (no direction prediction available)
    - Show last direction prediction timestamp

  **Must NOT do**:
  - Add complex direction dashboards — keep it minimal (arrow + percentage)
  - Show direction predictions for SPOOF or STALE walls
  - Clutter the chart with too many arrows — only show for top N walls by confidence

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 21
  - **Blocked By**: Task 19

  **Acceptance Criteria**:
  - [ ] Direction arrows render correctly (▲ for LONG, ▼ for SHORT)
  - [ ] Arrows only shown when confidence > threshold
  - [ ] SPOOF and STALE walls excluded from direction display

  **Commit**: YES (groups at Gate C)

- [ ] 21. End-to-End Integration Test (Full Pipeline)

  **What to do**:
  - Comprehensive test of the entire v2 system:
    - **Test 1**: Cold start → rule-based classification → start ML service → ML classification → start direction model → direction predictions visible
    - **Test 2**: Full pipeline latency: DOM update → wall detection → IPC → ML classify + direction → render on chart. Total budget < 500ms.
    - **Test 3**: Stress test: 30 minutes of live NQ data with v1 + v2 both active, ML service running, direction predictions active
    - **Test 4**: Model hot-swap: replace model file while service is running, verify new model loads on next cycle
    - **Test 5**: Final v1 integrity: `git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs` returns empty
  - Document any performance findings or issues

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Gate C
  - **Blocked By**: Tasks 19, 20

  **Acceptance Criteria**:
  - [ ] All 5 integration tests pass
  - [ ] Full pipeline latency < 500ms
  - [ ] 30-minute stress test passes without crash
  - [ ] v1 completely unmodified

  **Commit**: YES
  - Message: `feat(depth-radar): complete Phase C — direction prediction`

> **GATE C CHECKPOINT**: Direction predictions visible on chart for GENUINE/ICEBERG walls. Directional accuracy > 55%. Full system stress-tested.

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, check compilation). For each "Must NOT Have": search codebase for forbidden patterns (v1 modifications, DetectorRegistry references, rebuilt Databento infrastructure). Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run NT8 compile check + `dotnet test` + `pytest`. Review all changed files for: `as any`/`@ts-ignore` equivalent, empty catches, console.log/Print in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify SharpDX resource lifecycle (allocate in OnRenderTargetChanged, dispose in DisposeDx).
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `nt8-expert` skill)
  Start from clean state. Load v2 on NQ chart. Verify: walls render within 10s, colors match classification, HUD shows correct counts. Load v1 alongside — verify no interference for 5 minutes. Kill Python service — verify graceful degradation within 5s. Restart Python service — verify ML classifications resume. Save screenshots to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check v1 (`DEEP6DepthRadar.cs`) is UNMODIFIED via git diff. Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | v1 Integrity [PASS/FAIL] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Gate A**: `feat(depth-radar): add rule-based wall classification v2` — DEEP6DepthRadarV2.cs + tests
- **Gate B**: `feat(depth-radar): add ML wall classification via LightGBM` — Python service + IPC + integration tests
- **Gate C**: `feat(depth-radar): add direction prediction` — direction model + rendering

---

## Success Criteria

### Verification Commands
```bash
# C# compilation
powershell nt8-compile.ps1  # Expected: [COMPILE-RESULT] SUCCESS

# C# tests
dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "DepthRadarV2"  # Expected: All tests passed

# Python ML tests
pytest tests_v2/depth_radar/ -v  # Expected: All tests passed

# Python service health
curl http://localhost:9201/health  # Expected: {"status": "ok"}

# IPC latency
python tests_v2/depth_radar/ipc_latency_bench.py  # Expected: p99 < 50ms

# v1 integrity
git diff HEAD -- ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadar.cs  # Expected: no changes
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] v1 (`DEEP6DepthRadar.cs`) completely unmodified
- [ ] v2 compiles and renders on live NQ chart
- [ ] Rule-based classification works without Python service
- [ ] ML classification works when Python service is running
- [ ] Graceful degradation verified
- [ ] All C# and Python tests pass
