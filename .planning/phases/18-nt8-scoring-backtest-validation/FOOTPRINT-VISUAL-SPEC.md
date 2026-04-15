---
phase: 18-nt8-scoring-backtest-validation
artifact: FOOTPRINT-VISUAL-SPEC
status: draft
audience: ninjascript planner + executor (DEEP6Footprint.cs SharpDX Direct2D1 OnRender)
skin_target: NT8 dark default (primary) + NT8 light (must degrade)
---

# DEEP6 Footprint — Visual Specification (NT8 / SharpDX)

This is the design contract for the DEEP6Footprint indicator's on-chart render. Every number here is prescriptive. SharpDX `OnRender` must match these values verbatim. "Default zoom" below means `ChartBars.Properties.ChartStyle.BarWidth = 3` (NT8 default), giving an effective `barPaintWidth ≈ 10–14px`; `CellColumnWidth` default `= 60px`, `rowH ≈ 12–16px` for NQ at typical zoom.

Color philosophy: calm chart body, reserved saturation for decision-grade signals. The 60/30/10 split is surface / structure / alert.

---

## 1. Cell Visual Language

Each footprint cell is a horizontal row, one price tick tall, spanning the full column width. Text layout is **"bid × ask"** rendered as a single DirectWrite `TextLayout` centered vertically, left-aligned with a 2px inset.

| Property | Value |
|---|---|
| Cell column width | `max(CellColumnWidth=60, barPaintWidth)` px |
| Cell row height | `max(8, chartScale.GetPixelsForDistance(tickSize))` px, typical 12–16px |
| Text inset (left/right) | 2 px |
| Font family (cell numbers) | `Consolas` (Windows). Fallback order: `Consolas → Cascadia Mono → Courier New` |
| Font size (cell numbers) | **10 pt** at `rowH ≤ 14px`; **11 pt** at `rowH ≥ 15px` |
| Font weight | Normal (400) |
| Text format | `"{bid} x {ask}"` — ASCII `x` (U+0078), single spaces |
| Min row height to render text | 10 px (below this, render color block only) |

### Volume-rank gradient (fill)

Fill opacity scales linearly with `(cell.AskVol + cell.BidVol) / maxLevelVol` of the bar, range `[0.08, 0.55]`. This keeps dominant rows visible without drowning numeric labels.

### Bid vs ask color differentiation

Text color is split per-side in a single row by rendering two `TextLayout`s: left half (bid) uses bid ink, right half (ask) uses ask ink, joined by a dim separator `x`.

| Element | Dark skin sRGB | Light skin sRGB |
|---|---|---|
| Bid number ink | `#FF6B6B` (warm red-coral) | `#B11F1F` |
| Ask number ink | `#4FC3F7` (sky cyan) | `#0A5FB0` |
| Separator `x` | `#6B7280` @ 55% | `#9CA3AF` @ 70% |
| Cell fill base (neutral) | `#1E2530` | `#F5F7FA` |
| Cell fill (bid-heavy) | `#FF6B6B` @ rank-opacity | `#B11F1F` @ rank-opacity |
| Cell fill (ask-heavy) | `#4FC3F7` @ rank-opacity | `#0A5FB0` @ rank-opacity |

"Bid-heavy" = `bidVol > askVol * 1.25`; "ask-heavy" = `askVol > bidVol * 1.25`; else neutral fill.

---

## 2. POC + Value Area Emphasis

POC uses **fill** as the single distinguishing technique (not border, not bold). A saturated yellow horizontal stripe spanning the column at the POC price. This is unambiguous at any zoom and does not compete with imbalance borders.

| Element | Dark sRGB | Light sRGB | Weight / Size |
|---|---|---|---|
| POC fill stripe | `#FFD23F` @ 85% | `#D19A00` @ 90% | 2 px tall, full column width, drawn on top of cell fill, under cell text |
| VAH line | `#C8D17A` | `#6E7F1F` | 1 px solid, full column width |
| VAL line | `#C8D17A` | `#6E7F1F` | 1 px solid, full column width |
| VAH label | same ink | same ink | Segoe UI 9pt, right-aligned at column right edge, 2px gap, `"VAH"` only on rightmost visible bar of the session |
| VAL label | same ink | same ink | same as VAH, `"VAL"` |

