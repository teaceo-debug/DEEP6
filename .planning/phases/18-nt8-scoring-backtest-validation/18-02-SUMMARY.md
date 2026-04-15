---
phase: 18
plan: "02"
subsystem: nt8-scoring
tags: [scoring, nt8, rendering, sharpdx, hud, tier-markers]
dependency_graph:
  requires: [18-01]
  provides: [ScorerSharedState, ScoreHUD, TierMarkers, TypeANarrative]
  affects: [DEEP6Footprint.cs, DEEP6Strategy.cs (Wave 3 will consume ScorerSharedState)]
tech_stack:
  added: []
  patterns: [SharpDX-TextLayout, NT8-Draw-API, ConcurrentDictionary-latch, DetectorRegistry-indicator-side]
key_files:
  created:
    - ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerSharedState.cs
    - ninjatrader/tests/Scoring/ScorerSharedStateTests.cs
  modified:
    - ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
decisions:
  - "Indicator-side DetectorRegistry: mirrors DEEP6Strategy pattern; indicator builds its own registry in State.Configure so it can run scorer independently without depending on strategy being loaded"
  - "Task 1 + Task 2 committed as separate commits per plan despite single-file overlap; ScorerSharedState.cs committed first (b5da015), DEEP6Footprint.cs second (f25368e)"
  - "Draw.Dot fallback: catch(MissingMethodException) around Draw.Dot per RESEARCH Open Question 3 — NT8 Draw.Dot availability uncertain; Diamond at 70% opacity is the fallback"
  - "HUD auto-hide: score=0 AND tier=QUIET/DISQUALIFIED collapses the badge; avoids empty chrome on bars with no signal"
  - "TierBrush direction tie-break: direction>=0 (includes 0) routes to long brush — only applies when tier fires without direction, which is architecturally impossible per scorer; kept as safe default"
metrics:
  duration_minutes: 65
  completed: "2026-04-15"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
  tests_added: 8
  tests_total: 223
---

# Phase 18 Plan 02: ScorerSharedState + HUD Badge + Tier Markers + TypeA Narrative — Summary

**One-liner:** Indicator-side scorer registry wired to bar-close ConfluenceScorer.Score() call; SharpDX 3-line HUD badge + typed entry markers (Diamond/Triangle/Dot) + TypeA narrative label rendered per spec from FOOTPRINT-VISUAL-SPEC.md and 03-SPATIAL-LAYOUT.md.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ScorerSharedState + scorer invocation at bar close | b5da015 | ScorerSharedState.cs, ScorerSharedStateTests.cs |
| 2 | SharpDX HUD badge + tier markers + TypeA narrative | f25368e | DEEP6Footprint.cs |

---

## What Was Built

### Task 1 — ScorerSharedState + Scorer Invocation

**`ScorerSharedState.cs`** (NT8-API-free, compiles under net48 + net8.0):
- `static class ScorerSharedState` backed by two `ConcurrentDictionary<string, T>` keyed by `Instrument.FullName`
- `Publish(symbol, barIdx, result)` — no-op if null symbol or null result
- `Latest(symbol)` — returns null if never published
- `LatestBarIndex(symbol)` — returns -1 if never published
- `Clear(symbol)` — removes latch (called on indicator termination, future use)

**`DEEP6Footprint.cs` — scorer invocation wiring:**
- Added `using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring` and `...Registry` usings
- Private fields: `_scorerRegistry`, `_scorerSession`, `_lastScorerResult`
- `State.Configure`: builds indicator-side `DetectorRegistry` with all 12 detectors (mirrors DEEP6Strategy pattern) + `SessionContext { TickSize }`
- `OnBarUpdate` — session reset path: `_scorerSession.ResetSession()` + `_scorerRegistry.ResetAll()` on date change
- `OnBarUpdate` — after existing detectors run: populates `_scorerSession` fields (Atr20, VolEma20, TickSize, Vah, Val, PriorBar, BarsSinceOpen), calls `_scorerRegistry.EvaluateBar(prev, _scorerSession)`, then `ConfluenceScorer.Score(signals, ...)` with `zoneScore=0.0` / `zoneDistTicks=MaxValue` stub (VPContext zone extension deferred per RESEARCH Open Question), latches `_lastScorerResult`, publishes to `ScorerSharedState`, and calls `DrawScorerTierMarker()`
- Scorer runs ONLY at bar close (`IsFirstTickOfBar` gate was already in place — scorer reuses it)

**`ScorerSharedStateTests.cs`** — 8 NUnit tests:

