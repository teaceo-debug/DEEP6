# Phase 18: NT8 Scoring + Backtest Validation — Research

**Researched:** 2026-04-15
**Domain:** NinjaScript two-layer confluence scorer port; SharpDX HUD rendering; C#↔Python parity harness
**Confidence:** HIGH (all critical findings verified from codebase; no external web search required — source of truth is the repo itself)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Port weights and thresholds **verbatim** from Python `scoring/scorer.py`. Do not expose as NT8 Properties in Phase 18.
- HUD badge top-right of main pane (3 lines: score / tier / narrative-truncated-40). Updates on bar close only.
- Tier glyphs: TypeA solid diamond saturated, TypeB hollow triangle, TypeC small dot. Drawn via `Draw.Diamond` / `Draw.TriangleUp/Down` / `Draw.Dot`.
- On-chart narrative only for TypeA (≤50 chars); TypeB/C narrative only in strategy log.
- Parity bar: bit-for-bit on fixtures, ±0.05 + identical tier on replay sessions.
- Reuse Phase 17 NDJSON CaptureHarness + extend.
- Cut hardcoded STACKED/VA-EXTREME/WALL-ANCHORED rules in `DEEP6Strategy.EvaluateEntry`; replace with `score >= threshold && tier >= MinTierForEntry`.
- Risk gates must stay ABOVE scorer call — untouched.
- Python-bug-fix-first policy from Phase 17 carries forward.
- Two new files: `AddOns/DEEP6/Scoring/ConfluenceScorer.cs` and `AddOns/DEEP6/Scoring/NarrativeCascade.cs`.

### Claude's Discretion

- Exact SharpDX render order for HUD badge vs GEX lines vs footprint cells (planner to verify z-order).
- Narrative label opacity / background-box color (planner to pick readable default).
- `ScoreEntryThreshold` default value — use Python's `entry_threshold` constant verbatim.
- Whether HUD shows previous bar's score or forming bar's partial score (planner to default: previous bar only).
- File-by-file test fixture coverage — target at least 3 fixtures per scoring scenario.
- Scorer subprocess test harness: use `python3` path from env, or commit a Python replay entry-point script.

### Deferred Ideas (OUT OF SCOPE)

- User-tunable scoring weights via NT8 Properties (Phase 19+).
- Separate indicator pane with score as line chart.
- Per-bar score history visualization.
- Hover-to-show narrative on TypeB/C bars.
- Kronos E10 bias influence on scoring.
- Real-time parity dashboard / Next.js live view.
- Databento historical MBO vs Phase 17 NDJSON as parity dataset (Phase 19+).
</user_constraints>

---

## Summary

Phase 18 ports the Python two-layer confluence scorer (`deep6/scoring/scorer.py`) verbatim into NinjaScript, adds on-chart HUD rendering in `DEEP6Footprint.cs`'s existing `OnRender` pipeline, and replaces the hardcoded Tier-3 `EvaluateEntry` rules in `DEEP6Strategy.cs` with scorer-driven gates. The parity harness extends the existing `CaptureReplayLoader` / NDJSON infrastructure from Phase 17.

**Primary recommendation:** Compute scores inside `DEEP6Footprint.cs` (indicator-side) where the full `SignalResult[]` registry output already lands each bar, write results to a `ScorerResult` public property or shared state, let `DEEP6Strategy` read that property to gate entries. This matches the existing pattern where the strategy already reads `AbsorptionSignal` and `ExhaustionSignal` lists constructed from registry output.

**Critical pre-work (from Phase 17 VERIFICATION.md):** Before Phase 18 can proceed, the CS0102 duplicate `UseNewRegistry` property in `DEEP6Strategy.cs` (lines 698 and 805) must be fixed, and the double `_registry.EvaluateBar()` call (lines 334 and 384) must be collapsed to a single call. These are blocking regressions from Phase 17.

---

## Python Scorer — Verified Structure

### Category Weights [VERIFIED: deep6/scoring/scorer.py lines 99–110]

```
CATEGORY_WEIGHTS = {
    "absorption":     25.0,
    "exhaustion":     18.0,
    "trapped":        14.0,   # was 10 — raised after backtest
    "delta":          13.0,   # was 10 — delta agreement critical
    "imbalance":      12.0,
    "volume_profile": 10.0,
    "auction":         8.0,
    "poc":             1.0,   # was 3.0 then 7.0 — forensic shows POC combos lose money
}
```

**Total of all category weights:** 101.0 — but the score formula multiplies by `agreement` (0–1 ratio), so practical max before bonuses is well under 100.

### Tier Thresholds [VERIFIED: deep6/engines/signal_config.py ScorerConfig lines 195–198]

```
type_a_min:   80.0   (TypeA  — high conviction)
type_b_min:   72.0   (TypeB  — moderate conviction; was 65, raised to eliminate marginal losers)
type_c_min:   50.0   (TypeC  — observational)
QUIET:        below TypeC or < min_categories
```

### TypeA Entry Gate — All 7 Conditions Must Be True [VERIFIED: scorer.py lines 472–479]

1. `total_score >= 80.0`
2. `"absorption" in categories_agreeing OR "exhaustion" in categories_agreeing`
3. `zone_bonus > 0` (price inside or near an active zone scoring >= 30)
4. `cat_count >= 5`
5. `delta_agrees == True` (bar delta direction agrees with signal direction)
6. `NOT type_a_trap_veto` (trap veto only when >= 3 trap signals fire)
7. `NOT type_a_delta_chase` (large chase, |bar_delta| > 50 and same direction = chase)

TypeB: `score >= 72.0 AND cat_count >= 4 AND delta_agrees AND min_strength (narrative.strength >= 0.3)`
TypeC: `score >= 50.0 AND cat_count >= 4 AND min_strength (narrative.strength >= 0.3)`

**NOTE: TypeC in Python requires cat_count >= 4 — NOT 3.** The docstring says `min_categories=3` but the actual TypeC check in code (scorer.py line 485) is `cat_count >= 4`. This is a potential documentation bug in the Python source — the planner must verify by reading the code, not the docstring. The `min_categories` kwarg from ScorerConfig is NOT used in the TypeC branch.

### Zone Bonus Tiers [VERIFIED: signal_config.py ScorerConfig lines 203–209]

```
zone.score >= 50.0 → zone_bonus = +8.0  (zone_high_min / zone_high_bonus)
zone.score >= 30.0 → zone_bonus = +6.0  (zone_mid_min / zone_mid_bonus)
within 0.5 ticks of zone edge, score >= 50.0 → zone_bonus = +4.0  (zone_near_bonus)
zone.score < 30.0 → zone_bonus = 0.0
```

### Score Formula [VERIFIED: scorer.py lines 408–435]

