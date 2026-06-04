# ES/NQ Stacked Absorption Confluence Arrows

## TL;DR

> **Quick Summary**: Build a single NinjaTrader 8 indicator that detects synchronized stacked absorption across both NQ and ES at active Telegram session levels, plotting directional arrows only when both markets confirm the same bias. Runs on normal candles with hidden volumetric data series.
> 
> **Deliverables**:
> - `ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs` — Complete NinjaScript indicator
> - `ninjatrader/Custom/Indicators/DEEP6/Levels/sample-levels.csv` — Test CSV for level import
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: LIMITED — single-file sequential build with parallel verification
> **Critical Path**: Task 1 (build) → Task 2 (deploy+compile) → Task 4 (live verify)

---

## Context

### Original Request
Build an NT8 indicator for NQ and ES that detects synchronized stacked absorption and plots directional arrows only when both markets confirm the same absorption bias. Must support Telegram level import (manual + CSV), session window enforcement (8:30 AM–3:30 PM ET), configurable volume thresholds, and one-signal-per-level safety.

### Interview Summary
**Key Discussions**:
- **Volumetric data access**: User has Order Flow+ license. Use `AddVolumetric()` for hidden volumetric secondary series — chart shows normal candles, absorption logic reads volumetric data underneath
- **Simplicity emphasis**: User explicitly wants "as simple as possible — visually, graphically, and logically." Arrows only, no HUD/panels/labels
- **CSV format**: Simple `Price,Type` (one per line)
- **Volume defaults**: NQ 500 contracts/level, ES 1000 contracts/level (conservative institutional-size)
- **Verification**: Compile + add to live NQ chart

**Research Findings**:
- **Existing AbsorptionDetector.cs** in DEEP6 AddOns has 4 variants (ABS-01 through ABS-04) using `FootprintBar.Levels` — different data path from this indicator's VolumetricBarsType approach
- **VolumetricBarsType API**: `barsType.Volumes[CurrentBars[bip]].GetBidVolumeForPrice(price)` / `GetAskVolumeForPrice(price)`
- **Arrow convention from DEEP6TripleConfluenceArrows.cs**: unique tag per bar, `Low[0] - 4*TickSize` (bull) / `High[0] + 4*TickSize` (bear)
- **Session filtering**: `SessionIterator` is the robust approach per DEEP6LVNZones.cs
- **Deployment**: `nt8-deploy.ps1 -Target Indicators -Force` then `nt8-compile.ps1`
- **Namespace**: `NinjaTrader.NinjaScript.Indicators.DEEP6`

