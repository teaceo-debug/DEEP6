# DEEP6 LVN Zones Indicator for NinjaTrader 8

## TL;DR

> **Quick Summary**: Build a NinjaScript indicator that detects Low Volume Nodes from session-based volume profiles and renders them as semi-transparent filled rectangular zones on the chart, with multi-session persistence and dynamic zone boundaries.
> 
> **Deliverables**:
> - `DEEP6LVNZones.cs` — Complete NinjaScript indicator with SharpDX rendering
> - Deployed and compiled in NinjaTrader 8
> - Verified on live NQ chart with cross-validation against existing VPLowTFLVNLevels
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Task 1 (data types) → Task 2 (profile engine) → Task 3 (zone detection) → Task 4 (rendering) → Task 5 (multi-session) → Task 6 (integration) → F1-F4

---

## Context

### Original Request
Build an LVN Zones Indicator for NinjaTrader 8 using volume profile knowledge. Zones should be filled rectangular areas (not lines). Multi-agent parallel execution desired.

### Interview Summary
**Key Discussions**:
- Profile Source: Session-based, RTH only (9:30 AM – 4:00 PM ET) via SessionIterator
- Zone Lifecycle: Static — current session rebuilds live, prior sessions frozen on session end
- Data Source: Standard bars (approximate) + 1-minute LTF secondary data series for finer resolution
- Zone Height: Dynamic — extends from LVN price to adjacent HVN boundaries (volume gap edges via local maxima scan)
- Forward Projection: Yes — zones extend to chart right edge
- Visual Style: Semi-transparent fill (~20-25% opacity) + 1px border, DEEP6 institutional palette (cyan/DodgerBlue family)
- Multi-Session: Current + N prior sessions (dimmer opacity for older sessions)
- Labels: No text labels — zones only
- Strategy API: Expose `LvnZones` public property for strategy consumption

