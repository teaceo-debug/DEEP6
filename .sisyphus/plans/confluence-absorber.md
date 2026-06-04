# DEEP6 Confluence Absorber — NinjaTrader 8 Indicator

## TL;DR

> **Quick Summary**: Build a single NT8 indicator that merges three level sources (VP LVN weekly, GEX via FlashAlpha, MadeLevels.com via file bridge), identifies confluence zones where 2+ sources stack, monitors for real-time absorption at those zones using tick/DOM data, and fires a visual arrow + audio alert when absorption confirms — the unified "where + when" entry trigger.
> 
> **Deliverables**:
> - MadeLevels file bridge reader — reads MadeLevels.com commercial indicator data from disk (NOT DEEP6MADLevels.cs — that is a separate DEEP6 indicator, unused in this plan)
> - New indicator `DEEP6ConfluenceAbsorber.cs` with extracted utility classes (GexClient, VpLvnEngine, ConfluenceEngine) to prevent single-file bloat
> - Detector parameter analysis + sensitivity report (code analysis, not empirical backtest)
> - Compiles and runs on 1-min NQ chart alongside existing DEEP6 indicators
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Task 2 → Task 1 → Tasks 3+4 (parallel) → Task 5 → Tasks 6+7 (parallel) → Task 8 → F1-F4

---

## Context

### Original Request
User wants to unify their trading philosophy into a focused system: VP LVN levels (weekly), MadeLevels, and TraderGEX/FlashAlpha GEX levels — all on one NinjaTrader chart — with an absorption trigger that fires when price enters a level confluence zone and aggressive volume gets absorbed by passive orders.

### Interview Summary
**Key Discussions**:
- Platform: NinjaTrader 8 only (user chose over TV/hybrid/Python)
- Signal delivery: Visual arrow + audio alert only — manual entry decision
- VP LVN: Weekly profile, 1-min resolution, calculated internally
- GEX: FlashAlpha API, polled every ~5 min, dynamic throughout day, QQQ→NQ mapping
- MadeLevels: COMMERCIAL third-party indicator from MadeLevels.com (NOT DEEP6MADLevels.cs — that is a separate DEEP6-built indicator). Integration via shared file bridge — investigate where MadeLevels stores data on disk.
- Confluence: 2+ of 3 sources stacking within proximity threshold
- Absorption: Reuse existing DEEP6 AbsorptionDetector (ABS-01..04) + DeltaDetector

**Research Findings**:
- FlashAlpha API: Per-strike GEX via `GET /v1/exposure/gex/QQQ` (Growth tier — user confirmed). Returns per-strike net_gex values for bar-style rendering like TraderGEX Pro. ALSO `GET /v1/exposure/levels/QQQ` for summary levels (gamma flip, walls). Display: horizontal bars at each NQ strike — green=positive gamma, red=negative gamma, length=magnitude. Existing HTTP client pattern in `DEEP6GexLevels.cs:388-437`
- Absorption: Detector suite (ABS-01..07, DELT-01..11) exists but needs DEEP RESEARCH + BACKTESTING before production use. User explicitly wants parameter optimization to ensure signals produce alpha at confluence levels. FootprintV7 (data source for detectors) also needs assessment and development work.
- MadeLevels.com: COMMERCIAL third-party NT8 indicator. Cannot modify source. Cannot read DrawObjects cross-indicator. Integration via shared file bridge — need to discover where it stores level data on disk (config files, cached data, etc.)
- Tick handling: `DEEP6FootprintV7.cs:347-428` handles 1000+ callbacks/sec with lock-protected `AddTrade()`, ~10-50μs lock scope
- QQQ→NQ mapping: `nq_level = qqq_level / qqq_spot * nq_spot` (from `nq_mapper.py:10`)

### Metis Review
**Identified Gaps** (all addressed):
- MadeLevels auto-scan impossible via DrawObjects → RESOLVED: file bridge approach (investigate where MadeLevels.com stores data on disk, build reader)
- Dual tick processing performance risk → MITIGATED: self-contained FootprintBar, profile with both indicators
- Weekly VP cold start (Sunday/Monday) → MITIGATED: VP disabled until 120 bars accumulated
- Stale GEX data → MITIGATED: >2 min = amber warning, >10 min = exclude from confluence
- Scope creep risk → LOCKED: only AbsorptionDetector + DeltaDetector, no other detectors
- `System.Math` namespace shadowing → MUST use fully qualified `System.Math` (commit 1d61d0b)
- `DashStyle` ambiguity → MUST use `SharpDX.Direct2D1.DashStyle` fully qualified (commit 1d61d0b)

---

## Work Objectives

### Core Objective
Build a single NinjaTrader 8 indicator that provides a unified "Bias → Levels → Absorption → Entry" pipeline for NQ futures trading.

### Concrete Deliverables
- MadeLevels.com file bridge: reader class that loads levels from discovered data files on disk
- `DEEP6ConfluenceAbsorber.cs` — new indicator file in `ninjatrader/Custom/Indicators/DEEP6/`
- Deployed to NT8 custom indicators folder, compiled clean

### Definition of Done
- [ ] Indicator compiles via `nt8-compile.ps1` → `[COMPILE-RESULT] SUCCESS`
- [ ] VP LVN levels appear on chart after 120+ bars of weekly data
- [ ] GEX levels appear within 10s of indicator load (FlashAlpha API fetch)
- [ ] Confluence zones highlighted when 2+ sources stack within 8 ticks
- [ ] Absorption arrow + sound fires when AbsorptionDetector confirms at confluence zone
- [ ] No errors in NT8 Output Window during 5-minute live runtime

### Must Have
- VP LVN calculated from weekly profile with 1-min resolution bars
- FlashAlpha GEX levels with magnitude display, polled every 5 min, QQQ→NQ mapped
- MadeLevels.com file bridge integration (shared file reader)
- Confluence detection (2+ of 3 sources within configurable tick threshold)
- Absorption monitoring using AbsorptionDetector (ABS-01..04) at confluence zones
- Delta aggression flip detection using DeltaDetector (DELT-01, DELT-03, DELT-05)
- Visual arrow on chart at absorption confirmation
- Audio alert on absorption confirmation
- 5-bar cooldown between re-alerts at the same zone
- Graceful degradation when any source is unavailable (GEX API down, MadeLevels not loaded, VP warming up)

