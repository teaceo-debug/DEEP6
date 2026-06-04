# MAD Confluence AI — UX Overhaul + Signal Fix + Footprint Cells

## TL;DR

> **Quick Summary**: Fix three critical failures: (1) zero signals firing due to absurd thresholds, (2) no footprint visibility inside candles, (3) unreadable HUD. Redesign the entire visual system around real bid×ask footprint cells, a right-side decision rail, and a 5-state signal machine.
>
> **Deliverables**:
> - Signal pipeline producing real signals on live NQ (relaxed thresholds, 10-bar warm-up)
> - Per-price-level footprint cells with bid×ask text, imbalance coloring, POC/VA
> - Right-side decision rail replacing the floating dashboard (action/score/entry/stop/target)
> - 5-state visual system: Idle → Watch → Armed → Triggered → Expired
> - Signal persistence (markers stay 3-5 bars, not 1 frame)
> - Level clutter reduction (nearest 4 levels, not 50)
>
> **Estimated Effort**: Large (15 tasks across 4 waves)
> **Parallel Execution**: YES — 4 waves, up to 5 concurrent

---

## Context

### The Three Failures (From Live Trading Session)

**Failure 1 — Zero Signals in 1.5 Hours**:
- `WarmupBars = 50` blocks ALL signals for first 50 minutes
- ABS-01 requires bar range < 0.5 points; NQ 1-min bars are 1-3 points (almost never fires)
- ABS-02 requires 3-bar range < 0.75 points (too strict)
- IMB-01 requires 3:1 ratio; real NQ imbalances are 1.5-2:1
- DELT-01/02 require 10-11 bars history ON TOP of warm-up
- Even when signals fire, markers render ONLY on latest bar then vanish next bar

**Failure 2 — No Footprint Cells**:
- MADConfluenceAI has ZERO per-price-level bid×ask text rendering
- Only has translucent heatmap blocks and level bands — metadata, not evidence
- DEEP6Footprint has 1,100+ lines of working cell rendering with imbalance coloring
- The entire thesis (absorption/exhaustion) is invisible without footprint cells

**Failure 3 — Unreadable HUD**:
- Score number is biggest element (wrong — action should be biggest)
- 7 abbreviated category bars require decoding (ABS/EXH/DLT/IMB/ICE/LIQ/TRP)
- 220×260 floating card competes with price labels and chart content
- Up to 50 level zones clutter entire chart
- No visual difference between "nothing happening" and "Elite setup firing"
- Font sizes too small: action at 14pt, labels at 9pt

