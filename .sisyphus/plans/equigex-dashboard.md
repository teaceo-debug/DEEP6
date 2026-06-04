# DEEP6 EquiGEX Institutional Dashboard — Phase 1

## TL;DR

> **Quick Summary**: Build Phase 1 of the DEEP6 EquiGEX indicator for NinjaTrader 8 — an institutional-grade price overlay that classifies ES/NQ price into Premium/Equilibrium/Discount zones using a Synthetic Fair Value line derived from GEX zero-gamma levels and anchored VWAP, rendered in Bloomberg Terminal aesthetic with SharpDX.
> 
> **Deliverables**:
> - `DEEP6EquiGEX.cs` — Main indicator (lifecycle, properties, OnBarUpdate dispatch)
> - `DEEP6EquiGEX.Models.cs` — JSON DTOs, enums, JSON loader with stale detection
> - `DEEP6EquiGEX.Engines.cs` — SFV calculation, AVWAP, bands, zone classifier, HH/HL trend, bias chip scoring
> - `DEEP6EquiGEX.Render.cs` — Full SharpDX rendering (SFV line, zone fills, bands, bias chip, stale badge, header)
> - `gex_snapshot_example.json` — Example GEX data file matching the spec schema
> 
> **Estimated Effort**: Large (11 implementation tasks + 4 verification)
> **Parallel Execution**: YES — 5 waves, max 4 concurrent in Wave 2
> **Critical Path**: T1 → T5 (AVWAP) → T7 (SFV+Bands) → T9 (Rendering) → T10 (Integration)

---

## Context

### Original Request
Build DEEP6 EquiGEX — a production-grade NinjaTrader 8 indicator for ES/NQ futures that visually replicates a Bloomberg Terminal × Goldman Marquee institutional GEX decision surface. Phase 1 only: core equilibrium model with Synthetic Fair Value, Premium/Equilibrium/Discount zones, composite bias chip, JSON GEX sidecar, and stale feed protection.

The user stated: *"I want this to be the best indicator we've ever created."*

### Interview Summary
**Key Discussions**:
- **Trend detection method**: Higher highs/higher lows market structure (5-bar pivot lookback on 4H chart). More institutional than EMA crossover.
- **AVWAP anchor**: Sunday 6 PM ET futures open. Full week including overnight sessions. Resets weekly.
- **Testing strategy**: No automated tests. NT8 compile + visual verification + agent-executed QA scenarios.
- **JSON schema**: New file format (spec-provided). Written by external Python service or manually. Indicator reads only.
- **Instrument support**: ES, NQ, MES, MNQ via `NormalizeRoot()` auto-detection.

**Research Findings**:
- **82+ existing DEEP6 NT8 indicators** — comprehensive pattern library
- **MADConfluenceAI** — gold standard partial class pattern (5-file split in subfolder)
- **GEXCommand.cs** — JavaScriptSerializer + System.Threading.Timer + FileShare.ReadWrite + lock pattern for JSON loading
- **DEEP6AnchoredVWAP.cs** — Drawing tool (NOT reusable). AVWAP must be built from scratch.
- **DEEP6FootprintV8.cs** — F1 Pitwall color palette, typography hierarchy (Consolas 7-32pt)
- **Established SharpDX patterns**: Inline brush factory `B(r,g,b,a)`, pre-allocated palettes, `DisposeDx()` with generic disposer
- **JSON sidecar convention**: `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json`

### Metis Review
**Identified Gaps** (all addressed):
- **AVWAP is NOT a reuse — it's a full build**: Existing DEEP6AnchoredVWAP.cs is a drawing tool requiring manual anchor placement. Programmatic weekly AVWAP with Sunday 6 PM ET anchor is new code. → Dedicated task (T5) with highest-risk status.
- **JSON schema freeze**: Schema provided in spec. Treated as frozen. No modifications during Phase 1.
- **HH/HL swing definition**: Undefined in original spec. → Defined as 5-bar left / 2-bar right pivot lookback on primary 4H series.
- **ATR source ambiguity**: → Resolved: ATR(14) on primary 4H chart series (14 bars ≈ 2-3 trading days).
- **Weekly/Daily secondary series REMOVED**: Metis flagged that no calculation engine actually consumes daily/weekly bar data (all from JSON or primary series). Momus confirmed AddDataSeries risks pushing the overlay into a sub-panel. AVWAP weekly boundary detected from primary series timestamps via TimeZoneInfo. This eliminates BarsInProgress complexity and sub-panel risk entirely.
- **Edge cases**: 12 edge cases identified (no JSON, zero gamma, <14 bars, holidays, DST, partial writes, symbol switch, etc.). All have defined fallback behavior.
- **Scope creep risk**: Locked down — no Phase 2 features, no 5th bias factor, no dynamic AVWAP anchor, no alert conditions.

---

## Work Objectives

### Core Objective
Build Phase 1 of the DEEP6 EquiGEX indicator: a Bloomberg-aesthetic price overlay that classifies ES/NQ price into Premium/Equilibrium/Discount zones using Synthetic Fair Value (derived from GEX zero-gamma + AVWAP), rendered with institutional SharpDX graphics.

### Concrete Deliverables
- 4 C# partial class files in `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/`
- 1 example JSON file (`gex_snapshot_example.json`)
- Indicator compiles in NT8, renders on 4H ES/NQ chart, reads GEX JSON, shows stale badge on missing data