### Metis Review
**Identified Gaps** (addressed):
- **Dual AddVolumetric validation**: Must verify 3-BIP model works before building logic. Fallback to 5-BIP model (AddDataSeries + AddVolumetric per instrument) documented in Task 1
- **ES contract name**: Made a `[NinjaScriptProperty]` string input — user updates quarterly at rollover
- **Level type → arrow direction**: Support=bullish only, Resistance=bearish only, Magnet/Neutral=both (applied as default from user's spec)
- **Calculate mode**: `Calculate.OnBarClose` for V1 (volumetric data still contains full intrabar data at bar close)
- **Confirmation window**: Measured in primary chart bars (BarsInProgress 0)
- **CSV reload**: Load once at `State.DataLoaded`. Remove/re-add indicator to reload.
- **Daily expiration**: Triggered on `Bars.IsFirstBarOfSession`
- **Performance risk**: Two simultaneous volumetric feeds untested in DEEP6 — early Print verification validates data flow
- **Max level cap**: 30 levels to prevent performance degradation

---

## Work Objectives

### Core Objective
Build a single-file NinjaScript C# indicator that monitors both NQ and ES via hidden volumetric data series, detects stacked absorption near active Telegram levels, and plots directional arrows only when both instruments confirm the same bias within a configurable confirmation window.

### Concrete Deliverables
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs` — Complete indicator (~600-800 lines)
- `ninjatrader/Custom/Indicators/DEEP6/Levels/sample-levels.csv` — Test CSV file with sample levels

### Definition of Done
- [ ] `nt8-compile.ps1` returns `[COMPILE-RESULT] SUCCESS`
- [ ] Indicator loads on live NQ chart without errors
- [ ] Both NQ and ES volumetric feeds show data in Output Window
- [ ] Arrows appear only when both instruments confirm absorption at same Telegram level
- [ ] No arrows appear outside 8:30 AM – 3:30 PM ET session window
- [ ] CSV level import parses correctly and prints loaded levels
- [ ] One-signal-per-level enforced (no duplicate arrows at same level)

### Must Have
- Dual AddVolumetric for NQ + ES (hidden volumetric secondary series)
- Stacked absorption detection using VolumetricBarsType API directly
- Support/Resistance/Magnet/Neutral level categorization
- CSV import (simple `Price,Type` format)
- Manual level input via NinjaScriptProperty
- Session window enforcement (8:30 AM – 3:30 PM ET)
- Daily level expiration on session start
- One-signal-per-level with configurable reset distance
- Draw.ArrowUp (green) / Draw.ArrowDown (red) with unique tags
- Alert() with configurable sound/popup toggles
- All parameters configurable via NinjaScriptProperty

### Must NOT Have (Guardrails)
- **NO dependency on AbsorptionDetector.cs or any DEEP6 AddOn type** — use VolumetricBarsType directly, different data path
- **NO visual elements besides arrows** — no text labels, no horizontal level lines, no HUD, no info panel, no background zones
- **NO auto-trading** — pure indicator, no ATM hooks, no order entry
- **NO adaptive/dynamic volume thresholds** — fixed configurable values only
- **NO multi-timeframe scanning** — single volumetric period only
- **NO additional instruments beyond NQ + ES** — two-instrument architecture only
- **NO CSV auto-reload at runtime** — load once at startup, remove/re-add to reload
- **NO level management GUI** — CSV + NinjaScriptProperty only
- **NO historical performance tracking** — no win rate, no statistics
- **NO modification to existing AbsorptionDetector.cs or any AddOn file**

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (NinjaScript indicators have no unit test framework)
- **Automated tests**: NONE — verification via compile gates + Print() output + HERMES screenshots
- **Framework**: N/A

### QA Policy
Every task includes agent-executed QA scenarios using:
- **NT8 Compilation**: `nt8-deploy.ps1` + `nt8-compile.ps1` — binary PASS/FAIL
- **Output Window**: `Print()` statements read via HERMES screenshot of NT8 Output Window
- **Chart Screenshot**: HERMES captures chart showing arrows (or absence of arrows)
- Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Sequential Build — single file, each task builds on previous):
├── Task 1: Build full DEEP6StackedAbsorptionArrows.cs [deep]
│   (Step 1: Validate dual AddVolumetric architecture)
│   (Step 2: Level management system)
│   (Step 3: Stacked absorption detection)
│   (Step 4: Confluence + arrows + alerts + session)
│   (Step 5: Edge case guards)

Wave 2 (Deploy + Test Data — parallel after build):
├── Task 2: Deploy + compile + error fix loop [quick]
└── Task 3: Create test CSV + verify level loading [quick]

Wave 3 (Validation — after compile success):
└── Task 4: Live chart verification + screenshots [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| **1** | — | 2, 3, 4 | 1 |
| **2** | 1 | 4 | 2 |
| **3** | 1 | 4 | 2 |
| **4** | 2, 3 | F1-F4 | 3 |
| **F1-F4** | 4 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **1 task** — T1 → `deep` (nt8-expert, nt8-new skills)
- **Wave 2**: **2 tasks** — T2 → `quick` (nt8-fix skill), T3 → `quick`
- **Wave 3**: **1 task** — T4 → `unspecified-high` (display-topology skill)
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Build DEEP6StackedAbsorptionArrows.cs — Complete Indicator

  **What to do**:

  Build the full NinjaScript C# indicator file at `ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs`. This is a single-file indicator with 5 logical sections built in order. Estimated 600-800 lines.

  **CRITICAL BUILD ORDER** — validate architecture before building logic:

  **Step 1: Dual AddVolumetric Skeleton (VALIDATE FIRST)**
  - Create minimal indicator class inheriting `Indicator`
  - Namespace: `NinjaTrader.NinjaScript.Indicators.DEEP6`
  - In `State.SetDefaults`: Name, Description, `Calculate = Calculate.OnBarClose`, `IsOverlay = true`, `DrawOnPricePanel = true`, `IsSuspendedWhileInactive = true`, `BarsRequiredToPlot = 20`
  - In `State.Configure`: Call `AddVolumetric()` twice:
    ```csharp
    // BarsInProgress 0 = Primary NQ chart (normal candles — visual display)
    // BarsInProgress 1 = NQ Volumetric (hidden, data-only)
    AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, VolBarPeriod, VolumetricDeltaType.BidAsk, 1);
    // BarsInProgress 2 = ES Volumetric (hidden, data-only)
    AddVolumetric(EsInstrument, BarsPeriodType.Minute, VolBarPeriod, VolumetricDeltaType.BidAsk, 1);
    ```
  - In `OnBarUpdate`: Route by `BarsInProgress`:
    - BIP 0: Primary chart — skip (no logic here)
    - BIP 1: NQ volumetric bar closed — process NQ absorption
    - BIP 2: ES volumetric bar closed — process ES absorption
  - Add `Print()` statements for each BIP confirming data flow:
    ```csharp
    if (BarsInProgress == 1)
        Print($"NQ Vol BIP1 bar {CurrentBars[1]}: Delta={nqVolBars.Volumes[CurrentBars[1]].BarDelta}");
    if (BarsInProgress == 2)
        Print($"ES Vol BIP2 bar {CurrentBars[2]}: Delta={esVolBars.Volumes[CurrentBars[2]].BarDelta}");
    ```
  - **FALLBACK**: If `AddVolumetric()` alone fails for the ES instrument (compilation or runtime error), switch to the 5-BIP model:
    ```csharp
    AddDataSeries(Instrument.FullName, BarsPeriodType.Minute, VolBarPeriod);  // BIP 1
    AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, VolBarPeriod, VolumetricDeltaType.BidAsk, 1);  // BIP 2
    AddDataSeries(EsInstrument, BarsPeriodType.Minute, VolBarPeriod);  // BIP 3
    AddVolumetric(EsInstrument, BarsPeriodType.Minute, VolBarPeriod, VolumetricDeltaType.BidAsk, 1);  // BIP 4
    ```
    Adjust all BIP indices accordingly throughout the file.
  - **VolumetricBarsType cast pattern** (in `State.DataLoaded`):
    ```csharp
    _nqVolBars = BarsArray[1].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
    _esVolBars = BarsArray[2].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
    ```
  - Use `Instruments[bipIndex].MasterInstrument.TickSize` for each instrument's tick size — do NOT assume NQ and ES share tick size

  **Step 2: Level Management System**
  - **NinjaScriptProperty inputs for manual levels** (up to 5 manual levels):
    ```csharp
    [NinjaScriptProperty]
    [Display(Name = "Level 1 Price", GroupName = "2. Manual Levels", Order = 0)]
    public double ManualLevel1 { get; set; }

    [NinjaScriptProperty]
    [Display(Name = "Level 1 Type", GroupName = "2. Manual Levels", Order = 1)]
    public LevelType ManualLevel1Type { get; set; }
    ```
  - Define `LevelType` enum: `None, Support, Resistance, Magnet, Neutral`
  - **CSV import**: `[NinjaScriptProperty]` for CSV file path (default empty string)
    - In `State.DataLoaded`: If path not empty, read with `File.ReadAllLines()`
    - Parse each line: `string.Split(',')` → `double.TryParse` for price, string match for type
    - Skip bad lines with `Print()` warning per line
    - Cap at 30 levels max — print warning if exceeded
  - **Level data structure**:
    ```csharp
    private class TelegramLevel
    {
        public double Price;
        public LevelType Type;
        public bool SignalFired;  // one-signal-per-level guard
    }
    private List<TelegramLevel> _levels = new List<TelegramLevel>();
    ```
  - **Daily expiration**: On `Bars.IsFirstBarOfSession` in BIP 0, reset all `SignalFired = false`
  - **Level direction constraint**:
    - Support → only bullish absorption arrows
    - Resistance → only bearish absorption arrows
    - Magnet/Neutral → both directions allowed

  **Step 3: Stacked Absorption Detection Engine**
  - **Core method**: `DetectStackedAbsorption(int bipIndex, VolumetricBarsType volBars, bool isBullish)`
  - **Algorithm** (iterate price levels from Low to High of the volumetric bar):
    ```
    For each active TelegramLevel within ProximityTicks:
      stackCount = 0
      totalAbsorbedVol = 0
      For each price level from bar Low to bar High (step = tick size):
        bidVol = volBars.Volumes[barIdx].GetBidVolumeForPrice(price)
        askVol = volBars.Volumes[barIdx].GetAskVolumeForPrice(price)
        If bullish check: bidVol >= MinVolumePerLevel → stackCount++, totalAbsorbedVol += bidVol
        If bearish check: askVol >= MinVolumePerLevel → stackCount++, totalAbsorbedVol += askVol
      If stackCount >= MinStackedLevels AND totalAbsorbedVol >= MinTotalAbsorbedVolume:
        absorption detected at this level
    ```
  - **Bullish absorption**: Large bid-side volume (sellers hitting bid but price holds) — stackCount of bid volume levels ≥ threshold
  - **Bearish absorption**: Large ask-side volume (buyers lifting ask but price rejects) — stackCount of ask volume levels ≥ threshold
  - Store results per instrument:
    ```csharp
    private bool _nqBullAbsorption, _nqBearAbsorption;
    private int _nqAbsorptionBar;  // bar index when detected
    private bool _esBullAbsorption, _esBearAbsorption;
    private int _esAbsorptionBar;
    ```

  **Step 4: Confluence Engine + Arrows + Alerts + Session Filter**
  - **Session filtering** using `SessionIterator`:
    - In `State.DataLoaded`: Initialize `SessionIterator`
    - In `OnBarUpdate` BIP 0: Check if current time is within 8:30 AM – 3:30 PM ET
    - Use `ToTime(Time[0])` comparison: `if (ToTime(Time[0]) < 83000 || ToTime(Time[0]) > 153000) return;`
    - Simpler than full SessionIterator for this use case
  - **Confluence check** (in BIP 0 handler, after absorption results are set):
    ```
    If NQ bullish absorption AND ES bullish absorption
       AND both within ConfirmationWindow bars of current bar
       AND nearest level is Support or Magnet/Neutral
       AND that level's SignalFired == false:
         → Draw bullish arrow + fire alert + set SignalFired = true
    (Same logic for bearish with Resistance or Magnet/Neutral)
    ```
  - **Arrow drawing**:
    ```csharp
    // Bullish
    Draw.ArrowUp(this, "DEEP6SAC_Bull_" + CurrentBar, true, 0, Low[0] - 4 * TickSize, Brushes.Lime);
    // Bearish
    Draw.ArrowDown(this, "DEEP6SAC_Bear_" + CurrentBar, true, 0, High[0] + 4 * TickSize, Brushes.Red);
    ```
  - **Alerts** (configurable toggles):
    ```csharp
    if (EnableAlerts)
        Alert("DEEP6SAC_" + CurrentBar, Priority.High,
              "Bullish ES/NQ stacked absorption confirmed near active session level.",
              EnableSoundAlert ? NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav" : "",
              10, Brushes.Lime, Brushes.Black);
    ```
  - **Reset logic**: A level may re-fire only if:
    - Price moves away by `ResetDistanceTicks` from the level
    - Then returns to within `ProximityTicks`
    - A fresh stacked absorption event occurs
    - Track `_lastPriceAtLevel[levelIndex]` for distance monitoring

  **Step 5: Edge Case Guards**
  - Null guard on volumetric cast: `if (_nqVolBars == null || _esVolBars == null) return;`
  - Early bar guard: `if (CurrentBars[1] < BarsRequiredToPlot || CurrentBars[2] < BarsRequiredToPlot) return;`
  - Zero levels guard: Print warning once "No levels configured — indicator inactive" and return
  - Overlapping levels: If two levels within `ProximityTicks * 2` of each other, use first match
  - Duplicate CSV prices: Last row wins with Print warning
  - CSV errors: `double.TryParse` with skip + warning per bad line
  - Max level cap: If CSV + manual exceeds 30, truncate with warning
  - ES data staleness: Track `_lastEsBarTime`. If ES hasn't updated in 60 seconds, print warning. Never fire arrows on NQ-only data.

  **COMPLETE NinjaScriptProperty LIST** (all configurable):
  ```
  Group "1. Instruments":
    EsInstrument (string, default "ES 09-26") — ES contract name, update at rollover
    VolBarPeriod (int, default 1) — Volumetric bar period in minutes

  Group "2. Manual Levels":
    ManualLevel1-5 (double, default 0) — Manual level prices (0 = inactive)
    ManualLevel1Type-5Type (LevelType enum) — Level classification
    CsvFilePath (string, default "") — Path to CSV level file

  Group "3. Absorption":
    MinStackedLevels (int, default 3, range 2-10) — Min adjacent levels with qualifying volume
    MinVolumePerLevel_NQ (int, default 500) — Min contracts per level for NQ
    MinVolumePerLevel_ES (int, default 1000) — Min contracts per level for ES
    MinTotalAbsorbedVolume (int, default 1500) — Min total absorbed volume across stacked levels
    ProximityTicks (int, default 10, range 1-50) — Max distance from Telegram level in ticks

  Group "4. Confluence":
    ConfirmationWindow (int, default 3, range 1-10) — Max bars between NQ and ES absorption
    RequireConfirmationCandle (bool, default false) — Require follow-through candle

  Group "5. Session":
    SessionStartTime (int, default 83000) — Session start in HHMMSS format
    SessionEndTime (int, default 153000) — Session end in HHMMSS format
    ResetDistanceTicks (int, default 20) — Ticks away from level to allow re-signal

  Group "6. Alerts":
    EnableAlerts (bool, default true) — Master alert toggle
    EnableSoundAlert (bool, default true) — Play sound on signal
    EnablePopupAlert (bool, default true) — Show popup on signal
  ```

  **Must NOT do**:
  - Do NOT reference, import, or use AbsorptionDetector.cs or any DEEP6 AddOn type
  - Do NOT add ANY visual element besides Draw.ArrowUp and Draw.ArrowDown
  - Do NOT add adaptive/dynamic volume thresholds
  - Do NOT add multi-timeframe scanning
  - Do NOT add more than NQ + ES instruments
  - Do NOT add CSV auto-reload
  - Do NOT add level visualization on chart (no horizontal lines)
  - Do NOT add a HUD, info panel, or status text
  - Do NOT use `TickSize` for ES price iteration — use `Instruments[bipIndex].MasterInstrument.TickSize`

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex single-file build requiring NinjaScript expertise, volumetric API knowledge, multi-instrument architecture, and careful build ordering with architecture validation
  - **Skills**: [`nt8-expert`, `nt8-new`]
    - `nt8-expert`: NinjaScript API knowledge, NT8 state machine, namespace conventions, deployment paths, VolumetricBarsType patterns
    - `nt8-new`: Code generation patterns for new NinjaScript indicators, property declarations, Draw.* API
  - **Skills Evaluated but Omitted**:
    - `nt8-fix`: Not needed during build — only needed if compile fails (handled in Task 2)
    - `nt8-visual-design`: Not needed — no SharpDX rendering, just Draw.ArrowUp/Down
    - `nt8-architect`: Not needed — not modifying existing DEEP6 architecture, self-contained indicator

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (solo)
  - **Blocks**: Tasks 2, 3, 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Core.cs:1-310` — Minimal indicator template showing State machine, VolumetricBarsType cast, OnBarUpdate routing. Use as structural skeleton.
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs:74-234` — Absorption detection logic with 4 variants and threshold patterns. REFERENCE ONLY for algorithm understanding — do NOT import or depend on this code. Implement simplified inline version using VolumetricBarsType API.
  - `NinjaTraderTools/NJIndicators/ExhaustionAbsorption.cs:49-99` — VolumetricBarsType.Volumes[] access pattern showing GetBidVolumeForPrice/GetAskVolumeForPrice. Copy this data access pattern.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6TripleConfluenceArrows.cs` — Arrow drawing convention showing tag format, price offset, color patterns. Copy arrow drawing pattern exactly.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6BiasV3.cs:1-50` — NinjaScriptProperty declaration pattern with [Display(GroupName, Order)]. Copy property declaration style.
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs:1-125` — Cell (BidVol/AskVol) data structure for understanding what absorption looks like in data. REFERENCE ONLY — do NOT import.

  **API/Type References**:
  - `NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType` — The NT8 volumetric bars API. Cast from `BarsArray[bipIndex].BarsType`.
  - `VolumetricBarsType.Volumes[barIndex]` — Access per-bar volumetric data
  - `.GetBidVolumeForPrice(double price)` — Bid (sell-aggressor) volume at specific price level
  - `.GetAskVolumeForPrice(double price)` — Ask (buy-aggressor) volume at specific price level
  - `.BarDelta` — Net delta for the bar (AskVol - BidVol)
  - `NinjaTrader.NinjaScript.VolumetricDeltaType.BidAsk` — Enum for AddVolumetric delta type parameter

  **External References**:
  - NinjaTrader 8 AddVolumetric docs: https://ninjatrader.com/support/helpGuides/nt8/addvolumetric.htm
  - NinjaTrader 8 VolumetricBarsType: https://ninjatrader.com/support/helpGuides/nt8/volumetricbarstype.htm

  **WHY Each Reference Matters**:
  - `DEEP6Core.cs`: Copy the exact State machine structure, property style, and OnBarUpdate routing — this is the canonical DEEP6 indicator skeleton
  - `AbsorptionDetector.cs`: Understand HOW absorption is detected (wick volume %, delta ratio, stacking) — but implement using different API (VolumetricBarsType vs FootprintBar)
  - `ExhaustionAbsorption.cs`: This file shows the EXACT API calls you'll use (GetBidVolumeForPrice/GetAskVolumeForPrice) — copy the data access pattern
  - `DEEP6TripleConfluenceArrows.cs`: Copy the arrow tag naming convention and price offset pattern exactly — consistency with existing DEEP6 indicators

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Indicator compiles without errors
    Tool: Bash (PowerShell)
    Preconditions: File exists at ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs
    Steps:
      1. Run: .\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators -Force
      2. Run: .\ninjatrader\scripts\nt8-compile.ps1
      3. Assert output contains "[COMPILE-RESULT] SUCCESS"
    Expected Result: Compile succeeds with no errors
    Failure Indicators: "[COMPILE-RESULT] FAILED" or CS#### error codes
    Evidence: .sisyphus/evidence/task-1-compile-success.txt

  Scenario: File follows DEEP6 namespace and naming conventions
    Tool: Bash (grep)
    Preconditions: File built
    Steps:
      1. grep for "namespace NinjaTrader.NinjaScript.Indicators.DEEP6" in the file
      2. grep for "class DEEP6StackedAbsorptionArrows : Indicator"
      3. grep for "AddVolumetric" (should appear exactly 2 times)
      4. grep for "AbsorptionDetector" or "FootprintBar" (should NOT appear)
    Expected Result: Correct namespace, correct class name, 2 AddVolumetric calls, zero AddOn references
    Failure Indicators: Wrong namespace, missing AddVolumetric, or AddOn dependency found
    Evidence: .sisyphus/evidence/task-1-conventions-check.txt

  Scenario: All NinjaScriptProperty inputs declared correctly
    Tool: Bash (grep)
    Preconditions: File built
    Steps:
      1. grep for "[NinjaScriptProperty]" — count occurrences
      2. grep for "GroupName" — verify groups: "1. Instruments", "2. Manual Levels", "3. Absorption", "4. Confluence", "5. Session", "6. Alerts"
      3. Verify EsInstrument, VolBarPeriod, MinStackedLevels, MinVolumePerLevel_NQ, MinVolumePerLevel_ES, ProximityTicks, ConfirmationWindow, EnableAlerts exist
    Expected Result: All specified properties declared with proper Display attributes
    Failure Indicators: Missing properties or wrong GroupName strings
    Evidence: .sisyphus/evidence/task-1-properties-check.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-compile-success.txt — compile output
  - [ ] task-1-conventions-check.txt — namespace/naming grep results
  - [ ] task-1-properties-check.txt — property declaration grep results

  **Commit**: YES
  - Message: `feat(nt8): add ES/NQ stacked absorption confluence arrows indicator`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs`
  - Pre-commit: `nt8-compile.ps1 returns SUCCESS`

- [x] 2. Deploy + Compile + Error Fix Loop

  **What to do**:
  - Deploy the indicator to NinjaTrader 8 using the DEEP6 deployment scripts
  - Compile and verify success
  - If compile errors occur, fix them iteratively using NT8 error patterns

  Steps:
  1. Run `.\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators -Force` — copies .cs to NT8 Custom directory
  2. Run `.\ninjatrader\scripts\nt8-compile.ps1` — triggers NT8 compilation
  3. If `[COMPILE-RESULT] FAILED`:
     - Read error output
     - Common NT8 errors for this indicator type:
       - CS0246 (type not found): Missing `using` statement for VolumetricBarsType — add `using NinjaTrader.NinjaScript.BarsTypes;`
       - CS0019 (operator not applicable): Type mismatch in volume comparison — ensure `long` vs `double` consistency
       - CS0103 (name not in context): Variable scope issue in BIP routing
     - Fix the error in the source .cs file
     - Re-deploy + re-compile
     - Repeat until `[COMPILE-RESULT] SUCCESS`
  4. Verify indicator appears in NT8 indicator list

  **Must NOT do**:
  - Do NOT modify the deployment scripts themselves
  - Do NOT skip the deploy step and manually copy files
  - Do NOT ignore compile warnings

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Deployment is a scripted pipeline — run scripts, check output, fix if needed
  - **Skills**: [`nt8-fix`]
    - `nt8-fix`: NT8 compile error patterns and auto-fix recipes for CS#### errors
  - **Skills Evaluated but Omitted**:
    - `nt8-expert`: Not needed — deployment is scripted, nt8-fix covers error fixing
    - `nt8-build-verify`: Full 9-stage pipeline is overkill for initial compilation

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3)
  - **Parallel Group**: Wave 2 (with Task 3)
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:
  - `ninjatrader/scripts/nt8-deploy.ps1` — Deployment script. Use with `-Target Indicators -Force`
  - `ninjatrader/scripts/nt8-compile.ps1` — Compilation script. Polls DLL timestamp for success/failure
  - `.claude/skills/nt8-fix/` — Error fix recipes for common CS#### errors

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Deploy and compile succeeds
    Tool: Bash (PowerShell)
    Preconditions: Task 1 complete, .cs file exists
    Steps:
      1. Run: .\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators -Force
      2. Assert output shows file copied
      3. Run: .\ninjatrader\scripts\nt8-compile.ps1
      4. Assert output contains "[COMPILE-RESULT] SUCCESS"
    Expected Result: Deploy copies file, compile succeeds
    Failure Indicators: "FAILED" in either step
    Evidence: .sisyphus/evidence/task-2-deploy-compile.txt

  Scenario: Indicator appears in NT8 indicator list
    Tool: Bash (PowerShell)
    Preconditions: Compile succeeded
    Steps:
      1. Verify file exists at C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6StackedAbsorptionArrows.cs
      2. Test-Path confirms file presence
    Expected Result: File deployed to correct NT8 directory
    Failure Indicators: File missing from NT8 directory
    Evidence: .sisyphus/evidence/task-2-file-deployed.txt
  ```

  **Commit**: NO (groups with Task 1)