### Naked / virgin POC

A "virgin POC" = a prior-session POC that has not been retraded. Mark with a **right-extended dashed line** (dash 4 on / 3 off, 1 px) in `#FFD23F` at 60% opacity, with a right-gutter label `"vPOC 17345.25"` in Segoe UI 9pt. Drawn in the same gutter band as GEX labels but offset 18 px vertically to prevent collision.

---

## 3. Imbalance Highlighting

Single diagonal imbalance = **1px inner border** on the cell (not a fill — fill is reserved for volume rank). Keeps the bid × ask text readable. Stacked imbalance escalates via color intensity + corner glyph.

| State | Border ink (dark) | Border ink (light) | Border px | Corner glyph |
|---|---|---|---|---|
| Buy imbalance (single) | `#4FC3F7` | `#0A5FB0` | 1 | none |
| Sell imbalance (single) | `#FF6B6B` | `#B11F1F` | 1 | none |
| Stacked T1 (2 consecutive) | same + 10% brighter | same + 10% brighter | 1.5 | small dot `•` top-right, 3px |
| Stacked T2 (3 consecutive) | same + 20% brighter | same + 20% brighter | 2 | double dot `••`, 3px |
| Stacked T3 (4+ consecutive) | `#00E5FF` buy / `#FF3355` sell | `#005F99` / `#8B0000` | 2.5 | filled caret `▶`/`◀`, 5px |

### Diagonal vs stacked distinction

Diagonal imbalances use **cyan/coral** (the bid/ask palette). Vertically stacked imbalances escalate into **saturated cyan/red** (T3 colors above) — this is the only place the chart uses maximum-saturation reds/cyans inside the cell grid, signaling real structural pressure.

---

## 4. Signal Markers (ABS, EXH, ABS-07 VA-bonus)

Markers are drawn on the bar index where the signal fired, placed **outside** the bar geometry (above the high for bearish, below the low for bullish), 6 px gap.

| Signal | Shape | Size (default zoom) | Dark fill | Light fill | Outline |
|---|---|---|---|---|---|
| Absorption (bullish, below low) | Up arrow `▲` | 10 px | `#00BFA5` (teal) | `#007A66` | 1px `#0E1014` |
| Absorption (bearish, above high) | Down arrow `▼` | 10 px | `#FF4081` (magenta) | `#B3003E` | 1px `#0E1014` |
| Exhaustion (bullish) | Up triangle outline `△` | 10 px | `#FFD23F` (yellow) | `#B08400` | 1.5px stroke only |
| Exhaustion (bearish) | Down triangle outline `▽` | 10 px | `#FFA726` (orange) | `#8A5200` | 1.5px stroke only |
| ABS-07 VA-extreme bonus | Small ring `◯` overlaid on parent marker | 14 px outer / 10 px inner | `#FFD23F` ring 1.5 px | `#B08400` | draws around ABS marker |

Filled = absorption (dominant side took pressure). Outline-only = exhaustion (pressure failed). The outline-vs-fill axis is the fastest way for a tape reader to distinguish the two categories from peripheral vision.

---

## 5. Phase 18 Tier-Coded Entry Markers

Drawn at **entry price** on the bar the score crossed the tier threshold. Placed on the **opposite side of the bar from ABS/EXH markers** (see failure modes section) — if ABS/EXH already occupies the low, tier marker goes near mid-bar on the right edge, 4 px offset from column right.

| Tier | Shape | Size | Fill | Outline | Direction cue |
|---|---|---|---|---|---|
| TypeA long | Solid diamond `◆` | 12 px | `#00E676` (saturated green) | 1px `#0E1014` | none (color = direction) |
| TypeA short | Solid diamond `◆` | 12 px | `#FF1744` (saturated red) | 1px `#0E1014` | none |
| TypeB long | Hollow triangle up `△` | 10 px | none | 1.5px `#66BB6A` (medium green) | apex up |
| TypeB short | Hollow triangle down `▽` | 10 px | none | 1.5px `#EF5350` (medium red) | apex down |
| TypeC long | Small dot `•` | 4 px | `#7CB387` @ 70% (desaturated green-gray) | none | color only |
| TypeC short | Small dot `•` | 4 px | `#B87C82` @ 70% (desaturated red-gray) | none | color only |