```
base_score = sum(CATEGORY_WEIGHTS[cat] for cat in categories_agreeing)
  (GEX modifies absorption/exhaustion weight by gex_abs_mult, delta/imbalance by gex_momentum_mult)

total_score = min(
    (base_score * confluence_mult + zone_bonus + gex_near_wall_bonus) * agreement * ib_mult,
    100.0
)

# D-01: confirmation bonus
if narrative.confirmed_absorptions:
    total_score = min(total_score + len(confirmed) * 2.0, 100.0)

# VPIN final stage (from phase 12-01, locked order)
total_score *= vpin_modifier
total_score = max(0.0, min(100.0, total_score))
```

**Confluence multiplier:** `1.25 if cat_count >= 5 else 1.0` (SCOR-02; threshold from `ScorerConfig.confluence_threshold = 5`)

**IB multiplier:** `1.15 if 0 <= bar_index_in_session < 60 else 1.0`

**VPIN:** For Phase 18 port, `vpin_modifier = 1.0` (neutral) is the correct default — VPIN engine (E5 output feeds into this, but Phase 18 does not port the full VPIN pipeline; default 1.0 preserves formula equivalence).

### Signal→Category Mapping [VERIFIED: scorer.py lines 180–280]

The scorer maps signal IDs to categories via the `NarrativeResult` fields and `delta_signals / auction_signals / poc_signals` parameters:

| Category | Signal IDs | Source in NarrativeResult / params |
|----------|-----------|-------------------------------|
| absorption | ABS-01, ABS-02, ABS-03, ABS-04, ABS-07 | `narrative.absorption[]` — all AbsorptionSignal with direction != 0 |
| exhaustion | EXH-01, EXH-02, EXH-03, EXH-04, EXH-05, EXH-06 | `narrative.exhaustion[]` — all ExhaustionSignal with direction != 0 |
| trapped | TRAP-01 (INVERSE_TRAP from IMB-05) | `narrative.imbalances[]` where `"TRAP" in sig.imb_type.name` |
| imbalance | IMB-02 (STACKED_T1/T2/T3 only — deduplicated) | `narrative.imbalances[]` stacked types; one vote per direction, highest tier wins |
| delta | DELT-04 (DIVERGENCE), DELT-10 (CVD_DIVERGENCE), DELT-08 (SLINGSHOT), DELT-06 (TRAP), DELT-05 (FLIP) | `delta_signals[]` — only these 5 DeltaType values vote |
| auction | AUCT-02 (FINISHED_AUCTION), AUCT-01 (UNFINISHED_BUSINESS), AUCT-05 (MARKET_SWEEP) | `auction_signals[]` — only these 3 AuctionType values vote |
| poc | POC-02 (EXTREME_POC_HIGH/LOW), POC-08 (BULLISH/BEARISH_POC), POC-07 (VA_GAP) | `poc_signals[]` — only these 5 POCType values vote |
| volume_profile | (zone proximity, not a direct signal) | Active zones evaluated in scorer; adds category when bar_close inside/near zone scoring >= 30 |

**Critical implementation note — imbalance voting:** ONLY stacked imbalances (STACKED_T1, STACKED_T2, STACKED_T3) vote in the "imbalance" category. Single/oversized/diagonal/consecutive/reversal imbalances do NOT vote. TRAP signals within the imbalance list vote in "trapped" not "imbalance". This is a subtle dedup rule (D-02) that must be preserved exactly.

**Critical implementation note — delta voting:** Only 5 of the 11 DELT signal types vote: DIVERGENCE, CVD_DIVERGENCE, SLINGSHOT, TRAP, FLIP. The other 6 (RISE, DROP, TAIL, REVERSAL, SWEEP, VELOCITY) do NOT add a category vote. They still appear in SignalResult[] but are not consumed by the scorer's directional-vote layer.

### Midday Block [VERIFIED: signal_config.py lines 210–213, scorer.py lines 493–496]

Bars 240–330 of the session (10:30–13:00 ET on RTH) are forced to QUIET tier. This is a hard coded forensic finding (accumulated -$1,622 across 25 days). Phase 18 C# port MUST implement this block:
```csharp
if (tier != SignalTier.DISQUALIFIED
    && session.BarsSinceOpen >= 240
    && session.BarsSinceOpen <= 330)
    tier = SignalTier.QUIET;
```

### Edge Cases [VERIFIED: scorer.py]

| Scenario | Python behavior | C# must match |
|----------|----------------|---------------|
| Zero signals fire | `direction=0, agreement=0.0, cat_count=0, tier=QUIET, total_score=0.0` | Return ScorerResult with tier=QUIET, score=0.0 |
| Conflicting directions (bull absorption + bear exhaustion) | Dominant direction wins; losing direction's categories excluded from `categories_agreeing` | Same majority-vote logic |
| No zone in active_zones | `zone_bonus=0.0`; TypeA cannot fire (requires `zone_bonus > 0`) | TypeA gate includes `has_zone` flag |
| DISQUALIFIED veto | ConfluenceAnnotations.vetoes forces `tier=DISQUALIFIED` regardless of score | Phase 18: no ConfluenceRules port; `forced_disqualified=false` always; veto path not needed yet |
| GEX signal absent | All GEX multipliers = 1.0, no wall bonus | Default: `gex_abs_mult=1.0, gex_momentum_mult=1.0, gex_near_wall_bonus=0.0` |
| VPIN absent | `vpin_modifier=1.0` | Default 1.0 — no VPIN in Phase 18 |
| Midday window (bars 240–330) | Force QUIET regardless of score | Must check `session.BarsSinceOpen` |
| TypeA trap veto | `>= 3 trap signals` veto TypeA only | Count via SignalId prefix "TRAP" or flag bit check |
| TypeA delta chase | `direction > 0 and bar_delta > 0 and delta_mag > 50` blocks TypeA | Approximate: `|barDelta| > 50 and direction matches delta` |
| Confirmation bonus | `len(confirmed_absorptions) * 2.0` added to total_score | ABS-06 confirmation tracking not yet in C# — Phase 18 can default `confirmed_absorptions=0` initially |

### Suppression / Cooldown

The scorer itself has NO cooldown logic — it evaluates each bar independently. Cooldown for exhaustion (EXH-08: 5 bars) lives inside `ExhaustionDetector.cs` and is already implemented in Phase 17. The scorer simply receives whatever signals the detectors emit.

---

## Narrative Assembly — Phase 18 Scope

### Python narrative label format [VERIFIED: narrative.py, scorer.py lines 499–508]

The Python `NarrativeResult.label` is the primary signal's human-readable description. Examples:
- `"SELLERS ABSORBED @VAL — HIGH CONVICTION LONG ZONE"` (TypeA absorption at VAL)
- `"BUYERS ABSORBED @VAH — HIGH CONVICTION SHORT ZONE"` (TypeA absorption at VAH)
- `"BUYERS LOSING STEAM — NOT A TRADE YET"` (exhaustion, bearish signal)
- `"MOMENTUM IGNITION — JOIN BUYERS"` (momentum)
- `"QUIET"` (no signals)

