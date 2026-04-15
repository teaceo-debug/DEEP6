---
artifact: 03-SPATIAL-LAYOUT
target: NinjaTrader 8 — DEEP6Footprint + DEEP6GexLevels
coordinate_system: NT8 ChartPanel (origin top-left; X,Y,W,H in device-independent px)
skin: dark primary / light degrade
source_of_truth_for: OnRender anchor math, collision ordering, chart-size breakpoints
consumed_by: planner (phase tasks), executor (SharpDX layout code), ui-auditor
---

# DEEP6 Chart — Spatial Layout & Zone Blueprint

This spec defines every pixel of real estate on the DEEP6Footprint / DEEP6GexLevels rendered chart panel. It supersedes ad-hoc anchor math scattered across `DEEP6Footprint.cs OnRender` (line 1123 onward). Every zone, every collision, every breakpoint is declared here so the executor never guesses.

All coordinates are in ChartPanel space: `(0,0)` is the top-left of the chart panel, `(ChartPanel.W, ChartPanel.H)` is the bottom-right. Where this spec says `right = panelRight`, that means `ChartPanel.X + ChartPanel.W`. Where it says `bottom = panelBottom`, that means `ChartPanel.Y + ChartPanel.H`.

---

## 1. Chart Panel Zone Map

Default reference panel: 1920 × 1080 window → ChartPanel ≈ `1760 × 900` after NT8 workspace chrome.

```
panelLeft                                                            panelRight
+--------------------------------------------------------------------+
| TOOLBAR                                            GEX_BADGE       |  <- Y+4  (row 1)
| (x=+8, y=+4, w=520, h=36)                       (w=384, h=18)      |
|                                                    SCORE_HUD       |  <- Y+28 (row 2)
|                                                 (w=200, h=62)      |
|                                                                    |
|  LEFT_GUTTER  +--- CENTER: price + footprint cells ---+ RIGHT_GUT   |
|  (NT8 native) |                                       | (x=panel-  |
|  w=56         |  main data region                     |  Right-140,|
|               |  x = panelLeft + 56                   |  w=140)    |
|               |  y = panelTop + 44                    |            |
|               |  w = panelRight - 56 - 140            |  - PDH     |
|               |  h = panelBottom - 44 - 28            |  - PD POC  |
|               |                                       |  - VAH/VAL |
|               |  [footprint cells + bid x ask]        |  - PW POC  |
|               |  [POC stripe, VAH, VAL]               |  - nPOC    |
|               |  [imbalance borders]                  |  - GEX lbl |
|               |  [ABS/EXH/TypeA/B/C markers]          |            |
|               |  [TypeA narrative callout]            |            |
|               |                                       |            |
|               |                                       |            |
|               +---------------------------------------+            |
|                                                                    |
|        +------+ CLICK_DETAIL_MODAL +------+  (shown on click only)  |
|        | centered: x = (panelW-520)/2     |                         |
|        |          y = (panelH-360)/2      |                         |
|        | w=520 h=360                      |                         |
|        +----------------------------------+                         |
|                                                                    |
|  BOTTOM_GUTTER  (NT8 native time axis, h=28)                       |
+--------------------------------------------------------------------+
```

### Zone coordinate table

| Zone | Code Owner | x | y | w | h |
|------|------------|---|---|---|---|
| TOOLBAR | `RenderChartTraderToolbar()` | `panelLeft + 8` | `panelTop + 4` | `min(520, ctButtons*56+gaps)` | 36 |
| GEX_BADGE (conditional) | `RenderGexStatusBadge()` in DEEP6GexLevels | `panelRight - 384` | `panelTop + 4` | 384 | 18 |
| SCORE_HUD | `RenderScoreHud()` | `panelRight - 200` | `panelTop + 28` | 200 | 62 |
| LEFT_GUTTER | NT8 native price scale (left-side) | `panelLeft` | `panelTop + 44` | 56 | `panelH - 72` |
| CENTER | cell/marker/POC render loop | `panelLeft + 56` | `panelTop + 44` | `panelW - 56 - 140` | `panelH - 72` |
| RIGHT_GUTTER | `RenderProfileAnchors()` + GEX labels | `panelRight - 140` | `panelTop + 44` | 140 | `panelH - 72` |
| BOTTOM_GUTTER | NT8 native time axis | `panelLeft` | `panelBottom - 28` | `panelW` | 28 |
| CLICK_DETAIL_MODAL | `RenderClickDetail()` | centered | centered | 520 | 360 |