### Must NOT Have (Guardrails)
- Auto-execution, bracket orders, or trade management
- Full DetectorRegistry instantiation (only direct AbsorptionDetector + DeltaDetector)
- Custom SharpDX footprint cell rendering (this is an ALERT indicator, not a footprint chart)
- Multi-instrument support (NQ only)
- Configurable detector parameters via UI (use defaults; tuning is separate phase)
- WebSocket or SSE for GEX updates (HTTP polling sufficient)
- Historical backfill of absorption events
- Session replay integration
- Custom BarsType dependency
- More than 3 level sources
- Exhaustion, Imbalance, Auction, or any other detector types
- Objects allocated in OnMarketData hot path (no `new`, no string concat, no LINQ)
- VP LVN recalculation per-tick (bar close only)
- Non-thread-safe GEX profile swap (MUST use `Interlocked.Exchange(ref _gexProfile, newProfile)`)
- Any single `.cs` file exceeding 1000 lines (extract utility classes: GexClient, VpLvnEngine, ConfluenceEngine into AddOn or inner classes)
- OnMarketData callback exceeding 100μs average (performance budget: <50μs target, <100μs max with dual-indicator load)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (NinjaTrader compile + Output Window + chart visual inspection)
- **Automated tests**: None (NinjaScript has no unit test runner; verification via compile + runtime diagnostics)
- **Framework**: NT8 compile check + `Print()` diagnostics + `nt8-compile.ps1` automation

### QA Policy
Every task includes agent-executed QA scenarios:
- **Compile**: `nt8-compile.ps1 -CheckErrors` → SUCCESS
- **Runtime**: Add indicator to NQ 1-min chart, verify no Output Window errors
- **Diagnostics**: `Print()` statements for level counts, API responses, confluence zones
- **Visual**: `capture_screenshot(region="chart")` for level rendering verification

Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Research — MUST complete before implementation):
├── Task R1: MadeLevels.com file discovery — find where it stores levels on disk [deep]
├── Task R2: FlashAlpha per-strike GEX endpoint analysis — response format, rendering approach [deep]
├── Task R3: Absorption detector backtesting — run ABS-01..04 on historical NQ data, optimize parameters for confluence-level alpha [ultrabrain]
├── Task R4: FootprintV7 assessment — identify gaps, verify tick handling correctness, document what needs fixing [deep]

Wave 1 (Foundation — after Wave 0):
├── Task 2: Indicator skeleton + properties + lifecycle [quick]
├── Task 1: MadeLevels file bridge reader (depends: 2, R1) [deep]

Wave 2 (Data sources — after Wave 1, MAX PARALLEL):
├── Task 3: VP LVN engine (depends: 2) [deep]
├── Task 4: FlashAlpha GEX polling + per-strike bar rendering (depends: 2, R2) [deep]

Wave 3 (Signal infrastructure — after Wave 2):
├── Task 5: Confluence engine (depends: 1, 3, 4) [deep]
├── Task 6: Tick handler + FootprintBar builder (depends: 2, R4) [deep]
├── Task 7: SessionContext population (depends: 2, 6) [quick]

Wave 4 (Integration — after Wave 3):
├── Task 8: Absorption monitoring + alerts with optimized parameters (depends: 5, 6, 7, R3) [deep]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
├── F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| R1 | — | 1 | 0 |
| R2 | — | 4 | 0 |
| R3 | — | 8 | 0 |
| R4 | — | 6 | 0 |
| 2 | — | 1, 3, 4, 5, 6, 7 | 1 |
| 1 | R1, 2 | 5 | 1 |
| 3 | 2 | 5 | 2 |
| 4 | 2, R2 | 5 | 2 |
| 5 | 1, 3, 4 | 8 | 3 |
| 6 | 2, R4 | 7, 8 | 3 |
| 7 | 2, 6 | 8 | 3 |
| 8 | 5, 6, 7, R3 | F1-F4 | 4 |

### Agent Dispatch Summary