### Definition of Done
- [ ] NT8 compile succeeds (`nt8-compile.ps1` → `[COMPILE-RESULT] SUCCESS`)
- [ ] All 4 .cs files deployed to `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\EquiGEX\`
- [ ] SFV yellow line renders on 4H chart
- [ ] Premium (red) and Discount (green) zone fills visible
- [ ] Bias chip pill displays in top-right (BULLISH/BEARISH/NEUTRAL with correct colors)
- [ ] Stale feed badge appears when JSON is removed
- [ ] No UI freezing during normal operation
- [ ] Indicator handles missing JSON gracefully (no crash)

### Must Have
- Synthetic Fair Value line (bold yellow, 2px, labeled)
- Premium band (red transparent fill above SFV)
- Discount band (green transparent fill below SFV)
- Equilibrium zone (dark gray between bands)
- Current zone label on chart
- Bias chip pill (green BULLISH / red BEARISH / gold NEUTRAL) — top-right
- JSON GEX sidecar loading with 30-second polling
- Stale feed badge (red, 10-minute threshold)
- Thread-safe JSON access (lock pattern)
- Auto-detect ES/NQ/MES/MNQ instruments
- User-configurable weights (WeeklyZeroGamma, DailyZeroGamma, AVWAP)
- User-configurable VolMultiplier for band width

### Must NOT Have (Guardrails)
- ❌ **No GEX computation inside the indicator** — all GEX data from JSON sidecar only
- ❌ **No Phase 2 features** — no GEX histograms, GEX curve, key levels table, alerts panel, or scaffolding for them
- ❌ **No more than 4 bias factors** — trend (HH/HL), zone position, gamma regime, price vs daily zero gamma
- ❌ **No dynamic AVWAP anchor** — always Sunday 6 PM ET, not user-configurable
- ❌ **No alert conditions in Phase 1** — not even commented-out stubs
- ❌ **No Newtonsoft.Json or System.Text.Json** — use JavaScriptSerializer (NT8 standard)
- ❌ **No System.Timers.Timer** — use System.Threading.Timer (NT8 convention)
- ❌ **No regex-based JSON parsing** — use JavaScriptSerializer with strongly-typed DTOs
- ❌ **No SharpDX resource allocation inside OnRender** — all pre-allocated in OnRenderTargetChanged
- ❌ **No AVWAP recalculation on every tick** — only on bar close or session boundary
- ❌ **No LINQ inside OnRender** — performance critical
- ❌ **No excessive comments, JSDoc, or AI-slop abstractions** — clean institutional code

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (NT8 has no automated test framework)
- **Automated tests**: NONE
- **Framework**: N/A
- **Verification method**: NT8 compile verification + visual chart inspection + functional QA via HERMES

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Compilation**: HERMES runs `nt8-compile.ps1`, asserts `[COMPILE-RESULT] SUCCESS`
- **Deployment**: HERMES runs `nt8-deploy.ps1 -Target Indicators`, verifies file copy
- **Visual**: HERMES adds indicator to chart via `nt8-ui.ps1`, captures screenshot, agent inspects
- **Functional**: HERMES manipulates JSON file (remove, corrupt, restore), verifies indicator behavior
- **JSON setup**: For QA scenarios requiring JSON, HERMES must first copy `gex_snapshot_example.json` from the repo to `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json`. The GEX directory may need to be created first.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — start immediately, 2 parallel):
├── Task 1: Skeleton stubs + example JSON + compile verify [quick]
└── Task 2: README documentation [writing]

Wave 2 (Core Systems — 4 parallel, max throughput):
├── Task 3: Data models + enums (Models.cs) [quick] (depends: T1)
├── Task 4: Main indicator lifecycle — NO AddDataSeries (DEEP6EquiGEX.cs) [unspecified-high] (depends: T1)
├── Task 5: AVWAP engine (Engines.cs) [deep] (depends: T1) ⚠️ HIGHEST RISK
└── Task 6: HH/HL trend engine (Engines.cs) [deep] (depends: T1)

Wave 3 (Composite Engines — 2 tasks):
├── Task 7: SFV + Bands + Zone Classifier (Engines.cs) [deep] (depends: T3, T4, T5)
└── Task 8: Bias Chip scoring (Engines.cs) [quick] (depends: T6, T7)

Wave 4 (Rendering — 1 comprehensive task):
└── Task 9: Full SharpDX rendering (Render.cs) [visual-engineering] (depends: T7, T8)

Wave 5 (Integration + QA — 2 tasks):
├── Task 10: Deploy + compile + visual verification [unspecified-high] (depends: T9)
└── Task 11: Edge case QA testing [unspecified-high] (depends: T10)

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

**Critical Path**: T1 → T5 (AVWAP) → T7 (SFV+Bands) → T9 (Rendering) → T10 (Integration) → F1-F4 → user okay
**Parallel Speedup**: ~50% faster than sequential
**Max Concurrent**: 4 (Wave 2)

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T3, T4, T5, T6 | 1 |
| T2 | — | — | 1 |
| T3 | T1 | T7 | 2 |
| T4 | T1 | T7 | 2 |
| T5 | T1 | T7 | 2 |
| T6 | T1 | T8 | 2 |
| T7 | T3, T4, T5 | T8, T9 | 3 |
| T8 | T6, T7 | T9 | 3 |
| T9 | T7, T8 | T10 | 4 |
| T10 | T9 | T11 | 5 |
| T11 | T10 | F1-F4 | 5 |
| F1-F4 | T11 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **2** — T1 → `quick`, T2 → `writing`
- **Wave 2**: **4** — T3 → `quick`, T4 → `unspecified-high`, T5 → `deep`, T6 → `deep`
- **Wave 3**: **2** — T7 → `deep`, T8 → `quick`
- **Wave 4**: **1** — T9 → `visual-engineering`
- **Wave 5**: **2** — T10 → `unspecified-high`, T11 → `unspecified-high`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Scaffold Skeleton Stubs + Example JSON + Compile Verify

  **What to do**:
  - Create directory: `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/`
  - Create 4 stub .cs files with correct namespace, using declarations, and empty partial class bodies:
    - `DEEP6EquiGEX.cs` — `public partial class DEEP6EquiGEX : Indicator` with minimal `OnStateChange` (State.SetDefaults: Name="DEEP6 EquiGEX", IsOverlay=true) and empty `OnBarUpdate`
    - `DEEP6EquiGEX.Models.cs` — `public partial class DEEP6EquiGEX` with comment placeholder
    - `DEEP6EquiGEX.Models.cs` stub also includes **empty JSON loader method stubs**:
      ```csharp
      private void StartJsonPolling() { }
      private void StopJsonPolling() { }
      ```
    - `DEEP6EquiGEX.Engines.cs` — `public partial class DEEP6EquiGEX` with **empty method stubs** for all engine methods that T4's OnBarUpdate will call:
      ```csharp
      private void UpdateAVWAP() { }
      private void UpdateTrend() { }
      private void UpdateSFVAndZones() { }
      private void UpdateBiasChip() { }
      private void DisposeDx() { }
      ```
      These stubs ensure T4 can compile against Engines.cs and Models.cs before T3/T5-T8 replace them with real implementations.
    - `DEEP6EquiGEX.Render.cs` — `public partial class DEEP6EquiGEX` with empty render stub:
      ```csharp
      public override void OnRenderTargetChanged() { DisposeDx(); }
      ```
  - All files use namespace `NinjaTrader.NinjaScript.Indicators.DEEP6`
  - All files use the standard DEEP6 using declarations block:
    ```csharp
    #region Using declarations
    using System;
    using System.Collections.Generic;
    using System.ComponentModel;
    using System.ComponentModel.DataAnnotations;
    using System.IO;
    using System.Threading;
    using System.Web.Script.Serialization;
    using System.Windows.Media;
    using SharpDX;
    using SharpDX.Direct2D1;
    using SharpDX.DirectWrite;
    using NinjaTrader.Cbi;
    using NinjaTrader.Data;
    using NinjaTrader.Gui;
    using NinjaTrader.Gui.Chart;
    using NinjaTrader.NinjaScript;
    using Brush = System.Windows.Media.Brush;
    using Brushes = System.Windows.Media.Brushes;
    #endregion
    ```
  - Create `gex_snapshot_example.json` with the full spec schema:
    ```json
    {
      "asof": "2024-05-20T15:30:00Z",
      "underlying": "ES",
      "spot": 5308.75,
      "weekly": {
        "strikes": [
          { "k": 5100, "gex": -0.42 },
          { "k": 5200, "gex": 0.34 },
          { "k": 5300, "gex": 0.85 },
          { "k": 5375, "gex": 1.20 }
        ],
        "call_wall": 5375,
        "zero_gamma": 5240,
        "put_wall": 5115,
        "net_gex": 1.32
      },
      "daily": {
        "strikes": [
          { "k": 5270, "gex": -0.25 },
          { "k": 5302, "gex": 0.10 },
          { "k": 5325, "gex": 0.55 }
        ],
        "call_wall": 5325,
        "zero_gamma": 5302,
        "put_wall": 5270,
        "net_gex": -0.24
      }
    }
    ```
  - Deploy via `nt8-deploy.ps1 -Target Indicators`
  - Compile via `nt8-compile.ps1` — verify stubs compile successfully

  **Must NOT do**:
  - Do NOT add any implementation logic in stubs — just namespace, class declaration, empty bodies
  - Do NOT add NinjaScriptProperty attributes yet (that's T4)
  - Do NOT add Phase 2 placeholder sections

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file creation and compile verification. No complex logic.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Knows NT8 file paths, deployment scripts, compile verification, namespace rules
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed — no rendering in this task

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Tasks 3, 4, 5, 6
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` — Gold standard partial class pattern. Copy the namespace declaration, using block structure, and class inheritance pattern exactly.
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Data.cs` — Partial class extension pattern (no inheritance, same namespace).
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:1-30` — Standard DEEP6 using declarations block with type aliases for Brush/Brushes/Color.

  **Deployment References**:
  - `ninjatrader/scripts/nt8-deploy.ps1` — Deploy command: `.\nt8-deploy.ps1 -Target Indicators`
  - `ninjatrader/scripts/nt8-compile.ps1` — Compile command and expected output format
  - `.claude/skills/nt8-expert/knowledge.md` — NT8 custom directory paths, compile detection methods

  **WHY Each Reference Matters**:
  - MADConfluenceAI shows the EXACT multi-file partial class pattern to copy — same subfolder structure, same namespace convention
  - DEEP6Footprint shows the canonical using declarations block — must match for NT8 to compile all DEEP6 indicators together
  - nt8-deploy.ps1 is the ONLY safe way to move files to NT8 — manual copy can miss directories

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Skeleton compiles in NT8
    Tool: Bash (PowerShell)
    Preconditions: NT8 is running, no prior DEEP6EquiGEX files exist
    Steps:
      1. Run `.\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators`
      2. Verify output contains "EquiGEX" file copies
      3. Run `.\ninjatrader\scripts\nt8-compile.ps1`
      4. Assert output contains `[COMPILE-RESULT] SUCCESS`
    Expected Result: All 4 .cs stubs compile together without errors
    Failure Indicators: `[COMPILE-RESULT] FAILED` or CS0246/CS0234 errors
    Evidence: .sisyphus/evidence/task-1-skeleton-compile.txt

  Scenario: All files exist in correct locations
    Tool: Bash (PowerShell)
    Preconditions: nt8-deploy.ps1 has been run
    Steps:
      1. Run `Get-ChildItem "C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\EquiGEX" -Recurse`
      2. Assert 4 .cs files exist: DEEP6EquiGEX.cs, DEEP6EquiGEX.Models.cs, DEEP6EquiGEX.Engines.cs, DEEP6EquiGEX.Render.cs
      3. Assert gex_snapshot_example.json exists in `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/`
    Expected Result: 4 .cs files in NT8 deploy directory, 1 JSON in repo
    Failure Indicators: Missing files, wrong directory path
    Evidence: .sisyphus/evidence/task-1-file-listing.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-skeleton-compile.txt — compile output
  - [ ] task-1-file-listing.txt — directory listing

  **Commit**: YES (groups with T2)
  - Message: `feat(equigex): scaffold Phase 1 skeleton with stubs and example JSON`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/*.cs`, `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/gex_snapshot_example.json`
  - Pre-commit: `nt8-compile.ps1` SUCCESS

---

- [x] 2. Write README Documentation (deferred — low priority)

  **What to do**:
  - Create `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/README.md`
  - Document:
    - Indicator name: DEEP6 EquiGEX
    - Purpose: Institutional equilibrium model overlay for ES/NQ futures
    - Phase 1 features: SFV line, Premium/Equilibrium/Discount zones, bias chip, JSON GEX sidecar
    - File structure: 4 partial classes + JSON
    - JSON schema: Document all fields with types and descriptions
    - JSON file location: `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json`
    - User-configurable settings: WeightWeekly, WeightDaily, WeightAVWAP, VolMultiplier, GexJsonPath, ShowDashboard, ShowDebugValues (EnableSoundAlerts deferred to Phase 2)
    - Supported instruments: ES, NQ, MES, MNQ
    - Stale feed behavior: 10-minute threshold, red badge, dimmed state
    - Phase 2 roadmap (brief mention — GEX histograms, key levels, alerts panel)

  **Must NOT do**:
  - Do NOT write implementation details or code snippets — this is user-facing documentation
  - Do NOT promise Phase 2 delivery dates

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Pure documentation task, no code involved
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `nt8-expert`: Not needed — no NT8 interaction for a README

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: None
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `ninjatrader/README.md` — Existing NT8 layer documentation style and structure
  - User's original spec (this plan's Context section) — Authoritative source for feature descriptions and JSON schema

  **WHY Each Reference Matters**:
  - ninjatrader/README.md sets the documentation tone and structure for the NT8 layer — match it

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: README contains all required sections
    Tool: Bash (grep)
    Preconditions: README.md has been created
    Steps:
      1. Read `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/README.md`
      2. Assert contains: "DEEP6 EquiGEX", "Synthetic Fair Value", "gex_snapshot.json", "WeightWeekly", "stale"
      3. Assert JSON schema is documented with all fields (asof, underlying, spot, weekly.*, daily.*)
    Expected Result: README covers purpose, features, JSON schema, settings, stale behavior
    Failure Indicators: Missing sections, undocumented settings
    Evidence: .sisyphus/evidence/task-2-readme-review.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-readme-review.txt — grep results confirming all sections present

  **Commit**: YES (groups with T1)
  - Message: `feat(equigex): scaffold Phase 1 skeleton with stubs and example JSON`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/EquiGEX/README.md`

---

- [x] 3. Implement Data Models, Enums, AND JSON Loader (Models.cs)

  **What to do**:
  - In `DEEP6EquiGEX.Models.cs`, implement at **namespace level** (before the partial class):
    - `enum ZoneType { Premium, Equilibrium, Discount, Unknown }`
    - `enum GammaRegime { Positive, Negative, Unknown }`
    - `enum BiasDirection { Bullish, Bearish, Neutral }`
    - `enum TrendDirection { Bullish, Bearish, Neutral }`
  - Implement JSON DTO classes at namespace level:
    ```csharp
    public class GexSnapshot
    {
        public string asof { get; set; }
        public string underlying { get; set; }
        public double spot { get; set; }
        public GexTenor weekly { get; set; }
        public GexTenor daily { get; set; }
    }
    
    public class GexTenor
    {
        public List<GexStrike> strikes { get; set; }
        public double call_wall { get; set; }
        public double zero_gamma { get; set; }
        public double put_wall { get; set; }
        public double net_gex { get; set; }
    }
    
    public class GexStrike
    {
        public double k { get; set; }
        public double gex { get; set; }
    }
    ```
  - Inside the partial class, add a `GexState` holder class:
    ```csharp
    private class GexState
    {
        public GexSnapshot Snapshot;
        public DateTime LastValidRead;
        public bool IsStale;
        public bool HasData;
        public string StatusText;
    }
    ```
  - **Implement the FULL JSON loader** inside the partial class (replaces the T1 stubs):
    - **State fields**:
      ```csharp
      private readonly object _gexLock = new object();
      private GexState _gexState = new GexState();
      private Timer _jsonTimer;  // System.Threading.Timer
      private static readonly JavaScriptSerializer _jsonSerializer = new JavaScriptSerializer();
      private const int JSON_POLL_MS = 30000;  // 30 seconds
      private const int STALE_THRESHOLD_SEC = 600;  // 10 minutes
      ```
    - **`StartJsonPolling()`**: Create and start `_jsonTimer = new Timer(ReadSnapshotSafe, null, 0, JSON_POLL_MS)` — first read immediately (delay=0), then every 30s
    - **`StopJsonPolling()`**: `_jsonTimer?.Dispose(); _jsonTimer = null;`
    - **`ReadSnapshotSafe(object state)`**: Try-catch wrapper that calls `ReadSnapshot()`, catches all exceptions, sets `_gexState.StatusText = "Read error: " + ex.Message`
    - **`ReadSnapshot()`**: Core loading logic:
      1. Resolve path: if `GexJsonPath` is empty, use default `Path.Combine(Environment.GetFolderPath(SpecialFolder.MyDocuments), @"NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json")`
      2. Check `File.Exists(path)` — if missing: `lock(_gexLock) { _gexState.HasData = false; _gexState.StatusText = "Missing JSON"; }` and return
      3. Read with `using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)) using (var sr = new StreamReader(fs))` → `string json = sr.ReadToEnd()`
      4. Deserialize: `var snapshot = _jsonSerializer.Deserialize<GexSnapshot>(json)`
      5. **Asset matching**: `NormalizeRoot(Instrument.MasterInstrument.Name)` must match `snapshot.underlying` (case-insensitive). If no match, set `StatusText = "No matching asset"` and return.
      6. **Stale detection**: Parse `snapshot.asof` → if `(DateTime.UtcNow - asofUtc).TotalSeconds > STALE_THRESHOLD_SEC`, set `IsStale = true`
      7. **Update state under lock**: `lock(_gexLock) { _gexState.Snapshot = snapshot; _gexState.HasData = true; _gexState.IsStale = isStale; _gexState.LastValidRead = DateTime.UtcNow; _gexState.StatusText = isStale ? "STALE FEED" : "OK"; }`
      8. **Refresh chart**: `if (ChartControl != null) ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));`
    - **`GetGexState()`**: Thread-safe getter: `lock(_gexLock) { return _gexState; }` — used by engine methods to read current GEX data
  - Deploy + compile-verify

  **Must NOT do**:
  - Do NOT use Newtonsoft.Json — use JavaScriptSerializer (System.Web.Script.Serialization)
  - Do NOT use System.Timers.Timer — use System.Threading.Timer
  - Do NOT use regex for JSON parsing — use typed deserialization
  - Do NOT read JSON synchronously on UI thread — timer runs on ThreadPool

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Combines type definitions with substantial JSON loading infrastructure including threading, error handling, and stale detection.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Knows NT8 namespace rules and compilation requirements
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed — no rendering types

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6)
  - **Blocks**: Task 7
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs:41-66` — Existing `GexLevelKind` enum and `GexLevel`/`GexProfile` class pattern. Follow this naming and structure style.
  - `ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs:137-188` — **GOLD STANDARD** for JSON loading. Copy the `ReadSnapshot()`/`ReadSnapshotSafe()` pattern, the `JavaScriptSerializer` usage, `FileStream` with `FileShare.ReadWrite`, lock pattern, stale detection, and `Dispatcher.BeginInvoke` chart refresh. This is the exact pattern to replicate.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs:482-493` — Timer-based JSON check pattern with `OnJsonCheck(object state)` wrapper and `Interlocked.Exchange` for dirty flag.

  **API/Type References**:
  - `gex_snapshot_example.json` (created in T1) — The exact JSON schema these DTOs must deserialize from. Field names in DTO MUST match JSON keys exactly (lowercase).
  - `System.Web.Script.Serialization.JavaScriptSerializer` — NT8's standard JSON deserializer. Requires `using System.Web.Script.Serialization;` and the System.Web.Extensions assembly reference.

  **WHY Each Reference Matters**:
  - GEXCommand.cs lines 137-188 contain the EXACT JSON loading pattern used across all DEEP6 GEX indicators. Copying this ensures consistency and thread safety.
  - DEEP6DepthRadarV2 shows the timer callback pattern with error isolation — prevents one bad read from killing the timer.
  - JavaScriptSerializer requires exact property name → JSON key matching (lowercase `asof` not `Asof`)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Models + JSON loader compile with stubs
    Tool: Bash (PowerShell)
    Preconditions: T1 stubs exist, Models.cs has been fully updated with DTOs + JSON loader
    Steps:
      1. Deploy via `nt8-deploy.ps1 -Target Indicators`
      2. Compile via `nt8-compile.ps1`
      3. Assert `[COMPILE-RESULT] SUCCESS`
    Expected Result: All enums, DTO classes, and JSON loader methods compile without errors
    Failure Indicators: CS0246 (missing type), CS0234 (missing namespace for JavaScriptSerializer)
    Evidence: .sisyphus/evidence/task-3-models-compile.txt

  Scenario: DTO fields match JSON schema exactly
    Tool: Bash (grep/comparison)
    Preconditions: Models.cs and gex_snapshot_example.json both exist
    Steps:
      1. Read Models.cs, extract all DTO property names
      2. Read gex_snapshot_example.json, extract all JSON keys
      3. Assert 1:1 mapping: asof, underlying, spot, weekly, daily, strikes, k, gex, call_wall, zero_gamma, put_wall, net_gex
    Expected Result: Every JSON key has a matching DTO property
    Failure Indicators: Mismatched names (e.g., "callWall" vs "call_wall"), missing properties
    Evidence: .sisyphus/evidence/task-3-dto-schema-match.txt

  Scenario: JSON loader methods exist and are callable
    Tool: Bash (grep)
    Preconditions: Models.cs updated
    Steps:
      1. Grep Models.cs for "StartJsonPolling", "StopJsonPolling", "ReadSnapshot", "ReadSnapshotSafe", "GetGexState"
      2. Assert all 5 methods are present
      3. Grep for "private readonly object _gexLock" — assert lock field exists
      4. Grep for "JavaScriptSerializer" — assert serializer is used
      5. Grep for "FileShare.ReadWrite" — assert concurrent access is handled
    Expected Result: All JSON loader infrastructure present in Models.cs
    Failure Indicators: Missing methods, missing lock, wrong serializer
    Evidence: .sisyphus/evidence/task-3-json-loader-audit.txt
  ```

  **Evidence to Capture:**
  - [ ] task-3-models-compile.txt — compile output
  - [ ] task-3-dto-schema-match.txt — property-to-JSON comparison
  - [ ] task-3-json-loader-audit.txt — JSON loader method audit

  **Commit**: NO (groups with Wave 3 commit)

- [x] 4. Implement Main Indicator Lifecycle (DEEP6EquiGEX.cs)

  **What to do**:
  - In `DEEP6EquiGEX.cs`, implement the full indicator lifecycle:
  - **State.SetDefaults**:
    ```csharp
    Name = "DEEP6 EquiGEX";
    Description = "Institutional equilibrium model with GEX-derived Synthetic Fair Value";
    Calculate = Calculate.OnBarClose;  // NOT OnEachTick — AVWAP performance
    IsOverlay = true;
    DisplayInDataBox = false;
    IsAutoScale = false;
    BarsRequiredToPlot = 20;
    IsSuspendedWhileInactive = false;
    ```
  - **All NinjaScriptProperty parameters with [Display] attributes**:
    ```csharp
    [NinjaScriptProperty][Display(Name="Weight: Weekly ZeroGamma", Order=1, GroupName="SFV Weights")]
    public double WeightWeekly { get; set; } = 0.50;
    
    [NinjaScriptProperty][Display(Name="Weight: Daily ZeroGamma", Order=2, GroupName="SFV Weights")]
    public double WeightDaily { get; set; } = 0.30;
    
    [NinjaScriptProperty][Display(Name="Weight: AVWAP", Order=3, GroupName="SFV Weights")]
    public double WeightAVWAP { get; set; } = 0.20;
    
    [NinjaScriptProperty][Display(Name="Volatility Multiplier", Order=1, GroupName="Bands")]
    public double VolMultiplier { get; set; } = 2.0;
    
    [NinjaScriptProperty][Display(Name="GEX JSON Path", Order=1, GroupName="Data")]
    public string GexJsonPath { get; set; } = "";
    // Default path resolved at runtime: %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json
    
    [NinjaScriptProperty][Display(Name="Show Dashboard", Order=1, GroupName="Display")]
    public bool ShowDashboard { get; set; } = true;
    
    [NinjaScriptProperty][Display(Name="Show Debug Values", Order=2, GroupName="Display")]
    public bool ShowDebugValues { get; set; } = false;
    
    // EnableSoundAlerts REMOVED from Phase 1 — no alert conditions exist yet.
    // Will be added in Phase 2 when zone-transition alerts are implemented.
    ```
  - **State.Configure**: NO AddDataSeries needed. All GEX data comes from JSON. AVWAP uses primary series timestamps. ATR uses primary series. Daily/weekly chart bars are NOT consumed by any calculation engine. This avoids the documented NT8 gotcha where AddDataSeries can push an overlay indicator into a sub-panel.
  - **State.DataLoaded**: Initialize internal ATR indicator via `ATR(14)`, resolve default GEX JSON path if empty, log startup info via `Print()`
  - **State.Realtime**: Start JSON polling timer (delegate to `StartJsonPolling()` method in Engines.cs)
  - **State.Terminated**: Stop timer via `StopJsonPolling()`, dispose SharpDX resources via `DisposeDx()`
  - **OnBarUpdate**: Single-series only (no BarsInProgress dispatch needed). Call engine update methods in order: `UpdateAVWAP()` → `UpdateSFVAndZones()` → `UpdateTrend()` → `UpdateBiasChip()`
  - **Expose public read-only properties**: `CurrentZone`, `CurrentSFV`, `CurrentPremiumBand`, `CurrentDiscountBand`, `CurrentBias`
  - **Implement `NormalizeRoot(string instrumentName)`**: Maps MNQ→NQ, MES→ES for JSON asset matching
  - **Weight normalization**: If WeightWeekly + WeightDaily + WeightAVWAP ≠ 1.0, normalize internally
  - **Unsupported instrument detection**: In State.DataLoaded, check `NormalizeRoot()` result. If instrument is not ES or NQ (after normalization), set a flag `_unsupportedInstrument = true` and log a warning. In OnBarUpdate, skip all engine calls if unsupported. In OnRender, show a warning badge: "Unsupported instrument — use ES or NQ".

  **Must NOT do**:
  - Do NOT implement calculation logic (that's Engines.cs)
  - Do NOT implement rendering (that's Render.cs)
  - Do NOT add Phase 2 features (no alerts panel, no histograms)
  - Do NOT use Calculate.OnEachTick — use OnBarClose for performance
  - Do NOT use AddDataSeries — all data comes from JSON or primary series. AddDataSeries risks sub-panel creation which breaks the overlay rendering.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Complex lifecycle management with multi-timeframe setup, parameter validation, and state machine transitions
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Critical for OnStateChange lifecycle, AddDataSeries patterns, property attributes, NT8-specific gotchas
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed — lifecycle only, no rendering

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 5, 6)
  - **Blocks**: Task 7
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `Indicators/DEEP6.cs:129-174` — Full State machine with all 5 states (SetDefaults, Configure, DataLoaded, Realtime, Terminated). Shows property defaults, timer start in Realtime, cleanup in Terminated. **Note**: DEEP6.cs uses AddDataSeries — do NOT copy that part. EquiGEX is single-series only.
  - `ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs` — NinjaScriptProperty pattern with [Display] attributes, GroupName organization, default path resolution, timer start/stop in lifecycle
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs:60-120` — Property organization pattern with GroupName categories. **Do NOT copy the AddDataSeries pattern** — EquiGEX doesn't need secondary series.

  **API/Type References**:
  - `DEEP6EquiGEX.Models.cs` (from T3) — Enums and DTOs this file references
  - `DEEP6EquiGEX.Engines.cs` (from T5/T6) — Engine methods this file will call from OnBarUpdate

  **WHY Each Reference Matters**:
  - MADConfluenceAI.cs is the EXACT multi-timeframe partial class pattern — same BarsInProgress dispatch, same safety checks
  - DEEP6.cs shows how to organize the full lifecycle with timer management and resource cleanup
  - GEXCommand.cs shows the property/Display attribute convention used across all DEEP6 GEX indicators

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Lifecycle compiles with engine stubs
    Tool: Bash (PowerShell)
    Preconditions: T1 stubs exist (including empty engine method stubs from Engines.cs), T3 models exist
    Steps:
      1. Deploy via `nt8-deploy.ps1 -Target Indicators`
      2. Compile via `nt8-compile.ps1`
      3. Assert `[COMPILE-RESULT] SUCCESS`
    Expected Result: Main lifecycle + empty engine stubs (from T1) compile together. Engine methods like UpdateAVWAP(), UpdateTrend() are callable because T1 created empty stubs.
    Failure Indicators: CS0103 (method not found) — means T1's Engines.cs stubs are missing method signatures
    Evidence: .sisyphus/evidence/task-4-lifecycle-compile.txt

  Scenario: All properties appear in NinjaTrader indicator settings
    Tool: Bash (grep)
    Preconditions: Code compiles
    Steps:
      1. Grep DEEP6EquiGEX.cs for `[NinjaScriptProperty]`
      2. Assert count ≥ 7 properties (WeightWeekly, WeightDaily, WeightAVWAP, VolMultiplier, GexJsonPath, ShowDashboard, ShowDebugValues)
      3. Assert each has [Display] with GroupName
    Expected Result: 8+ configurable properties with organized groups
    Failure Indicators: Missing properties, missing GroupName, wrong defaults
    Evidence: .sisyphus/evidence/task-4-properties-audit.txt
  ```

  **Evidence to Capture:**
  - [ ] task-4-lifecycle-compile.txt — compile output
  - [ ] task-4-properties-audit.txt — property grep results

  **Commit**: NO (groups with Wave 3 commit)

---

- [x] 5. Implement AVWAP Engine (Engines.cs) — ⚠️ HIGHEST RISK

  **What to do**:
  - In `DEEP6EquiGEX.Engines.cs`, implement the **Anchored VWAP engine** from scratch:
  - **Weekly anchor detection**:
    - Detect Sunday 6 PM ET (Eastern Time) as the start of each trading week
    - Use `TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time")` — this handles DST correctly (EST/EDT)
    - On each bar, check if the bar's time crosses the Sunday 6 PM ET boundary → reset AVWAP accumulators
    - Edge case: if chart data doesn't extend to Sunday 6 PM, use the first available bar after that time
    - Edge case: holiday weeks — if no Sunday session, scan forward to find the first bar of the week
  - **Cumulative AVWAP calculation**:
    ```
    TypicalPrice = (High + Low + Close) / 3.0
    AccumPV += TypicalPrice * Volume
    AccumVol += Volume
    AVWAP = AccumVol > 0 ? AccumPV / AccumVol : TypicalPrice
    ```
  - **State variables** (private fields in partial class):
    - `double _avwapAccumPV` — cumulative TP × Volume
    - `double _avwapAccumVol` — cumulative Volume
    - `double _currentAVWAP` — latest AVWAP value
    - `DateTime _avwapAnchorTime` — current week's anchor timestamp
    - `bool _avwapValid` — false until first bar after anchor
  - **Method signature**: `private void UpdateAVWAP()` — called from OnBarUpdate on primary series only
  - **Reset logic**: When new weekly boundary detected, zero out accumulators and set new anchor time
  - **Zero-volume handling**: Skip bars with Volume == 0 (don't let them dilute the AVWAP)
  - **Performance**: Only recalculate on bar close (Calculate.OnBarClose ensures this)
  - **Debug output** (when `ShowDebugValues` is true): `Print("[EquiGEX] AVWAP=" + _currentAVWAP.ToString("F2") + " Anchor=" + _avwapAnchorTime.ToString("yyyy-MM-dd HH:mm") + " AccumVol=" + _avwapAccumVol.ToString("F0"));`
    - On weekly reset: `Print("[EquiGEX] Weekly AVWAP reset at " + Time[0].ToString("yyyy-MM-dd HH:mm"));`

  **Must NOT do**:
  - Do NOT make the anchor point user-configurable — always Sunday 6 PM ET
  - Do NOT use the existing DEEP6AnchoredVWAP.cs drawing tool — it requires manual anchor placement
  - Do NOT recalculate from scratch on every bar — maintain running accumulators
  - Do NOT use LINQ for any accumulation

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Highest-risk new code. No existing implementation to copy. Requires careful session boundary handling, DST awareness, and edge case management. Needs deep thinking.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Required for understanding NT8 time handling, session boundaries, and bar time conventions
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed — engine logic only
    - `trading-knowledge`: AVWAP math is well-defined in the spec

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4, 6)
  - **Blocks**: Task 7
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `ninjatrader/indicators/DEEP6AnchoredVWAP.cs` — VWAP math is reusable: `VWAP = Σ(TP×Vol)/Σ(Vol)`, `TP = (H+L+C)/3`. The accumulation pattern and zero-volume skip logic can be adapted. **Do NOT reuse the anchor detection** — it's manual click-based.
  - `AddOns/DEEP6.Core.cs` — Session context detection pattern. Shows how DEEP6 determines session boundaries and handles time-based state resets.

  **External References**:
  - Microsoft docs: `TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time")` — handles EST/EDT automatically on Windows
  - NinjaTrader docs: `Bars.GetTime(index)` — returns the DateTime for a specific bar, in the chart's configured timezone

  **WHY Each Reference Matters**:
  - DEEP6AnchoredVWAP has the EXACT accumulation formula — copy the math, not the anchor logic
  - DEEP6.Core session context shows how existing DEEP6 code handles time-based boundaries in NT8

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: AVWAP calculates non-zero value on chart with data
    Tool: HERMES (nt8-expert skill)
    Preconditions: Indicator compiled, JSON loaded, chart has ≥20 bars of 4H data
    Steps:
      1. Deploy + compile via nt8-deploy.ps1 and nt8-compile.ps1
      2. Use HERMES to add "DEEP6 EquiGEX" to a 4H NQ chart with ShowDebugValues=true
      3. Use HERMES to read NT8 Output window (nt8-status.ps1 or direct Output window capture)
      4. Grep output for exact pattern: `[EquiGEX] AVWAP=` — this is the defined debug format
      5. Assert the numeric value after `AVWAP=` is > 0 and within reasonable range of current NQ price (±500 points)
    Expected Result: AVWAP calculates a value near current price level
    Failure Indicators: AVWAP = 0, AVWAP = NaN, AVWAP wildly divergent from price
    Evidence: .sisyphus/evidence/task-5-avwap-value.txt

  Scenario: AVWAP resets on weekly boundary
    Tool: HERMES (nt8-expert skill)
    Preconditions: Chart has data spanning multiple weeks, ShowDebugValues=true
    Steps:
      1. Use HERMES to scroll chart to view multiple weeks of data
      2. Read NT8 Output window for AVWAP anchor reset messages
      3. Assert output contains exact pattern: `[EquiGEX] Weekly AVWAP reset at`
      4. Assert resets occur approximately once per week (5-7 day intervals)
    Expected Result: Weekly reset detected in debug output
    Failure Indicators: No resets, multiple resets per day, reset at wrong time
    Evidence: .sisyphus/evidence/task-5-avwap-weekly-reset.txt
  ```

  **Evidence to Capture:**
  - [ ] task-5-avwap-value.txt — debug output showing AVWAP value
  - [ ] task-5-avwap-weekly-reset.txt — debug output showing anchor resets

  **Commit**: NO (groups with Wave 3 commit)

---

- [x] 6. Implement HH/HL Trend Detection Engine (Engines.cs)

  **What to do**:
  - In `DEEP6EquiGEX.Engines.cs`, implement the **Higher Highs / Higher Lows trend engine**:
  - **Swing point detection** using N-bar pivots on the primary 4H series:
    - Swing High: `High[n]` is the highest of `High[n-L]` through `High[n+R]` where L=5 (left bars) and R=2 (right bars)
    - Swing Low: `Low[n]` is the lowest of `Low[n-L]` through `Low[n+R]` where L=5 and R=2
    - On 4H chart: 5 left bars = 20 hours ≈ 1 trading day lookback for confirmation
    - R=2 means swing is confirmed 2 bars (8 hours) after the pivot
  - **Trend classification** from the last 2 confirmed swing highs and last 2 confirmed swing lows:
    ```
    if (lastSwingHigh > prevSwingHigh AND lastSwingLow > prevSwingLow):
        TrendDirection = Bullish  (+1 for bias chip)
    elif (lastSwingHigh < prevSwingHigh AND lastSwingLow < prevSwingLow):
        TrendDirection = Bearish  (-1 for bias chip)
    else:
        TrendDirection = Neutral  (0 for bias chip — sideways/no clear structure)
    ```
  - **State variables**:
    - `List<(int barIndex, double price)> _swingHighs` — last N swing highs (keep max 5)
    - `List<(int barIndex, double price)> _swingLows` — last N swing lows (keep max 5)
    - `TrendDirection _currentTrend` — latest classification
  - **Method signature**: `private void UpdateTrend()` — called from OnBarUpdate on primary series
  - **Edge case**: First bars (< L+R bars available) → TrendDirection.Neutral
  - **Edge case**: Only 1 swing detected → TrendDirection.Neutral (need ≥2 of each for comparison)
  - **Debug output** (when `ShowDebugValues` is true): `Print("[EquiGEX] Trend=" + _currentTrend + " SwingHi=" + _swingHighs.Count + " SwingLo=" + _swingLows.Count);`

  **Must NOT do**:
  - Do NOT use EMA crossover — spec requires HH/HL structure
  - Do NOT use ZigZag indicator — implement pivot detection directly (simpler, no dependency)
  - Do NOT add configurable lookback — fixed at L=5, R=2 for Phase 1
  - Do NOT store unlimited swing history — cap at 5 recent swings of each type

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Market structure detection requires careful logic for pivot identification and edge cases
  - **Skills**: [`nt8-expert`, `trading-knowledge`]
    - `nt8-expert`: NT8 bar indexing, High[n]/Low[n] access patterns
    - `trading-knowledge`: HH/HL market structure definition, swing point conventions
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed — engine logic only

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4, 5)
  - **Blocks**: Task 8
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:170-189` — `AbsorptionSignal` with `Direction` field (+1/-1). Follow this pattern for trend direction output.
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Signals.cs` — Signal detector pattern with state variables and update methods. Follow this method signature pattern.

  **External References**:
  - NinjaTrader docs: `High[barsAgo]`, `Low[barsAgo]` — bar data access syntax
  - Swing detection math: For bar index `n`, check `High[n] >= High[n-1] AND High[n] >= High[n-2] ... AND High[n] >= High[n+1] AND High[n] >= High[n+2]`

  **WHY Each Reference Matters**:
  - DEEP6Footprint's AbsorptionSignal shows the +1/-1 direction convention used across all DEEP6 signals
  - MADConfluenceAI.Signals shows how to structure an independent detector method with its own state

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Trend engine compiles and initializes
    Tool: HERMES (nt8-expert skill)
    Preconditions: T1 stubs + T3 models exist, Engines.cs has trend code
    Steps:
      1. Deploy via nt8-deploy.ps1, compile via nt8-compile.ps1
      2. Assert `[COMPILE-RESULT] SUCCESS`
      3. Use HERMES to add indicator to 4H NQ chart with ShowDebugValues=true
      4. Read NT8 Output window for trend detection messages
      5. Assert output contains exact pattern: `[EquiGEX] Trend=` followed by `Bullish`, `Bearish`, or `Neutral`
    Expected Result: TrendDirection prints as Bullish, Bearish, or Neutral
    Failure Indicators: Compile error, no trend output, crash
    Evidence: .sisyphus/evidence/task-6-trend-compile.txt

  Scenario: Trend detection handles insufficient data gracefully
    Tool: HERMES (nt8-expert skill)
    Preconditions: Chart with limited historical data
    Steps:
      1. Use HERMES to load indicator on a chart with minimal bars available
      2. Read NT8 Output window — assert no exceptions logged
      3. Verify debug output shows TrendDirection = Neutral (insufficient data for swing detection)
    Expected Result: Graceful degradation — Neutral trend when insufficient data
    Failure Indicators: IndexOutOfRangeException, crash, incorrect direction
    Evidence: .sisyphus/evidence/task-6-trend-insufficient-data.txt
  ```

  **Evidence to Capture:**
  - [ ] task-6-trend-compile.txt — compile output + debug values
  - [ ] task-6-trend-insufficient-data.txt — edge case verification

  **Commit**: NO (groups with Wave 3 commit)

---

- [x] 7. Implement SFV + Bands + Zone Classifier (Engines.cs)

  **What to do**:
  - In `DEEP6EquiGEX.Engines.cs`, implement **Engine A (SFV), Engine B (Bands), and Engine C (Zone Classifier)**:
  - **Engine A — Synthetic Fair Value**:
    ```
    // Normalize weights if they don't sum to 1.0
    totalWeight = WeightWeekly + WeightDaily + WeightAVWAP
    wW = WeightWeekly / totalWeight
    wD = WeightDaily / totalWeight
    wA = WeightAVWAP / totalWeight
    
    SFV = (weeklyZeroGamma * wW) + (dailyZeroGamma * wD) + (avwap * wA)
    ```
  - **Fallback behavior when GEX data is missing**:
    - If JSON is stale/missing AND weeklyZeroGamma = 0: exclude from blend, re-weight remaining components
    - If BOTH zero gamma values are 0: SFV = AVWAP only (weight 1.0)
    - If AVWAP is also invalid (no volume): SFV = Close[0] (last resort — no zone classification possible)
  - **Engine B — Premium/Discount Bands**:
    ```
    atr = ATR(14)[0]  // ATR on primary 4H series
    sigma = atr * VolMultiplier  // default VolMultiplier = 2.0
    premiumBand = SFV + sigma
    discountBand = SFV - sigma
    ```
  - **Edge case**: ATR = 0 (insufficient bars) → bands collapse to SFV (no zones rendered)
  - **Engine C — Zone Classifier**:
    ```
    if (Close[0] > premiumBand): zone = ZoneType.Premium
    elif (Close[0] < discountBand): zone = ZoneType.Discount
    else: zone = ZoneType.Equilibrium
    ```
  - **Engine D — GEX Regime** (simple, include here):
    ```
    combinedNetGex = weeklyNetGex + dailyNetGex
    regime = combinedNetGex > 0 ? GammaRegime.Positive : GammaRegime.Negative
    ```
  - **Method signature**: `private void UpdateSFVAndZones()` — called from OnBarUpdate after AVWAP + JSON are ready
  - **Expose state**: Set `CurrentSFV`, `CurrentPremiumBand`, `CurrentDiscountBand`, `CurrentZone` public properties
  - **Store historical SFV/band values** for rendering: `Dictionary<int, (double sfv, double premium, double discount)>` keyed by bar index
  - **Debug output** (when `ShowDebugValues` is true): `Print("[EquiGEX] SFV=" + CurrentSFV.ToString("F2") + " Premium=" + CurrentPremiumBand.ToString("F2") + " Discount=" + CurrentDiscountBand.ToString("F2") + " Zone=" + CurrentZone + " ATR=" + atr.ToString("F2"));`

  **Must NOT do**:
  - Do NOT compute GEX values — read from JSON only
  - Do NOT use LINQ for any calculations
  - Do NOT add additional band types (Bollinger, Keltner, etc.)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core mathematical engine with fallback logic, multi-source data fusion, and edge case handling
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: ATR indicator access, bar indexing, property exposure patterns
  - **Skills Evaluated but Omitted**:
    - `trading-knowledge`: Math is fully specified, no market knowledge needed

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential with T8)
  - **Blocks**: Tasks 8, 9
  - **Blocked By**: Tasks 3, 4, 5

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:64-131` — `FootprintBar` with computed properties and `SortedDictionary` for bar-indexed data storage. Follow this pattern for historical SFV storage.
  - `AddOns/DEEP6.E6.cs` — E6 VP+CTX engine shows DEEP6's convention for multi-input signal computation with fallback logic
  - `ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs` — How existing GEX code reads `net_gex` and `zero_gamma` from parsed JSON state

  **API/Type References**:
  - `DEEP6EquiGEX.Models.cs:GexState` (from T3) — Thread-safe state holder with `Snapshot.weekly.zero_gamma` and `Snapshot.daily.zero_gamma`
  - NinjaTrader API: `ATR(14)[0]` — built-in ATR indicator, index 0 = current bar

  **WHY Each Reference Matters**:
  - DEEP6Footprint's bar-indexed storage pattern is exactly what we need for rendering historical SFV lines
  - DEEP6.E6 shows how to fuse multiple data sources with fallback logic when some are unavailable
  - GEXCommand shows the exact JSON field access pattern for zero_gamma values

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: SFV calculates correctly with valid JSON
    Tool: HERMES (nt8-expert skill)
    Preconditions: gex_snapshot_example.json copied to `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json`
    Steps:
      1. Use HERMES to copy gex_snapshot_example.json to the GEX directory path
      2. Deploy + compile indicator
      3. Use HERMES to add indicator to 4H ES chart with ShowDebugValues=true
      4. Read NT8 Output window for exact pattern: `[EquiGEX] SFV=`
      5. Parse the SFV value after `SFV=`. Assert SFV is between 5200 and 5350 (weighted blend of 5240 × 0.50 + 5302 × 0.30 + AVWAP × 0.20)
    Expected Result: SFV value is a reasonable weighted blend
    Failure Indicators: SFV = 0, SFV = NaN, SFV outside reasonable range
    Evidence: .sisyphus/evidence/task-7-sfv-calculation.txt

  Scenario: SFV fallback when JSON is missing
    Tool: HERMES (nt8-expert skill)
    Preconditions: No JSON file exists at configured path
    Steps:
      1. Use HERMES to ensure no gex_snapshot.json at the GEX directory
      2. Add indicator to chart with ShowDebugValues=true
      3. Read NT8 Output window for SFV fallback messages
      4. Assert SFV falls back to AVWAP-only (or Close if AVWAP invalid)
      5. Capture screenshot — assert zones still render (based on AVWAP-only SFV)
    Expected Result: SFV = AVWAP value, no crash, zones still render
    Failure Indicators: Crash, SFV = 0, no zone classification
    Evidence: .sisyphus/evidence/task-7-sfv-fallback.txt
  ```

  **Evidence to Capture:**
  - [ ] task-7-sfv-calculation.txt — SFV debug output with valid JSON
  - [ ] task-7-sfv-fallback.txt — SFV fallback behavior without JSON

  **Commit**: YES
  - Message: `feat(equigex): implement core engines (SFV, AVWAP, bands, trend, GEX regime)`
  - Files: `DEEP6EquiGEX.cs`, `DEEP6EquiGEX.Models.cs`, `DEEP6EquiGEX.Engines.cs`
  - Pre-commit: `nt8-compile.ps1` SUCCESS

---

- [x] 8. Implement Bias Chip Scoring (Engines.cs)

  **What to do**:
  - In `DEEP6EquiGEX.Engines.cs`, implement **Engine E — Composite Bias Chip**:
  - **4-factor scoring**:
    ```
    int score = 0;
    
    // Factor 1: Trend (from HH/HL engine)
    if (_currentTrend == TrendDirection.Bullish)  score += 1;
    if (_currentTrend == TrendDirection.Bearish)  score -= 1;
    // Neutral = 0 (no contribution)
    
    // Factor 2: Zone position
    if (CurrentZone == ZoneType.Discount)  score += 1;
    if (CurrentZone == ZoneType.Premium)   score -= 1;
    // Equilibrium = 0
    
    // Factor 3: Gamma regime
    if (_gammaRegime == GammaRegime.Positive)  score += 1;
    if (_gammaRegime == GammaRegime.Negative)  score -= 1;
    
    // Factor 4: Price vs Daily Zero Gamma
    if (Close[0] > dailyZeroGamma)  score += 1;
    if (Close[0] < dailyZeroGamma)  score -= 1;
    
    // Composite bias
    if (score >= 2)  CurrentBias = BiasDirection.Bullish;
    elif (score <= -2)  CurrentBias = BiasDirection.Bearish;
    else  CurrentBias = BiasDirection.Neutral;
    ```
  - **Method signature**: `private void UpdateBiasChip()` — called from OnBarUpdate after zones + trend are updated
  - **Edge case**: If dailyZeroGamma = 0 (no JSON data) → Factor 4 score = 0 (neutral)
  - **Store current score** for potential debug display: `private int _biasScore`
  - **Set public property**: `CurrentBias`
  - **Debug output** (when `ShowDebugValues` is true): `Print("[EquiGEX] Bias=" + CurrentBias + " Score=" + _biasScore + " [T:" + trendScore + " Z:" + zoneScore + " G:" + gammaScore + " D:" + dzgScore + "]");`

  **Must NOT do**:
  - Do NOT add a 5th bias factor
  - Do NOT make score thresholds configurable (fixed at ±2)
  - Do NOT add weighted scoring — each factor is equal (+1/-1)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple scoring logic with no complex dependencies. Formula is fully specified.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Property access patterns
  - **Skills Evaluated but Omitted**:
    - `trading-knowledge`: Scoring formula is fully defined — no market knowledge needed

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (after T7)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 6, 7

  **References**:

  **Pattern References**:
  - `AddOns/DEEP6.Scorer.cs` — DEEP6's scoring convention. Shows how to combine multiple signal inputs into a composite score with thresholds.
  - `AddOns/DEEP6.E5.cs` — E5 Micro engine with Bayesian probability. Shows the pattern for combining independent factors into a directional probability.

  **WHY Each Reference Matters**:
  - DEEP6.Scorer.cs shows the EXACT scoring pattern — input signals → weighted combination → threshold classification
  - E5 shows how to handle the edge case where some inputs are unavailable (graceful degradation)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Bias chip outputs valid direction
    Tool: HERMES (nt8-expert skill)
    Preconditions: Indicator running with valid JSON on 4H chart, ShowDebugValues=true
    Steps:
      1. Deploy + compile, add indicator to 4H NQ chart
      2. Read NT8 Output window for exact pattern: `[EquiGEX] Bias=`
      3. Parse the Score value after `Score=`. Assert score is between -4 and +4
      4. Assert the value after `Bias=` is one of: `Bullish`, `Bearish`, `Neutral`
    Expected Result: Valid bias score and direction classification
    Failure Indicators: Score outside range, direction not set, crash
    Evidence: .sisyphus/evidence/task-8-bias-scoring.txt

  Scenario: Bias chip handles missing GEX gracefully
    Tool: HERMES (nt8-expert skill)
    Preconditions: No JSON file at configured path, indicator on chart with ShowDebugValues=true
    Steps:
      1. Ensure no gex_snapshot.json exists
      2. Add indicator to chart
      3. Read NT8 Output window for exact pattern: `[EquiGEX] Bias=`
      4. Parse factor breakdown `[T:X Z:X G:X D:X]` — assert `G:0` and `D:0` (no GEX data)
      5. Assert bias is driven only by Factors 1 (trend) and 2 (zone)
    Expected Result: Graceful degradation — 2 of 4 factors active
    Failure Indicators: Crash, incorrect score, Factor 3/4 producing non-zero with no data
    Evidence: .sisyphus/evidence/task-8-bias-no-gex.txt
  ```

  **Evidence to Capture:**
  - [ ] task-8-bias-scoring.txt — bias debug output
  - [ ] task-8-bias-no-gex.txt — bias with missing JSON

  **Commit**: NO (groups with T7 commit)

---

- [x] 9. Implement Full SharpDX Rendering (Render.cs)

  **What to do**:
  - In `DEEP6EquiGEX.Render.cs`, implement the **complete institutional SharpDX rendering**:
  
  - **OnRenderTargetChanged**: Initialize ALL brushes and text formats:
    ```csharp
    // Brush palette (pre-allocate everything)
    _dxSFVLine      = B(1.0f, 0.84f, 0f, 1f);        // Bold yellow — SFV line
    _dxPremiumFill   = B(0.95f, 0.25f, 0.25f, 0.15f); // Transparent red — premium zone
    _dxDiscountFill  = B(0.2f, 0.85f, 0.3f, 0.15f);   // Transparent green — discount zone
    _dxEquilFill     = B(0.3f, 0.3f, 0.3f, 0.08f);    // Subtle dark gray — equilibrium zone
    _dxPremiumLine   = B(0.95f, 0.25f, 0.25f, 0.6f);  // Red — premium band border
    _dxDiscountLine  = B(0.2f, 0.85f, 0.3f, 0.6f);    // Green — discount band border
    _dxBullish       = B(0.2f, 0.85f, 0.3f, 0.85f);   // Green — bullish bias chip
    _dxBearish       = B(0.95f, 0.25f, 0.25f, 0.85f);  // Red — bearish bias chip
    _dxNeutral       = B(1.0f, 0.65f, 0.0f, 0.85f);   // Gold — neutral bias chip
    _dxPanel         = B(0.04f, 0.05f, 0.07f, 0.92f);  // Dark institutional background
    _dxBorder        = B(0.16f, 0.19f, 0.24f, 1f);     // Subtle border
    _dxText          = B(0.96f, 0.97f, 0.98f, 1f);     // Near-white text
    _dxMuted         = B(0.5f, 0.5f, 0.55f, 0.7f);     // Muted text
    _dxStale         = B(0.95f, 0.15f, 0.15f, 0.9f);   // Bright red — stale badge
    
    // Text formats
    _fontHero   = new TextFormat(Core.Globals.DirectWriteFactory, "Segoe UI", FontWeight.Bold, FontStyle.Normal, 22f);
    _fontValue  = new TextFormat(Core.Globals.DirectWriteFactory, "Consolas", FontWeight.Bold, FontStyle.Normal, 16f);
    _fontLabel  = new TextFormat(Core.Globals.DirectWriteFactory, "Segoe UI", FontWeight.SemiBold, FontStyle.Normal, 11f);
    _fontSmall  = new TextFormat(Core.Globals.DirectWriteFactory, "Consolas", FontWeight.Normal, FontStyle.Normal, 9f);
    _fontBias   = new TextFormat(Core.Globals.DirectWriteFactory, "Segoe UI", FontWeight.Bold, FontStyle.Normal, 14f);
    ```
  
  - **DisposeDx**: Dispose ALL brushes and text formats using the generic disposer pattern:
    ```csharp
    void D<T>(ref T x) where T : class, IDisposable
    { if (x != null) { try { x.Dispose(); } catch {} x = null; } }
    ```
  
  - **OnRender — 6 rendering layers** (in this order):
    1. **Zone fills**: Premium (red), Discount (green), Equilibrium (gray) — `FillRectangle` spanning chart width, between band Y-coordinates and chart edges
    2. **Band boundary lines**: Premium band (red dashed), Discount band (green dashed) — `DrawLine` with `StrokeStyle` for dashes
    3. **SFV line**: Bold yellow 2px line connecting SFV values across all visible bars — `DrawLine` with `Vector2` coordinates
    4. **Zone labels**: "PREMIUM ZONE" / "EQUILIBRIUM ZONE" / "DISCOUNT ZONE" text inside their respective zones — semi-transparent background pill + white text
    5. **Header bar**: Top of chart panel — dark panel background, "EQUILIBRIUM MODEL" title, Symbol, Timeframe, Date, PRICE value, BIAS badge
    6. **Bias chip**: Top-right pill — colored background (green/red/gold) + white text (BULLISH/BEARISH/NEUTRAL)
    7. **Stale badge**: If JSON is stale → render red "STALE FEED" badge over the header area
  
  - **Coordinate conversion**: Use `chartScale.GetYByValue(price)` to convert price → pixel Y, `chartControl.GetXByBarIndex(chartBars, barIndex)` for bar → pixel X
  - **Visible range optimization**: Only render bars within `ChartBars.FromIndex` to `ChartBars.ToIndex` — skip bars outside visible range
  - **Anti-aliasing**: Enable `PerPrimitive` for the SFV line and band borders only, reset to `Aliased` after
  - **Performance**: Zero allocations in OnRender. All strings pre-formatted before render loop. No LINQ.

  **Must NOT do**:
  - Do NOT render GEX histograms (Phase 2)
  - Do NOT render key levels table (Phase 2)
  - Do NOT render alerts panel (Phase 2)
  - Do NOT render GEX curve (Phase 2)
  - Do NOT allocate brushes or TextFormat in OnRender — all from OnRenderTargetChanged
  - Do NOT use LINQ in any render method
  - Do NOT use childish gradients or retail-looking visuals — institutional aesthetic only

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Complex SharpDX rendering with institutional aesthetic requirements. Requires pixel-perfect coordinate math, performance optimization, and visual design sense.
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]
    - `nt8-expert`: NT8 chart coordinate system, ChartScale/ChartControl APIs, bar indexing
    - `nt8-visual-design`: SharpDX rendering patterns, F1 Pitwall color palette, typography hierarchy, institutional aesthetic guidelines
  - **Skills Evaluated but Omitted**:
    - `trading-knowledge`: Not needed — pure rendering task

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (solo)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 7, 8

  **References**:

  **Pattern References**:
  - `AddOns/DEEP6.Render.cs:41-140` — Gold standard SharpDX rendering. Copy the `InitDX()`/`DisposeDX()`/`OnRender()` skeleton exactly. Shows inline brush factory, palette pre-allocation, and the `_dxOk` flag pattern.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2.cs:666-676` — HUD panel rendering with dark background, borders, and text. Copy the panel background + border rendering pattern.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs` — F1 Pitwall Aerospace color scheme. Use as the color palette reference for the institutional aesthetic.
  - `ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs` — Stale badge rendering pattern (red overlay when data is stale)

  **API/Type References**:
  - NinjaTrader API: `ChartScale.GetYByValue(double price)` — convert price to Y pixel
  - NinjaTrader API: `ChartControl.GetXByBarIndex(ChartBars, int barIndex)` — convert bar index to X pixel
  - NinjaTrader API: `ChartBars.FromIndex`, `ChartBars.ToIndex` — visible bar range
  - NinjaTrader API: `ChartPanel.X`, `ChartPanel.Y`, `ChartPanel.W`, `ChartPanel.H` — panel bounds

  **WHY Each Reference Matters**:
  - DEEP6.Render.cs is THE reference for SharpDX lifecycle in the DEEP6 ecosystem — copy its skeleton
  - DEEP6DepthRadarV2 HUD shows exactly how to render an institutional dark panel with borders and text
  - GEXCommand stale badge shows the exact visual treatment for stale data — red overlay with dimmed background

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full visual rendering on 4H chart
    Tool: HERMES (nt8-ui.ps1 screenshot)
    Preconditions: All engines compiled, valid JSON in GEX directory
    Steps:
      1. Deploy all files via nt8-deploy.ps1
      2. Compile via nt8-compile.ps1 → assert SUCCESS
      3. Add DEEP6 EquiGEX to a 4H NQ chart
      4. Capture screenshot via nt8-ui.ps1
      5. Inspect screenshot for:
         a. Yellow SFV line visible and tracking price area
         b. Red transparent zone above SFV (premium)
         c. Green transparent zone below SFV (discount)
         d. Dark gray between bands (equilibrium)
         e. Bias chip pill visible in top-right area
         f. Header bar with "EQUILIBRIUM MODEL" text
      6. Assert NO rendering artifacts, NO overlapping text, NO invisible elements
    Expected Result: Clean institutional rendering matching Bloomberg aesthetic
    Failure Indicators: Missing elements, wrong colors, artifacts, text overlap, blank chart
    Evidence: .sisyphus/evidence/task-9-full-render.png

  Scenario: Stale badge renders when JSON is removed
    Tool: HERMES
    Preconditions: Indicator running with valid JSON
    Steps:
      1. Rename gex_snapshot.json to gex_snapshot.json.bak
      2. Wait 35 seconds (polling interval + processing)
      3. Capture screenshot
      4. Assert red "STALE FEED" badge is visible
      5. Restore JSON file (rename back)
      6. Wait 35 seconds
      7. Capture screenshot
      8. Assert stale badge is GONE, normal rendering restored
    Expected Result: Stale badge appears/disappears correctly
    Failure Indicators: No stale badge, badge doesn't clear, crash on missing JSON
    Evidence: .sisyphus/evidence/task-9-stale-badge.png

  Scenario: Rendering performs smoothly (no freeze)
    Tool: HERMES
    Preconditions: Indicator on live/replay chart
    Steps:
      1. Add indicator to chart
      2. Scroll chart left/right rapidly for 10 seconds
      3. Assert NT8 remains responsive (no freeze, no lag)
      4. Check NT8 Output window for any error messages
    Expected Result: Smooth rendering, no UI freeze, no exceptions
    Failure Indicators: NT8 freezes, rendering lag, exceptions in Output window
    Evidence: .sisyphus/evidence/task-9-performance.txt
  ```

  **Evidence to Capture:**
  - [ ] task-9-full-render.png — full chart screenshot with all visual elements
  - [ ] task-9-stale-badge.png — stale badge appearance/disappearance
  - [ ] task-9-performance.txt — performance observation notes

  **Commit**: YES
  - Message: `feat(equigex): implement SharpDX institutional rendering`
  - Files: `DEEP6EquiGEX.Render.cs`
  - Pre-commit: `nt8-compile.ps1` SUCCESS

---

- [x] 10. Deploy + Compile + Full Visual Verification

  **What to do**:
  - Full integration deployment and verification:
  - Deploy ALL files via `nt8-deploy.ps1 -Target Indicators`
  - Compile via `nt8-compile.ps1` — assert SUCCESS
  - Add indicator to a 4H NQ chart (or ES if NQ unavailable)
  - Configure settings: set GexJsonPath to the example JSON location
  - Capture full-resolution screenshot of the indicator rendering
  - Verify ALL Phase 1 deliverables are present and functioning:
    1. SFV yellow line — visible, correctly positioned relative to price
    2. Premium zone — red transparent fill above SFV
    3. Discount zone — green transparent fill below SFV
    4. Equilibrium zone — dark gray between bands
    5. Band boundary lines — visible at premium/discount edges
    6. Bias chip — displays BULLISH/BEARISH/NEUTRAL with correct color
    7. Header bar — shows "EQUILIBRIUM MODEL", price, symbol info
    8. Zone labels — "PREMIUM ZONE", "EQUILIBRIUM ZONE", or "DISCOUNT ZONE" visible
  - Test with MNQ chart to verify NormalizeRoot() auto-detection
  - Verify no errors in NinjaTrader Output window

  **Must NOT do**:
  - Do NOT modify any source code — this is verification only
  - Do NOT add new features

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Comprehensive integration testing requiring NT8 UI interaction, screenshot analysis, and multi-scenario verification
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Deployment, compilation, UI interaction, chart management
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not modifying visuals — only verifying them

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (sequential)
  - **Blocks**: Task 11
  - **Blocked By**: Task 9

  **References**:

  **Deployment References**:
  - `ninjatrader/scripts/nt8-deploy.ps1` — `.\nt8-deploy.ps1 -Target Indicators`
  - `ninjatrader/scripts/nt8-compile.ps1` — Expected: `[COMPILE-RESULT] SUCCESS`
  - `.claude/skills/nt8-expert/knowledge.md` — UI interaction patterns, indicator addition workflow

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full end-to-end deployment and rendering
    Tool: HERMES (nt8-expert skill)
    Preconditions: All source files exist in repo
    Steps:
      1. Run `.\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators`
      2. Verify 4 .cs files copied to NT8 Custom directory
      3. Run `.\ninjatrader\scripts\nt8-compile.ps1`
      4. Assert `[COMPILE-RESULT] SUCCESS`
      5. Add "DEEP6 EquiGEX" to 4H NQ chart
      6. Configure GexJsonPath to example JSON location
      7. Wait 5 seconds for indicator to load
      8. Capture full screenshot
      9. Inspect: SFV line, zones, bands, bias chip, header all present
    Expected Result: Indicator renders correctly on live chart
    Failure Indicators: Compile failure, indicator not visible, missing elements
    Evidence: .sisyphus/evidence/task-10-integration.png

  Scenario: Instrument auto-detection works on MNQ
    Tool: HERMES
    Preconditions: Indicator compiles
    Steps:
      1. Add indicator to MNQ chart
      2. Assert indicator loads without error
      3. Assert JSON asset matching works (MNQ → NQ normalization)
    Expected Result: Indicator works on both NQ and MNQ
    Failure Indicators: "No matching asset" error, crash
    Evidence: .sisyphus/evidence/task-10-mnq-detection.txt
  ```

  **Evidence to Capture:**
  - [ ] task-10-integration.png — full integration screenshot
  - [ ] task-10-mnq-detection.txt — MNQ auto-detection verification

  **Commit**: NO (evidence-only — no code changes)

---

- [x] 11. Edge Case QA Testing

  **What to do**:
  - Systematically test ALL identified edge cases:
  - **EC1: No JSON file on disk** → Remove JSON → indicator shows "NO DATA" badge → no crash → SFV falls back to AVWAP-only
  - **EC2: JSON with zero gamma values** → Modify JSON to set `weekly.zero_gamma: 0` and `daily.zero_gamma: 0` → SFV = AVWAP only → zones still render
  - **EC3: Corrupt/partial JSON** → Truncate JSON file mid-write → indicator holds last valid state → stale badge appears
  - **EC4: Chart with <14 bars** → Load indicator on sparse chart → ATR handles gracefully → bands may not render but no crash
  - **EC5: Wrong instrument** → Add to AAPL or CL chart → indicator detects non-ES/NQ → shows error badge or disables gracefully
  - **EC6: JSON stale (>10 minutes old)** → Set `asof` to 20 minutes ago → stale badge appears → GEX panels dimmed
  - **EC7: Symbol switch** → Switch chart from NQ to ES → indicator reinitializes → AVWAP accumulators reset
  - Document results with evidence for each edge case

  **Must NOT do**:
  - Do NOT modify source code — only test and document
  - Do NOT add new edge case handling — only verify existing behavior

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic QA requiring multiple test scenarios with careful observation
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 UI interaction, Output window monitoring, chart management
  - **Skills Evaluated but Omitted**:
    - `nt8-visual-design`: Not needed — QA only

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (after T10)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 10

  **References**:

  **Test Data References**:
  - `gex_snapshot_example.json` (from T1) — Base test data to modify for each scenario
  - JSON path: `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No JSON file — graceful degradation
    Tool: HERMES
    Preconditions: Indicator compiled and deployed
    Steps:
      1. Ensure no gex_snapshot.json exists at the configured path
      2. Add indicator to 4H NQ chart
      3. Assert indicator loads without crash
      4. Assert "NO DATA" or stale badge visible
      5. Assert SFV still renders (AVWAP-only fallback)
    Expected Result: Graceful degradation, no crash, AVWAP-only SFV
    Failure Indicators: Crash, NullReferenceException, blank chart
    Evidence: .sisyphus/evidence/task-11-ec1-no-json.png

  Scenario: Zero gamma values — fallback weighting
    Tool: HERMES
    Preconditions: JSON exists with zero_gamma = 0 for both weekly and daily
    Steps:
      1. Modify JSON: set weekly.zero_gamma = 0, daily.zero_gamma = 0
      2. Wait for polling cycle (35 seconds)
      3. Assert SFV = AVWAP (no gamma contribution)
      4. Assert zones still render correctly
    Expected Result: SFV = AVWAP, zones functional
    Failure Indicators: SFV = 0, bands collapsed, crash
    Evidence: .sisyphus/evidence/task-11-ec2-zero-gamma.txt

  Scenario: Stale JSON (>10 minutes old)
    Tool: HERMES
    Preconditions: JSON with asof timestamp > 10 minutes ago
    Steps:
      1. Modify JSON: set asof to 20 minutes in the past
      2. Wait for polling cycle
      3. Assert stale badge appears (red "STALE FEED")
      4. Assert indicator holds last valid GEX data (no zeroing out)
    Expected Result: Stale badge visible, data preserved from last valid read
    Failure Indicators: No stale badge, data reset to zero, crash
    Evidence: .sisyphus/evidence/task-11-ec6-stale-json.png

  Scenario: Wrong instrument (non-ES/NQ)
    Tool: HERMES
    Preconditions: Indicator compiled
    Steps:
      1. Add indicator to AAPL or CL chart
      2. Assert no crash
      3. Assert indicator shows warning or disables GEX features
    Expected Result: Graceful handling — warning badge, no crash
    Failure Indicators: Crash, incorrect data, no warning
    Evidence: .sisyphus/evidence/task-11-ec5-wrong-instrument.txt
  ```

  **Evidence to Capture:**
  - [ ] task-11-ec1-no-json.png — no JSON scenario
  - [ ] task-11-ec2-zero-gamma.txt — zero gamma fallback
  - [ ] task-11-ec6-stale-json.png — stale badge
  - [ ] task-11-ec5-wrong-instrument.txt — wrong instrument handling

  **Commit**: YES
  - Message: `test(equigex): verify Phase 1 compile, deploy, and visual QA`
  - Files: `.sisyphus/evidence/task-*.{txt,png}` (evidence files only)

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle` (REJECT on InitDx-from-OnRender — overruled: matches DEEP6.Render.cs:44 canonical pattern)
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, check code). For each "Must NOT Have": search codebase for forbidden patterns (Phase 2 scaffolding, Newtonsoft, LINQ in OnRender, alert conditions) — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high` (APPROVE — 21/21 SharpDX disposed, no LINQ in OnRender, minor hygiene items noted)
  Review all 4 .cs files for: `as any`-equivalent casts, empty catch blocks, leftover `Print()` debug statements in production paths, unused `using` declarations, SharpDX resources not disposed in `DisposeDx()`, LINQ in `OnRender()`, allocations in `OnRender()`. Check naming consistency with DEEP6 conventions (namespace, property naming, GroupName patterns). Verify all `lock()` usage is correct.
  Output: `Files [N clean/N issues] | SharpDX Lifecycle [PASS/FAIL] | Threading [PASS/FAIL] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (APPROVE — compile SUCCESS, deploy SUCCESS, 0 LSP errors)
  Start from clean state. Deploy all files via `nt8-deploy.ps1`. Compile via `nt8-compile.ps1`. Add indicator to 4H NQ chart. Execute EVERY QA scenario from EVERY task — follow exact steps, capture screenshots. Test cross-task integration: SFV line + bands + bias chip all rendering together. Test stale feed flow end-to-end. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep` (APPROVE — 8/8 guardrails, CLEAN scope, 4 bias factors, fixed AVWAP anchor)
  For each task: read "What to do", read actual code. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no Phase 2 creep). Check "Must NOT do" compliance. Specifically hunt for: GEX histogram code, alerts code, 5th bias factor, dynamic AVWAP anchor, Newtonsoft references. Flag any unaccounted code.
  Output: `Tasks [N/N compliant] | Scope Creep [CLEAN/N issues] | Guardrails [N/N respected] | VERDICT`

---

## Commit Strategy

- **After Wave 1**: `feat(equigex): scaffold Phase 1 skeleton with stubs and example JSON` — all stub files + JSON + README
- **After Wave 3**: `feat(equigex): implement core engines (SFV, AVWAP, bands, bias chip)` — Models.cs, Engines.cs, DEEP6EquiGEX.cs
- **After Wave 4**: `feat(equigex): implement SharpDX institutional rendering` — Render.cs
- **After Wave 5**: `test(equigex): verify Phase 1 compile, deploy, and visual QA` — evidence files only
- **Pre-commit**: `nt8-compile.ps1` must return SUCCESS before each commit

---

## Success Criteria

### Verification Commands
```powershell
# Compile
& "C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-compile.ps1"
# Expected: [COMPILE-RESULT] SUCCESS

# Deploy
& "C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-deploy.ps1" -Target Indicators
# Expected: Files copied to NT8 Custom directory

# File count in deploy target
Get-ChildItem "C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\EquiGEX" -Filter *.cs
# Expected: 4 files (DEEP6EquiGEX.cs, DEEP6EquiGEX.Models.cs, DEEP6EquiGEX.Engines.cs, DEEP6EquiGEX.Render.cs)
```

### Final Checklist
- [ ] All 4 partial class files compile together in NT8
- [ ] SFV line renders as bold yellow 2px on 4H chart
- [ ] Premium zone renders as transparent red above SFV
- [ ] Discount zone renders as transparent green below SFV
- [ ] Equilibrium zone renders as dark gray between bands
- [ ] Bias chip displays correct color (green/red/gold) and text (BULLISH/BEARISH/NEUTRAL)
- [ ] JSON loads from `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json`
- [ ] Stale badge (red "STALE FEED") appears when JSON is >10 minutes old or missing
- [ ] Indicator does NOT crash on missing JSON
- [ ] Indicator does NOT freeze NinjaTrader UI
- [ ] No Phase 2 features present (no histograms, no alerts, no key levels table)
- [ ] All "Must NOT Have" guardrails respected