GEX_BADGE is **conditional**: only rendered if `DEEP6GexLevels` indicator is also loaded on the same panel. When absent, SCORE_HUD slides up into the row 1 slot (`y = panelTop + 4`) so top-right chrome budget stays ≤ 90px vertical.

---

## 2. Z-Order Master List (back-to-front)

Draw order is the law. Each call to SharpDX happens in this sequence:

| # | Layer | Code Path | Opacity |
|---|-------|-----------|---------|
| 1 | Chart panel background | NT8 native `ChartControl.Properties.ChartBackground` | 100% |
| 2 | Grid lines (vertical + horizontal) | NT8 native | 100% |
| 3 | Price bars (candles/OHLC) | NT8 native | 100% |
| 4 | GEX horizontal lines | `DEEP6GexLevels.RenderLevels()` | 55–85% (per level type) |
| 5 | Prior-day / prior-week range shading | `RenderProfileAnchors()` rect fills | 10–15% |
| 6 | Liquidity walls (L2 horizontal segments) | `DrawWallsForSide()` | 60% |
| 7 | Naked / virgin POC dashed extensions | `RenderVirginPocs()` | 60% |
| 8 | VAH / VAL lines | inside cell loop | 100% |
| 9 | Footprint cell fills (volume-rank gradient) | cell render loop | 8–55% |
| 10 | POC stripe (2px yellow fill) | cell render loop | 85% |
| 11 | Imbalance borders + corner glyphs | cell render loop | 100% |
| 12 | Cell text `bid × ask` | cell render loop | 100% |
| 13 | Profile-anchor labels (PDH / PDL / PD POC / PW POC / VAH / VAL) | `RenderProfileAnchors()` labels | 90% |
| 14 | GEX right-gutter labels | `DEEP6GexLevels.RenderLabels()` | 90% |
| 15 | ABS / EXH markers (outside bar geometry) | `RenderSignalMarkers()` | 100% (100% current bar, 70% bars -1..-3) |
| 16 | Phase 18 tier markers (◆ / △ / •) | `RenderTierMarker()` | 100% / 70% decay |
| 17 | TypeA narrative callout label | `RenderTypeANarrative()` | 92% (low-op bg box) |
| 18 | TOOLBAR (Chart Trader button strip) | `RenderChartTraderToolbar()` | 100% |
| 19 | GEX_BADGE | `RenderGexStatusBadge()` | 92% |
| 20 | SCORE_HUD | `RenderScoreHud()` | 92% |
| 21 | CLICK_DETAIL_MODAL (when active) | `RenderClickDetail()` | 96% (drop-shadow 2px y-offset, 20% black) |
| 22 | NT8 crosshair + native overlays | NT8 native | 100% |

The modal is the only layer that dims everything beneath it: when active, layers 1–20 render under a 40% black scrim (drawn at layer 20.5).

---

## 3. Collision Rules

Every pair of elements that can occupy the same pixels has an explicit winner.