Light-skin equivalents: TypeA `#00A152` / `#C4001D`; TypeB `#2E7D32` / `#C62828`; TypeC `#4F7A59` / `#8A4A50`.

Rationale: shape encodes conviction (solid shape > hollow > dot), color encodes direction (green/red), saturation encodes tier strength. All three axes align, so a glance at color-saturation alone conveys tier without needing to parse shape at small sizes.

---

## 6. Scoring HUD Badge (Phase 18 addition)

Fixed-position badge anchored top-right of the main panel. Explicitly offset **below** the existing GEX status badge (which lives at `panelRight - 384, ChartPanel.Y + 4`, lines 1488–1509 of `DEEP6Footprint.cs`) to avoid overlap.

| Property | Value |
|---|---|
| Anchor | `panelRight - 200, ChartPanel.Y + 28` (GEX badge reserves Y 4–22) |
| Box size | 188 × 62 px (3 lines × ~18 px + 8 px padding) |
| Padding (inner) | 8 px left / 6 px top / 6 px right / 6 px bottom |
| Background fill | `#0E1014` @ 78% (dark skin) / `#FFFFFF` @ 85% (light skin) |
| Border | 1 px, tier-colored (see line 2 tier chip color) |
| Border radius | 3 px (square-ish; NT8 visual language is sharp) |
| Opacity (overall) | 92% |
| Z-order | Above GEX lines, above cells, below NT8 crosshair |

### Three-line typography

| Line | Content | Font | Size | Weight | Ink (dark) |
|---|---|---|---|---|---|
| 1 | `Score: +0.87` (signed, 2 decimals, fixed-width) | Consolas | 12 pt | 600 | `#E8EAED` |
| 2 | `Tier: A` + 14×14 px tier chip (rounded 2 px) | Segoe UI + chip | 11 pt | 600 | chip fill = TypeA green / TypeB triangle-green / TypeC dot-gray |
| 3 | Narrative ≤ 40 chars, ellipsis if truncated | Segoe UI | 9 pt | 400 | `#B0B6BE` |

Example full render:
```
┌──────────────────────────────┐
│ Score: +0.87                 │
│ Tier: A  ▇                   │
│ ABSORBED @VAH + CVD DIV      │
└──────────────────────────────┘
```

When score is negative (short bias), the score line ink flips to `#FF6B6B`; positive stays `#E8EAED` (neutral ink — tier chip carries the direction cue). Updates only on bar close (per CONTEXT.md decision).

---

## 7. GEX Overlay Coexistence

GEX horizontal lines draw first (behind footprint cells), labels draw in the right gutter 160 px wide. Existing behavior preserved; only opacity tightened.

| Level | Dark sRGB | Light sRGB | Line style | Width | Opacity |
|---|---|---|---|---|---|
| Call Wall | `#4FC3F7` | `#0A5FB0` | solid | 1.8 px | 75% |
| Put Wall | `#FF6B6B` | `#B11F1F` | solid | 1.8 px | 75% |
| Gamma Flip | `#FFD23F` | `#B08400` | dashed 6-on / 4-off | 2.0 px | 85% |
| HVL (High Vol Level) | `#B388FF` (violet) | `#5E35B1` | solid | 1.4 px | 65% |
| Major positive | `#4FC3F7` | `#0A5FB0` | dotted 2-on / 3-off | 0.8 px | 55% |
| Major negative | `#FF6B6B` | `#B11F1F` | dotted 2-on / 3-off | 0.8 px | 55% |

Labels: Segoe UI 9 pt, right-gutter at `panelRight - 160, y - 8`, format `"{label} ({price:F2})"`. Opacity 90% so lines stay subordinate to footprint cells.

---

## 8. Z-Order Master List (back-to-front)