### Research Findings
- **DEEP6Footprint.cs** rendering pattern: per-level cells with "{BidVol,4} x {AskVol,-4}", 9pt Consolas monospace, tiered imbalance coloring (amber 3x / cyan 5x / extreme 8x with corner brackets), POC purple line, VAH/VAL olive lines
- **Professional platforms** (ATAS/Bookmap/Sierra Chart): dark backgrounds (#1A1A1A), high-contrast text (14:1 ratio), monospace fonts, traffic-light color system, 1-second-glance hierarchy
- **Oracle UX audit**: replace floating dashboard with reserved right-side rail, add signal persistence buffer, implement 5-state visual machine, limit levels to nearest 2-4

---

## Work Objectives

### Core Objective
Transform MADConfluenceAI from a metadata overlay into a real footprint chart with institutional execution intelligence — where traders can SEE absorption/exhaustion happening inside candles, get unmissable signal alerts, and make split-second decisions from a clean visual hierarchy.

### Concrete Deliverables
- Signal thresholds recalibrated for real NQ microstructure
- Per-price-level footprint cell rendering (bid×ask text, imbalance coloring)
- Right-side decision rail (240px reserved panel)
- 5-state signal visual system with persistence
- Level clutter reduction (4 nearest levels, not 50)
- Performance-safe rendering (zoom-aware degradation)

### Must Have
- Footprint cells showing bid×ask at each price level for recent bars
- Imbalance coloring (3-tier: 150%/300%/500%)
- POC line per bar + session VAH/VAL
- Signal markers that persist for 3-5 bars on originating bar (not current bar)
- Right-side decision rail: Action (32pt), Score/Tier, Entry/Stop/Target, Why Now
- 5-state visual system: Idle (gray/calm) → Watch (amber) → Armed (colored) → Triggered (pulsing) → Expired (fade)
- Signals actually fire on normal NQ price action (relaxed thresholds)
- Warm-up reduced to 10-15 bars

### Must NOT Have
- Floating 220×260 top-right dashboard (replaced by rail)
- 50 concurrent level zones (max 4 nearest)
- 7-bar category taxonomy permanently visible
- Signals that vanish after 1 bar
- Hard-coded thresholds that never fire on NQ
- Full-width SL/TP zones that obscure the chart

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Automated tests**: YES (update existing + new tests for relaxed thresholds)
- **Framework**: NUnit 3.14.0 (existing)
- **NT8 Compile**: `nt8-deploy.ps1` + `nt8-compile.ps1` → SUCCESS

### QA Policy
- Unit tests for recalibrated thresholds (signals MUST fire on known NQ patterns)
- NT8 compile verification after each wave
- Screenshot evidence of visual changes

### Verification Toolchain Reference
| Tool | Command | Purpose |
|------|---------|---------|
| Test suite | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q` | Run all tests |
| Test filter | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~MADConfluenceAI" --nologo -v q` | Run MAD-specific tests |
| Deploy | `ninjatrader/scripts/nt8-deploy.ps1` | Sync .cs files to NT8 Custom folder |
| Compile | `ninjatrader/scripts/nt8-compile.ps1 -Quiet` | Trigger NT8 recompile → `[COMPILE-RESULT] SUCCESS/FAILED` |
| Errors | `ninjatrader/scripts/nt8-errors.ps1 -Format Json` | Read compile errors from NT8 Output Window |
| Screenshot | `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` | Capture NT8 chart to `captures/` |
| Screenshot inspect | `Look_at` tool with `file_path` = screenshot path, `goal` = specific visual check | Agent-executed visual verification (multimodal image analysis) |
| Status | `ninjatrader/scripts/nt8-status.ps1 -ShowErrors` | NT8 health check + deployed file inventory |
| Dev API | `ninjatrader/scripts/nt8-dev-api.ps1 -Action errors -Format Json` | In-process error read (preferred over nt8-errors.ps1) |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Signal Fix — 5 tasks, MAX PARALLEL):
├── T1:  Reduce WarmupBars from 50 to 10 [quick]
├── T2:  Relax ABS-01/ABS-02 thresholds (bar range 0.5→2.0, 3-bar range 0.75→3.0) [quick]
├── T3:  Relax IMB-01 ratio (3.0→1.5), reduce DELT history requirement (10→5 bars) [quick]
├── T4:  Add signal persistence buffer — signals remember originating bar, persist 5 bars [unspecified-high]
├── T5:  Update tests for new thresholds + verify signals fire on NQ fixture data [unspecified-high]

Wave 2 (Footprint Cells — 4 tasks, after Wave 1):
├── T6:  Add CellColumnWidth + CellFontSize parameters, create cell font in OnRenderTargetChanged [quick]
├── T7:  Implement RenderFootprintCells() — per-price bid×ask text with cell rectangles [deep]
├── T8:  Implement imbalance coloring (3-tier: 150%/300%/500%) with diagonal comparison [deep]
├── T9:  Add per-bar POC line + session VAH/VAL thin lines in footprint area [unspecified-high]

Wave 3 (Visual Redesign — 4 tasks, after Wave 2):
├── T10: Replace floating dashboard with right-side decision rail (240px reserved panel) [visual-engineering]
├── T11: Implement 5-state signal visual system (Idle/Watch/Armed/Triggered/Expired) [visual-engineering]
├── T12: Reduce level zones to nearest 4 levels around current price [quick]
├── T13: Move signal markers to originating bar (not latest bar) + size by confidence [visual-engineering]

Wave 4 (Polish + Deploy — 2 tasks, after Wave 3):
├── T14: Performance profiling + zoom-aware degradation (compress cells when zoomed out) [unspecified-high]
├── T15: Deploy + compile + verification screenshot + test suite pass [quick]
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T5 | 1 |
| T2 | — | T5 | 1 |
| T3 | — | T5 | 1 |
| T4 | — | T13 | 1 |
| T5 | T1, T2, T3 | T6 | 1 |
| T6 | T5 | T7 | 2 |
| T7 | T6 | T8, T9 | 2 |
| T8 | T7 | T10 | 2 |
| T9 | T7 | T10 | 2 |
| T10 | T8, T9 | T14 | 3 |
| T11 | T4 | T14 | 3 |
| T12 | — | T14 | 3 |
| T13 | T4 | T14 | 3 |
| T14 | T10-T13 | T15 | 4 |
| T15 | T14 | — | 4 |

---

## TODOs

