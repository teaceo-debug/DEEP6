# DEEP6FootprintV7 Arrow / Marker Audit

Date: 2026-05-24
Scope: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` only. Read-only audit.

## Executive recommendation

| System | V7 lines | Current default | Recommendation | Why |
|---|---:|---|---|---|
| `DrawTriggeredMarker` | 740-757 | Implicitly ON when a setup triggers | **KEEP** | Highest-signal, post-confirmation event. Already downstream of Type A scoring + armed/triggered lifecycle. Sparse and actionable. |
| `DrawAbsorptionMarker` | 914-925 | `ShowAbsorptionMarkers=false` | **GATE** | Raw detector output, no confluence gate, no cooldown, can emit multiple markers on one bar. Biggest clutter source. |
| `DrawExhaustionMarker` | 927-947 | `ShowExhaustionMarkers=false` | **GATE** | Raw detector output, no confluence gate in V7 marker path. Less noisy than absorption because detector has 5-bar subtype cooldown, but still visually busy. |
| `RenderTier1Overlay` | 1849-1911 | `ShowTier1Overlay=true` | **KEEP** | Type A only, short-lived, conveys setup/armed/triggered state plus entry context. Rare enough to keep on by default. |

## Scoring facts used for gating

- `SignalTier.TYPE_C/B/A` thresholds are defined in `SignalTier.cs:25-32`.
- Actual scorer promotion rules are in `ConfluenceScorer.cs:445-466`:
  - **TYPE_A:** score `>=80`, `hasAbsorption || hasExhaustion`, zone present, `catCount >= 5`, delta agrees.
  - **TYPE_B:** score `>=72`, `catCount >= 4`, delta agrees, min strength.
  - **TYPE_C:** score `>=50`, `catCount >= 4`, min strength.
- The scorer stores the usable confluence count as `ScorerResult.CategoryCount` (`ScorerResult.cs:30-35`), set from `catCount` in `ConfluenceScorer.cs:508-519`. There is no separate `ConfluenceCount` property in this path.

## Recommended new gating parameters

| Parameter | Recommended value | Reasoning |
|---|---:|---|
| `MinArrowConfluence` | **4** | Aligns raw arrow visibility with the first meaningful scorer bucket (`catCount >= 4` for TYPE_C/TYPE_B). This is materially below Type A's `>=5`, but high enough to suppress one-off detector spam. |
| `MinExhaustionStrength` | **0.60** | Keeps only structurally meaningful exhaustion markers. `EXH-01` already emits fixed strength `0.6`; weaker exhaustion variants below 0.60 are the most likely clutter. |

## Detailed system audit

### 1) `DrawTriggeredMarker`

- **Location:** `DEEP6FootprintV7.cs:740-757`
- **Call site:** `DEEP6FootprintV7.cs:708-724`
- **Trigger condition:**
  1. A scored setup must survive `ApplyVersionTwoSetupMetadata()` and lifecycle management.
  2. The active setup must be `TradeSetupState.Armed` (`DEEP6FootprintV7.cs:702-706`).
  3. The trigger bar must close through `EntryPrice` in the setup direction (`DEEP6FootprintV7.cs:708-716`).
  4. In practice this is a **Type A path**, because V7 only draws scorer tier markers for `TYPE_A` (`DEEP6FootprintV7.cs:2264-2299`) and the Tier 1 overlay also hard-requires `TYPE_A` (`DEEP6FootprintV7.cs:1851-1854`).
- **Visual:** green up-arrow / red down-arrow plus `Long Triggered` / `Short Triggered` text.
- **Estimated frequency:** **~0-1 per RTH session, usually closer to 0.2/session or less.** Evidence: `overnight_findings.md:92-100` shows only 65 TYPE_A bars across 332 sessions (~0.20/session), and `regime_analysis.py:660-663` notes TYPE_A fires on `<0.1%` of bars.
- **Redundancy:** overlaps with the pulsing arrow inside `RenderTier1Overlay` when the setup reaches `Triggered`, but this overlap happens only on rare Type A events.
- **Recommendation:** **KEEP (default ON).** This is the cleanest execution-grade marker in the file.

### 2) `DrawAbsorptionMarker`

- **Location:** `DEEP6FootprintV7.cs:914-925`
- **Call site:** `DEEP6FootprintV7.cs:511-515`
- **Trigger condition:**
  - Fires for **every raw absorption signal** returned by `AbsorptionDetector.Detect(...)` whenever `ShowAbsorptionMarkers` is enabled.
  - No confluence filter, no score filter, no tier filter, no setup-state filter.
  - Raw absorption families include `ABS-01/02/03/04`, plus `ABS-07` VA bonus diagnostics in the detector path (`AbsorptionDetector.cs:1-7`, `143-205`).
- **Visual:** cyan/magenta triangle plus 3-letter subtype label (`CLA`, `PAS`, `STO`, `EFF`) from `s.Kind.ToString().Substring(0,3).ToUpper()`.
- **Estimated frequency:** **high; roughly 10-40 markers per RTH session, with bursty multi-marker bars possible.** Reason: the detector has **no cooldown** and can emit multiple subtypes on the same bar (`AbsorptionDetector.cs:109-205`).
- **Redundancy:** very high. It often repeats information that later appears in scorer-driven Type A setup markers, Tier 1 overlay text, and triggered markers.
- **Recommendation:** **GATE (default OFF).**
  - Only show if scorer confluence is already meaningful: `CategoryCount >= MinArrowConfluence`.
  - If a future implementation must be stricter, raise to 5 for Type-A-only visibility; do **not** lower below 4.

### 3) `DrawExhaustionMarker`

- **Location:** `DEEP6FootprintV7.cs:927-947`
- **Call site:** `DEEP6FootprintV7.cs:518-521`
- **Trigger condition:**
  - Fires for **every raw exhaustion signal** returned by `_exhDetector.Detect(...)` whenever `ShowExhaustionMarkers` is enabled.
  - No confluence filter, no score filter, no tier filter in the marker path.
  - Exhaustion families are `EXH-01..06` (`ExhaustionDetector.cs:1-6`, `149-315`).
  - The detector does have a built-in **5-bar cooldown per subtype** (`ExhaustionDetector.cs:34-35`, `151`, `174`, `216`, `239`, `259`, `277`, `362-372`), so this path is less spammy than absorption.
- **Visual:** yellow long arrow, orange-red short arrow, or slate-gray diamond for neutral `EXH-04` fat prints, with percent text for neutral prints.
- **Estimated frequency:** **moderate; roughly 5-20 markers per RTH session.** The cooldown makes it materially less frequent than raw absorption, but still too chatty to leave ungated.
- **Redundancy:** medium-high. Useful as context, but frequently duplicates what the scorer already compresses into categories and tiers.
- **Recommendation:** **GATE (default OFF).**
  - Require `CategoryCount >= MinArrowConfluence`.
  - Require `Strength >= MinExhaustionStrength` with **`MinExhaustionStrength=0.60`** to preserve only the stronger exhaustion prints.

### 4) `RenderTier1Overlay`

- **Location:** `DEEP6FootprintV7.cs:1849-1911`
- **Call site:** `DEEP6FootprintV7.cs:1189`
- **Trigger condition:**
  1. `ShowTier1Overlay == true`.
  2. `_lastScorerResult` exists and is `SignalTier.TYPE_A` with non-zero direction (`DEEP6FootprintV7.cs:1851-1854`).
  3. `EntryPrice > 0` and the signal is still visible inside `ArmedSignalValidBars` (`DEEP6FootprintV7.cs:1840-1847`, `1853-1854`).
  4. If the setup is triggered, the overlay adds a pulsing directional arrow at the trigger bar (`DEEP6FootprintV7.cs:1879-1910`).
- **Visual:** right-edge callout text for setup state + detail, plus pulsing Type A arrow on triggered bars.
- **Estimated frequency:** **~0-1 overlay episodes per RTH session, typically under 1.** Same rarity basis as Type A above.
- **Redundancy:** some duplication with `DrawTriggeredMarker` during triggered state, but not with raw absorption/exhaustion markers. The overlay carries lifecycle context that the raw marker paths do not.
- **Recommendation:** **KEEP (default ON).** It is sparse, stateful, and already heavily filtered.

## Redundancy conclusions

1. **Main clutter source = raw detector markers, not scorer-driven Type A visuals.**
   - `DrawAbsorptionMarker` and `DrawExhaustionMarker` bypass the scorer entirely.
2. **`DrawTriggeredMarker` and `RenderTier1Overlay` are partially redundant only at the exact trigger moment.**
   - Acceptable because Type A is rare.
3. **`DrawAbsorptionMarker` is the most redundant system.**
   - It can emit multiple labels on a single bar before any confluence or tradeability check exists.

## Final recommended default policy for V8

- **KEEP / default ON:**
  - `DrawTriggeredMarker`
  - `RenderTier1Overlay`
- **GATE / default OFF:**
  - `DrawAbsorptionMarker` with `MinArrowConfluence=4`
  - `DrawExhaustionMarker` with `MinArrowConfluence=4`, `MinExhaustionStrength=0.60`
- **REMOVE:** none of the four need removal outright; the problem is ungated raw-signal rendering, not the existence of the Type A lifecycle visuals.