**Research Findings**:
- Existing `VPLowTFLVNLevels.cs`: Proven LVN detection via local minima algorithm, 1-min LTF bars, proportional volume distribution — reuse this algorithm exactly
- Existing `DEEP6LVNRadarStrategy.cs`: Multi-period profiles with ProfileState sealed class pattern — reuse encapsulation pattern
- Existing `DEEP6FootprintV8.cs`: Most comprehensive SharpDX reference (40+ brushes, FillRectangle, DisposeDx pattern, OnRender guards) — follow rendering patterns
- Existing `DEEP6LowVolumeNodeTool.cs`: LVN color scheme (DodgerBlue #1E90FF / Cyan #00E0FF) — match colors
- All DEEP6 indicators: Direct `Indicator` inheritance, `NinjaTrader.NinjaScript.Indicators.DEEP6` namespace, no shared base class
- DEEP6 does NOT use NT8's built-in Volumetric bars — all custom volume distribution

### Metis Review
**Identified Gaps** (all addressed):
- Zone boundary algorithm: Specified as adjacent local maxima scan (novel logic, no precedent in codebase)
- Session definition: Confirmed as RTH (9:30 AM – 4:00 PM ET), requires SessionIterator instead of calendar-day period key
- Current session behavior: Clarified as live rebuild during active session, freeze on session end
- Strength-to-color mapping: Simplified to uniform color with session-recency-based opacity
- Multi-session archival: New infrastructure — no existing pattern, specified as `List<SessionZoneData>` with configurable max count
- Edge cases: MinBarsForProfile guard (30), holiday/half-day handling, LVN at profile edge clamping, adjacent LVN overlap acceptance

---

## Work Objectives

### Core Objective
Build a production-quality NinjaScript indicator that detects LVN zones from RTH session volume profiles and renders them as filled rectangular zones with multi-session persistence and forward projection.

### Concrete Deliverables
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6LVNZones.cs` — Single-file NinjaScript indicator
- Deployed to NinjaTrader 8 and compiling successfully
- Verified on NQ chart with screenshot evidence

### Definition of Done
- [ ] `nt8-compile.ps1` returns `[COMPILE-RESULT] SUCCESS`
- [ ] Indicator loads on NQ 5-min chart without errors in Output window
- [ ] Semi-transparent zones visible on chart with correct forward projection
- [ ] Multiple sessions visible with opacity gradient (current brighter, prior dimmer)
- [ ] LVN prices match existing VPLowTFLVNLevels indicator (cross-validation)
- [ ] Add → Remove → Re-add cycle produces no errors or artifacts

### Must Have
- RTH session boundary detection via SessionIterator
- 1-minute LTF secondary data series for profile resolution
- Local minima LVN detection (reuse VPLowTFLVNLevels algorithm)
- Dynamic zone boundaries via adjacent local maxima (HVN) scan
- SharpDX FillRectangle + DrawRectangle zone rendering
- Forward projection to chart right edge
- Multi-session archival (configurable N prior sessions, default 2)
- Opacity-tiered brush array (not per-session brushes)
- `LvnZones` public property for strategy consumption
- DisposeDx + SafeDispose resource management pattern
- MinBarsForProfile guard (minimum 30 bars for detection)
- Configurable parameters: Rows, LvnStrength, MaxSessions, ZoneOpacity, ZoneColor

### Must NOT Have (Guardrails)
- Zone merging — each LVN gets its own zone, overlaps accepted
- Zone decay or touch tracking — static lifecycle only
- Text labels on zones — zones only, no text rendering
- Alerting or notifications — pure visualization + data exposure
- Volume profile visualization (no histogram, POC, VAH/VAL, HVN markers)
- Interactive zones (no click to dismiss, drag to resize)
- Strategy entry/exit logic — the indicator EXPOSES data, strategies CONSUME it
- Per-session color customization — one color scheme, opacity varies by recency only
- Zone filtering by size or strength — show all detected zones in v1
- New LVN detection algorithm — MUST reuse proven local minima from VPLowTFLVNLevels exactly
- Volumetric bars dependency — standard bars with proportional approximation only

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (NT8 has no unit test framework for NinjaScript)
- **Automated tests**: NO
- **Framework**: N/A — NinjaScript compiles in NT8's built-in editor
- **QA**: Agent-executed via HERMES (deploy → compile → add to chart → screenshot → verify)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **NinjaScript compilation**: Use `nt8-compile.ps1` via Bash — verify `[COMPILE-RESULT] SUCCESS`
- **Deployment**: Use `nt8-deploy.ps1` via Bash — copy .cs to NT8 indicators directory
- **Visual verification**: Use `nt8-ui.ps1 -Screenshot` via Bash — capture chart screenshot showing zones
- **Cross-validation**: Add both VPLowTFLVNLevels and DEEP6LVNZones to same chart, screenshot, compare LVN prices

---

## Execution Strategy

### Parallel Execution Waves

> This is a single-file indicator, but the logical components can be developed as sequential tasks.
> The indicator MUST be a single .cs file (NT8 requirement for simple indicators).
> Tasks build incrementally on the same file.

```
Wave 1 (Foundation — data types + skeleton):
├── Task 1: Indicator skeleton + data types + properties [quick]
└── Task 2: Volume profile engine (profile building from 1-min bars) [deep]

Wave 2 (Core logic — depends on Wave 1):
├── Task 3: LVN detection + zone boundary detection [deep]
└── Task 4: SharpDX rendering engine (zone fill + border) [visual-engineering]

Wave 3 (Integration — depends on Wave 2):
├── Task 5: Multi-session archival + session lifecycle [unspecified-high]
└── Task 6: Full integration + deployment + cross-validation [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

> Note: Since this is a single .cs file, Waves 1-3 are sequential (each builds on prior).
> Within each wave, tasks CAN run in parallel conceptually but write to the same file.
> The FINAL wave runs 4 review agents in parallel.

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 3, 4, 5, 6 | 1 |
| 2 | 1 | 3, 5 | 1 |
| 3 | 2 | 4, 5, 6 | 2 |
| 4 | 1, 3 | 6 | 2 |
| 5 | 2, 3 | 6 | 3 |
| 6 | 3, 4, 5 | F1-F4 | 3 |
| F1-F4 | 6 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 2 tasks — T1 → `quick`, T2 → `deep`
- **Wave 2**: 2 tasks — T3 → `deep`, T4 → `visual-engineering`
- **Wave 3**: 2 tasks — T5 → `unspecified-high`, T6 → `unspecified-high`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Indicator Skeleton + Data Types + Properties

  **What to do**:
  - Create `ninjatrader/Custom/Indicators/DEEP6/DEEP6LVNZones.cs`
  - Namespace: `NinjaTrader.NinjaScript.Indicators.DEEP6`
  - Class: `public class DEEP6LVNZones : Indicator`
  - Define using aliases: `using Brush = System.Windows.Media.Brush;`, `using Color = System.Windows.Media.Color;`
  - Define inner data types:
    - `private sealed class LvnZone { public double Top; public double Bottom; public double LvnPrice; }` — single zone boundary
    - `private sealed class SessionZoneData { public int PeriodKey; public DateTime SessionStart; public List<LvnZone> Zones; }` — archived session
    - `private struct BarHLV { public double High; public double Low; public double Volume; }` — 1-min bar data for profile building
  - Implement `OnStateChange`:
    - `State.SetDefaults`: Set `Name`, `Description`, `Calculate = Calculate.OnBarClose`, `IsOverlay = true`, `DisplayInDataBox = false`. Declare all properties with defaults.
    - `State.Configure`: `AddDataSeries(BarsPeriodType.Minute, 1);` for LTF resolution
    - `State.DataLoaded`: Initialize `SessionIterator` for RTH detection, initialize `_periodBars = new List<BarHLV>()`, `_sessionHistory = new List<SessionZoneData>()`, `_currentZones = new List<LvnZone>()`
    - `State.Terminated`: Call `DisposeDx()`
  - Implement configurable properties with DEEP6 grouping convention:
    - `[NinjaScriptProperty] [Range(10, 1000)] [Display(Name="Profile Rows", Order=1, GroupName="1. Profile")] public int Rows { get; set; }` — default 200
    - `[NinjaScriptProperty] [Range(1, 100)] [Display(Name="LVN Strength", Order=2, GroupName="1. Profile")] public int LvnStrength { get; set; }` — default 5
    - `[NinjaScriptProperty] [Range(0, 10)] [Display(Name="Prior Sessions", Order=3, GroupName="1. Profile")] public int MaxSessions { get; set; }` — default 2
    - `[NinjaScriptProperty] [Range(10, 100)] [Display(Name="Zone Opacity %", Order=1, GroupName="2. Display")] public int ZoneOpacity { get; set; }` — default 22
    - `[Display(Name="Zone Color", Order=2, GroupName="2. Display")] public Brush ZoneBrush { get; set; }` — default DodgerBlue #1E90FF
    - `[Display(Name="Zone Border Color", Order=3, GroupName="2. Display")] public Brush ZoneBorderBrush { get; set; }` — default Cyan #00E0FF
    - `[NinjaScriptProperty] [Range(10, 200)] [Display(Name="Min Bars for Profile", Order=4, GroupName="1. Profile")] public int MinBarsForProfile { get; set; }` — default 30
  - Expose zone data: `[Browsable(false)] [XmlIgnore] public List<LvnZone> LvnZones { get { return _allZones; } }` — combined current + prior session zones
  - Implement SafeDispose helper: `private static void SafeDispose<T>(ref T resource) where T : class, IDisposable { if (resource == null) return; try { resource.Dispose(); } catch { } resource = null; }`
  - Implement empty DisposeDx stub: `private void DisposeDx() { }` — will be populated in Task 4
  - Implement empty OnBarUpdate stub: `protected override void OnBarUpdate() { }` — will be populated in Task 2
  - Implement empty OnRender stub: `protected override void OnRender(ChartControl chartControl, ChartScale chartScale) { base.OnRender(chartControl, chartScale); }` — will be populated in Task 4

  **Must NOT do**:
  - Do NOT implement profile building logic (Task 2)
  - Do NOT implement LVN detection (Task 3)
  - Do NOT implement SharpDX rendering (Task 4)
  - Do NOT add zone merging, text labels, alerting, or VP visualization

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Boilerplate skeleton with established patterns — straightforward copy-and-adapt from existing DEEP6 indicators
  - **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`]
    - `nt8-expert`: NT8 file paths, namespace conventions, deployment patterns
    - `ninjatrader-builder-doctor`: NinjaScript property attributes, state machine lifecycle, AddDataSeries patterns
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed yet — rendering is Task 4

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (sequential with Task 2)
  - **Blocks**: Tasks 2, 3, 4, 5, 6
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:31-38` — VPProfilePeriod enum, BarHLV struct definition pattern
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:41-84` — OnStateChange lifecycle with AddDataSeries for 1-min LTF
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:218-270` — Property exposure with NinjaScriptProperty, Range, Display attributes
  - `ninjatrader/Custom/Strategies/DEEP6/DEEP6LVNRadarStrategy.cs:57-67` — ProfileState sealed class pattern for session data encapsulation
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:1223-1286` — DisposeDx + SafeDispose helper pattern
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV3.cs:86-142` — Clean OnStateChange with timer initialization pattern

  **WHY Each Reference Matters**:
  - VPLowTFLVNLevels.cs is the closest existing indicator — same domain, same data approach. Copy its struct/property patterns.
  - DEEP6LVNRadarStrategy.cs shows how to encapsulate session data in a sealed class — copy this for SessionZoneData.
  - DEEP6FootprintV8.cs is the gold standard for resource management — copy DisposeDx exactly.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: File compiles in NT8
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1)
    Preconditions: NT8 running, NinjaScript Editor accessible
    Steps:
      1. Run: .\ninjatrader\scripts\nt8-deploy.ps1 -File "DEEP6LVNZones.cs"
      2. Run: .\ninjatrader\scripts\nt8-compile.ps1
      3. Check output for "[COMPILE-RESULT] SUCCESS"
    Expected Result: Compilation succeeds with zero errors
    Failure Indicators: "[COMPILE-RESULT] FAILED" or any CS#### error codes
    Evidence: .sisyphus/evidence/task-1-compile-success.txt

  Scenario: Indicator loads on chart without errors
    Tool: Bash (nt8-ui.ps1)
    Preconditions: DEEP6LVNZones compiled successfully
    Steps:
      1. Add DEEP6LVNZones to NQ 5-min chart via NT8 UI
      2. Check NinjaScript Editor Output window for errors
      3. Take screenshot of chart
    Expected Result: Indicator appears in indicator list, loads without errors in Output window
    Failure Indicators: Error messages in Output window, indicator not found in list
    Evidence: .sisyphus/evidence/task-1-indicator-loaded.png
  ```

  **Commit**: NO (intermediate — commits with Task 6)

---

- [x] 2. Volume Profile Engine (Profile Building from 1-min Bars)

  **What to do**:
  - Implement `OnBarUpdate()` in DEEP6LVNZones.cs:
    - Route `BarsInProgress == 1` (1-min LTF bars): Collect bar data into `_periodBars` list as `BarHLV(High, Low, Volume)`
    - Route `BarsInProgress == 0` (primary bars): Detect RTH session boundaries using `SessionIterator`
    - On session boundary change:
      1. If `_currentZones.Count > 0`: Archive current zones into `_sessionHistory` as `SessionZoneData`
      2. If `_sessionHistory.Count > MaxSessions`: Remove oldest (index 0)
      3. Clear `_periodBars`, reset profile arrays
    - On each primary bar close (within RTH):
      1. Rebuild volume profile from `_periodBars`
      2. Find yMin/yMax across all collected 1-min bars
      3. Calculate bin step: `step = (yMax - yMin) / Rows`, clamped to `>= TickSize`
      4. Allocate `_vpValues = new double[Rows + 1]` and `_vpYVol = new double[Rows + 1]`
      5. For each 1-min bar: distribute volume evenly across all bins the bar spans (proportional approximation)
      6. Call zone detection (Task 3 — stub for now)
  - Implement RTH session boundary detection:
    - Initialize `SessionIterator` in `State.DataLoaded`: `_sessionIterator = new SessionIterator(Bars);`
    - On each primary bar: `_sessionIterator.GetNextSession(Time[0], IsIntraday);`
    - Compare `_sessionIterator.ActualSessionBegin` / `_sessionIterator.ActualSessionEnd` to detect session transitions
    - Only collect bars that fall within RTH window (9:30 AM – 4:00 PM ET)
  - Guard: Skip profile rebuild if `_periodBars.Count < MinBarsForProfile`
  - Guard: Skip if `yMax <= yMin` (no price range)
  - Guard: Skip if `size <= LvnStrength * 2 + 1` (insufficient profile for LVN detection)

  **Must NOT do**:
  - Do NOT implement LVN detection logic (Task 3)
  - Do NOT implement rendering (Task 4)
  - Do NOT use calendar-day period keys — MUST use SessionIterator for RTH
  - Do NOT use Volumetric bars or OnMarketData — standard bars only

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Session boundary detection with SessionIterator is nuanced — must handle RTH correctly for NQ futures. Volume distribution algorithm must match existing VPLowTFLVNLevels exactly.
  - **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`]
    - `nt8-expert`: NT8 SessionIterator API, Bars object, multi-series BarsInProgress routing
    - `ninjatrader-builder-doctor`: OnBarUpdate patterns, AddDataSeries handling, SessionIterator usage
  - **Skills Evaluated but Omitted**:
    - `volume-profile-lvn`: Theory reference, but implementation should follow NT8 code patterns not Python

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (sequential after Task 1)
  - **Blocks**: Tasks 3, 5
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:88-161` — Complete OnBarUpdate with BarsInProgress routing, period bar collection, profile building, volume distribution across bins
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:130-161` — Volume distribution algorithm: `for each bar → for each bin in bar's H-L range → vpValues[bin] += bar.Volume / binsSpanned`
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:98-120` — Period boundary detection and profile reset (NOTE: uses calendar-day — we MUST replace with SessionIterator)

  **API/Type References**:
  - NinjaTrader `SessionIterator` class: `GetNextSession(DateTime, bool)`, `ActualSessionBegin`, `ActualSessionEnd` properties
  - NinjaTrader `BarsInProgress` property: 0 = primary, 1 = secondary (1-min LTF)

  **WHY Each Reference Matters**:
  - VPLowTFLVNLevels.cs:130-161 contains the EXACT volume distribution algorithm to reuse. Do not reinvent.
  - VPLowTFLVNLevels.cs:98-120 shows the session boundary pattern BUT uses calendar-day keys. Must REPLACE with SessionIterator while keeping the same reset logic.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Profile builds from 1-min bars during RTH
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1)
    Preconditions: NT8 running with NQ chart, market session in progress or historical data loaded
    Steps:
      1. Deploy updated DEEP6LVNZones.cs
      2. Compile — expect SUCCESS
      3. Add to NQ 5-min chart
      4. Add Print() statements to verify: _periodBars.Count increases during RTH, profile rebuilds on each primary bar close
      5. Check NinjaScript Editor Output window for Print output
    Expected Result: _periodBars accumulates 1-min bars; profile arrays (_vpValues) populate with non-zero values during RTH
    Failure Indicators: Empty _periodBars, zero-filled _vpValues, profile building during non-RTH hours
    Evidence: .sisyphus/evidence/task-2-profile-builds.txt

  Scenario: Session boundary resets profile correctly
    Tool: Bash (nt8-compile.ps1 + Output window inspection)
    Preconditions: Chart loaded with multiple days of NQ historical data
    Steps:
      1. Add Print() to log session transitions: Print($"SESSION BOUNDARY: {_sessionIterator.ActualSessionBegin} to {_sessionIterator.ActualSessionEnd}")
      2. Compile and add to chart
      3. Verify Output window shows session transitions at RTH boundaries (9:30 AM ET)
      4. Verify _periodBars.Count resets to 0 on session change
    Expected Result: Session transitions logged at 9:30 AM ET boundaries, profile resets cleanly
    Failure Indicators: Transitions at midnight instead of 9:30 AM, _periodBars not clearing
    Evidence: .sisyphus/evidence/task-2-session-boundary.txt
  ```

  **Commit**: NO (intermediate — commits with Task 6)