- [x] 1. Reduce WarmupBars from 50 to 10

  **What to do**:
  - In `MADConfluenceAI.cs`, change default `WarmupBars` property from 50 to 10
  - In `MADConfig`, update `Defaults` to use `WarmupBars = 10`
  - In `MADConfluenceAI.cs` OnBarUpdate, verify the warm-up guard uses `<=` not `<`

  **Must NOT do**: Remove the warm-up entirely (ATR needs some bars to stabilize)

  **Recommended Agent Profile**: `quick` with `nt8-expert`
  **Blocked By**: None
  **Blocks**: T5

  **Acceptance Criteria**:
  - [ ] WarmupBars default = 10 in both property and MADConfig.Defaults
  - [ ] Signals can fire on bar 11 (not bar 51)

  **QA Scenario**:
  1. `grep "WarmupBars" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → verify default = 10
  2. `grep "WarmupBars" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → verify MADConfig.Defaults sets WarmupBars = 10
  3. `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~ConfigTests" --nologo -v q` → ALL PASS
  4. Expected: No test regressions; WarmupBars = 10 in both property default and config defaults

  **Commit**: YES (groups with Wave 1)

- [x] 2. Relax Absorption Thresholds

  **What to do**:
  - In `MADConfluenceAI.Signals.cs` DetectAbs01: change `bar.BarRange > 0.5` to `bar.BarRange > 2.0` (8 ticks instead of 2)
  - In DetectAbs02: change `priceRange > 0.75` to `priceRange > 3.0` (12 ticks over 3 bars)
  - These new values allow normal NQ 1-minute price action to qualify

  **Must NOT do**: Remove range checks entirely (they still filter noise)

  **Recommended Agent Profile**: `quick` with `trading-knowledge`
  **Blocked By**: None
  **Blocks**: T5

  **Acceptance Criteria**:
  - [ ] ABS-01 fires on bars with range up to 2.0 points
  - [ ] ABS-02 fires on 3-bar sequences with range up to 3.0 points

  **QA Scenario**:
  1. `grep "BarRange" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Signals.cs` → verify threshold = 2.0 in DetectAbs01
  2. `grep "priceRange" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Signals.cs` → verify threshold = 3.0 in DetectAbs02
  3. `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~OrderFlowDetector" --nologo -v q` → ALL PASS
  4. Expected: Thresholds relaxed in code; existing absorption tests still pass or are updated in T5

  **Commit**: YES (groups with Wave 1)

- [x] 3. Relax Imbalance + Delta Thresholds

  **What to do**:
  - In `MADConfluenceAI.cs`, change `ImbalanceRatio` default from 3.0 to 1.5
  - In `MADConfluenceAI.Signals.cs` DetectDelt01: change history requirement from `< 10` to `< 5`
  - In DetectDelt02: change from `< 11` to `< 6`
  - In DetectExh01: consider reducing DeltaQualityScalar gate from 0.5 to 0.3

  **Recommended Agent Profile**: `quick` with `trading-knowledge`
  **Blocked By**: None
  **Blocks**: T5

  **Acceptance Criteria**:
  - [ ] IMB-01 fires at 1.5:1 imbalance ratio
  - [ ] DELT-01 fires after 5 bars of history
  - [ ] EXH-01 fires with delta quality > 0.3

  **QA Scenario**:
  1. `grep "ImbalanceRatio" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → verify default = 1.5
  2. `grep "DetectDelt01\|DetectDelt02" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Signals.cs` → verify history thresholds = 5 and 6
  3. `grep "DeltaQualityScalar" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Signals.cs` → verify gate = 0.3
  4. `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~LiquidityDetector" --nologo -v q` → ALL PASS
  5. Expected: All three threshold classes relaxed; no test regressions

  **Commit**: YES (groups with Wave 1)

- [x] 4. Add Signal Persistence Buffer

  **What to do**:
  - In `MADConfluenceAI.cs`, add `private List<(int barIndex, List<MADSignalResult> signals, MADDecision decision)> _signalHistory`
  - After MakeDecision, store `(CurrentBar, signals, decision)` in history buffer
  - Cap buffer at 100 entries, remove entries older than 20 bars
  - This feeds into T13 (markers on originating bar) and T11 (visual states)

  **Recommended Agent Profile**: `unspecified-high` with `nt8-expert`
  **Blocked By**: None
  **Blocks**: T11, T13

  **Acceptance Criteria**:
  - [ ] Signal history stores last 20 bars of signals
  - [ ] Each entry has barIndex, signals list, and decision
  - [ ] Buffer auto-prunes entries > 20 bars old

  **QA Scenario**:
  1. `grep "_signalHistory" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → verify field exists and is initialized
  2. `grep "_signalHistory" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → verify pruning logic (entries > 20 bars removed)
  3. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  4. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  5. Expected: Buffer field declared, populated after MakeDecision, auto-pruned; compiles clean

  **Commit**: YES (groups with Wave 1)