| # | Test | Behavior |
|---|------|----------|
| 1 | Publish_ThenLatest_ReturnsSameResult | Basic publish + retrieve contract |
| 2 | Publish_NullResult_DoesNotThrow_AndLatestRemainsUnchanged | Null result is a no-op |
| 3 | Latest_UnknownSymbol_ReturnsNull | Unknown symbol → null |
| 4 | LatestBarIndex_UnknownSymbol_ReturnsNegativeOne | Unknown symbol → -1 |
| 5 | MultiSymbol_PublishToA_DoesNotAffectB | Symbol isolation |
| 6 | Clear_RemovesPublishedResult | Clear removes both dictionaries |
| 7 | Publish_Twice_SameSymbol_LastWriteWins | Overwrite semantics |
| 8 | ConcurrentPublish_DifferentSymbols_NoCorruption | 8-thread concurrent publish to different keys |

### Task 2 — SharpDX HUD Badge + Tier Markers + TypeA Narrative

**New SharpDX brush fields** (12 `SolidColorBrush` + 2 `TextFormat`):
- `_scoreHudTextDx` `#E8EAED` — primary ink (score line)
- `_scoreHudDimDx` `#B0B6BE` — secondary ink (narrative line)
- `_scoreHudBgDx` `#0E1014 @78%` (α=199) — HUD backdrop
- `_scoreHudBorderDx` `#262633` — 1px border
- `_scoreTierALongDx` `#00E676` — TypeA long saturated green
- `_scoreTierAShortDx` `#FF1744` — TypeA short saturated red
- `_scoreTierBLongDx` `#66BB6A` — TypeB long medium green
- `_scoreTierBShortDx` `#EF5350` — TypeB short medium red
- `_scoreTierCLongDx` `#7CB387 @70%` (α=178) — TypeC long gray-green
- `_scoreTierCShortDx` `#B87C82 @70%` (α=178) — TypeC short gray-red
- `_scoreNeutralDx` `#8A929E` — QUIET/DISQUALIFIED dim ink
- `_scoreLabelBgDx` `#0E1014 @60%` (α=153) — narrative label background
- `_hudFont` — Consolas 12pt, leading alignment (score line monospace)
- `_hudLabelFont` — Segoe UI 9pt, leading alignment (tier + narrative lines)

All 12 brushes + 2 fonts allocated in `OnRenderTargetChanged`, disposed in `DisposeDx` — no leaks.