The `ScorerResult.label` from `score_bar()` overwrites with tier-specific text for TypeA/B/C:
```python
TYPE_A: "TYPE A — TRIPLE CONFLUENCE LONG (6 categories, score 87)"
TYPE_B: "TYPE B — DOUBLE CONFLUENCE SHORT (4 categories, score 74)"
TYPE_C: "TYPE C — SIGNAL (4 categories, score 52)"
QUIET:  [narrative.label verbatim]
```

### HUD badge content (3 lines) [VERIFIED: 18-CONTEXT.md]

```
Line 1: "Score: +0.87"  (signed, 2 decimals — scores are 0–100, not 0–1; display as fraction: score/100)
Line 2: "Tier: A"       (A / B / C / -)
Line 3: narrative label truncated to 40 chars
```

**Note:** The CONTEXT.md says "Score: +0.87" (signed, 2 decimals). Since `total_score` is 0–100, the signed display is `total_score / 100` formatted as `+0.87`. This normalization must be explicit in the C# HUD renderer: `string.Format("{0:+0.00;-0.00;0.00}", totalScore / 100.0)`.

### On-chart narrative label (TypeA only) [VERIFIED: 18-CONTEXT.md]

The Python `NarrativeResult.label` or the dominant signal's `detail` field provides the label text. For the C# port, the `SignalResult.Detail` field of the highest-strength absorption/exhaustion signal is the source. Format rules:
- Take the dominant signal's `Detail` string.
- Append up to 2 supporting signal identifiers from the same bar: `" + " + supportingSignalId`.
- Truncate to 50 chars with ellipsis.

Example: `"ABSORBED @VAH + CVD DIVERGENCE + OVERSIZED IMB..."` → truncated at 50.

---

## SharpDX HUD Rendering in NT8

### Confirmed pattern from DEEP6Footprint.cs [VERIFIED: DEEP6Footprint.cs lines 1502–1509]

The existing GEX status badge uses exactly the pattern the HUD badge needs:

```csharp
// Top-right anchored text badge (existing pattern in DEEP6Footprint.cs)
using (var statusLayout = new TextLayout(
    NinjaTrader.Core.Globals.DirectWriteFactory,
    textContent,
    _labelFont,        // existing TextFormat at 12pt
    380f,              // max width
    18f))              // max height per line
{
    RenderTarget.DrawTextLayout(
        new Vector2(panelRight - 384, (float)ChartPanel.Y + 4),
        statusLayout, brushRef);
}
```

`panelRight` is computed as `(float)(ChartPanel.X + ChartPanel.W)` — this anchors the badge to the chart panel frame, not to a price level.

### HUD badge anchoring [VERIFIED: DEEP6Footprint.cs line 1484]

```csharp
float panelRight = (float)(ChartPanel.X + ChartPanel.W);
// HUD badge: offset left from panelRight by badge width + padding
// Top: ChartPanel.Y + padding (12px default per CONTEXT.md)
Vector2 hudOrigin = new Vector2(
    panelRight - hudWidth - 12f,    // 12px right padding
    (float)ChartPanel.Y + 12f       // 12px top padding
);
```

### Multi-line HUD: one TextLayout per line [ASSUMED]

NT8's SharpDX DirectWrite `TextLayout` renders one string block. For 3 distinct lines with different colors (Score text, tier colored text, narrative), create 3 separate `TextLayout` objects positioned vertically by incrementing Y by font height (~16px for 12pt mono).

### Z-order for Score HUD vs existing renders [VERIFIED: DEEP6Footprint.cs lines 1485–1521]

Existing `OnRender` call order (bottom to top):
1. GEX horizontal levels (`RenderGex`) — lowest Z
2. Liquidity Walls (`RenderLiquidityWalls`)
3. Footprint cells (the bar loop)
4. GEX status badge (top-right, highest Z among existing elements)

**Score HUD must be rendered AFTER the GEX status badge** so it does not get occluded. Position the score HUD below the GEX status badge (add ~22px Y offset from the top), or use a distinct X offset so they don't overlap. Given the GEX status renders at `panelRight - 384, ChartPanel.Y + 4`, the score HUD can render at `panelRight - 200, ChartPanel.Y + 4` (narrower width since 3 short lines).

### SharpDX brush lifecycle [VERIFIED: DEEP6Footprint.cs lines 1406–1472]

All SharpDX brushes are created in `OnRenderTargetChanged()` and disposed in `DisposeDx()`. The score HUD needs 3 additional brushes:
- `_scoreHudTextDx` — neutral white/gray text
- `_scoreTierADx` — TypeA saturated green (long) or red (short)
- `_scoreTierBDx` — TypeB medium saturation
- `_scoreTierCDx` — TypeC 50% saturation gray-green/gray-red

Add these to the existing `DisposeDx()` / `OnRenderTargetChanged()` pattern.

### TextFormat pool [VERIFIED: DEEP6Footprint.cs line 1450]

The existing `_ctBtnFont` (Segoe UI 10pt, center alignment) and `_labelFont` are already allocated. Phase 18 should reuse `_labelFont` for HUD text (12pt as specified in CONTEXT.md), or add a new `_hudFont` at 12pt monospace. Creating a new TextFormat at construction time follows the same `OnRenderTargetChanged` pattern.

---

## Draw.Diamond / Draw.TriangleUp/Down / Draw.Dot APIs

### Confirmed usage from DEEP6Footprint.cs [VERIFIED: DEEP6Footprint.cs lines 1295–1322]

```csharp
// Existing triangle markers (ABS/EXH):
Draw.TriangleUp(this, tag, false, barsAgo, priceLevel, brush);   // isOutline=false
Draw.TriangleDown(this, tag, false, barsAgo, priceLevel, brush);
Draw.Diamond(this, tag, false, barsAgo, priceLevel, brush);      // neutral direction
Draw.Text(this, tag + "_lbl", text, barsAgo, priceLevel, brush); // label next to marker
```

**Parameter order:** `(owner, tag, isAutoScale, barsAgo, y, brush)`

### Tier-coded marker patterns for Phase 18

```csharp
// TypeA: solid diamond, fully saturated
// isOutline=false = filled/solid
Draw.Diamond(this, "SCORE_A_" + barIdx, false, barsAgo, entryPrice, direction > 0 ? solidGreenBrush : solidRedBrush);

// TypeB: hollow triangle, medium saturation
// isOutline=true = hollow outline only
Draw.TriangleUp(this, "SCORE_B_" + barIdx, false, barsAgo, entryPrice - 4*TickSize, medGreenBrush);   // long
Draw.TriangleDown(this, "SCORE_B_" + barIdx, false, barsAgo, entryPrice + 4*TickSize, medRedBrush);   // short
// NOTE: Draw.TriangleUp/Down does not expose isOutline directly as a parameter;
// "hollow" effect is achieved by using a transparent brush with colored outline, or
// via Draw.Line drawing a triangle outline. Investigate Draw.Triangle for isOutline support.

// TypeC: small dot
Draw.Dot(this, "SCORE_C_" + barIdx, false, barsAgo, entryPrice, grayGreenBrush);
```