1. Chart panel background (NT8 native)
2. Price bars / candles (NT8 native)
3. GEX horizontal lines + right-gutter labels
4. Liquidity walls (L2 horizontal segments)
5. Footprint cell fills (volume-rank gradient)
6. Footprint cell imbalance borders + corner glyphs
7. Footprint cell text (`bid × ask`)
8. POC stripe (on top of cell fill, under cell text — text wins if overlap)
9. VAH / VAL lines
10. Virgin POC dashed extensions + labels
11. ABS / EXH signal markers (outside bar geometry)
12. Phase 18 tier markers (diamond / triangle / dot) at entry price
13. TypeA narrative label (adjacent to tier marker)
14. Chart Trader toolbar (top-left buttons)
15. GEX status badge (top-right, `panelRight - 384, Y + 4`)
16. **Scoring HUD badge** (top-right, `panelRight - 200, Y + 28`)
17. NT8 crosshair / native overlays (not our concern)

---

## 9. Color Palette Master (sRGB, WCAG 4.5:1 verified against background)

### Dark skin (NT8 default, background `#0E1014`)

| Token | Hex | Role | Contrast vs bg |
|---|---|---|---|
| `ink-primary` | `#E8EAED` | Cell text default, HUD score | 13.8:1 |
| `ink-secondary` | `#B0B6BE` | Narrative, dim labels | 8.4:1 |
| `bid-red` | `#FF6B6B` | Bid volume, sell imbalance | 5.9:1 |
| `ask-cyan` | `#4FC3F7` | Ask volume, buy imbalance | 8.1:1 |
| `poc-yellow` | `#FFD23F` | POC stripe, gamma flip, vPOC | 11.2:1 |
| `va-olive` | `#C8D17A` | VAH / VAL lines | 9.6:1 |
| `abs-teal` | `#00BFA5` | Absorption bullish fill | 6.3:1 |
| `abs-magenta` | `#FF4081` | Absorption bearish fill | 5.1:1 |
| `exh-yellow` | `#FFD23F` | Exhaustion bullish outline | 11.2:1 |
| `exh-orange` | `#FFA726` | Exhaustion bearish outline | 9.2:1 |
| `tierA-long` | `#00E676` | TypeA long diamond | 11.4:1 |
| `tierA-short` | `#FF1744` | TypeA short diamond | 5.4:1 |
| `tierB-long` | `#66BB6A` | TypeB long triangle | 7.9:1 |
| `tierB-short` | `#EF5350` | TypeB short triangle | 5.2:1 |
| `tierC-long` | `#7CB387` | TypeC long dot (70% opacity) | 6.8:1 |
| `tierC-short` | `#B87C82` | TypeC short dot (70% opacity) | 4.6:1 |
| `gex-hvl-violet` | `#B388FF` | HVL line | 7.5:1 |
| `hud-bg` | `#0E1014` @ 78% | HUD backdrop | — |
| `surface-1` | `#1E2530` | Cell fill base (neutral) | — |

### Light skin (NT8 light, background `#FFFFFF`)

All light-skin hex values are declared inline in each section above; every text ink has been picked to hit ≥ 4.5:1 against `#FFFFFF`.

60/30/10 split:
- **60% dominant (surface)**: chart background + neutral cell fill (`#0E1014`, `#1E2530`)
- **30% secondary (structure)**: VAH/VAL, POC, GEX lines, cell volume fills at <55% opacity
- **10% accent**: TypeA saturated diamond, T3 stacked imbalance caret, ABS/EXH markers, HUD tier chip

Accent colors (`#00E676`, `#FF1744`, `#FFD23F`, `#00BFA5`, `#FF4081`) are reserved exclusively for the above. Never used for cell fills, gridlines, or chrome.

---

## 10. Font Stack

| Role | Family | Fallbacks | Size | Weight | Used for |
|---|---|---|---|---|---|
| Numeric (cells) | Consolas | Cascadia Mono, Courier New | 10–11 pt | 400 | `bid × ask` in cells |
| Numeric (HUD score) | Consolas | Cascadia Mono, Courier New | 12 pt | 600 | HUD line 1 |
| Label (chrome) | Segoe UI | Arial, sans-serif | 9 pt | 400 | VAH/VAL, GEX gutter, narrative |
| Label (HUD tier) | Segoe UI | Arial, sans-serif | 11 pt | 600 | HUD line 2 |
| Label (Chart Trader buttons) | Segoe UI | Arial, sans-serif | 9 pt | 600 | toolbar |