| Pair | Rule |
|------|------|
| TOOLBAR vs GEX_BADGE | Toolbar always at left (`x = panelLeft + 8`), badge always at right (`x = panelRight - 384`). Minimum 16px gap required at panel widths ≥ 920px; below that, see breakpoints §4. |
| GEX_BADGE vs SCORE_HUD | HUD is anchored exactly 6px below GEX_BADGE (`y = panelTop + 28`). Vertical exclusion zone `Y 4 → Y 22` reserved for GEX; `Y 28 → Y 90` reserved for HUD. Never overlap. |
| SCORE_HUD vs TOOLBAR | HUD right-anchored, toolbar left-anchored. If `panelW < 920`, HUD drops to icon-only badge (see §4). |
| PDH label vs PD POC label (Δprice ≤ 3 ticks) | Stacking algorithm: render higher-priced label at natural Y; render lower-priced label at Y + 9px; draw 1px `#6B7280` 40% connector line from label anchor back to the tick price. Apply recursively for 3+ labels within 3-tick cluster. |
| PD POC vs PW POC at same price | PD POC wins visibility; PW POC hidden (absorbed into PD POC label as suffix: `"PD/PW POC 17345.25"`). |
| Naked POC line vs active VAH line | Naked POC drawn first (layer 7, 60% opacity), VAH on top (layer 8, 100%). If they intersect at the same tick, VAH wins — naked POC label suppressed at that bar, line continues dashed behind VAH. |
| TypeA tier marker vs ABS marker same bar same direction | ABS stays outside bar geometry (above high / below low). Tier marker stacks 14px further out from bar body (so a bullish ABS below the low + bullish TypeA long → ABS at `low - 6`, TypeA at `low - 20`). Minimum 12px between any two markers. |
| TypeA tier marker vs EXH marker same bar | EXH is outline-only, tier marker is solid fill. Tier marker wins pixel ownership if overlap; EXH outline drawn last so its stroke remains visible over the tier fill. |
| TypeA narrative vs RIGHT_GUTTER level labels | Narrative renders in CENTER zone only. `narrativeMaxX = panelRight - 140 - 8` = 8px pad before gutter. If `narrativeAnchorX + narrativeWidth > narrativeMaxX`, rewrap as leader-line callout pointing back to the bar (20px horizontal leader, label aligned right-justified at narrativeMaxX). |
| Cell `bid × ask` text vs POC stripe | POC stripe at layer 10, text at layer 12. Text always wins. |
| Cell imbalance border vs volume-rank fill | Border at layer 11, fill at layer 9. Border always wins. |
| Click-detail modal vs everything | Modal + scrim (layer 20.5 + 21) dims all prior layers to 40% brightness. Crosshair (layer 22) still renders above modal — user can still see the tick they're inspecting. |
| Virgin POC label vs GEX gutter label (same Y ± 10px) | Iterate GEX labels first, reserve their Y bands. vPOC label offsets +18px Y from nearest reserved band. |

---

## 4. Responsive Breakpoints

Single-stage degradation based on `ChartPanel.W`. Check on every `OnRender` (cheap — integer compare).

| panelW range | Toolbar | SCORE_HUD | Right gutter | Modal |
|--------------|---------|-----------|--------------|-------|
| ≥ 1600px | Full labeled buttons (up to 520px wide) | 200×62 with 3-line narrative | 140px wide, all label classes | 520×360 centered |
| 1200–1599px | Full labeled buttons | 200×62, narrative truncated to 32 chars | 140px, suppress composite VA (show only VAH, hide VAL if redundant) | 520×360 |
| 800–1199px | Icon-only buttons, 40px each | Stacked below GEX with narrative hidden (40×62 → 200×42, 2 lines) | 120px wide, drop PW POC labels, keep PDH/PDL/PD POC/active VAH/VAL/active nPOCs | 480×320 |
| 600–799px | Hamburger menu (40×36), expands on click | Icon-only score pill: `+0.87 [A]` (80×22) | 100px wide, active nPOCs + PD POC only | Full-width: `panelW - 32`, h = 320, top-anchored at `y=60` |
| < 600px | Hamburger only | Hidden entirely (tooltip on hover over hamburger shows score) | Hidden; levels still drawn as lines without labels | Full width, full height minus toolbar |

Breakpoints are evaluated off ChartPanel.W only; ChartPanel.H does not trigger chrome changes (cells just get fewer price ticks of range).

---

## 5. Real-Estate Budget

The cardinal rule: CENTER zone (price + footprint cells + markers) must occupy **≥ 75%** of ChartPanel visible area at `panelW ≥ 1200`. Every chrome element has a hard max and is enforced by the zone table in §1.