- [x] 3. Create Test CSV + Verify Level Loading

  **What to do**:
  - Create a sample CSV file with test Telegram levels for verification
  - Verify the CSV path convention works

  Steps:
  1. Create directory `ninjatrader/Custom/Indicators/DEEP6/Levels/` if not exists
  2. Create `sample-levels.csv` with realistic NQ/ES test levels:
     ```
     21500.00,Support
     21650.00,Resistance
     21575.00,Magnet
     21400.00,Support
     21700.00,Resistance
     21550.00,Neutral
     ```
  3. Verify file format: no BOM, no trailing whitespace, Unix or Windows line endings both accepted

  **Must NOT do**:
  - Do NOT use complex CSV format (headers, extra columns)
  - Do NOT create more than 30 levels in the sample

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file creation — one small CSV file
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**:
    - All skills unnecessary for creating a simple text file

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2)
  - **Parallel Group**: Wave 2 (with Task 2)
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:
  - The indicator's CSV parsing logic (in Task 1) expects `Price,Type` format with types: Support, Resistance, Magnet, Neutral

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CSV file exists with correct format
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Verify file exists at ninjatrader/Custom/Indicators/DEEP6/Levels/sample-levels.csv
      2. Read file content
      3. Verify each line matches pattern: number,word
      4. Verify at least 4 levels present
      5. Verify types are only: Support, Resistance, Magnet, Neutral
    Expected Result: Valid CSV with 6 test levels
    Failure Indicators: File missing, wrong format, invalid types
    Evidence: .sisyphus/evidence/task-3-csv-format.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `feat(nt8): add ES/NQ stacked absorption confluence arrows indicator`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/Levels/sample-levels.csv`

- [x] 4. Live Chart Verification + Screenshots

  **What to do**:
  - Add the compiled indicator to a live NQ chart in NinjaTrader 8
  - Verify all subsystems work correctly
  - Capture evidence screenshots

  Steps:
  1. **Add indicator to chart**: Use HERMES to add DEEP6StackedAbsorptionArrows to a live NQ chart
  2. **Configure settings**: Set `EsInstrument` to the current ES front-month contract, set `CsvFilePath` to the sample CSV
  3. **Verify Output Window** (via HERMES screenshot):
     - BIP 1 (NQ volumetric) firing and printing delta values
     - BIP 2 (ES volumetric) firing and printing delta values
     - Level loading message: "Loaded N levels: [list]"
     - Session window enforcement: no processing prints outside 8:30-3:30 ET
  4. **Verify chart visuals** (via HERMES screenshot):
     - Only arrows visible (no other drawings)
     - Arrows at correct positions (below candle for bull, above for bear)
     - Correct colors (green/lime for bull, red for bear)
  5. **Verify session filtering**: Scroll to pre-market bars → confirm zero arrows
  6. **Verify indicator properties panel**: Screenshot showing all parameter groups correctly organized

  **Must NOT do**:
  - Do NOT modify the indicator code during verification
  - Do NOT use TradingView MCP for this — use HERMES + NT8 tools

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: End-to-end validation requiring chart interaction, Output Window reading, and evidence capture
  - **Skills**: [`nt8-expert`, `display-topology`]
    - `nt8-expert`: NT8 chart interaction, indicator properties, Output Window
    - `display-topology`: Monitor layout for accurate screenshot positioning
  - **Skills Evaluated but Omitted**:
    - `nt8-build-verify`: Full 9-stage pipeline is more than needed here — manual verification is sufficient

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (solo)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 2, 3

  **References**:
  - HERMES invocation for NT8 interaction: `wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'TASK' -s deep6-deployment-operator -Q --yolo --max-turns N 2>&1"`
  - NT8 indicator properties are accessible via right-click → Indicators on chart
  - Output Window accessible via NT8 menu → New → Output Window

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Both volumetric feeds active
    Tool: Bash (HERMES)
    Preconditions: Indicator added to live NQ chart with market open or recent data
    Steps:
      1. Open NT8 Output Window via HERMES
      2. Wait for 3-5 bars to close
      3. Screenshot Output Window
      4. Assert output contains "NQ Vol BIP1 bar" entries
      5. Assert output contains "ES Vol BIP2 bar" entries
    Expected Result: Both NQ and ES volumetric data flowing, Print statements visible
    Failure Indicators: Missing BIP1 or BIP2 entries, null reference errors, "object not set" errors
    Evidence: .sisyphus/evidence/task-4-volumetric-feeds.png

  Scenario: Levels loaded from CSV
    Tool: Bash (HERMES)
    Preconditions: CsvFilePath set to sample-levels.csv path
    Steps:
      1. Read Output Window after indicator loads
      2. Assert output contains "Loaded 6 levels"
      3. Assert level prices and types are listed
    Expected Result: All 6 sample levels loaded with correct types
    Failure Indicators: "No levels configured" or parsing errors
    Evidence: .sisyphus/evidence/task-4-levels-loaded.png

  Scenario: Chart shows only arrows (no visual clutter)
    Tool: Bash (HERMES)
    Preconditions: Indicator running on live chart
    Steps:
      1. Screenshot the full NQ chart via HERMES
      2. Visual inspection: only candles + arrows visible
      3. No text labels, no horizontal lines, no HUD panels
    Expected Result: Clean chart with only price candles and directional arrows
    Failure Indicators: Extra visual elements visible on chart
    Evidence: .sisyphus/evidence/task-4-chart-clean.png

  Scenario: No arrows in pre-market hours
    Tool: Bash (HERMES)
    Preconditions: Historical data available for pre-market bars
    Steps:
      1. Scroll chart to show bars before 8:30 AM ET
      2. Screenshot pre-market section
      3. Assert zero arrows visible in pre-market bars
    Expected Result: No arrows before 8:30 AM ET
    Failure Indicators: Arrows visible in pre-market hours
    Evidence: .sisyphus/evidence/task-4-session-filter.png
  ```

  **Evidence to Capture:**
  - [ ] task-4-volumetric-feeds.png — Output Window showing both NQ + ES data
  - [ ] task-4-levels-loaded.png — Output Window showing CSV level loading
  - [ ] task-4-chart-clean.png — Chart screenshot showing arrows only
  - [ ] task-4-session-filter.png — Pre-market bars with no arrows

  **Commit**: NO (no code changes)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read the .cs file, check for AddVolumetric calls, CSV parsing, session filtering, arrow drawing, alert calls). For each "Must NOT Have": search codebase for forbidden patterns (AbsorptionDetector reference, Draw.Text, Draw.Line, ATM, adaptive threshold). Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Review `DEEP6StackedAbsorptionArrows.cs` for: `as any` equivalent (unsafe casts without null check), empty catches, Print/Console in hot path, commented-out code, unused usings, generic variable names (data/result/temp). Check proper disposal of resources. Verify namespace matches DEEP6 convention. Check NinjaScriptProperty declarations have proper Display attributes.
  Output: `Build [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task. Deploy indicator, add to live NQ chart, verify Output Window shows volumetric data for both instruments. Verify CSV loads correctly. Check session window filtering by scrolling to pre-market bars. Check arrow appearance. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  Read "What to do" for each task. Read the actual .cs file. Verify 1:1 — everything in spec was built (no missing features), nothing beyond spec was built (no scope creep: no extra visuals, no adaptive logic, no AddOn dependency). Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `feat(nt8): add ES/NQ stacked absorption confluence arrows indicator` — `ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs`, `ninjatrader/Custom/Indicators/DEEP6/Levels/sample-levels.csv`

---

## Success Criteria

### Verification Commands
```powershell
# Deploy to NT8
.\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators -Force
# Expected: Files copied to NT8 Custom directory

# Compile
.\ninjatrader\scripts\nt8-compile.ps1
# Expected: [COMPILE-RESULT] SUCCESS

# Verify via HERMES
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Take a screenshot of the NQ chart showing DEEP6StackedAbsorptionArrows indicator' -s deep6-deployment-operator -Q --yolo --max-turns 6 2>&1"
# Expected: Screenshot showing NQ chart with green/red arrows at absorption confluence points
```

### Final Checklist
- [ ] All "Must Have" present in indicator code
- [ ] All "Must NOT Have" absent from indicator code
- [ ] Compile success confirmed
- [ ] Indicator loads on live chart without errors
- [ ] Both volumetric feeds confirmed active
- [ ] Arrows render correctly at confluence points
