# V8 vs V7 Footprint Comparison

**Date:** 2026-05-24
**Method:** Static code analysis (NT8 replay requires UI — documented from code)
**Files:** `DEEP6FootprintV7.cs` (2584 lines) vs `DEEP6FootprintV8.cs` (2802 lines)

## Executive Summary

| Criterion | Result |
|-----------|--------|
| V8 defaults ≤ V7 signal count | **PASS** — V8 renders significantly fewer signals |
| V8 all-toggles-ON = V7 detections | **PASS** — detection logic identical, rendering differs cosmetically |
| Detection regression | **NONE** — upstream detection pipeline unchanged |

## 1. Detection Logic Comparison

All signal detection runs upstream of rendering. Every detection call is **byte-identical** between V7 and V8:

| Detection Method | V7 Line | V8 Line | Identical? |
|-----------------|---------|---------|------------|
| `OnMarketData` tick intake | 347-371 | 377-401 | YES |
| `FootprintBar.Finalize` | 476 | 506 | YES |
| `AbsorptionDetector.Detect()` | 513 | 543 | YES — same 7 args |
| `ExhaustionDetector.Detect()` | 520 | 550 | YES — same 5 args |
| `_scorerRegistry.EvaluateBar()` | 542 | 572 | YES — same 12 detectors |
| `ConfluenceScorer.Score()` | 547-558 | 577-588 | YES — same 12 params |
| `ApplyVersionTwoSetupMetadata()` | 609-657 | 640-688 | YES |
| `DrawScorerTierMarker()` | 2264-2301 | 2386-2423 | YES |

**Config defaults also identical:**
- `AbsorbWickMinPct = 30.0` (both)
- `ExhaustWickMinPct = 35.0` (both)
- `ImbalanceRatio = 3.0` (both)
- `ArmedSignalValidBars = 3` (both)
- Same 12 detectors registered in same order (both)

## 2. V8 New Rendering Gates

V8 adds **three layers of rendering gates** that do not exist in V7. All gates operate AFTER detection — they suppress visual output, not signal computation.

### Layer A: Per-Variant Toggles (10 properties)

| # | Property | Default | What it gates |
|---|----------|---------|---------------|
| 1 | `ShowClassicAbsorption` | **ON** | `AbsorptionType.Classic` markers |
| 2 | `ShowPassiveAbsorption` | OFF | `AbsorptionType.Passive` markers |
| 3 | `ShowStoppingVolume` | OFF | `AbsorptionType.StoppingVolume` markers |
| 4 | `ShowEffortVsResult` | **ON** | `AbsorptionType.EffortVsResult` markers |
| 5 | `ShowZeroPrint` | OFF | `ExhaustionType.ZeroPrint` markers |
| 6 | `ShowExhaustionPrint` | **ON** | `ExhaustionType.ExhaustionPrint` markers |
| 7 | `ShowThinPrint` | OFF | `ExhaustionType.ThinPrint` markers |
| 8 | `ShowFatPrint` | **ON** | `ExhaustionType.FatPrint` markers |
| 9 | `ShowFadingMomentum` | OFF | `ExhaustionType.FadingMomentum` markers |
| 10 | `ShowBidAskFade` | **ON** | `ExhaustionType.BidAskFade` markers |

**5 ON, 5 OFF** → 50% of variant types suppressed at default.

### Layer B: Quality Thresholds

| # | Property | Default | Effect |
|---|----------|---------|--------|
| 11 | `MinArrowConfluence` | 4 | Suppresses absorption/exhaustion markers when `CategoryCount < 4` |
| 12 | `MinExhaustionStrength` | 0.504331 | Suppresses exhaustion markers when `Strength < threshold` |
| 13 | `ShowTriggeredArrows` | true | Toggle for triggered signal arrows |
| 14 | `BiasLongThreshold` | 0.59481 | Bias box long entry threshold |
| 15 | `BiasShortThreshold` | -0.649336 | Bias box short entry threshold |
| 16 | `BiasLookback` | 4 | Lookback period for bias computation |

### Layer C: Frequency Limiter

| # | Property | Default | Effect |
|---|----------|---------|--------|
| 17 | `MaxSignalsPerSession` | 23 | Hard cap on rendered signals per session |

Applied in three places: `DrawAbsorptionMarker`, `DrawExhaustionMarker`, `DrawTriggeredMarker`.

### Visual Change: Bias Box

| # | Property | Default | Effect |
|---|----------|---------|--------|
| 18 | `ShowBiasBox` | true | Replaces V7 diamond+percentage for direction=0 exhaustion |
| 19 | `ShowRawPercentage` | false | Falls back to V7-style diamond when true |

## 3. Signal Count Analysis

### V7 with ShowAbsorptionMarkers=ON + ShowExhaustionMarkers=ON:
- **All** 4 absorption variants rendered (Classic, Passive, StoppingVolume, EffortVsResult)
- **All** 6 exhaustion variants rendered (ZeroPrint, ExhaustionPrint, ThinPrint, FatPrint, FadingMomentum, BidAskFade)
- No confluence gate
- No strength gate
- No frequency limiter
- **Result: Maximum visual signal output**

### V8 with defaults (ShowAbsorptionMarkers=ON + ShowExhaustionMarkers=ON):
- **2 of 4** absorption variants rendered (Classic, EffortVsResult)
- **3 of 6** exhaustion variants rendered (ExhaustionPrint, FatPrint, BidAskFade)
- MinArrowConfluence=4 → signals with < 4 categories firing suppressed
- MinExhaustionStrength=0.504331 → weak exhaustion suppressed
- MaxSignalsPerSession=23 → hard cap
- **Result: Dramatically fewer visual signals (estimated 70-85% reduction)**

### V8 with all toggles ON + thresholds zeroed:
- All 10 variant toggles ON
- MinArrowConfluence=0
- MinExhaustionStrength=0.0
- MaxSignalsPerSession=0 (unlimited)
- **Result: Same detections as V7** (minor cosmetic differences only)

## 4. Cosmetic Differences (V8 with all toggles ON vs V7)

| Difference | V7 | V8 |
|-----------|----|----|
| Triggered arrow tag prefix | `V7_TRIGGER_` | `V8_TRIGGER_` |
| Direction=0 exhaustion | Diamond + strength % | Bias box ("LONG"/"SHORT"/"—") unless ShowRawPercentage=true |
| Signal direction tracking | Not tracked | `TrackRecentSignalDirection()` builds bias history |
| Session signal counter | Not present | `_sessionSignalCount` incremented (no-op when cap=0) |
| ShowTier1Overlay default | true | false |

## 5. New V8 Methods (not in V7)

| Method | Purpose |
|--------|---------|
| `TrackRecentSignalDirection(int)` | Enqueues +1/-1 into rolling window for bias computation |
| `ComputeBiasScore(int)` | Returns [-1.0, 1.0] bias from recent signal directions |

Both are rendering-support methods that do not affect detection.

## 6. Verdict

- **Signal count: V8 defaults ≤ V7** — CONFIRMED
- **Regression: None** — Detection pipeline unchanged; V8 gates are rendering-only
- **Reversibility: Full** — Setting all V8 toggles ON + thresholds to 0 recovers V7 behavior

## Evidence Files

- `.sisyphus/evidence/task-15-signal-count-comparison.txt` — detailed signal count analysis
- `.sisyphus/evidence/task-15-regression.txt` — regression proof with line-by-line comparison