| Element | Max dims | Budget notes |
|---------|----------|--------------|
| TOOLBAR | 520 × 36 | Grows with button count: `(n × 56 + (n-1) × 4)`. Cap at 520, overflow → hamburger. |
| GEX_BADGE | 384 × 18 | Fixed. Text: `"GEX: OK | 12 levels | 17:04 UTC"`. |
| SCORE_HUD | 200 × 62 | Fixed at ≥1200. Shrinks per §4. |
| RIGHT_GUTTER labels | 140 wide × per-label 14 tall | Total gutter occupancy ≤ 140 × panelH. |
| LEFT_GUTTER | 56 wide | NT8 native — we do not own. |
| BOTTOM_GUTTER | panelW × 28 | NT8 native. |
| CLICK_DETAIL_MODAL | 520 × 360 | Ephemeral. Max 1 instance active. |
| TypeA narrative label | 160 × 20 | Max. Low-opacity bg box, 2px padding. |
| ABS / EXH / tier markers | 14 × 14 | Max per marker. |

At 1760×900 reference: CENTER = (1760 − 56 − 140) × (900 − 44 − 28) = 1564 × 828 = 1,294,992 px² out of 1,584,000 = **81.7%**. Budget holds.

At 1000×600: CENTER = (1000 − 56 − 120) × (600 − 44 − 28) = 824 × 528 = 435,072 / 600,000 = **72.5%** — below target, which is why breakpoint 800–1199 compresses the HUD and right gutter.

---

## 6. Empty States

| State | Behavior |
|-------|----------|
| No signals fired this session | SCORE_HUD visible with score=0.00 on line 1, line 2 = `Tier: —` with neutral gray chip, line 3 = `"SCANNING"` in `#6B7280`. Never hide the HUD — absence-of-signal is itself information. |
| DEEP6GexLevels indicator not loaded | GEX_BADGE hidden entirely. SCORE_HUD promotes to row 1 slot: `y = panelTop + 4`. GEX-related right-gutter labels absent. No placeholder. |
| < 10 RTH sessions of history (PW POC warming up) | PW POC label hidden. PD POC label suffixed with `" (PW warming 7/10)"` in `#B0B6BE`. TOOLBAR shows a small yellow dot on the leftmost 4px of its status bar until warmup completes. |
| Pre-market / overnight session (ETH) | PDH, PDL, PD POC, prior VAH/VAL all drawn at 50% opacity. Active session levels (today's developing POC/VAH/VAL) unchanged. GEX_BADGE shows `"GEX: ETH (stale 4h)"` in `#B0B6BE` if last refresh > 1 hour old. |
| No L2 depth subscription | Liquidity walls layer hidden silently. SCORE_HUD line 3 shows `"L2 OFFLINE"` in coral `#FF6B6B`. |
| Chart paused (NT8 data connection lost) | All chrome renders at 60% opacity. NT8 native "disconnected" badge takes precedence (layer 22). |

---

## 7. Transition States

NT8 `Draw*` primitives are not animated, but per-render opacity changes persist bar-to-bar and produce step animations:

| Event | Visual transition |
|-------|-------------------|
| New TypeA signal fires | Marker renders at 100% on bar of fire. Next 3 bars: 85%, 75%, 70%. Bars beyond: steady 70%. Transition triggered by `barsAgo` delta computed each OnRender. |
| New ABS / EXH fires | Same decay curve: 100% → 85% → 75% → 70%. |
| Naked POC is retested (price trades through it) | Fade from 60% to 40% over next 2 bars: 50%, 40%. Dashed style changes to dotted. Label suffix appends `" (retested)"`. After 5 more bars, line removed entirely. |
| Session boundary crossed (RTH open, RTH close, new trading day) | Prior levels snap from "live" class (100%) to "prior day" class (70%) on the first OnRender after boundary crossed. Label prefixes mutate: `"POC"` → `"PD POC"`, `"VAH"` → `"PD VAH"`. No smooth fade — step change. |
| Score crosses tier boundary (B → A) | HUD border hex changes on next OnRender. No animation; hard swap. Tier chip fill also swaps. |
| Modal opened / closed | Scrim layer appears at 40% opacity in one render frame. NT8 doesn't give us sub-frame interpolation, so closure is also instant. |

---

## 8. Scrollback Behavior

When the user scrolls back N bars (`ChartBars.FromIndex` changes), the layout must preserve historical accuracy:

| Element | Scrollback behavior |
|---------|---------------------|
| PDH / PDL / PD POC / PD VAH / PD VAL | **Absolute** — each bar knows which session it belongs to. Prior-day anchors for a historical bar are drawn from that bar's prior-day context, not today's. Requires per-session snapshot store (already partially implemented in `RenderProfileAnchors()` line 1277). |
| Active developing POC / VAH / VAL | **Re-computed** from visible range of current session only. If scrollback puts the current developing session off-screen, these lines are not drawn. |
| SCORE_HUD | **Always shows most-recent bar's score**, regardless of scroll position. HUD is a "now" indicator, not a replay. |
| Historical tier markers (TypeA / B / C) | Drawn at their original fire-bar index. Opacity frozen at 70% (no further decay). |
| Historical ABS / EXH markers | Same — frozen at 70% after 3-bar decay elapsed. |
| Naked POC history | All naked POCs from last **N = 20** RTH sessions remain drawn even when scrolled back, provided their price is within visible range. When scrolled into a period that predates a given naked POC's creation, it is hidden (can't exist before it was formed). |
| GEX lines | Drawn only for dates where GEX snapshot is cached. If scrollback enters a date with no cached GEX data, lines hidden, right-gutter labels show `"GEX: no data"` in `#6B7280`. |
| Click-detail modal on past marker | Clicking any historical TypeA/B/C/ABS/EXH marker opens modal showing the **snapshot HUD at the time of fire** (score, tier, narrative, contributing signals) plus the bar's OHLCV + footprint cell summary. Snapshot is recovered from the phase-18 scored-bar database, not recomputed. If snapshot unavailable: modal shows `"Historical snapshot not available (bar predates scoring system)"`. |