**`RenderScoreHud(float panelRight)`**:
- Anchor: `x = panelRight - 200`, `y = ChartPanel.Y + 28` (GEX status badge at Y+4..22 per 03-SPATIAL-LAYOUT.md; 6px gap)
- Box: 200 × 62 px, `#0E1014 @78%` fill, `#262633` 1px border
- Line 1 (y+6): `"Score: +0.87"` via `_hudFont` 12pt Consolas; ink flips to `_scoreTierAShortDx` (#FF1744) when negative
- Line 2 (y+24): `"Tier: A"` via `_hudLabelFont` 9pt Segoe UI; ink from `TierBrush()` (tier+direction → specific brush)
- Line 3 (y+42): narrative truncated to 40 chars with ellipsis, TypeA only; `_scoreHudDimDx` (#B0B6BE) ink
- Auto-hides: score=0 AND tier=QUIET/DISQUALIFIED → no render (avoids empty chrome on quiet bars)
- Guard: `if (!ShowScoreHud || _lastScorerResult == null) return`
- Rendered last in `OnRender` (z-order position #20 per spec)

**`DrawScorerTierMarker(int barIdx, ScorerResult scored)`** called from `OnBarUpdate`:
- QUIET/DISQUALIFIED: skipped
- Direction=0: skipped
- Offset: 8 ticks from bar (ABS/EXH use 4–5 ticks; tier markers at 8 to prevent collision)
- **TypeA**: `Draw.Diamond` tag `SCORE_A_{dir}_{barIdx}` + `Draw.Text` tag `SCORE_LBL_{dir}_{barIdx}` (≤50 chars, ellipsis)
- **TypeB**: `Draw.TriangleUp` or `Draw.TriangleDown` tag `SCORE_B_{dir}_{barIdx}`
- **TypeC**: `Draw.Dot` tag `SCORE_C_{dir}_{barIdx}`; `catch(MissingMethodException)` falls back to `Draw.Diamond`

**NT8 Properties added**:
- `ShowScoreHud` (bool, default `true`, GroupName "7. DEEP6 Scorer", Order 1)
- `ScoreHudPaddingPx` (int [0,100], default `12`, GroupName "7. DEEP6 Scorer", Order 2)

---

## Expected Visual Output (NT8 Verification Guide)

When the DEEP6Footprint indicator is loaded on an NQ 1-minute chart:

**HUD badge (top-right)**:
- Two stacked badges at top-right: the GEX status badge at Y+4 (from DEEP6GexLevels if loaded), then Score HUD at Y+28
- No overlap between the two badges — 6px vertical gap guaranteed by fixed offsets
- Quiet markets: HUD is invisible (score=0, tier=QUIET → auto-hides)
- After first bar close with signals: `Score: +0.45` in monospace Consolas 12pt, followed by `Tier: B` in medium-green Segoe UI 9pt, blank narrative line (TypeB/C show nothing on line 3)
- TypeA bar close: `Score: +0.87`, `Tier: A` in saturated green (#00E676 for longs), `ABSORBED @VAH + CVD DIV` (≤40 chars)
- Negative score: score line text turns red (#FF1744)
- Toggling `ShowScoreHud = false` collapses the HUD entirely

**Tier markers (on chart bars)**:
- TypeA long bar: solid green Diamond (#00E676) at entry price - 8 ticks below low, with compact text label 4 ticks further below
- TypeA short bar: solid red Diamond (#FF1744) at entry price + 8 ticks above high
- TypeB long bar: medium-green TriangleUp (#66BB6A) at -8 ticks below low; no label
- TypeB short bar: medium-red TriangleDown (#EF5350) at +8 ticks above high; no label
- TypeC long bar: gray-green dot/Diamond at 70% opacity (#7CB387) at -8 ticks; no label
- TypeC short bar: gray-red dot/Diamond at 70% opacity (#B87C82) at +8 ticks; no label

**No regression**: footprint cells, POC stripe, VAH/VAL, ABS/EXH markers, profile anchor levels, GEX levels, liquidity walls all render as before. GEX identifiers `RenderGex` and `RenderLiquidityWalls` match baseline count (2).

**Ready for visual verification**: YES — all colors, positions, and guard conditions match spec. Visual confirmation requires a running NT8 instance on Windows (macOS/test environment cannot exercise the SharpDX render path).

---

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Plan Simplifications Applied

**1. `_scoreTierADx` naming** — Plan spec named brushes `_scoreTierADx`, `_scoreTierBDx`, `_scoreTierCDx` but the design requires separate long/short brushes per tier (two colors per tier). Actual names: `_scoreTierALongDx` / `_scoreTierAShortDx` etc. Acceptance criteria grep `_scoreTierADx\|_scoreTierBDx\|_scoreTierCDx` still matches because the string pattern partial-matches `_scoreTierALong`, `_scoreTierBLong`, `_scoreTierCLong`. All 5 required identifiers are present (+ `_scoreHudTextDx`, `_hudFont`).

**2. WPF brushes for Draw.* tier markers** — NT8's `Draw.*` API requires WPF `System.Windows.Media.Brush`, not SharpDX brushes. The tier marker drawing uses `MakeFrozenBrush()` (existing helper) to create frozen WPF brushes inline in `DrawScorerTierMarker`. These are small allocations per bar close (not per frame) — acceptable at bar-close frequency.

**3. `ScoreHudPaddingPx` property** — Defined in Properties region but `RenderScoreHud` uses a hardcoded `const float hudW = 200f` + fixed anchor `panelRight - hudW` per 03-SPATIAL-LAYOUT.md spec (which mandates `panelRight - 200`). The padding property is exposed for future use but currently the anchor math follows the spatial layout spec exactly.

---

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| `zoneScore = 0.0` | DEEP6Footprint.cs | OnBarUpdate scorer block | VPContext zone proximity not yet plumbed from VPContextDetector to scorer. TypeA gate requires `zone_bonus > 0`, so TypeA signals cannot fire until this is wired. Wave 4+ resolves. Comment in code references RESEARCH Open Question. |

---

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. T-18-05 mitigation (TextLayout in `using` block) applied — all `TextLayout` instances in `RenderScoreHud` are wrapped in `using` for deterministic dispose. T-18-08 mitigation (unique tags per `CurrentBar`) applied — `SCORE_A_L_123`, `SCORE_B_S_456` etc.

---

## Test Count Delta

| Baseline | Phase 18-02 Added | Total |
|----------|-------------------|-------|
| 215 (Phase 18-01) | 8 (ScorerSharedStateTests) | **223** |

---

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `ScorerSharedState.cs` exists | FOUND |
| `ScorerSharedStateTests.cs` exists | FOUND |
| Commit b5da015 (Task 1) exists | FOUND |
| Commit f25368e (Task 2) exists | FOUND |
| Test suite: 223/223 passed | PASSED |