**IMPORTANT CAVEAT [ASSUMED]:** The existing code uses `Draw.Diamond(this, tag, false, barsAgo, price, brush)` but there is no `Draw.Dot` call anywhere in the codebase. `Draw.Dot` may not be a valid NT8 DrawingTool method name — NT8's drawing tools include `Draw.Dot`, but it renders at 4px and may have different parameter order. The planner must verify `Draw.Dot` signature in NT8 documentation before using it. Fallback: use `Draw.Diamond` at a smaller size, or `Draw.Ellipse`.

**All drawing object tags must be unique per bar.** The tag pattern `"SCORE_A_" + barIdx` ensures no collision between bars or between signal types.

### Persistence of Draw objects across bar updates [VERIFIED: pattern analysis]

NT8 drawing objects added via `Draw.*` with `isAutoScale=false` persist until the chart repaints or they are explicitly removed via `RemoveDrawObject(tag)`. For scorer markers, call `RemoveDrawObject("SCORE_A_" + barIdx)` before redrawing if the bar index is being re-evaluated (historical replay mode). The tag-based system handles this automatically since the same tag overwrites.

---

## Strategy ↔ Indicator Coupling — Recommended Architecture

### Option A: Score in Indicator, Strategy Reads Public Property (RECOMMENDED)

The `DEEP6Footprint` indicator already holds `_registry`, `_session`, and the full `SignalResult[]` from `DetectorRegistry.EvaluateBar()` each bar. The indicator:

1. Calls scorer with the signal results after `EvaluateBar()`.
2. Stores the last `ScorerResult` in a public property: `public ScorerResult LastScorerResult { get; private set; }`.
3. Renders HUD badge and tier markers in `OnBarUpdate` (draw objects) and `OnRender` (SharpDX badge).

`DEEP6Strategy` reads the indicator's result:
```csharp
var indicatorResult = Values[0]; // if score is exposed as a Plot
// OR:
var deep6 = (DEEP6Footprint)Indicators.First(i => i is DEEP6Footprint);
var scored = deep6.LastScorerResult;
```

**Why Option A:** The indicator owns the registry, session context, and rendering pipeline. The strategy currently already reads `AbsorptionSignal`/`ExhaustionSignal` lists from the registry output (lines 346–358 in DEEP6Strategy.cs). Extending this to read a `ScorerResult` is the minimal-diff approach.

### Option B: Score in Strategy (NOT RECOMMENDED)

The strategy would need its own registry reference and session context, duplicating Phase 17 initialization code. The indicator's `OnRender` would need to read from the strategy. Cross-indicator/strategy state sharing in NT8 is fragile and version-dependent.

### Implementation pattern for strategy reading indicator result [ASSUMED]

NT8 strategies can reference indicators via the strategy's `Indicators` collection or by casting a series value. The standard pattern for accessing a custom indicator's public property in NT8 is:

```csharp
// In DEEP6Strategy.OnStateChange, State.Configure:
var footprint = DEEP6Footprint(/* params */);
AddChartIndicator(footprint);
// In DEEP6Strategy.OnBarUpdate:
var lastScore = footprint.LastScorerResult;
```

This assumes `DEEP6Footprint` is a `NinjaTrader.NinjaScript.Indicator` subclass (it is — confirmed by reading the file header). The strategy can hold a typed reference and call its public properties directly.

---

## DEEP6Strategy.EvaluateEntry Migration

### Current implementation (to be replaced) [VERIFIED: DEEP6Strategy.cs lines 405–466]

```csharp
private void EvaluateEntry(int barIdx, List<AbsorptionSignal> abs, List<ExhaustionSignal> exh, (double vah, double val) va)
{
    // Three hardcoded Tier-3 confluence rules:
    // (a) STACKED: ABS + EXH same direction, both str >= 0.5
    // (b) VA-EXTREME: abs at VAH/VAL with strength >= ConfluenceVaExtremeStrength
    // (c) WALL-ANCHORED: signal within N ticks of supportive wall, str >= 0.55

    if (trigger == null || direction == 0) return;

    // Risk gates called AFTER confluence check
    if (!RiskGatesPass(direction, signalPrice, trigger, barIdx)) return;
    EnterWithAtm(direction, atmTemplate, trigger, signalPrice);
}
```

### Replacement pattern [VERIFIED from CONTEXT.md locked decisions]

```csharp
private void EvaluateEntry(int barIdx, ScorerResult scored)
{
    if (scored == null) return;
    if (scored.Score < ScoreEntryThreshold) return;
    if ((int)scored.Tier < (int)MinTierForEntry) return;  // TypeA=3, TypeB=2, TypeC=1
    if (scored.Direction == 0) return;

    double entryPrice = scored.EntryPrice;  // from dominant signal's Price field
    string trigger = string.Format("SCORER_{0}_{1:F0}", scored.Tier, scored.Score);

    // RISK GATES — still evaluated before any order
    if (!RiskGatesPass(scored.Direction, entryPrice, trigger, barIdx)) return;
    EnterWithAtm(scored.Direction, AtmTemplateDefault, trigger, entryPrice);
}
```

**Legacy types:** `AbsorptionSignal` / `ExhaustionSignal` lists should be kept as compatibility wrappers on `DEEP6Strategy` until `EvaluateEntry` is fully cut over. Once the scorer replaces the hardcoded rules, these can be removed in a follow-up clean-up.

### NT8 property additions to DEEP6Strategy

```csharp
[NinjaScriptProperty]
[Display(Name="Score Entry Threshold", GroupName="DEEP6 Scorer", Order=1)]
public double ScoreEntryThreshold { get; set; } = 80.0;  // verbatim from Python type_a_min

[NinjaScriptProperty]
[Display(Name="Min Tier For Entry", GroupName="DEEP6 Scorer", Order=2)]
public SignalTier MinTierForEntry { get; set; } = SignalTier.TYPE_A;
```

### Risk gate position [VERIFIED: DEEP6Strategy.cs lines 490–550]

`RiskGatesPass` evaluates: AccountWhitelist (line 496), RTH window (line 503), news blackout (line 513), kill switch (line 528), max trades/session (line 535), daily loss cap (line 540). None of these touch scorer output. The scorer call must precede the risk gates in `OnBarUpdate`'s call order — but `EvaluateEntry` itself must call `RiskGatesPass` before `EnterWithAtm`, preserving the current guard structure.

---

## Scoring Parity Harness

### Phase 17 NDJSON sessions — coverage status [VERIFIED: ninjatrader/tests/fixtures/sessions/]