Scrollback should not cause HUD flicker: HUD updates are gated on `IsFirstTickOfBar` for the current bar only. Scrolling back does not re-trigger HUD renders.

---

## Appendix — Implementation Anchors

For the executor, the existing `DEEP6Footprint.cs` anchors that must be refactored to match this spec:

- Line 1123: `panelRight = ChartPanel.X + ChartPanel.W` — keep.
- Line 1223–1224: toolbar anchor `(+8, +8)` — change to `(+8, +4)` to match row 1 Y.
- Line 1356: GEX label anchor `(panelRight - 160, y - 8)` — update to `panelRight - 140` to match 140px gutter.
- Line 1435: wall label anchor `(panelRight - 184, y - 8)` — also update to `panelRight - 140`.
- GEX_BADGE (in DEEP6GexLevels) anchor `(panelRight - 384, Y + 4)` — add conditional check: if DEEP6Footprint is also loaded, confirm SCORE_HUD will live at `Y + 28`.
- New: `RenderScoreHud()` must compute anchor as:
  ```
  float hudY = gexLevelsLoaded ? (panelTop + 28) : (panelTop + 4);
  float hudX = panelRight - hudWidth;  // hudWidth per §4 breakpoint
  ```
- New: Modal handler (click-detail) registers via existing `ChartControl.MouseDown` wiring (already referenced at line 1248).

---

## LAYOUT COMPLETE

**File:** `/Users/teaceo/DEEP6/.planning/design/ninjatrader-chart/03-SPATIAL-LAYOUT.md`

**Top-3 collision rules (executor must not violate):**

1. **GEX_BADGE vs SCORE_HUD** — HUD anchored at `Y = panelTop + 28` with 6px gap below GEX_BADGE (`Y 4–22`). When DEEP6GexLevels is absent, HUD promotes to `Y = panelTop + 4`. Never overlap.
2. **TypeA tier marker vs ABS/EXH on same bar same direction** — ABS/EXH stays adjacent to bar geometry (6px gap). Tier marker stacks 14px further from bar body. Minimum 12px between any two markers. Never co-locate.
3. **TypeA narrative vs right-gutter level labels** — Narrative `maxX = panelRight - 140 - 8`. If overflow, rewrap as right-justified leader-line callout. Narrative never bleeds into the 140px right gutter.