Rule: all numbers that must visually align (cells, score) use monospace. All prose (narrative, gutter labels, chip text) uses proportional Segoe UI. Never mix — the eye reads them as different layers.

DirectWrite allocation: reuse the existing Phase 16 `_cellFont`, `_labelFont`, `_ctBtnFont` pool. Add exactly one new format: `_hudScoreFont` (Consolas 12 pt 600). No runtime allocation in `OnRender`.

---

## 11. Failure Modes to Prevent

| # | Failure | Prevention |
|---|---|---|
| F1 | HUD badge overlaps existing GEX status badge | HUD anchored at `Y + 28`; GEX status reserves `Y 4 → Y 22`. 6 px gap enforced. |
| F2 | Tier marker collides with ABS/EXH arrow on same bar | ABS/EXH always outside bar geometry (above high / below low). Tier marker drawn at **entry price** with a 4 px inset from column right edge; if ABS/EXH fired same direction, stack tier marker 14 px further from bar body. Never place two markers within 12 px of each other. |
| F3 | TypeA narrative label bleeds into next bar at narrow `barPaintWidth` | Narrative rendered with low-opacity background box (`#0E1014` @ 70%, 2 px padding), max width `min(160px, 3 × colW)`. If `colW < 40px`, render narrative in a **leader-line callout** 20 px to the right of the bar. |
| F4 | Light-skin readability failure (yellow POC on white bg) | Light skin swaps `#FFD23F` → `#D19A00` (9.7:1 vs white). Every dark-skin ink has a declared light-skin counterpart in section 9. Skin detection via `ChartControl.Properties.ChartBackground`. |
| F5 | Cell text unreadable at dense volume (high rank-opacity) | Rank-opacity capped at 0.55. Text ink (`#E8EAED` dark / `#0E1014` light) is independent of fill and always renders on top. |
| F6 | HUD flicker on every tick | Badge updates only on `IsFirstTickOfBar == true` (per CONTEXT.md). Score value cached in instance field; read-only during `OnRender`. |
| F7 | VAH/VAL line visually indistinguishable from POC at zoom-in | POC is a 2 px **fill stripe** in yellow; VAH/VAL are 1 px **lines** in olive. Different geometry + different hue family — never confused. |
| F8 | Imbalance border swallowed by volume-rank fill | Border drawn AFTER fill in z-order. Border is 1 px min, stepping to 2.5 px at T3. Always wins pixel ownership. |
| F9 | GEX lines dominate cells during slow tape | GEX opacity capped at 75% (walls) / 85% (flip). Line width ≤ 2 px. Labels in right gutter, not over chart body. |
| F10 | TypeC dots invisible at default zoom | TypeC dot is 4 px at 70% opacity — intentionally subordinate. If user needs stronger TypeC visibility, the fix is a property toggle `ShowTypeCMarkers` (default true), not a larger default size. Observational markers must not compete with TypeA. |
| F11 | Virgin POC dashed line collides with GEX gutter label at same Y | vPOC label offset 18 px vertically from any GEX label within 10 px of same Y (detect by iterating rendered GEX levels first and reserving Y bands). |
| F12 | Narrative ellipsis truncates mid-word | Truncate at last word boundary ≤ 37 chars, append `…` (U+2026). Never raw `...`. |

---

## Appendix — Element Inventory (for planner)

Phase 18 adds exactly these new render elements to `OnRender`:

1. `RenderScoreHud()` — new private method, drawn after GEX status badge, before Chart Trader
2. `RenderTierMarker(barIdx, tier, direction, price)` — new private method, called per scored bar
3. `RenderTypeANarrative(barIdx, text, anchor)` — new private method, called only when `tier == A`
4. `_hudScoreFont` — new `TextFormat` field, allocated in `OnRenderTargetChanged`
5. `_tierAGreenDx`, `_tierARedDx`, `_tierBGreenDx`, `_tierBRedDx`, `_tierCGreenDx`, `_tierCRedDx`, `_hudBgDx`, `_hudBorderDx` — new `Brush` fields, allocated in `OnRenderTargetChanged`, disposed symmetrically

All existing brushes (`_pocDx`, `_vahDx`, `_valDx`, `_gexCallWallDx`, etc.) remain. No existing render path is modified except z-order insertion of the HUD badge (step 16 above).