5 sessions exist: `session-01.ndjson` through `session-05.ndjson`. **These are minimal synthetic sessions, NOT live Rithmic captures.** The longest session has 22 lines total (session-01.ndjson: 5 bars, 10 DOM events). They do not produce the variety of signal combinations needed for meaningful scoring parity.

**Phase 18 must extend these sessions** to include bars that fire multiple signal categories so the scorer's TypeA/B/C outputs can be validated. Three approaches:
1. **Augment synthetic sessions** — add more bars to existing fixtures with explicit level data (bid/ask volume per level) that triggers absorption, imbalances, delta divergence.
2. **New synthetic scoring fixtures** — create dedicated scoring fixtures with known signal combinations and pre-computed expected scores (analogous to `tests/fixtures/absorption/*.json`).
3. **Live capture** — record a real NQ session using `CaptureHarness.cs` (blocked by Phase 17 Gap 3: no live captures exist yet, and strategy has CS0102 compile error).

**Recommendation:** Approach 2 (dedicated scoring fixtures) for the unit-test/fixture-level parity gate, plus Approach 1 (augmented sessions) for the session-replay parity gate. This mirrors the Python `tests/test_scorer.py` structure: hand-crafted scenarios with known expected outputs.

### Python subprocess pattern for parity harness [VERIFIED: CONTEXT.md specifics section]

CONTEXT.md specifies: `python3 -m deep6.scoring.replay_scorer` with NDJSON on stdin, JSON lines on stdout.

This script does not exist yet — it must be created as Wave 0 work. The interface:
- Stdin: NDJSON lines, one per bar (same format as existing `session-0N.ndjson` but extended with signal fields)
- Stdout: JSON lines, one per bar: `{"bar_index": N, "score": S, "tier": T, "narrative": "..."}`

```python
# deep6/scoring/replay_scorer.py (to be created in Wave 0)
import sys, json
from deep6.scoring.scorer import score_bar, SignalTier
# ... read NDJSON from stdin, score each bar, print JSON to stdout
```

### C# subprocess invocation [ASSUMED — standard .NET pattern, not verified in codebase]

```csharp
// In ScoringParityHarness NUnit test
var psi = new System.Diagnostics.ProcessStartInfo
{
    FileName = "python3",
    Arguments = "-m deep6.scoring.replay_scorer",
    WorkingDirectory = "/Users/teaceo/DEEP6",  // repo root
    RedirectStandardInput  = true,
    RedirectStandardOutput = true,
    UseShellExecute = false,
};
using var proc = System.Diagnostics.Process.Start(psi);
// write NDJSON to proc.StandardInput
// read scored JSON from proc.StandardOutput
proc.WaitForExit(timeoutMs: 30000);
```

**Environment path issue:** On macOS, `python3` may not be on the PATH available to `dotnet test` unless the test is run from a shell with the correct PATH. The test should fall back to checking `PYTHON3_PATH` env var, then `$(which python3)` if unresolved. Document this as a Wave 0 prerequisite.

### NUnit project target framework [VERIFIED: ninjatrader.tests.csproj from Phase 17 VERIFICATION.md]

The NUnit project uses `<TargetFramework>net8.0</TargetFramework>`. `System.Diagnostics.Process` is available in .NET 8. No additional NuGet packages needed for subprocess invocation.

---

## Phase 17 Inherited Bugs — Must Fix First

**These are BLOCKING for Phase 18.** Both must be resolved in Wave 0 before scorer work begins.

| Bug | Location | Impact | Fix |
|-----|----------|--------|-----|
| CS0102 duplicate `UseNewRegistry` | `DEEP6Strategy.cs` lines 698 + 805 | Strategy cannot load in NT8; all Phase 16/17 signals blocked live | Remove stale line 698 declaration; keep line 805 (`= true`, GroupName="DEEP6 Migration") |
| Double `_registry.EvaluateBar()` call | `DEEP6Strategy.cs` lines 334 + 384 | Stateful detectors advance rolling history twice per bar (DeltaDetector, TrapDetector queue bias) | Collapse to one EvaluateBar() call; use the returned `SignalResult[]` for both ABS/EXH extraction AND the new scorer |

---

## Architecture Patterns

### Recommended Project Structure for Phase 18 additions

```
ninjatrader/Custom/AddOns/DEEP6/
├── Scoring/
│   ├── ConfluenceScorer.cs       # Two-layer scorer (NEW)
│   └── NarrativeCascade.cs       # Narrative string assembly (NEW)
├── Registry/                     # Phase 17 (unchanged)
├── Detectors/                    # Phase 17 (unchanged)
└── Math/                         # Phase 17 (unchanged)

ninjatrader/Custom/Indicators/DEEP6/
└── DEEP6Footprint.cs             # Add HUD rendering + scorer invocation

ninjatrader/Custom/Strategies/DEEP6/
└── DEEP6Strategy.cs              # Fix bugs + add scorer-gated EvaluateEntry

ninjatrader/tests/
├── Scoring/                      # NEW — scorer unit tests
│   ├── ConfluenceScorerTests.cs
│   └── ScoringParityHarness.cs   # Python subprocess comparator
├── fixtures/
│   └── scoring/                  # NEW — scorer fixture scenarios
│       ├── type-a-all-categories.json
│       ├── type-b-no-zone.json
│       ├── type-c-suppressed.json
│       ├── quiet-zero-signals.json
│       └── midday-block.json
└── SessionReplay/
    └── fixtures/
        └── sessions/
            └── session-0[1-5].ndjson  # Extend with richer bar data
```

### ConfluenceScorer.cs public interface [VERIFIED design from Python scorer.py]

```csharp
// AddOns/DEEP6/Scoring/ConfluenceScorer.cs
namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    public sealed class ScorerResult
    {
        public double TotalScore;      // 0–100
        public SignalTier Tier;        // DISQUALIFIED=-1, QUIET=0, TYPE_C=1, TYPE_B=2, TYPE_A=3
        public int Direction;          // +1 / -1 / 0
        public double EngineAgreement; // 0–1
        public int CategoryCount;
        public double ConfluenceMult;  // 1.0 or 1.25
        public double ZoneBonus;       // 0, 4, 6, or 8
        public string Narrative;       // human-readable label
        public string[] CategoriesFiring;
    }

    public enum SignalTier { DISQUALIFIED = -1, QUIET = 0, TYPE_C = 1, TYPE_B = 2, TYPE_A = 3 }

    public static class ConfluenceScorer
    {
        public static ScorerResult Score(
            SignalResult[] signals,
            int barsSinceOpen,
            long barDelta,
            double barClose,
            // zone proximity omitted Phase 18 — default zone_bonus=0 until VPContext extended
            double vpocScore = 0.0,
            double vpocBot = 0.0,
            double vpocTop = 0.0);
    }
}
```