- [x] 5. Update Tests for Relaxed Thresholds

  **What to do**:
  - Update `OrderFlowDetectorTests.cs`: adjust ABS-01/ABS-02 fixture data for new thresholds
  - Update `LiquidityDetectorTests.cs`: adjust IMB-01 fixtures for 1.5 ratio
  - Add NEW test: "ABS-01 fires on 1.5-point range bar" (was impossible before)
  - Add NEW test: "IMB-01 fires at 1.8:1 ratio" (was impossible before)
  - Run full suite: `dotnet test --filter "MADConfluenceAI"` → ALL PASS

  **Recommended Agent Profile**: `unspecified-high`
  **Blocked By**: T1, T2, T3
  **Blocks**: T6

  **Acceptance Criteria**:
  - [ ] All existing tests updated or still pass
  - [ ] New tests prove signals fire on relaxed thresholds
  - [ ] `dotnet test --filter "MADConfluenceAI"` → ALL PASS

  **QA Scenario**:
  1. `grep "1.5-point\|1.5 point\|1.8:1\|1.8 ratio" ninjatrader/tests/MADConfluenceAI/OrderFlowDetectorTests.cs` → verify new test methods exist
  2. `grep "1.5\|1.8" ninjatrader/tests/MADConfluenceAI/LiquidityDetectorTests.cs` → verify updated fixture data
  3. `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~MADConfluenceAI" --nologo -v normal` → ALL PASS (use `-v normal` to see test names)
  4. Count new test methods: at least 2 new tests added
  5. Expected: ≥2 new tests; full MADConfluenceAI suite passes; no regressions in other test namespaces

  **Commit**: YES (Wave 1 commit: `fix(mad): recalibrate signal thresholds for live NQ microstructure`)

- [x] 6. Add Footprint Cell Parameters + Font Setup

  **What to do**:
  - Add 3 new NinjaScript parameters (replacing 3 less-useful ones to stay at 30):
    - `CellColumnWidth` (int, default 80, range 40-200)
    - `CellFontSize` (int, default 9, range 7-14)
    - `ShowFootprintCells` (bool, default true)
  - Remove: `ShowAbsorptionZones`, `ShowSweepMarkers`, `ShowImbalanceHighlights` (these get merged into footprint cell rendering)
  - In OnRenderTargetChanged: create `_cellFont` TextFormat (Consolas, CellFontSize pt)
  - In DisposeDx: dispose `_cellFont`

  **Recommended Agent Profile**: `quick` with `nt8-expert`
  **Blocked By**: T5
  **Blocks**: T7

  **Acceptance Criteria**:
  - [ ] Still exactly 30 NinjaScriptProperty attributes
  - [ ] _cellFont created/disposed correctly
  - [ ] NT8 compile succeeds

  **QA Scenario**:
  1. `grep -c "NinjaScriptProperty" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → count = 30
  2. `grep "ShowAbsorptionZones\|ShowSweepMarkers\|ShowImbalanceHighlights" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → 0 matches (removed)
  3. `grep "CellColumnWidth\|CellFontSize\|ShowFootprintCells" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → 3 matches (added)
  4. `grep "_cellFont" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify creation in OnRenderTargetChanged + disposal in DisposeDx
  5. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  6. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  7. Expected: Exactly 30 properties; 3 old removed, 3 new added; font lifecycle correct; compiles clean

  **Commit**: YES (groups with Wave 2)