- [x] 3. LVN Detection + Zone Boundary Detection

  **What to do**:
  - Implement LVN detection method (reuse proven algorithm from VPLowTFLVNLevels.cs):
    - `private void DetectLvnZones()` — called after profile rebuild on each primary bar close
    - For each bin `i` where `_vpValues[i] > 0`:
      - Check if ALL non-zero neighbors within `±LvnStrength` radius have `>=` volume
      - If yes → this bin is an LVN
    - Skip detection if `_vpValues.Length <= LvnStrength * 2 + 1`
  - Implement zone boundary detection (NEW LOGIC — adjacent local maxima scan):
    - For each detected LVN at bin index `i`:
      - **Scan upward** (`i+1, i+2, ...`) to find nearest LOCAL MAXIMUM (a bin where all non-zero neighbors within `±LvnStrength` have LOWER volume). This price becomes `zone.Top`.
      - **Scan downward** (`i-1, i-2, ...`) to find nearest LOCAL MAXIMUM. This price becomes `zone.Bottom`.
      - **Edge case**: No local max found on one side → clamp to `yMax` (for top) or `yMin` (for bottom)
      - **Edge case**: Zone Top must be > Zone Bottom. If not, skip this LVN.
      - Create `LvnZone { Top = topPrice, Bottom = bottomPrice, LvnPrice = lvnPrice }`
    - Store in `_currentZones` list (cleared before each rebuild)
  - Update `_allZones` combined list: `_allZones = _currentZones.Concat(all prior session zones).ToList()`
  - Ensure `LvnZones` property always returns non-null (empty list if no zones)

  **Must NOT do**:
  - Do NOT merge overlapping zones — each LVN gets its own zone
  - Do NOT filter zones by width or strength — show all detected zones
  - Do NOT invent a new LVN detection algorithm — reuse VPLowTFLVNLevels exactly
  - Do NOT add touch tracking, decay, or zone lifecycle beyond static

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Zone boundary detection via adjacent local maxima is novel logic with edge cases (profile edges, adjacent LVNs, zero-volume gaps). Requires careful algorithm implementation.
  - **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`]
    - `nt8-expert`: NinjaScript conventions, existing DEEP6 code access
    - `ninjatrader-builder-doctor`: NinjaScript development patterns
  - **Skills Evaluated but Omitted**:
    - `volume-profile-lvn`: Algorithm reference, but the code pattern from VPLowTFLVNLevels.cs is authoritative

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (after Tasks 1+2)
  - **Blocks**: Tasks 4, 5, 6
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:164-214` — EXACT LVN detection algorithm: local minima with strength window. Lines 173-190 contain the core loop. COPY THIS EXACTLY.
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:193-210` — Post-detection: sorting LVN prices, identifying lowest-volume LVN for emphasis
  - `ninjatrader/Custom/DrawingTools/DEEP6LowVolumeNodeTool.cs:208-235` — Alternative LVN detection in drawing tool (same algorithm, different context)

  **WHY Each Reference Matters**:
  - VPLowTFLVNLevels.cs:173-190 is THE algorithm to copy. It has been validated in production. Do not modify the core detection logic.
  - The zone boundary detection (scanning for adjacent local maxima) is NEW and has no reference — implement from the specification in this task description.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: LVN zones detected from session profile
    Tool: Bash (nt8-compile.ps1 + Output window)
    Preconditions: Chart with historical NQ data, at least one full RTH session
    Steps:
      1. Add Print() to log detected zones: Print($"LVN ZONE: {zone.Bottom:F2} - {zone.Top:F2}, LVN at {zone.LvnPrice:F2}")
      2. Compile and add to NQ 5-min chart
      3. Check Output window for zone detection logs
      4. Verify at least 1 zone detected per session (typical NQ sessions have 3-8 LVNs)
      5. Verify zone.Bottom < zone.LvnPrice < zone.Top for every zone
    Expected Result: Multiple LVN zones detected with valid boundary ordering
    Failure Indicators: Zero zones detected, zone.Top <= zone.Bottom, zone.LvnPrice outside zone bounds
    Evidence: .sisyphus/evidence/task-3-zones-detected.txt

  Scenario: LVN prices match VPLowTFLVNLevels
    Tool: Bash (nt8-compile.ps1 + Output window comparison)
    Preconditions: Both DEEP6LVNZones and VPLowTFLVNLevels on same chart with same Rows and LvnStrength
    Steps:
      1. Add both indicators to NQ 5-min chart with Rows=200, LvnStrength=5
      2. Print() LVN prices from both indicators
      3. Compare the LVN price lists — they must match exactly
    Expected Result: Same set of LVN prices detected by both indicators
    Failure Indicators: Different LVN prices, different count of LVNs, prices differ by more than TickSize
    Evidence: .sisyphus/evidence/task-3-cross-validation.txt
  ```

  **Commit**: NO (intermediate — commits with Task 6)