**VPContext note (from Phase 17 VERIFICATION.md):** `VPContextDetector.cs` in Phase 17 only implemented POC proximity — LVN/GEX deferred to Phase 18. Phase 18 must extend VPContextDetector to populate zone proximity data that the scorer can consume. Until that extension is complete, `zone_bonus = 0.0` is the safe default (TypeA cannot fire but scoring proceeds).

### Category derivation in C# from SignalResult[] [VERIFIED by mapping Python scorer to NT8 signal IDs]

```csharp
// Map SignalId prefixes + specific IDs to categories
var categoriesBull = new HashSet<string>();
var categoriesBear = new HashSet<string>();

foreach (var r in signals)
{
    if (r.Direction == 0) continue;
    var cats = r.Direction > 0 ? categoriesBull : categoriesBear;

    // absorption category
    if (r.SignalId.StartsWith("ABS")) cats.Add("absorption");

    // exhaustion category
    else if (r.SignalId.StartsWith("EXH")) cats.Add("exhaustion");

    // trapped category (TRAP-01 = inverse trap / IMB TRAP signals)
    else if (r.SignalId == "TRAP-01") cats.Add("trapped");

    // imbalance: stacked only — one vote per direction (highest tier wins, handled separately)
    // handle via stacked_bull_tier / stacked_bear_tier accumulator

    // delta: only these 5 types vote
    else if (r.SignalId == "DELT-04" || r.SignalId == "DELT-10" ||
             r.SignalId == "DELT-08" || r.SignalId == "DELT-06" ||
             r.SignalId == "DELT-05")
        cats.Add("delta");

    // auction: only 3 types vote
    else if (r.SignalId == "AUCT-01" || r.SignalId == "AUCT-02" || r.SignalId == "AUCT-05")
        cats.Add("auction");

    // poc: 5 types vote
    else if (r.SignalId == "POC-02" || r.SignalId == "POC-08" || r.SignalId == "POC-07")
        cats.Add("poc");
}
// Stacked imbalance dedup (D-02): accumulate max tier per direction, add one vote
// e.g. if both IMB-03-T1 and IMB-03-T3 fire bullish, only add "imbalance" once
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SharpDX text rendering | Custom text-drawing engine | Existing `_labelFont` + `TextLayout` + `DrawTextLayout` pattern in DEEP6Footprint.cs | Already working for GEX badge; identical pattern |
| JSON parsing in test | Custom string parser | Existing `CaptureReplayLoader` minimal field extractor, OR add `Newtonsoft.Json` (already available in NT8 AddOns) | Field extractor already handles NDJSON; scorer output is simpler |
| Python subprocess isolation | Thread pool + pipe management | `System.Diagnostics.Process` with `RedirectStandardInput/Output` | Standard .NET pattern; 30s timeout sufficient for test batch |
| Score formula precision | Custom floating-point rounding | Match Python double precision exactly; use `Math.Min` / `Math.Max` | Python uses `min(x, 100.0)` which maps directly to `Math.Min(x, 100.0)` |
| SignalTier as int comparison | Custom comparator | `(int)tier >= (int)SignalTier.TYPE_A` | IntEnum in Python maps to C# int-backed enum — same comparison works |

---

## Common Pitfalls

### Pitfall 1: TypeC category count is 4, not 3

**What goes wrong:** Reading the `ScorerConfig` docstring (`min_categories: int = 3`) and assuming TypeC fires at 3 categories. In the actual scorer code (line 485), TypeC requires `cat_count >= 4`.
**Why it happens:** `min_categories` in `ScorerConfig` is a legacy kwarg carried forward; the TypeC branch hardcodes `>= 4` since the optimization raising it from 3 (noted in the function docstring).
**How to avoid:** Port the actual code, not the docstring. Check every tier condition independently against scorer.py lines 472–488.

### Pitfall 2: Stacked imbalance dedup — only STACKED_T* types vote

**What goes wrong:** Assuming all IMB-* signals add to the "imbalance" category vote, inflating cat_count.
**Why it happens:** Python's scorer only votes on `STACKED_T1/T2/T3` types; single, oversized, diagonal, and consecutive imbalances are silently excluded.
**How to avoid:** Implement the `stacked_bull_tier / stacked_bear_tier` accumulator and only add "imbalance" category when `stacked_*_tier > 0`.

### Pitfall 3: Score is 0–100, HUD displays 0–1 signed

**What goes wrong:** Displaying raw `total_score` (e.g., `87.3`) as `+87.3` instead of the CONTEXT.md-specified `+0.87`.
**Why it happens:** CONTEXT.md says "Score: +0.87 (signed, 2 decimals)" implying normalized 0–1 scale.
**How to avoid:** In HUD rendering, divide `totalScore / 100.0` for display only. Internal logic uses the 0–100 range for threshold comparisons.

### Pitfall 4: Double EvaluateBar() bug from Phase 17

**What goes wrong:** If the double-call bug (lines 334 + 384 in DEEP6Strategy.cs) is not fixed, stateful detectors advance rolling histories twice, causing DeltaDetector's lookback windows to drift by 2x. Scorer output will systematically diverge from Python reference.
**Why it happens:** Phase 17 Wave 5 added a second EvaluateBar() call for "logging" without removing the first.
**How to avoid:** Fix the double-call bug in Wave 0 before any scorer work begins.

### Pitfall 5: Midday block silently changes TypeA to QUIET

**What goes wrong:** The midday block (bars 240–330) causes TypeA signals to become QUIET without any other visible change. Parity tests will fail if the C# scorer doesn't implement this block.
**Why it happens:** It's applied AFTER the tier classification, as a post-processing step in scorer.py lines 493–496.
**How to avoid:** Implement `if (tier != DISQUALIFIED && barsSinceOpen >= 240 && barsSinceOpen <= 330) tier = QUIET;` as the final step in tier classification.

### Pitfall 6: HUD badge renders at wrong Z position relative to GEX status badge

**What goes wrong:** Score HUD and GEX status badge overlap in top-right corner.
**Why it happens:** Both use `panelRight - N` anchoring to the same top-right position.
**How to avoid:** Render score HUD at `panelRight - 200` (narrower than GEX status at `panelRight - 384`). Or vertically offset the score HUD below the GEX status badge (~24px lower).

### Pitfall 7: SignalResult.Price field not populated for all signals

**What goes wrong:** `ScorerResult.EntryPrice` is undefined because not all `SignalResult` instances have a `Price` set.
**Why it happens:** `SignalResult.Price` defaults to `0.0` per `SignalResult.cs` comment ("Default 0.0 when not set").
**How to avoid:** In `ConfluenceScorer`, derive entry price from the dominant ABS or EXH signal's `Price` field. Fall back to `bar.Close` if no ABS/EXH signal fired.

---

## Code Examples

### GEX status badge pattern (verbatim from Phase 17 codebase) [VERIFIED: DEEP6Footprint.cs lines 1488–1509]

```csharp
// Existing pattern — score HUD follows same structure
float panelRight = (float)(ChartPanel.X + ChartPanel.W);
string hudLine1 = string.Format("Score: {0:+0.00;-0.00;+0.00}", _lastScorerResult.TotalScore / 100.0);
string hudLine2 = string.Format("Tier: {0}", TierChar(_lastScorerResult.Tier));
string hudLine3 = Truncate(_lastScorerResult.Narrative, 40);