- **Wave 1**: **2 tasks** — T2 → `quick`, T1 → `deep`
- **Wave 2**: **2 tasks** — T3 → `deep`, T4 → `deep`
- **Wave 3**: **3 tasks** — T5 → `deep`, T6 → `deep`, T7 → `quick`
- **Wave 4**: **1 task** — T8 → `deep`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [ ] R1. Research: MadeLevels.com File Discovery

  **What to do**:
  - Search NT8 directories for any files created/modified by MadeLevels.com indicator
  - Check: `C:\Users\Tea\Documents\NinjaTrader 8\db\`, `bin\Custom\`, workspace XMLs, template files
  - Search for `.xml`, `.json`, `.csv`, `.dat`, `.cfg` files with "mad", "level", "made" in name/content
  - Check if MadeLevels has a data export feature, API, or writes to a known location
  - Visit MadeLevels.com for documentation on data access/export
  - Document: file path, format, update frequency, fields available

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]

  **Parallelization**: Wave 0, parallel with R2/R3/R4
  **Blocks**: Task 1
  **Acceptance Criteria**: File location + format documented, or confirmed no file access available (fallback to manual)

  **QA Scenarios**:
  ```
  Scenario: MadeLevels file discovery
    Tool: Bash (file system search)
    Steps:
      1. Search C:\Users\Tea\Documents\NinjaTrader 8\ recursively for files with "mad" or "level" in name
      2. Check modification dates for recently-touched files when MadeLevels was active
      3. Document file path, format, and sample content
    Expected Result: At least one file identified with parseable level data, OR documented confirmation that no files exist
    Evidence: .sisyphus/evidence/r1-madlevels-files.txt
  ```

- [ ] R2. Research: FlashAlpha Per-Strike GEX Endpoint

  **What to do**:
  - Make test call to `GET /v1/exposure/gex/QQQ` with Growth tier API key
  - Document exact JSON response structure: field names, data types, number of strikes returned
  - Determine: is net_gex in dollars, contracts, or notional? What units?
  - Test call to `GET /v1/exposure/gex/NDX` — is NDX available as alternative to QQQ?
  - Document rate limits for Growth tier
  - Design rendering approach: how to draw horizontal bars at each NQ-mapped strike using SharpDX
  - Reference TraderGEX Pro visual design from user's screenshot

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 0, parallel with R1/R3/R4
  **Blocks**: Task 4
  **Acceptance Criteria**: Response JSON documented, rendering approach designed, rate limits confirmed

  **QA Scenarios**:
  ```
  Scenario: FlashAlpha GEX endpoint test
    Tool: Bash (curl or Python request)
    Steps:
      1. Call GET https://lab.flashalpha.com/v1/exposure/gex/QQQ with X-Api-Key header
      2. Parse response JSON, document structure
      3. Verify per-strike data includes strike price + net_gex value
      4. Count number of strikes returned
    Expected Result: JSON response with 10+ strikes, each having a price and gamma value
    Evidence: .sisyphus/evidence/r2-gex-response.json
  ```

- [ ] R3. Research: Absorption Detector Code Analysis + Parameter Sensitivity

  **What to do**:
  - Deep code review of AbsorptionDetector (ABS-01..04) and DeltaDetector (DELT-01, DELT-03, DELT-05)
  - For each signal: document exact trigger conditions, threshold math, edge cases, false-positive risks
  - Parameter sensitivity analysis (code-based, not empirical):
    - ABS-01: How does AbsorbWickMin (20% vs 30% vs 40%) change trigger frequency? Math analysis of volume distribution
    - ABS-01: How does AbsorbDeltaMax (0.08 vs 0.12 vs 0.16) affect false positives vs missed signals?
    - ABS-03: StopVolMult at 2.0x — is this appropriate for NQ's volume profile? Check VolEma ranges
    - ABS-04: EvrRangeCap at 0.30 × ATR — is this too tight for NQ's typical range?
  - Cross-reference with trading knowledge: which absorption patterns are most reliable at institutional levels (VP LVN, GEX walls)?
  - Review academic/practitioner literature on absorption as a reversal signal
  - Determine which signals to INCLUDE vs EXCLUDE for the confluence absorber, with rationale
  - Determine recommended Strength threshold for alerting (conservative vs aggressive)
  - Document findings in `.sisyphus/research/r3-detector-analysis.md` with: signal ID, parameters analyzed, sensitivity assessment, recommendation, rationale

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
  - **Skills**: [`trading-knowledge`]

  **Parallelization**: Wave 0, parallel with R1/R2/R4
  **Blocks**: Task 8
  **Acceptance Criteria**: Document at `.sisyphus/research/r3-detector-analysis.md` containing: per-signal analysis, parameter sensitivity, inclusion/exclusion recommendation with rationale, suggested Strength threshold

  **QA Scenarios**:
  ```
  Scenario: Research deliverable completeness
    Tool: Bash (read file)
    Steps:
      1. Read .sisyphus/research/r3-detector-analysis.md
      2. Verify sections exist for: ABS-01, ABS-02, ABS-03, ABS-04, DELT-01, DELT-03, DELT-05
      3. Verify each section has: parameter analysis, sensitivity assessment, recommendation
      4. Verify a "Summary" section with final signal selection and threshold
    Expected Result: Document with 7 signal analyses + summary with concrete recommendations
    Evidence: .sisyphus/evidence/r3-analysis-check.txt
  ```

- [ ] R4. Research: FootprintV7 Assessment + Gap Analysis

  **What to do**:
  - Read DEEP6FootprintV7.cs thoroughly — document current capabilities and limitations
  - Assess tick handling correctness: is aggressor classification accurate? Lock contention analysis?
  - Identify gaps: what's missing for production-quality absorption data?
  - Verify: does FootprintBar.AddTrade() correctly accumulate bid/ask volume per price level?
  - Verify: does Finalize() correctly compute delta, POC, wick volumes?
  - Check: does OnMarketDepth capture sufficient DOM depth for absorption detection?
  - Document: what needs fixing vs what works, estimated effort for each fix
  - Determine: can we use FootprintV7 patterns as-is for the Confluence Absorber, or do we need fixes first?

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]

  **Parallelization**: Wave 0, parallel with R1/R2/R3
  **Blocks**: Task 6
  **Acceptance Criteria**: Gap list with severity ratings, clear go/no-go for using FootprintV7 patterns
  **Decision Gate**: After R4 completes, one of three paths:
  - **GO**: FootprintV7 patterns are sound → Task 6 copies pattern as-is
  - **FIX-FIRST**: Critical bugs found → add fix tasks before Task 6, re-sequence waves
  - **REDESIGN**: Fundamental issues → Task 6 builds simplified tick accumulator without FootprintV7 dependency

  **QA Scenarios**:
  ```
  Scenario: FootprintV7 gap assessment deliverable
    Tool: Bash (read file + code review)
    Steps:
      1. Read R4 output document
      2. Verify it lists: capabilities, limitations, gap severity ratings
      3. Verify it includes a clear GO/FIX-FIRST/REDESIGN recommendation
      4. Verify tick handling correctness assessment (aggressor classification, lock analysis)
    Expected Result: Document with gap list, severity ratings, and one of the three decision recommendations
    Evidence: .sisyphus/evidence/r4-footprint-assessment.txt
  ```

- [ ] 1. MadeLevels.com File Bridge — Discover Storage + Build Reader

  **What to do**:
  - Investigate where MadeLevels.com NT8 indicator stores its level data on disk:
    - Check `C:\Users\Tea\Documents\NinjaTrader 8\` for MadeLevels config/data files
    - Search for files created/modified by MadeLevels: `*.xml`, `*.json`, `*.csv`, `*.dat` in NT8 directories
    - Check NT8 workspace/template files for serialized indicator state
    - Check if MadeLevels writes to a known output directory
  - Build a file reader class (`MadeLevelsFileReader`) that:
    - Watches the discovered file path for changes (FileSystemWatcher or poll-on-timer)
    - Parses level data (price + level type) into `List<double>` of active levels
    - Thread-safe: file read on background thread, copy-on-write to chart thread
  - Fallback: if no file discovered, provide manual input via comma-separated price string property
  - Integrate reader into DEEP6ConfluenceAbsorber skeleton

  **Must NOT do**:
  - Modify MadeLevels.com source code (commercial, not ours)
  - Attempt to read DrawObjects cross-indicator (NT8 API limitation)
  - Reverse-engineer MadeLevels proprietary algorithms

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 file system knowledge, indicator data storage patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Task 5 (Confluence engine needs MadeLevels data)
  - **Blocked By**: None

  **References**:
  - `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\` — where MadeLevels indicator .cs file likely lives
  - `C:\Users\Tea\Documents\NinjaTrader 8\db\` — NT8 database directory for cached indicator data
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs` — pattern for background timer-based file/data reading
  - MadeLevels.com website — documentation on data export or API if available

  **Acceptance Criteria**:
  - [ ] MadeLevels data file location identified OR fallback manual input provided
  - [ ] File reader parses at least 1 level correctly from discovered file
  - [ ] Thread-safe read (no chart thread blocking)
  - [ ] `Print()` shows "MadeLevels: N levels loaded from {path}" or "MadeLevels: manual mode, N levels"
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: File discovery and parsing
    Tool: Bash (file search + nt8-compile.ps1)
    Preconditions: MadeLevels indicator installed and has been run on NT8
    Steps:
      1. Search NT8 directories for MadeLevels data files
      2. Identify file format (XML/JSON/CSV)
      3. Parse at least one price level from the file
      4. Compile indicator with file reader integrated
    Expected Result: "MadeLevels: N levels loaded from {path}" in Output Window
    Failure Indicators: No MadeLevels files found, parse errors, or 0 levels
    Evidence: .sisyphus/evidence/task-1-madlevels-discovery.txt

  Scenario: Fallback to manual input
    Tool: Bash (nt8-compile.ps1)
    Preconditions: No MadeLevels data file available
    Steps:
      1. Set ManualLevels property to "20000,20050,20100"
      2. Load indicator
      3. Verify levels parsed from manual input
    Expected Result: "MadeLevels: manual mode, 3 levels" in Output Window
    Evidence: .sisyphus/evidence/task-1-manual-fallback.txt
  ```

  **Commit**: YES — group 1
  - Message: `feat(confluence-absorber): add MadeLevels file bridge reader`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 2. Indicator Skeleton — File, Properties, Lifecycle, AddDataSeries

  **What to do**:
  - Create `DEEP6ConfluenceAbsorber.cs` in `ninjatrader/Custom/Indicators/DEEP6/`
  - Implement `OnStateChange` with all states: SetDefaults, Configure, DataLoaded, Terminated
  - Add `AddDataSeries(BarsPeriodType.Minute, 1)` in Configure (ALWAYS add — even if chart is 1-min, secondary series is needed for VP accumulation via BarsInProgress==1)
  - Define all NinjaScriptProperty inputs:
    - VP: Rows (200), VpLvnStrength (15)
    - GEX: FlashAlphaApiKey (string), GexPollIntervalSeconds (300), GexSymbol ("QQQ")
    - Confluence: ProximityTicks (8), MinSources (2)
    - Alert: CooldownBars (5), AlertSoundFile (default NT8 alert)
    - Debug: EnableDiagnostics (bool)
  - Pre-allocate SessionContext, detector instances in State.DataLoaded
  - Stub MadeLevels file reader integration point (actual reader from Task 1)
  - Implement empty OnBarUpdate (BarsInProgress routing) and stub OnMarketData/OnMarketDepth
  - Use `System.Math` fully qualified throughout (commit 1d61d0b fix)
  - Must compile clean as an empty indicator

  **Must NOT do**:
  - Implement any calculation logic yet (stubs only)
  - Use `HttpClient` or async patterns
  - Add SharpDX rendering (later task)
  - Allocate in OnMarketData

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`, `nt8-new`]
    - `nt8-expert`: NT8 deploy/compile workflow
    - `nt8-new`: NinjaScript code generation patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Tasks 3, 4, 5, 6, 7
  - **Blocked By**: None

  **References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs` — OnStateChange lifecycle pattern with System.Threading.Timer setup (search for `State.Configure` and `System.Threading.Timer`)
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:40-68` — AddDataSeries pattern for 1-min bars
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs` — Timer-based background polling pattern for external data
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6_ZoneEntry_v2.cs:111-137` — Guard pattern: skip AddDataSeries if chart already matches
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — SessionContext class to pre-allocate
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` — Direct instantiation pattern
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs` — Direct instantiation pattern

  **Acceptance Criteria**:
  - [ ] File created at correct path with proper namespace
  - [ ] All properties have [NinjaScriptProperty] attributes with correct types/ranges
  - [ ] AddDataSeries called unconditionally for 1-min secondary series
  - [ ] MadeLevels file reader integration point stubbed
  - [ ] SessionContext and detectors pre-allocated
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: Skeleton compiles and loads on chart
    Tool: Bash (nt8-compile.ps1 + nt8-status.ps1)
    Preconditions: DEEP6ConfluenceAbsorber.cs created and deployed
    Steps:
      1. Deploy via nt8-deploy.ps1 -Target Indicators
      2. Compile via nt8-compile.ps1 -WaitSeconds 15 -CheckErrors
      3. Check nt8-status.ps1 -ShowErrors for new errors
    Expected Result: [COMPILE-RESULT] SUCCESS, no new errors
    Failure Indicators: CS#### errors, namespace conflicts, missing type references
    Evidence: .sisyphus/evidence/task-2-compile.txt
  ```

  **Commit**: YES — group 2
  - Message: `feat(confluence-absorber): add indicator skeleton with properties and lifecycle`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 3. VP LVN Engine — Weekly Profile with 1-Min Resolution

  **What to do**:
  - Implement weekly volume profile calculation inside DEEP6ConfluenceAbsorber
  - Accumulate 1-min bars from BarsInProgress==1 into period bar list (pattern from VPLowTFLVNLevels.cs)
  - Detect weekly period boundaries via `GetPeriodStart()` (Monday-based week start)
  - Build profile: distribute volume across price bins (200 rows)
  - Detect LVN levels: local minima with LvnStrength=15 neighbors (identical algorithm to VolumeProfileLVN.cs FindLVNs)
  - Store detected LVN prices in `List<double> _vpLvnLevels`
  - Draw LVN levels as horizontal lines (color-coded: bull=blue, bear=orange) using `Draw.Line`
  - VP disabled until MinBarsForVP (120) bars accumulated — print "VP warming up" diagnostic
  - Rebuild profile at bar close only (NOT per-tick)

  **Must NOT do**:
  - Render full volume profile histogram (only LVN level lines)
  - Recalculate per tick
  - Support daily or monthly profiles (weekly only for this indicator)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 compile verification

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 4)
  - **Blocks**: Task 5 (Confluence needs VP levels)
  - **Blocked By**: Task 2 (skeleton must exist)

  **References**:
  - `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\VolumeProfileLVN.cs:185-247` — BuildProfile + FindLVNs algorithm (just fixed in this session)
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:71-95` — BarsInProgress==1 accumulation + period boundary detection
  - `C:\Users\Tea\DEEP6\.planning\research\pine\VP_LVN.pine:37-68` — Pine Script LVN detection (original reference implementation)

  **Acceptance Criteria**:
  - [ ] Weekly profile accumulates 1-min bars correctly
  - [ ] LVN levels detected match TradingView output (same algorithm, same parameters)
  - [ ] `Print()` shows "VP: N LVN levels detected" with N > 0 after 120+ bars
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: VP LVN produces levels after warm-up
    Tool: Bash (nt8-compile.ps1 + nt8-status.ps1)
    Preconditions: Indicator deployed with VP engine, chart has 120+ bars of 1-min NQ data
    Steps:
      1. Compile and verify SUCCESS
      2. Check Output Window for "VP warming up" message during first 120 bars
      3. Check Output Window for "VP: N LVN levels detected" after warm-up
      4. Verify N > 0
    Expected Result: VP produces at least 1 LVN level after warm-up period
    Failure Indicators: "VP: 0 LVN levels detected" or no VP diagnostic output
    Evidence: .sisyphus/evidence/task-3-vp-levels.txt

  Scenario: VP does not fire during warm-up
    Tool: Bash (nt8-status.ps1 -ShowLog 50)
    Preconditions: Fresh indicator load with < 120 bars
    Steps:
      1. Check Output Window for "VP warming up" message
      2. Verify no LVN lines drawn before 120 bars
    Expected Result: "VP warming up" appears, no premature LVN detection
    Evidence: .sisyphus/evidence/task-3-vp-warmup.txt
  ```

  **Commit**: YES — group 2
  - Message: `feat(confluence-absorber): add VP LVN weekly profile engine`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 4. FlashAlpha GEX Polling — HTTP Timer, Response Parsing, QQQ→NQ Mapping

  **What to do**:
  - Implement FlashAlpha HTTP client inside the indicator (pattern from DEEP6GexLevels.cs:388-437)
  - Use `System.Threading.Timer` for polling (NOT async, NOT chart thread)
  - Set `ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12`
  - HTTP GET to `https://lab.flashalpha.com/v1/exposure/gex/QQQ` (Growth tier — per-strike GEX heatmap) with `X-Api-Key` header
  - ALSO call `https://lab.flashalpha.com/v1/exposure/levels/QQQ` for summary levels (gamma flip, call/put walls)
  - Parse JSON: per-strike response returns `{"strikes": [{strike: float, net_gex: float}, ...]}` — full gamma exposure by strike
  - Map ALL strikes QQQ→NQ: `nq_level = qqq_strike / qqq_spot * nq_spot` (nq_spot from NinjaTrader's current chart price)
  - Store mapped profile in `GexProfile` object: per-strike {nq_price, net_gex_value}, plus summary levels {gamma_flip, call_wall, put_wall}
  - Copy-on-write pattern: build new profile on timer thread, atomic reference swap to chart thread
  - **Render as horizontal bars at each strike** (like TraderGEX Pro screenshot):
    - Green bars extending RIGHT from price axis = positive gamma (dealer long gamma)
    - Red bars extending RIGHT from price axis = negative gamma (dealer short gamma)
    - Bar LENGTH proportional to |net_gex| magnitude (normalize to chart width)
    - Gamma flip zone (where net_gex crosses zero) drawn with distinct solid line
    - Bars update dynamically as GEX data refreshes throughout the day
  - SharpDX OnRender for bar drawing (NOT Draw.Rectangle — too many objects). Follow DEEP6GexLevels.cs rendering pattern.
  - Stale data handling: >poll_interval×2 (default >10 min) = dim lines + amber warning text, >poll_interval×4 (default >20 min) = exclude from confluence
  - Retry with exponential backoff on API errors (5s → 15s → 60s → 120s)
  - API key read from indicator property (user enters in settings) or from environment variable

  **Must NOT do**:
  - Use HttpClient (not available in .NET Framework 4.8 NinjaScript context)
  - Make HTTP calls on chart thread
  - Use WebSocket or SSE
  - Poll more frequently than every 60 seconds (API rate limit consideration)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 compile verification

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 3)
  - **Blocks**: Task 5 (Confluence needs GEX levels)
  - **Blocked By**: Task 2 (skeleton must exist)

  **References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs:388-437` — FlashAlphaClient: HTTP GET, TLS 1.2, regex JSON parsing, retry logic
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs:892-914` — QQQ→NQ price ratio mapping
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs:962-990` — Adaptive polling intervals by session time
  - `nq_atlas/nq_mapper.py:10` — QQQ→NQ formula: `nq_level = qqq_level / qqq_spot * nq_spot`
  - `nq_atlas/flashalpha_client.py` — Python FlashAlpha SDK wrapper (API endpoint reference)
  - `.env.atlas` — FlashAlpha API key environment variable name: `NQ_ATLAS_FLASHALPHA_API_KEY`

  **Acceptance Criteria**:
  - [ ] FlashAlpha API returns per-strike GEX data within 10s of indicator load
  - [ ] `Print()` shows "GEX fetch success, N strikes" with N > 10 and valid NQ-range prices (19000-22000)
  - [ ] QQQ→NQ mapping produces sane values (not QQQ range, not zero)
  - [ ] Horizontal GEX bars visible on chart: green=positive gamma, red=negative gamma, length proportional to magnitude
  - [ ] Gamma flip zone clearly marked with distinct line
  - [ ] Bars update visually when GEX data refreshes (every 5 min)
  - [ ] Stale warning appears after simulated timeout (>2 min)
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: GEX levels fetch and display
    Tool: Bash (nt8-compile.ps1 + nt8-status.ps1)
    Preconditions: Indicator deployed with FlashAlpha API key configured, market hours
    Steps:
      1. Compile and verify SUCCESS
      2. Add indicator to NQ 1-min chart
      3. Wait 10 seconds
      4. Check Output Window for "GEX fetch success" message
      5. Verify mapped levels are in NQ price range (19000-22000)
    Expected Result: "GEX fetch success, 7 levels" with valid NQ prices
    Failure Indicators: "GEX fetch failed", prices in QQQ range (400-500), or zero levels
    Evidence: .sisyphus/evidence/task-4-gex-fetch.txt

  Scenario: GEX graceful degradation on API failure
    Tool: Bash (nt8-status.ps1)
    Preconditions: Invalid API key or no network
    Steps:
      1. Set API key to "INVALID"
      2. Load indicator
      3. Check Output Window for error handling
    Expected Result: "GEX fetch failed: 401/403" log, no crash, indicator continues
    Evidence: .sisyphus/evidence/task-4-gex-error.txt
  ```

  **Commit**: YES — group 3
  - Message: `feat(confluence-absorber): add FlashAlpha GEX polling with QQQ→NQ mapping`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 5. Confluence Engine — Level Aggregation, Proximity Matching, Zone Management

  **What to do**:
  - Aggregate levels from all 3 sources into a unified list: `List<ConfluenceLevel>` where each entry has {Price, Source (VP/GEX/MAD), Strength}
  - Read MadeLevels prices from file bridge reader (built in Task 1) — degrade gracefully if no data available
  - Read VP LVN levels from internal list
  - Read GEX levels from latest GexProfile snapshot
  - **Proximity matching**: For each pair of levels from different sources, if |price1 - price2| ≤ ProximityTicks × TickSize, group them into a ConfluenceZone
  - ConfluenceZone: {MidPrice, SourceCount (2 or 3), Width (max-min of grouped levels), IsActive (price within zone)}
  - Deduplicate: if two levels from the same source are within threshold, count as 1
  - Max 5 active zones tracked simultaneously (prioritize by source count, then proximity to price)
  - Draw confluence zones as shaded rectangles on chart (semi-transparent, color intensity by source count)
  - Zone activation: when `Close[0]` enters a zone (price between zone high and zone low), set `IsActive = true`
  - Zone expiration: zones expire at session end (RTH close) or when all component levels shift away
  - Run confluence calculation at bar close only (efficient)
  - `Print()` diagnostic: "CONFLUENCE: N zones, M active" on each recalculation

  **Must NOT do**:
  - Run confluence matching per tick
  - Support more than 3 level sources
  - Auto-adjust ProximityTicks based on volatility (static parameter for now)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential — needs all 3 sources ready)
  - **Blocks**: Task 8 (Absorption needs confluence zones)
  - **Blocked By**: Tasks 1, 3, 4

  **References**:
  - Task 1 output — MadeLevels file bridge reader providing `List<double>` of price levels
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` — ABS-07 VA Extreme pattern (proximity bonus, similar concept)

  **Acceptance Criteria**:
  - [ ] All 3 sources contribute levels to the unified list
  - [ ] Confluence zones correctly identified when 2+ sources stack within ProximityTicks
  - [ ] Zones visually highlighted on chart as shaded rectangles
  - [ ] `Print()` shows "CONFLUENCE: N zones, M active" with N ≥ 1 when levels stack
  - [ ] Graceful degradation: works with 2 sources if 1 is unavailable
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: Confluence detected when levels stack
    Tool: Bash (nt8-status.ps1)
    Preconditions: VP LVN and GEX both producing levels, MadeLevels on chart
    Steps:
      1. Load indicator on NQ 1-min chart with MadeLevels
      2. Wait for VP warm-up (120+ bars) and GEX fetch
      3. Check Output Window for "CONFLUENCE:" messages
      4. Verify zone count > 0 when levels naturally overlap
    Expected Result: At least 1 confluence zone detected during session
    Failure Indicators: "CONFLUENCE: 0 zones" persistently, or no diagnostic output
    Evidence: .sisyphus/evidence/task-5-confluence.txt

  Scenario: Graceful degradation without MadeLevels
    Tool: Bash (nt8-status.ps1)
    Preconditions: Indicator loaded WITHOUT MadeLevels on chart
    Steps:
      1. Load only DEEP6ConfluenceAbsorber (no MadeLevels)
      2. Verify no crash or null reference errors
      3. Check Output Window for "MadeLevels: not loaded, using VP + GEX only"
    Expected Result: Indicator runs with 2 sources, logs warning, no crash
    Evidence: .sisyphus/evidence/task-5-degradation.txt
  ```

  **Commit**: YES — group 4
  - Message: `feat(confluence-absorber): add confluence engine with 3-source proximity matching`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 6. Tick Handler + FootprintBar Builder — OnMarketData/OnMarketDepth

  **What to do**:
  - Implement `OnMarketData(MarketDataEventArgs e)` following DEEP6FootprintV7.cs:347-371 pattern
  - Classify aggressor on stack: ask-side hit = buyer aggressor, bid-side hit = seller aggressor (zero allocation)
  - Lock-protected `AddTrade()` to current FootprintBar (~10-50μs lock scope)
  - FootprintBar accumulates: bidVolume/askVolume per price level, total delta, total volume, high/low/open/close, POC
  - `Finalize()` FootprintBar at bar close (OnBarUpdate, BarsInProgress==0) — compute final delta, POC, wick volumes
  - Implement `OnMarketDepth(MarketDepthEventArgs e)` for DOM snapshot — track bid/ask depth at price levels
  - Store DOM snapshot in SessionContext.BidDomLevels / AskDomLevels
  - Separate `_tickLock` for tick data, `_l2Lock` for DOM depth (different update frequencies)
  - Minimize allocations in OnMarketData: pre-allocate all buffers and dictionaries in State.DataLoaded. New price levels use pre-sized dictionaries (first-seen insert is acceptable). No per-tick heap allocation for already-tracked price levels. No string concatenation, no LINQ, no boxing.
  - Pre-allocate FootprintBar pool (reuse objects, don't create new per bar)

  **Must NOT do**:
  - Render footprint cells (this is NOT a footprint chart)
  - Use LINQ in OnMarketData
  - Allocate strings in OnMarketData
  - Process more than current bar's ticks (no historical tick replay)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (partial — with Task 5)
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 7, 8
  - **Blocked By**: Task 2 (skeleton)

  **References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:347-428` — OnMarketData tick handler: lock, aggressor classification, AddTrade pattern
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:430-480` — OnMarketDepth handler: L2 wall tracking, batched pruning
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` — FootprintBar accumulation pattern: tick-to-bar aggregation, delta tracking, volume-at-price (search for `AddTrade` or equivalent tick handler)
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — BidDomLevels, AskDomLevels fields

  **Acceptance Criteria**:
  - [ ] OnMarketData processes ticks without allocation (no `new` in hot path)
  - [ ] FootprintBar accumulates volume correctly (bid + ask = total)
  - [ ] `Print()` diagnostic shows "Bar finalized: vol=N, delta=N, poc=N" at bar close
  - [ ] DOM snapshot populated from OnMarketDepth
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: Tick processing produces valid FootprintBar
    Tool: Bash (nt8-status.ps1)
    Preconditions: Indicator on live NQ chart during market hours
    Steps:
      1. Wait for 2-3 bar closes
      2. Check Output Window for "Bar finalized:" diagnostics
      3. Verify volume > 0, delta is non-zero, POC is within bar range
    Expected Result: Each bar close produces valid footprint summary
    Failure Indicators: Volume = 0, POC outside bar range, or no diagnostic output
    Evidence: .sisyphus/evidence/task-6-footprint.txt

  Scenario: No allocations in OnMarketData (performance)
    Tool: Bash (ast_grep_search)
    Preconditions: DEEP6ConfluenceAbsorber.cs complete
    Steps:
      1. Search OnMarketData method body for `new ` keyword
      2. Search for string concatenation (`+` with string)
      3. Search for LINQ (.Where, .Select, .OrderBy)
    Expected Result: Zero matches for allocating patterns in OnMarketData
    Evidence: .sisyphus/evidence/task-6-alloc-check.txt
  ```

  **Commit**: YES — group 4
  - Message: `feat(confluence-absorber): add tick handler and FootprintBar builder`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 7. SessionContext Population — ATR, VolEma, Rolling Histories

  **What to do**:
  - Compute ATR(20) from primary bar series, store in `_session.Atr20`
  - Compute EMA(20) of volume from primary bar series, store in `_session.VolEma20`
  - Set `_session.TickSize` from `TickSize` property
  - Track VAH/VAL from VP LVN calculation (optional: use VP data if available, otherwise skip)
  - After each bar's FootprintBar is finalized and detectors evaluated:
    - Push bar delta to `_session.DeltaHistory`
    - Push CVD to `_session.CvdHistory`
    - Push close price to `_session.PriceHistory`
  - Call `_session.ResetSession()` at RTH boundary (09:30 ET)
  - Store prior bar reference: `_session.PriorBar = currentBar` after evaluation

  **Must NOT do**:
  - Compute session-level statistics beyond what SessionContext requires
  - Add custom fields to SessionContext (use existing fields only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 6 for FootprintBar data)
  - **Parallel Group**: Wave 3 (after Task 6)
  - **Blocks**: Task 8
  - **Blocked By**: Tasks 2, 6

  **References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — All fields to populate: Atr20, VolEma20, TickSize, VAH, VAL, DeltaHistory, CvdHistory, PriceHistory, PriorBar, BidDomLevels, AskDomLevels
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` — How existing indicator computes ATR/VolEma

  **Acceptance Criteria**:
  - [ ] SessionContext.Atr20 populated with non-zero value after 20 bars
  - [ ] SessionContext.VolEma20 populated with non-zero value after 20 bars
  - [ ] Rolling histories grow each bar (DeltaHistory.Count increases)
  - [ ] Session resets at RTH boundary
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: SessionContext populated correctly
    Tool: Bash (nt8-status.ps1)
    Preconditions: Indicator running on live NQ chart, 20+ bars elapsed
    Steps:
      1. Check Output Window for "Session: ATR=N, VolEma=N, History=N bars" diagnostic
      2. Verify ATR > 0, VolEma > 0, History count > 0
    Expected Result: All SessionContext fields populated with sane values
    Evidence: .sisyphus/evidence/task-7-session.txt
  ```

  **Commit**: YES — group 4
  - Message: `feat(confluence-absorber): add SessionContext population`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

- [ ] 8. Absorption Monitoring + Alert System — Detectors at Confluence Zones

  **What to do**:
  - At each bar close (OnBarUpdate, BarsInProgress==0):
    1. Check if any confluence zone IsActive (price within zone)
    2. If yes: call `_absorptionDetector.OnBar(currentFootprintBar, _session)` → get `SignalResult[]`
    3. Also call `_deltaDetector.OnBar(currentFootprintBar, _session)` → get `SignalResult[]`
    4. Filter results: keep ABS-01, ABS-02, ABS-03, ABS-04 with Strength ≥ 0.4
    5. Filter delta results: keep DELT-01 (direction), DELT-03 (reversal), DELT-05 (CVD flip) as confirmation
    6. **Absorption confirmed** when: any ABS signal fires AND at least one DELT signal agrees on direction
    7. Direction: ABS signal's Direction field (+1 long, -1 short)
  - On confirmation:
    - Check cooldown: skip if fewer than CooldownBars (5) since last alert at this zone
    - Draw arrow: `Draw.ArrowUp` or `Draw.ArrowDown` at signal bar, at absorption price
    - Play sound: `Alert("ConfAbsorb", Priority.High, "Absorption at confluence", alertSoundFile, 10, Brushes.Yellow, Brushes.Black)`
    - Print diagnostic: "ABSORPTION CONFIRMED: {Direction} at {Price}, Zone sources={N}, ABS={SignalId}, Strength={S}"
    - Record alert timestamp + zone for cooldown tracking
  - Arrow persistence: arrows stay on chart until session end (removed on session reset)
  - Color: green arrow for long, red arrow for short
  - Zone visual: briefly flash the confluence zone rectangle brighter when alert fires

  **Must NOT do**:
  - Place orders or manage positions
  - Use detectors beyond AbsorptionDetector + DeltaDetector
  - Alert outside of confluence zones (absorption alone is NOT sufficient)
  - Fire alerts during VP warm-up period

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (final implementation task)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 5, 6, 7

  **References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` — Full algorithm, OnBar signature, SignalResult output
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs` — DELT-01, DELT-03, DELT-05 signals
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs` — Direction, Strength, SignalId, Detail fields
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6_ZoneEntry.cs` — Arrow drawing + Alert() pattern for entry signals
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` — Arrow rendering at signal bars

  **Acceptance Criteria**:
  - [ ] AbsorptionDetector.OnBar called only when price is in active confluence zone
  - [ ] Arrow drawn at correct price/bar when absorption confirms
  - [ ] Alert sound plays on confirmation
  - [ ] Cooldown prevents rapid re-alerting (5 bars minimum)
  - [ ] No alerts fire outside confluence zones
  - [ ] No alerts during VP warm-up
  - [ ] `Print()` shows full diagnostic with signal details
  - [ ] `nt8-compile.ps1 -CheckErrors` → SUCCESS

  **QA Scenarios**:
  ```
  Scenario: Full signal chain fires during live trading
    Tool: Bash (nt8-status.ps1 + capture_screenshot)
    Preconditions: Indicator fully assembled on live NQ chart during RTH, VP warmed up, GEX loaded, MadeLevels active
    Steps:
      1. Monitor Output Window for "ABSORPTION CONFIRMED" messages
      2. When alert fires, verify arrow visible on chart
      3. Verify direction matches signal (green=long, red=short)
      4. Capture screenshot showing arrow + confluence zone
    Expected Result: Arrow at confluence zone, diagnostic output with signal details
    Failure Indicators: No alerts during entire session, or alerts outside zones
    Evidence: .sisyphus/evidence/task-8-absorption-alert.png

  Scenario: Cooldown prevents rapid re-alerting
    Tool: Bash (nt8-status.ps1)
    Preconditions: First alert has fired at a zone
    Steps:
      1. After first alert, check if second alert fires within 5 bars at same zone
      2. After 5+ bars, check if re-alert is possible
    Expected Result: No duplicate alerts within cooldown window
    Evidence: .sisyphus/evidence/task-8-cooldown.txt

  Scenario: No alerts outside confluence zones
    Tool: Bash (nt8-status.ps1)
    Preconditions: Indicator running with absorption signals firing (visible in diagnostics)
    Steps:
      1. Monitor diagnostic output for absorption signals
      2. Verify ALL "ABSORPTION CONFIRMED" messages include "Zone sources=N" with N ≥ 2
      3. Search Output Window for any alert without zone association
    Expected Result: Zero alerts without confluence zone context
    Evidence: .sisyphus/evidence/task-8-zone-gate.txt
  ```

  **Commit**: YES — group 5
  - Message: `feat(confluence-absorber): add absorption monitoring + alert system`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6ConfluenceAbsorber.cs`
  - Pre-commit: `nt8-compile.ps1 -CheckErrors`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, check method/property). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `nt8-compile.ps1 -CheckErrors`. Review DEEP6ConfluenceAbsorber.cs for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify `System.Math` is fully qualified. Verify no allocations in OnMarketData. Verify lock scopes are minimal.
  Output: `Compile [PASS/FAIL] | OnMarketData alloc-free [YES/NO] | Namespace safety [YES/NO] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `nt8-expert` skill)
  Deploy indicator to NT8. Add to 1-min NQ chart. Verify: VP LVN levels appear, GEX levels appear, confluence zones highlight, no Output Window errors during 5-min runtime. Capture screenshots as evidence.
  Output: `VP LVN [PASS/FAIL] | GEX [PASS/FAIL] | Confluence [PASS/FAIL] | Runtime Errors [CLEAN/N issues] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual code. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT Have" compliance. Flag any detector usage beyond AbsorptionDetector + DeltaDetector. Flag any auto-execution logic.
  Output: `Tasks [N/N compliant] | Scope [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Commit 1**: `feat(confluence-absorber): add indicator skeleton with properties and lifecycle` — DEEP6ConfluenceAbsorber.cs
- **Commit 2**: `feat(confluence-absorber): add MadeLevels file bridge + VP LVN engine` — DEEP6ConfluenceAbsorber.cs
- **Commit 3**: `feat(confluence-absorber): add FlashAlpha GEX polling` — DEEP6ConfluenceAbsorber.cs
- **Commit 4**: `feat(confluence-absorber): add confluence engine + tick handler` — DEEP6ConfluenceAbsorber.cs
- **Commit 5**: `feat(confluence-absorber): add absorption monitoring + alerts` — DEEP6ConfluenceAbsorber.cs
- Pre-commit for all: `nt8-compile.ps1 -CheckErrors`

---

## Success Criteria

### Verification Commands
```bash
nt8-compile.ps1 -CheckErrors  # Expected: [COMPILE-RESULT] SUCCESS
nt8-status.ps1 -ShowErrors     # Expected: no new errors
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Indicator compiles clean
- [ ] VP LVN levels render on chart (weekly profile, 1-min resolution)
- [ ] GEX levels render on chart (FlashAlpha API, QQQ→NQ mapped)
- [ ] Confluence zones highlighted when 2+ sources stack
- [ ] Absorption arrow + sound fires at confluence zone
- [ ] No Output Window errors during 5-min live runtime
- [ ] Graceful degradation when GEX API unavailable