---

- [x] 4. SharpDX Rendering Engine (Zone Fill + Border)

  **What to do**:
  - Implement `OnRenderTargetChanged()`:
    - Call `DisposeDx()` first
    - Guard: `if (RenderTarget == null) return;`
    - Create zone fill brushes — pre-allocate opacity-tiered array for multi-session rendering:
      - `_zoneFillBrushes = new SolidColorBrush[MaxSessions + 1]` — index 0 = current session (full opacity), index N = Nth prior session (dimmer)
      - Opacity formula: `baseOpacity * (1.0f - (sessionIndex * dimFactor))` where `dimFactor = 0.6f / Math.Max(1, MaxSessions)`
      - Extract RGB from user's `ZoneBrush` property, create `SolidColorBrush` with computed alpha for each tier
    - Create zone border brushes — same tier array with `_zoneBorderBrushes`:
      - Extract RGB from `ZoneBorderBrush`, create with 80% alpha for current, dimming for prior
    - Create TextFormat (even though no labels — needed for potential future use): SKIP — no text needed per requirements
  - Implement full `DisposeDx()`:
    - Dispose fill brush array: `if (_zoneFillBrushes != null) { for each brush: SafeDispose; array = null; }`
    - Dispose border brush array: same pattern
    - Any StrokeStyle if used
  - Implement `OnRender()`:
    - Guards (in order): `if (IsInHitTest) return;` → `if (RenderTarget == null || ChartBars == null) return;` → `if (_zoneFillBrushes == null) return;`
    - Call `base.OnRender(chartControl, chartScale);`
    - Set `RenderTarget.AntialiasMode = AntialiasMode.Aliased;` for crisp zone edges
    - Calculate visible chart range: `float panelLeft = (float)ChartPanel.X;` `float panelRight = (float)(ChartPanel.X + ChartPanel.W);`
    - Render prior session zones first (drawn behind), then current session zones (drawn on top):
      - For each `SessionZoneData` in `_sessionHistory` (oldest first):
        - `int tierIndex = sessionAge` (0 for most recent prior, increasing for older)
        - For each zone in session:
          - `float zoneTopY = chartScale.GetYByValue(zone.Top);`
          - `float zoneBotY = chartScale.GetYByValue(zone.Bottom);`
          - `var rect = new RectangleF(panelLeft, zoneTopY, panelRight - panelLeft, zoneBotY - zoneTopY);`
          - `RenderTarget.FillRectangle(rect, _zoneFillBrushes[tierIndex + 1]);` (index 0 reserved for current)
          - `RenderTarget.DrawRectangle(rect, _zoneBorderBrushes[tierIndex + 1], 1f);`
      - For each zone in `_currentZones`:
        - Same rectangle calculation
        - `RenderTarget.FillRectangle(rect, _zoneFillBrushes[0]);` (current session = brightest)
        - `RenderTarget.DrawRectangle(rect, _zoneBorderBrushes[0], 1f);`

  **Must NOT do**:
  - Do NOT render text labels, volume amounts, or price annotations
  - Do NOT render per-bar rectangles — each zone is ONE rectangle spanning full chart width
  - Do NOT use radial gradients or glow effects (save GPU budget)
  - Do NOT use PerPrimitive antialiasing for zone fills (Aliased is crisper for rectangles)
  - Do NOT store brushes per-session — use shared opacity-indexed arrays

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: SharpDX rendering with brush lifecycle management, coordinate conversion, and opacity-tiered fill — core visual task
  - **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`, `nt8-visual-design/knowledge`]
    - `nt8-expert`: NT8 chart coordinate system, ChartPanel/ChartScale API
    - `ninjatrader-builder-doctor`: OnRender lifecycle, SharpDX Direct2D1 patterns
    - `nt8-visual-design/knowledge`: DEEP6 color palette, brush creation patterns, DisposeDx conventions, performance rules
  - **Skills Evaluated but Omitted**:
    - `volume-profile-lvn`: Not relevant to rendering

  **Parallelization**:
  - **Can Run In Parallel**: NO (writes to same file as Task 3)
  - **Parallel Group**: Wave 2 (after Task 3)
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 1, 3

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:1073-1221` — Complete OnRenderTargetChanged with 40+ brush allocations, TextFormat creation, DisposeDx call at start
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:1223-1286` — DisposeDx with DisposeBrush/DisposeSolidBrush helpers
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:1288-1372` — OnRender with guards, antialiasing, FillRectangle for cells
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV3.cs:354-384` — Clean OnRenderTargetChanged with glow bloom brush arrays (tier pattern to follow)
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DOMHeatMap.cs:204-237` — Tier-based brush array allocation and disposal
  - `ninjatrader/Custom/DrawingTools/DEEP6LowVolumeNodeTool.cs:242-298` — LVN-specific color scheme: DodgerBlue #1E90FF @ 85%, Cyan #00E0FF

  **External References**:
  - SharpDX.Direct2D1.RenderTarget.FillRectangle API: fills a rectangle with a brush
  - SharpDX.Direct2D1.RenderTarget.DrawRectangle API: draws rectangle outline with stroke width

  **WHY Each Reference Matters**:
  - DEEP6FootprintV8.cs:1073-1221 is THE template for OnRenderTargetChanged. Follow its structure exactly.
  - DEEP6DOMHeatMap.cs:204-237 shows the EXACT tier-based brush array pattern needed for multi-session opacity tiers.
  - DEEP6LowVolumeNodeTool.cs:242-298 defines the specific LVN colors (DodgerBlue/Cyan) to match.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zones render as semi-transparent filled rectangles
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1 + nt8-ui.ps1 -Screenshot)
    Preconditions: DEEP6LVNZones with detected zones (Tasks 1-3 complete)
    Steps:
      1. Deploy and compile
      2. Add to NQ 5-min chart with historical data
      3. Take screenshot
      4. Verify: semi-transparent rectangular zones visible on chart
      5. Verify: zones span full chart width (forward projection to right edge)
      6. Verify: zones have visible 1px border
    Expected Result: Screenshot shows filled rectangular zones spanning chart width with border
    Failure Indicators: No zones visible, zones truncated before right edge, no border visible, opaque zones hiding price action
    Evidence: .sisyphus/evidence/task-4-zones-rendered.png

  Scenario: Resource cleanup on remove/re-add
    Tool: Bash (nt8-ui.ps1 + Output window)
    Preconditions: Indicator on chart
    Steps:
      1. Remove indicator from chart
      2. Check Output window for dispose errors
      3. Re-add indicator to chart
      4. Check Output window for allocation errors
      5. Verify zones render correctly after re-add
    Expected Result: Zero errors in Output window during remove/re-add cycle, zones render correctly after re-add
    Failure Indicators: ObjectDisposedException, null reference errors, visual artifacts after re-add
    Evidence: .sisyphus/evidence/task-4-resource-cleanup.txt
  ```

  **Commit**: NO (intermediate — commits with Task 6)

---

- [x] 5. Multi-Session Archival + Session Lifecycle

  **What to do**:
  - Implement multi-session zone archival in OnBarUpdate session boundary handler:
    - When SessionIterator detects RTH session transition:
      1. If `_currentZones.Count > 0`: Create `SessionZoneData { PeriodKey, SessionStart, Zones = new List<LvnZone>(_currentZones) }`
      2. Add to `_sessionHistory`
      3. If `_sessionHistory.Count > MaxSessions`: `_sessionHistory.RemoveAt(0)` (remove oldest)
      4. Clear `_currentZones` and `_periodBars`
      5. Reset profile arrays (`_vpValues`, `_vpYVol`)
  - Implement `_allZones` update on every profile rebuild:
    - `_allZones = new List<LvnZone>(_currentZones.Count + _sessionHistory.Sum(s => s.Zones.Count))`
    - Add current zones first, then all prior session zones (newest first)
  - Implement session age tracking for opacity mapping:
    - In OnRender, compute `sessionAge` for each SessionZoneData: `sessionAge = _sessionHistory.Count - sessionIndex` (0 = most recent prior)
    - Map to brush tier: `int tierIndex = Math.Min(sessionAge, _zoneFillBrushes.Length - 1)`
  - Handle edge cases:
    - Chart loaded on weekend (all sessions are "prior"): All zones render as prior-session with appropriate dimming
    - Indicator added mid-session: Current session builds from available bars, prior sessions empty until a full session boundary is crossed
    - Holiday/half-day: If `_periodBars.Count < MinBarsForProfile`, session produces no zones (no empty SessionZoneData archived)

  **Must NOT do**:
  - Do NOT add zone merging across sessions
  - Do NOT add per-session color customization
  - Do NOT add zone decay or expiration by time
  - Do NOT add touch tracking or retest counting

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Session lifecycle management with edge cases, list management, and coordination with rendering — moderately complex integration
  - **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`]
    - `nt8-expert`: SessionIterator behavior, NT8 session boundaries
    - `ninjatrader-builder-doctor`: OnBarUpdate lifecycle, multi-series data handling
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design/knowledge`: Rendering already implemented in Task 4

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (after Tasks 2, 3)
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:98-120` — Session boundary detection and profile reset (calendar-day version — adapt to SessionIterator)
  - `ninjatrader/Custom/Strategies/DEEP6/DEEP6LVNRadarStrategy.cs:382-415` — Multi-period profile management with ClearProfile() on boundary change
  - `ninjatrader/Custom/AddOns/DEEP6/Levels/ProfileAnchorLevels.cs:177-192` — Session completion archival pattern with age tracking and max session limit

  **WHY Each Reference Matters**:
  - ProfileAnchorLevels.cs:177-192 is the closest existing multi-session archival pattern. It tracks prior-session POCs with age-based expiration. Follow this lifecycle pattern for zone archival.
  - DEEP6LVNRadarStrategy.cs:382-415 shows how to cleanly reset a profile state on session boundary.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Multiple sessions visible with opacity gradient
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1 + nt8-ui.ps1 -Screenshot)
    Preconditions: Chart loaded with 3+ days of NQ historical data, MaxSessions=2
    Steps:
      1. Deploy and compile
      2. Add to NQ 5-min chart showing 3+ trading days
      3. Take screenshot
      4. Verify: current session zones are brightest
      5. Verify: prior session zones are progressively dimmer
      6. Verify: at most MaxSessions prior session zone sets visible
    Expected Result: Screenshot shows 2-3 session zone sets with clear opacity difference between current and prior
    Failure Indicators: All zones same opacity, more than MaxSessions prior sessions visible, prior session zones brighter than current
    Evidence: .sisyphus/evidence/task-5-multi-session.png

  Scenario: Session boundary resets zones correctly
    Tool: Bash (nt8-compile.ps1 + Output window)
    Preconditions: Chart with multiple NQ sessions
    Steps:
      1. Add Print() logging: zone count per session, session archive count
      2. Compile and load on chart
      3. Verify: _sessionHistory.Count <= MaxSessions
      4. Verify: _currentZones clears on session transition
      5. Verify: prior session zones persist after transition
    Expected Result: Session archive respects MaxSessions limit, current zones reset cleanly
    Failure Indicators: _sessionHistory grows unbounded, zones carry over across sessions, old sessions not pruned
    Evidence: .sisyphus/evidence/task-5-session-lifecycle.txt
  ```

  **Commit**: NO (intermediate — commits with Task 6)

---

- [x] 6. Full Integration + Deployment + Cross-Validation

  **What to do**:
  - Final integration pass on DEEP6LVNZones.cs:
    - Remove all debug Print() statements added in prior tasks
    - Verify all method stubs are fully implemented (no empty methods)
    - Verify `_allZones` is always non-null (initialized as empty list in SetDefaults or DataLoaded)
    - Add XML serialization support for Brush properties: `[XmlIgnore]` on Brush + `[Browsable(false)] public string ZoneBrushSerialize { get { return Serialize.BrushToString(ZoneBrush); } set { ZoneBrush = Serialize.StringToBrush(value); } }`
    - Add `#region Properties` / `#endregion` organization
    - Add brief XML comments on class and key methods
  - Deploy and compile:
    - `nt8-deploy.ps1` → copy to NT8 indicators directory
    - `nt8-compile.ps1` → verify SUCCESS
  - Full QA validation:
    - Add to NQ 5-min chart — verify zones render
    - Add to NQ 15-min chart — verify zones render (timeframe independence)
    - Add VPLowTFLVNLevels to same chart — cross-validate LVN prices match
    - Remove → re-add cycle — verify no errors
    - Screenshot all states
  - Run `lsp_diagnostics` on the .cs file to catch any remaining issues
  - Verify every brush in OnRenderTargetChanged has matching dispose in DisposeDx

  **Must NOT do**:
  - Do NOT add features beyond the plan (no labels, alerts, merging, etc.)
  - Do NOT modify any other DEEP6 files
  - Do NOT leave debug Print() statements in final code

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Integration, cleanup, deployment, and multi-scenario QA — requires careful attention to detail
  - **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`, `nt8-visual-design/knowledge`]
    - `nt8-expert`: NT8 deployment, compilation, UI automation for adding indicator to chart
    - `ninjatrader-builder-doctor`: NinjaScript best practices, property serialization
    - `nt8-visual-design/knowledge`: Visual verification of zone rendering against DEEP6 standards
  - **Skills Evaluated but Omitted**:
    - `volume-profile-lvn`: Not needed for integration/QA

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (final implementation task)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 3, 4, 5

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs:218-270` — Property serialization pattern for Brush properties with [XmlIgnore] + Serialize helper
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:2469-2599` — Property grouping and organization pattern
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV3.cs:552-563` — Clean DisposeDx pattern for verification

  **WHY Each Reference Matters**:
  - VPLowTFLVNLevels.cs:218-270 shows the exact Brush serialization pattern NT8 requires. Missing this causes settings to not persist across chart reloads.
  - DEEP6FootprintV8.cs:2469-2599 shows the property grouping convention to follow.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full compilation and deployment
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1)
    Preconditions: DEEP6LVNZones.cs fully integrated
    Steps:
      1. Run: .\ninjatrader\scripts\nt8-deploy.ps1 -File "DEEP6LVNZones.cs"
      2. Run: .\ninjatrader\scripts\nt8-compile.ps1
      3. Verify: [COMPILE-RESULT] SUCCESS
      4. Run lsp_diagnostics on ninjatrader/Custom/Indicators/DEEP6/DEEP6LVNZones.cs
      5. Verify: zero errors
    Expected Result: Clean compilation with zero errors and zero diagnostics
    Failure Indicators: Any CS error, any lsp_diagnostic error
    Evidence: .sisyphus/evidence/task-6-final-compile.txt

  Scenario: Cross-validation — LVN prices match VPLowTFLVNLevels
    Tool: Bash (nt8-ui.ps1 -Screenshot)
    Preconditions: Both indicators compiled, NQ 5-min chart with RTH data
    Steps:
      1. Add DEEP6LVNZones with Rows=200, LvnStrength=5
      2. Add VPLowTFLVNLevels with Rows=200, LvnStrength=5
      3. Take screenshot showing both indicators on same chart
      4. Visually verify: LVN zone center lines align with VPLowTFLVNLevels horizontal lines
    Expected Result: Zone midpoints (LvnPrice) align with VPLowTFLVNLevels lines within 1 tick
    Failure Indicators: Zone centers at different prices, different number of zones vs lines
    Evidence: .sisyphus/evidence/task-6-cross-validation.png

  Scenario: Timeframe independence — works on 15-min chart
    Tool: Bash (nt8-ui.ps1 -Screenshot)
    Preconditions: DEEP6LVNZones compiled
    Steps:
      1. Add DEEP6LVNZones to NQ 15-min chart
      2. Take screenshot
      3. Verify: zones visible and correctly rendered
      4. Verify: zones from current + prior sessions present
    Expected Result: Zones render correctly on 15-min chart (1-min secondary series handles resolution)
    Failure Indicators: No zones visible, rendering errors, different zones than 5-min chart
    Evidence: .sisyphus/evidence/task-6-timeframe-independence.png

  Scenario: Remove and re-add cycle
    Tool: Bash (nt8-ui.ps1 + Output window)
    Preconditions: DEEP6LVNZones on NQ chart
    Steps:
      1. Remove DEEP6LVNZones from chart
      2. Check Output window — expect zero errors
      3. Re-add DEEP6LVNZones to chart
      4. Check Output window — expect zero errors
      5. Verify zones render correctly after re-add
      6. Take screenshot
    Expected Result: Zero errors during remove/re-add, zones render correctly after re-add
    Failure Indicators: ObjectDisposedException, null reference, visual artifacts, zones missing after re-add
    Evidence: .sisyphus/evidence/task-6-remove-readd.png
  ```

  **Commit**: YES
  - Message: `feat(indicators): add DEEP6LVNZones — session-based LVN zone indicator with SharpDX rendering`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6LVNZones.cs`
  - Pre-commit: `nt8-compile.ps1` returns SUCCESS

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists in `DEEP6LVNZones.cs` (read file, check class members, verify method signatures). For each "Must NOT Have": search the .cs file for forbidden patterns (zone merging, text rendering, alerting, Volumetric bars) — reject with line number if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `lsp_diagnostics` on `DEEP6LVNZones.cs`. Review for: `as any` equivalents, empty catches (except in SafeDispose), unused imports, commented-out code. Verify every brush allocated in `OnRenderTargetChanged` has a matching dispose in `DisposeDx`. Check thread safety for cross-thread access to zone data. Verify OnRender guards match DEEP6 convention (IsInHitTest, RenderTarget null, ChartBars null).
  Output: `Diagnostics [PASS/FAIL] | Resource Mgmt [PASS/FAIL] | Thread Safety [PASS/FAIL] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `nt8-expert` skill)
  Deploy indicator to NT8 via `nt8-deploy.ps1`. Compile via `nt8-compile.ps1`. Add to NQ 5-min chart. Screenshot showing zones. Add VPLowTFLVNLevels to same chart — screenshot comparing LVN prices. Remove indicator, re-add — check Output window for errors. Try on 15-min chart — verify zones still render. Save all screenshots to `.sisyphus/evidence/final-qa/`.
  Output: `Compile [PASS/FAIL] | Zones Visible [PASS/FAIL] | Cross-Validation [PASS/FAIL] | Remove/Re-add [PASS/FAIL] | Multi-TF [PASS/FAIL] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  Read `DEEP6LVNZones.cs` end-to-end. For each task in the plan: verify the described functionality exists. Check "Must NOT Have" list — search for zone merging logic, text rendering code, alert code, interactive mouse handlers, POC/VAH/VAL computation. Flag any code that wasn't in the plan. Verify file is in correct namespace and directory.
  Output: `Tasks [N/N compliant] | Guardrails [N/N clean] | Unaccounted [CLEAN/N items] | VERDICT`

---

## Commit Strategy

- **Single commit after Task 6**: `feat(indicators): add DEEP6LVNZones — session-based LVN zone indicator with SharpDX rendering`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6LVNZones.cs`
  - Pre-commit: `nt8-compile.ps1` returns SUCCESS

---

## Success Criteria

### Verification Commands
```powershell
# Deploy to NT8
.\ninjatrader\scripts\nt8-deploy.ps1 -File "DEEP6LVNZones.cs"

# Compile in NT8
.\ninjatrader\scripts\nt8-compile.ps1
# Expected: [COMPILE-RESULT] SUCCESS

# Screenshot chart with indicator
.\ninjatrader\scripts\nt8-ui.ps1 -Screenshot
# Expected: Semi-transparent rectangular zones visible on NQ chart
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Compiles without errors
- [ ] Zones render correctly on chart (screenshot evidence)
- [ ] Multi-session opacity gradient visible (screenshot evidence)
- [ ] Forward projection to chart right edge (screenshot evidence)
- [ ] Cross-validation: LVN prices match VPLowTFLVNLevels
- [ ] Add/remove/re-add cycle: no errors in Output window
- [ ] Works on both 5-min and 15-min primary timeframes