using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                    hudLine1 + "\n" + hudLine2 + "\n" + hudLine3,
                                    _hudFont, 180f, 54f))
{
    RenderTarget.DrawTextLayout(
        new Vector2(panelRight - 192, (float)ChartPanel.Y + 28),  // below GEX status badge
        layout, _scoreHudTextDx);
}
```

### Score formula (verbatim port from Python) [VERIFIED: scorer.py lines 408–435]

```csharp
// C# verbatim port of Python scorer.py score formula
double baseScore = 0.0;
foreach (var cat in categoriesAgreeing)
{
    double w = GetCategoryWeight(cat);  // 25.0, 18.0, etc.
    baseScore += w;
}

double confluenceMult = categoriesAgreeing.Count >= 5 ? 1.25 : 1.0;
double totalScore = Math.Min(
    (baseScore * confluenceMult + zoneBonus) * agreement * ibMult,
    100.0
);

// VPIN modifier (Phase 18: vpinModifier = 1.0 always)
totalScore *= vpinModifier;  // 1.0 default
totalScore = Math.Max(0.0, Math.Min(100.0, totalScore));
```

### Existing Draw.Diamond usage (confirmed working) [VERIFIED: DEEP6Footprint.cs line 1321]

```csharp
// Existing neutral-direction diamond marker — already in codebase
Draw.Diamond(this, tag, false, barsAgo, s.Price, brush);