- [x] 7. Implement RenderFootprintCells() — Core Cell Rendering

  **What to do**:
  - In `MADConfluenceAI.Rendering.cs`, implement `RenderFootprintCells()`:
  - For each visible bar (last 20-30 bars), for each price level in that bar's footprint:
    - Calculate cell rectangle: x = barCenterX - CellColumnWidth/2, y = chartScale.GetYByValue(price), height = pixels per tick
    - Draw text: `string.Format("{0,4} x {1,-4}", cell.BidVol, cell.AskVol)` in Consolas monospace
    - Text color: primary white (#F2F4F8) for normal, bright for extreme
  - Reference: `DEEP6Footprint.cs` lines 1529-1576 for the exact pattern
  - Gate: only render if `ShowFootprintCells == true`
  - Performance: skip bars outside visible range, limit to 30 bars max

  **Recommended Agent Profile**: `deep` with `nt8-expert`, `ninjatrader-builder-doctor`
  **Blocked By**: T6
  **Blocks**: T8, T9

  **Acceptance Criteria**:
  - [ ] Bid×ask text visible at each price level inside recent bars
  - [ ] Monospace font alignment (numbers line up vertically)
  - [ ] Cell width matches CellColumnWidth parameter
  - [ ] NT8 compile succeeds + no SharpDX exceptions

  **QA Scenario**:
  1. `grep "RenderFootprintCells" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → method exists and is called from OnRender
  2. `grep "ShowFootprintCells" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → gate check present
  3. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  4. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  5. `ninjatrader/scripts/nt8-errors.ps1 -Format Json` → 0 errors (no SharpDX exceptions)
  6. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  7. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Verify bid×ask text (monospace numbers like '  42 x 38  ') is visible at price levels inside recent candle bars. Check for readable white text on dark background."
  8. Expected: Compile SUCCESS; Look_at confirms bid×ask text visible at price levels; no runtime exceptions in NT8 log

  **Commit**: YES (groups with Wave 2)

- [x] 8. Implement Imbalance Coloring (3-Tier)

  **What to do**:
  - In RenderFootprintCells(), add imbalance detection per cell:
    - Compare ask volume at price N with bid volume at price N+1 (diagonal)
    - Tier 1 (≥ 150%): amber fill at 18% alpha
    - Tier 2 (≥ 300%): cyan (buy) or magenta (sell) fill at 28% alpha
    - Tier 3 (≥ 500%): same color + white text + corner bracket markers
  - Corner brackets: L-shaped reticle at 4 corners of extreme cells (from DEEP6Footprint pattern)
  - Stacked imbalances: if 3+ consecutive levels qualify, thicker border

  **Recommended Agent Profile**: `deep` with `trading-knowledge`
  **Blocked By**: T7
  **Blocks**: T10

  **Acceptance Criteria**:
  - [ ] 3-tier coloring visible on bars with imbalances
  - [ ] Corner brackets on extreme cells (≥500%)
  - [ ] Diagonal comparison correct (not straight bid vs ask at same level)

  **QA Scenario**:
  1. `grep "150\|300\|500" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify 3 imbalance tier thresholds present
  2. `grep "N+1\|price.*\+.*1\|diagonal" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify diagonal comparison (ask@N vs bid@N+1)
  3. `grep "corner\|bracket\|reticle" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify corner bracket drawing for extreme cells
  4. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  5. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  6. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  7. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Verify colored cell backgrounds are visible (amber/cyan/magenta tints) at price levels with imbalances. Check for L-shaped corner bracket markers on extreme cells."
  8. Expected: Compile SUCCESS; Look_at confirms colored imbalance cells visible; corner brackets on extreme cells

  **Commit**: YES (groups with Wave 2)

- [x] 9. Add POC Line + VAH/VAL Lines

  **What to do**:
  - In RenderFootprintCells(), after drawing cells for each bar:
    - Draw thin horizontal POC line at bar's PocPrice (yellow #FFD23F, 2px)
    - Draw session VAH/VAL lines (olive #C8D17A, 1px dashed)
  - These are thin precise lines, not the wide zone bands from before

  **Recommended Agent Profile**: `unspecified-high` with `nt8-expert`
  **Blocked By**: T7
  **Blocks**: T10

  **Acceptance Criteria**:
  - [ ] POC line visible at correct price on each bar
  - [ ] VAH/VAL as thin dashed lines (not wide zones)

  **QA Scenario**:
  1. `grep "PocPrice\|FFD23F" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify POC line drawn with yellow color
  2. `grep "VahPrice\|ValPrice\|C8D17A" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify VAH/VAL lines with olive color
  3. `grep "DashStyle\|dashed\|Dashed" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify dashed line style for VAH/VAL
  4. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  5. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  6. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  7. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Verify thin yellow horizontal POC line visible at each bar's high-volume price. Check for olive-colored dashed VAH/VAL lines. Confirm these are thin lines, NOT wide zone bands."
  8. Expected: Compile SUCCESS; Look_at confirms thin POC (yellow) and VAH/VAL (olive dashed) lines visible

  **Commit**: YES (groups with Wave 2: `feat(mad): add real footprint cells with imbalance coloring and POC/VA`)

- [x] 10. Replace Dashboard with Right-Side Decision Rail

  **What to do**:
  - Remove `RenderConfidenceDashboard()` (the 220×260 floating card)
  - Implement `RenderDecisionRail()`: reserved 240px right-side panel
    - Background: #0E1014 with #262633 border
    - Hero: Action text 32pt Consolas Bold (BUY=#00E676 / SELL=#FF1744 / WAIT=#FFB300 / —=#8A929E)
    - Score: 20pt with tier badge (ELITE/HIGH/MOD/WATCH/DNT)
    - Entry/Stop/Target: 12pt Consolas Bold with prices and tick distances
    - Why Now: max 2 lines showing top 2 contributing signals (e.g., "ABS + SWEEP")
    - Regime/Session: 9pt secondary text at bottom
  - Chart body automatically has 240px less width for footprint cells

  **Recommended Agent Profile**: `visual-engineering` with `nt8-expert`
  **Blocked By**: T8, T9
  **Blocks**: T14

  **Acceptance Criteria**:
  - [ ] Rail renders as fixed 240px right panel
  - [ ] Action is largest text (32pt)
  - [ ] Score/tier visible but smaller
  - [ ] Entry/Stop/Target with prices
  - [ ] Old floating dashboard removed

  **QA Scenario**:
  1. `grep "RenderConfidenceDashboard" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → 0 matches (old dashboard removed)
  2. `grep "RenderDecisionRail" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → method exists and is called from OnRender
  3. `grep "240" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify 240px rail width
  4. `grep "32.*pt\|32.*font\|fontSize.*32" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify 32pt action text
  5. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  6. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  7. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  8. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Verify a dark vertical panel exists on the right edge of the chart (~240px wide). Check that the largest text element says BUY, SELL, or WAIT. Confirm there is NO floating rectangular dashboard card overlapping the chart area."
  9. Expected: Compile SUCCESS; Look_at confirms right-side rail with large action text; no floating dashboard

  **Commit**: YES (groups with Wave 3)

- [x] 11. Implement 5-State Signal Visual System

  **What to do**:
  - Define 5 visual states based on score/decision:
    - **Idle** (score < MinConfidence): Gray rail, no overlays, calm footprint
    - **Watch** (score 60-74): Amber action text, show nearest entry reference
    - **Armed** (score 75-89): Colored action text, entry line on chart, 1-line reason
    - **Triggered** (score ≥ 90): Pulsing arrow on originating bar, solid entry/dashed SL/TP, colored rail
    - **Expired**: Fade to gray after 5 bars, mark "EXPIRED"
  - Use signal persistence buffer from T4 to track state transitions
  - "Nothing happening" should look deliberately calm (gray, sparse)
  - "Act now" should be unmissable (color, large text, origin marker)

  **Recommended Agent Profile**: `visual-engineering` with `trading-knowledge`
  **Blocked By**: T4
  **Blocks**: T14

  **Acceptance Criteria**:
  - [ ] 5 distinct visual states with clear color transitions
  - [ ] Idle state is calm/gray
  - [ ] Triggered state is unmissable (pulsing, colored, large)
  - [ ] Expired state fades gracefully

  **QA Scenario**:
  1. `grep "Idle\|Watch\|Armed\|Triggered\|Expired" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify all 5 states implemented
  2. `grep "_signalHistory" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify it uses persistence buffer from T4
  3. `grep "MinConfidence\|score.*60\|score.*75\|score.*90" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify score thresholds for state transitions
  4. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  5. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  6. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  7. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Verify the right-side rail panel uses a color scheme consistent with one of the 5 signal states (gray=Idle, amber=Watch, green/red=Armed, pulsing/bright=Triggered, faded=Expired). The visual tone should match the current score."
  8. Expected: Compile SUCCESS; Look_at confirms visual state coloring matches current score; code contains all 5 state branches

  **Commit**: YES (groups with Wave 3)

- [x] 12. Reduce Level Zones to Nearest 4

  **What to do**:
  - In RenderLevelZones(), change from rendering ALL levels to only the nearest 4:
    - Get current price (Close[0])
    - Call `_levelEngine.GetNearbyLevels(currentPrice, toleranceTicks: 40)` (10 NQ points)
    - Sort by quality score, take top 4
    - Only render those 4 levels
  - Remove psychological level rendering (too noisy)
  - Keep PDH/PDL, VWAP, POC, VAH/VAL as eligible level types

  **Recommended Agent Profile**: `quick`
  **Blocked By**: None
  **Blocks**: T14

  **Acceptance Criteria**:
  - [ ] Maximum 4 level zones visible at any time
  - [ ] Levels are the nearest/highest-quality
  - [ ] No psychological level clutter

  **QA Scenario**:
  1. `grep "Take\|take\|\.Take(4)\|top 4\|max.*4" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify level count capped at 4
  2. `grep "Psychological\|psychological\|PsychLevel" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify psychological levels removed/skipped
  3. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  4. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  5. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  6. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Count the number of horizontal level/zone bands visible on the chart. There should be at most 4. Verify there are no round-number psychological levels (like 20000, 20100, etc.)."
  7. Expected: Compile SUCCESS; Look_at confirms ≤4 level zones visible; no psychological level clutter

  **Commit**: YES (groups with Wave 3)

- [x] 13. Move Signal Markers to Originating Bar

  **What to do**:
  - In `RenderSignalMarkers()`, use signal persistence buffer (T4) instead of `_lastSignals`:
    - For each entry in `_signalHistory` within the last 5 bars:
      - Draw markers at `entry.barIndex` (the REAL originating bar), not `toIdx`
      - Size proportional to confidence score
      - Fade older signals (alpha decreases with age)
  - Remove the "force to latest bar" logic that made all signals appear on the current candle

  **Recommended Agent Profile**: `visual-engineering` with `nt8-expert`
  **Blocked By**: T4
  **Blocks**: T14

  **Acceptance Criteria**:
  - [ ] Signal markers appear on the bar where they actually fired
  - [ ] Markers persist for 5 bars with fading alpha
  - [ ] Latest signals are brightest/largest

  **QA Scenario**:
  1. `grep "_signalHistory" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify RenderSignalMarkers uses persistence buffer
  2. `grep "_lastSignals\|toIdx" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify old "force to latest bar" logic removed
  3. `grep "entry.barIndex\|barIndex" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify markers drawn at originating bar
  4. `grep "alpha\|Alpha\|opacity" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify fading alpha for older signals
  5. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  6. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  7. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves to `captures/` directory
  8. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Verify signal markers (arrows or triangles) appear on DIFFERENT historical bars, NOT all clustered on the rightmost/current bar. Check that older markers appear more faded/transparent than recent ones."
  9. Expected: Compile SUCCESS; Look_at confirms markers distributed across bars with fading; no markers forced to current bar

  **Commit**: YES (Wave 3 commit: `feat(mad): redesign visual system — decision rail, footprint cells, signal states`)

- [x] 14. Performance Profiling + Zoom-Aware Degradation

  **What to do**:
  - Profile RenderFootprintCells() with Stopwatch
  - If chart is zoomed out (bar width < 20px): switch to simplified rendering (no text, just colored rectangles)
  - If chart is zoomed way out (bar width < 8px): skip cell rendering entirely, show only heatmap
  - Add render time monitoring: if average > 12ms, auto-reduce cell count
  - Run performance tests

  **Recommended Agent Profile**: `unspecified-high`
  **Blocked By**: T10, T11, T12, T13
  **Blocks**: T15

  **Acceptance Criteria**:
  - [ ] Rendering stays under 12ms at normal zoom
  - [ ] Graceful degradation when zoomed out
  - [ ] No SharpDX exceptions during zoom transitions

  **QA Scenario**:
  1. `grep "Stopwatch\|_renderTime\|renderMs" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify Stopwatch profiling added
  2. `grep "barWidth\|bar.*width\|< 20\|< 8" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify zoom-aware degradation thresholds
  3. `grep "12.*ms\|> 12\|auto.*reduce" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs` → verify auto-reduce at >12ms
  4. `ninjatrader/scripts/nt8-deploy.ps1 -Target Indicators` → files synced
  5. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  6. `ninjatrader/scripts/nt8-dev-api.ps1 -Action log -Lines 50` → check for SharpDX exceptions or render warnings
  7. Expected: Compile SUCCESS; no SharpDX exceptions in log; code contains 3-tier zoom degradation (full → simplified → heatmap-only)

  **Commit**: YES (groups with Wave 4)

- [x] 15. Deploy + Compile + Verification

  **What to do**:
  - Run full test suite: `dotnet test --filter "MADConfluenceAI"` → ALL PASS
  - Deploy: `nt8-deploy.ps1` → all files synced
  - Compile: `nt8-compile.ps1` → `[COMPILE-RESULT] SUCCESS`
  - Screenshot evidence of the new visual design on live NQ chart
  - Verify: footprint cells visible, decision rail readable, signals firing

  **Recommended Agent Profile**: `quick` with `nt8-expert`
  **Blocked By**: T14
  **Blocks**: None

  **Acceptance Criteria**:
  - [ ] All tests pass
  - [ ] NT8 compile succeeds
  - [ ] Screenshot shows footprint cells + decision rail + signal markers
  - [ ] No file > 1500 lines

  **QA Scenario**:
  1. `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~MADConfluenceAI" --nologo -v q` → ALL PASS
  2. `ninjatrader/scripts/nt8-deploy.ps1` → all files synced (exit code 0)
  3. `ninjatrader/scripts/nt8-compile.ps1 -Quiet` → `[COMPILE-RESULT] SUCCESS`
  4. `ninjatrader/scripts/nt8-errors.ps1 -Format Json` → empty array (0 errors)
  5. `ninjatrader/scripts/nt8-ui.ps1 -Action screenshot` → saves final evidence to `captures/`
  6. `Look_at` tool: `file_path` = captured screenshot path, `goal` = "Final verification: (1) bid×ask footprint cells visible inside recent candle bars, (2) right-side decision rail panel with large BUY/SELL/WAIT text, (3) signal markers on originating bars (not all on current bar), (4) at most 4 horizontal level zones. Report pass/fail for each."
  7. File line count check: `(Get-ChildItem ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/*.cs | ForEach-Object { "$($_.Name): $((Get-Content $_.FullName).Count) lines" })` → no file > 1500 lines
  8. `grep -c "NinjaScriptProperty" ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.cs` → count = 30
  9. Expected: Full green — tests pass, compile succeeds, 0 errors, Look_at confirms all 4 visual checks pass, all files under 1500 lines, exactly 30 properties

  **Commit**: YES (Wave 4 commit: `feat(mad): performance tuning + deploy verification`)

---

## Color Palette (Standardized)

| Purpose | Color | Hex |
|---------|-------|-----|
| Background (rail) | Deep black | #0E1014 |
| Border/grid | Dark gray | #262633 |
| Primary text | White | #F2F4F8 |
| Secondary text | Light gray | #9BA3AE |
| Inactive | Mid gray | #5A636E |
| Long/Buy | Green | #00E676 |
| Short/Sell | Red | #FF1744 |
| Watch/Caution | Amber | #FFB300 |
| Neutral | Gray | #8A929E |
| Absorption | Cyan | #00E0FF |
| Exhaustion | Magenta | #FF38C8 |
| POC | Yellow | #FFD23F |
| VAH/VAL | Olive | #C8D17A |
| Imbalance fill (buy) | Cyan 28% | #00E0FF @ 0.28 |
| Imbalance fill (sell) | Magenta 28% | #FF38C8 @ 0.28 |
| Moderate imbalance | Amber 18% | #FFB300 @ 0.18 |

## Font Hierarchy

| Element | Size | Font | Weight |
|---------|------|------|--------|
| Action (BUY/SELL/WAIT) | 32pt | Consolas | Bold |
| Score + Price plan | 20-22pt | Consolas | Bold |
| Tier badge | 14-16pt | Segoe UI | Semibold |
| Entry/Stop/Target | 12-13pt | Consolas | Bold |
| Footprint cells | 9-10pt | Consolas | Regular |
| Minor labels | 8-9pt | Segoe UI | Regular |

---

## Success Criteria

### Verification Commands
```powershell
dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~MADConfluenceAI" --nologo -v q    # Expected: ALL PASS
ninjatrader/scripts/nt8-deploy.ps1                                                                                    # Expected: all files synced
ninjatrader/scripts/nt8-compile.ps1 -Quiet                                                                            # Expected: [COMPILE-RESULT] SUCCESS
ninjatrader/scripts/nt8-errors.ps1 -Format Json                                                                       # Expected: [] (empty)
ninjatrader/scripts/nt8-ui.ps1 -Action screenshot                                                                     # Expected: screenshot in captures/
# Then: Look_at tool on screenshot with goal="Final verification: footprint cells, decision rail, signal markers, ≤4 levels"
```

### Final Checklist
- [ ] Signals fire within first 15 bars of session
- [ ] At least 3 signals per hour during active NQ session
- [ ] Footprint cells visible with bid×ask text
- [ ] Imbalance coloring visible on real data
- [ ] Decision rail readable in < 1 second
- [ ] Visual states change noticeably as score changes
- [ ] Maximum 4 level zones visible
- [ ] Signal markers on originating bars (not current bar)
- [ ] All files < 1500 lines
- [ ] 30 NinjaScriptProperty attributes