// TypeA extension (new):
string tag = "SCORE_A_" + barIdx + "_" + (direction > 0 ? "L" : "S");
Brush markerBrush = direction > 0 ? Brushes.Lime : Brushes.OrangeRed;
Draw.Diamond(this, tag, false, CurrentBar - barIdx, entryPrice, markerBrush);
```

---

## Runtime State Inventory

> Phase 18 is not a rename/refactor phase — no runtime state inventory required.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `dotnet test` | NUnit scorer tests | ✓ | net8.0 (verified Phase 17) | — |
| `python3` | Subprocess parity harness | ✓ | macOS system python3 (assume ≥3.10) | Set `PYTHON3_PATH` env var in test runner |
| NT8 installed | Live compile + integration test | ✗ (macOS) | — | Tests run via dotnet test without NT8 dependency (same pattern as Phase 17) |
| `deep6.scoring.scorer` importable | Python subprocess parity script | ✓ | Python package installed in repo | If not installed: `pip install -e .` from repo root |
| `ninjatrader/captures/*.ndjson` | Session-level parity | ✗ (no live captures) | — | Use augmented synthetic sessions; live captures deferred until NT8 runs on Windows with Rithmic |

**Missing dependencies with no fallback:**
- None that block Phase 18 completely.

**Missing dependencies with fallback:**
- Live NT8+Rithmic session captures — fallback is augmented synthetic sessions with rich bar data.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | NUnit 3.14.0 (.NET 8.0) |
| Config file | `ninjatrader/tests/ninjatrader.tests.csproj` |
| Quick run command | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "Category=Scoring" --nologo -v q` |
| Full suite command | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCOR-01 | Two-layer engine agreement + category confluence | unit | `dotnet test --filter "ScorerTest"` | ❌ Wave 0 |
| SCOR-02 | Confluence multiplier at 5+ categories = 1.25x | unit | `dotnet test --filter "ScorerTest_ConfluenceMult"` | ❌ Wave 0 |
| SCOR-03 | Zone bonus tiers (+8/+6/+4) | unit | `dotnet test --filter "ScorerTest_ZoneBonus"` | ❌ Wave 0 |
| SCOR-04 | TypeA/B/C/QUIET classification | unit | `dotnet test --filter "ScorerTest_Tier"` | ❌ Wave 0 |
| SCOR-05 (partial) | Midday block forces QUIET bars 240–330 | unit | `dotnet test --filter "ScorerTest_MiddayBlock"` | ❌ Wave 0 |
| SCOR-06 | Narrative label format matches Python | unit | `dotnet test --filter "ScorerTest_Label"` | ❌ Wave 0 |
| Parity D1 | Bit-for-bit score match on fixtures | unit | `dotnet test --filter "ScoringParityFixture"` | ❌ Wave 0 |
| Parity D2 | ±0.05 score envelope on 5 session replays | integration | `dotnet test --filter "ScoringParitySession"` | ❌ Wave 0 |
| Parity D3 | Risk gates still fire above scorer | smoke | `dotnet test --filter "RiskGateRegression"` | ❌ Wave 0 |
| Parity D4 | 180/180 existing Phase 17 tests still green | regression | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj` | ✅ existing |

### 4-Dimension Validation Plan (VALIDATION.md scope)

**D1 — Correctness (bit-for-bit on fixtures)**
- 5 hand-crafted JSON scoring fixtures (TypeA / TypeB / TypeC / QUIET / midday-block)
- C# `ConfluenceScorer.Score()` on each fixture must produce `score` within 0.0001 of Python `score_bar()` reference value
- `tier` must be identical enum value
- Run: `dotnet test --filter "ScoringParityFixture"` (new test class)

**D2 — Performance (µs per bar)**
- Scorer must complete in < 500µs per bar (signals are already computed; scoring is pure arithmetic)
- Measure via `System.Diagnostics.Stopwatch` in a tight 10,000-iteration benchmark inside a dedicated NUnit test
- HUD SharpDX rendering: no budget gate — OnRender is on the chart thread at display frame rate (~60fps), not the data thread

**D3 — Safety (risk gate regression)**
- Existing 180/180 Phase 17 NUnit tests must still pass (no regression from scorer additions)
- Specific gate: add a test that verifies `EvaluateEntry` does NOT submit an order when score < ScoreEntryThreshold even if signals fire
- `AccountWhitelist`, `RTH window`, `kill switch` paths must still pass their existing gate tests

**D4 — Completeness (≥5 session parity PASS)**
- 5 augmented synthetic sessions extended with bid/ask volume per level data
- Each session replayed through C# `ConfluenceScorer` AND Python `deep6.scoring.replay_scorer`
- Per-bar delta: `|csharp_score - python_score| <= 0.05`
- Per-bar tier verdict: identical (TypeA/B/C/QUIET must match exactly)
- Parity report committed as `18-PARITY-REPORT.md` in the phase directory

### Sampling Rate

- **Per task commit:** `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "Category=Scoring" --nologo -v q`
- **Per wave merge:** `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q` (full 180+ suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `ninjatrader/tests/Scoring/ConfluenceScorerTests.cs` — covers SCOR-01..06 + parity fixtures
- [ ] `ninjatrader/tests/Scoring/ScoringParityHarness.cs` — C#↔Python subprocess comparator
- [ ] `ninjatrader/tests/fixtures/scoring/type-a-all-categories.json` — TypeA scenario
- [ ] `ninjatrader/tests/fixtures/scoring/type-b-no-zone.json` — TypeB scenario
- [ ] `ninjatrader/tests/fixtures/scoring/type-c-suppressed.json` — TypeC suppressed by cat count
- [ ] `ninjatrader/tests/fixtures/scoring/quiet-zero-signals.json` — zero signals scenario
- [ ] `ninjatrader/tests/fixtures/scoring/midday-block.json` — bar 250 forced QUIET
- [ ] `deep6/scoring/replay_scorer.py` — Python subprocess entry point (reads NDJSON stdin, writes scored JSON stdout)
- [ ] Fix `DEEP6Strategy.cs` CS0102 duplicate `UseNewRegistry` (line 698 removal)
- [ ] Fix `DEEP6Strategy.cs` double `_registry.EvaluateBar()` call (lines 334 + 384 collapse)

---

## Security Domain

> This phase adds no new network calls, authentication, or sensitive data paths. The scorer is pure arithmetic operating on already-validated signal data. Security analysis: N/A for Phase 18.

---

## Open Questions

1. **VPContextDetector zone proximity for Phase 18 scorer**
   - What we know: Phase 17's `VPContextDetector.cs` only implements POC proximity; LVN/GEX zone proximity was explicitly deferred to Phase 18.
   - What's unclear: Does Phase 18 extend `VPContextDetector` with zone proximity output (enabling `zone_bonus > 0` and therefore TypeA), or does Phase 18 default `zone_bonus = 0.0` and only validate TypeB/TypeC parity?
   - Recommendation: Include a simple LVN zone proximity check in `VPContextDetector.cs` (emit a `ZONE-PROX` SignalResult when bar_close is inside a zone scoring >= 30). Without zone proximity, TypeA cannot fire — parity will trivially pass but the scorer will not demonstrate full TypeA behavior.

2. **synthetic session enrichment for scoring parity**
   - What we know: The 5 existing NDJSON sessions are minimal (5 bars, 10 DOM events, no bid/ask volume per level). They will not produce absorption or stacked imbalance signals when replayed.
   - What's unclear: Should Phase 18 replace these sessions with richer synthetics (risk: rewrites Phase 17 parity baseline), or create a separate `scoring-session-0[1-5].ndjson` set for the scoring parity harness?
   - Recommendation: Create a separate scoring session set under `ninjatrader/tests/fixtures/scoring/sessions/` that have full `cell.AskVol / BidVol` per level data and are designed to fire specific signal combinations. Do NOT modify the existing `fixtures/sessions/` files — those are the Phase 17 parity baseline.

3. **`Draw.Dot` availability and signature in NT8**
   - What we know: The codebase uses `Draw.Diamond`, `Draw.TriangleUp/Down`, `Draw.Text`, `Draw.ArrowUp/Down`. No `Draw.Dot` call exists anywhere in the project.
   - What's unclear: Whether NT8 8.x exposes `Draw.Dot` as a method on `NinjaScriptBase`, or whether the TypeC small-dot marker needs to be implemented differently (e.g., `Draw.Diamond` scaled down, or a SharpDX `FillEllipse` call in `OnRender`).
   - Recommendation: The planner should check NT8 documentation / NinjaTrader forum for `Draw.Dot` signature before committing to it. If unavailable, use `Draw.Diamond` for TypeC with a smaller price offset (so it visually reads as a smaller marker) or render TypeC as a 4px filled circle in `OnRender` using `RenderTarget.FillEllipse`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Draw.Dot` is a valid NT8 method matching `Draw.Diamond` signature | Draw APIs section | TypeC markers need alternative implementation (Draw.Diamond or FillEllipse) |
| A2 | DEEP6Strategy can access DEEP6Footprint's `LastScorerResult` via typed indicator reference held in Configure state | Strategy coupling section | May need to use a static shared class, a Plot series, or a different inter-object communication pattern |
| A3 | `python3` is on PATH when `dotnet test` runs (for subprocess parity harness) | Parity harness section | Test must fall back to `PYTHON3_PATH` env var; macOS zsh PATH may differ from subprocess PATH |
| A4 | Multi-line `TextLayout` with `\n` separators renders correctly in NT8's SharpDX DirectWrite | HUD rendering section | If not, create 3 separate `TextLayout` objects positioned at Y + 16px increments |

**All other critical claims in this research were verified directly from the codebase (`[VERIFIED: filename lines N-M]`).**

---

## Sources

### Primary (HIGH confidence — verified from codebase)

- `deep6/scoring/scorer.py` — complete scorer implementation, category weights, tier thresholds, formula
- `deep6/engines/signal_config.py` — `ScorerConfig` dataclass with all numeric constants
- `deep6/engines/narrative.py` — narrative cascade, label format, NarrativeResult structure
- `tests/test_scorer.py` — reference test scenarios (TypeA/B/C/QUIET, zone bonus tiers, stacked dedup)
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` lines 1295–1322 — confirmed Draw.* APIs
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` lines 1488–1509 — confirmed SharpDX HUD pattern
- `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` lines 405–466 — EvaluateEntry current implementation
- `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs` — SignalResult shape consumed by scorer
- `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — BarsSinceOpen field for IB/midday gates
- `ninjatrader/tests/SessionReplay/CaptureReplayLoader.cs` — NDJSON replay infrastructure to extend
- `ninjatrader/tests/fixtures/sessions/session-0[1-5].ndjson` — confirmed synthetic (not live Rithmic)
- `.planning/phases/17-nt8-detector-refactor-remaining-signals-port/17-VERIFICATION.md` — Phase 17 known gaps

### Tertiary (LOW confidence — marked [ASSUMED])

- `Draw.Dot` API availability in NT8 8.x — not verified in codebase, assumed from NT8 docs knowledge
- DEEP6Strategy typed indicator reference pattern — standard NT8 pattern, not verified for this specific code path
- Python subprocess PATH behavior on macOS with dotnet test — macOS convention, not codebase-verified

---

## Metadata

**Confidence breakdown:**

- Python scorer weights/thresholds: HIGH — read verbatim from source
- C# port architecture: HIGH — verified against existing Phase 17 patterns
- SharpDX HUD rendering: HIGH — confirmed pattern exists in DEEP6Footprint.cs
- Draw.* API signatures: HIGH for Diamond/Triangle/Text/Arrow; LOW for Dot
- Parity harness design: HIGH — CaptureReplayLoader infrastructure verified; subprocess pattern ASSUMED
- Session fixture status: HIGH — confirmed 5 minimal synthetic files, not live Rithmic captures

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable codebase; only invalidated by further Phase 18 commits)
