---
phase: 11.3
round: R6
type: design-retrospective
date: 2026-04-13
status: proposed
subject: FootprintRenderer — Numbers Bar redesign
supersedes: Phase 11.2 Plan 03 (volume-bar / gradient-wing renderer)
---

# Footprint Chart Redesign — R6: Numbers Bar

> Reason for this document: after five rounds of visual polish the trader-operator reviewed the chart and said *"the charts still look crazy, maybe a different way through graphic design."* That one sentence closes the door on the gradient-wing renderer lineage and opens the Numbers Bar path.

---

## 1. Why the Redesign

The Phase 11.2 Plan 03 renderer and its three subsequent refinement passes (R1 depth pass, R2 polish pass, R3 enrichment pass) produced a visually ambitious footprint using proportional bid/ask wings with gradient tapers, bloom effects on imbalance cells, CVD markers, and a heavy-volume row tint. It was technically correct and individually coherent. It was also — for a practicing trader accustomed to Sierra Chart, ATAS, or Bookmap — *unreadable at speed*.

The core problem: **a novel visual language forces cognitive translation.** Every time the trader looks at the chart, their brain must re-learn the grammar. Professional traders spend years building muscle memory on numbers-based footprints. Wings require a perceptual mapping step that numbers bypass entirely. When trading NQ at speed with 44 signals competing for attention, that extra step is cost they will not pay.

The user's feedback was not "make the wings prettier." It was "maybe a different way through graphic design." That is a signal to reboot the visual approach entirely, not polish the existing one.

---

## 2. What Was Replaced

The gradient-wing renderer (introduced in Plan 03, iterated through R1–R3) had these characteristics:

- Per-row bid/ask bars extending from a centerline — proportional to `vol / maxVolume` — resembling Bookmap's vertical histogram style
- Gradient taper at bar edges for a softened-shadow appearance
- Bloom filter on imbalance cells (`imbalanceRatio ≥ 3.0×`)
- Stacked imbalance run: lime vertical line across consecutive imbalanced rows
- Delta footer below each bar (bid/ask split bar + numeric delta label)
- CVD dot marker on the POC row
- Bar header with timestamp and mini bid/ask split bar at large zoom levels

All of this was graphically dense but *organic* — the information was encoded in shape and color rather than numbers. Three full iteration rounds could not resolve the fundamental illegibility concern, because the issue was the encoding paradigm, not the rendering quality.

---

## 3. What It Was Replaced With

**Sierra/ATAS-style Numbers Bar** — the industry-standard footprint representation used by every major professional order-flow platform.

Each row of a bar shows two numbers in a cell, formatted as:

```
┌─────────────────────────────────┐
│  247 × 89                       │  ← bid × ask at this price level
│   12 × 380                      │
│   55 × 61                       │  ← neutral (no imbalance)
└─────────────────────────────────┘
```

Cell background color carries imbalance and context:

```
┌──────────────────────────────────────────────┐
│  247 × 89   ← RED bg: bid > 3× ask           │
│   12 × 380  ← GREEN bg: ask > 3× bid         │
│   55 × 61   ← AMBER bg: POC (max volume row) │
│   18 × 22   ← grey shade: neutral            │
└──────────────────────────────────────────────┘
```

The text is `text-xs` (11px) JetBrains Mono 400, `font-variant-numeric: tabular-nums`. Numbers are right-aligned (bid) and left-aligned (ask) within their half-cell. The `×` separator is fixed at the cell center.

---

## 4. Why This Works Better

**Instantly readable — numbers do not require interpretation.** A trader who has used Sierra Chart for two years looks at `247 × 89` and immediately knows what happened. No mapping from wing length to volume. No calibration for "how long is a big wing in this zoom level." The number is the information.

**Respects trader muscle memory.** Every major professional platform — Sierra Chart, ATAS, Bookmap, Jigsaw — uses numbers-based footprint cells as the default view. The visual grammar is universal. DEEP6 adopts the grammar rather than proposing a new one.

**Information density without visual noise.** In the wings renderer, a bar at low zoom became a mass of colored shapes. In the Numbers Bar, every row is always readable at any zoom level above the minimum row height (16px). The information degrades gracefully: at tight zoom the numbers disappear before the cell backgrounds do, so you still see imbalance from color even when individual values are too small to read.

**Colors carry secondary signal without competing with primary.** In the wings renderer, color was also encoding volume magnitude (through opacity and gradient). That meant color was doing double duty: both "how much volume" and "is this imbalanced." In the Numbers Bar, the *number* carries the magnitude and *color* carries only the imbalance/POC semantic. Each channel has exactly one job.

---

## 5. Chart Mode Selector

The redesign introduces a mode selector widget on the footprint chart panel. Three modes:

| Mode | Status | Description |
|---|---|---|
| **Numbers Bar** | Default / active | Sierra/ATAS-style numeric cells with imbalance background |
| **Wings** | Retained | The gradient-wing renderer from Phase 11.2/R1–R3 — preserved for users who prefer it |
| **Heatmap** | Stub (future) | Bookmap-style continuous color heatmap; no numbers |

The Wings mode is preserved for two reasons: first, some traders genuinely prefer visual encoding; second, it represents three rounds of careful rendering work that should not be discarded entirely. The mode toggle is a `<Select>` in the footprint panel header, persisting per-session in `localStorage` under key `deep6.footprintMode`.

---

## 6. Key Code Paths

### Where numbers get drawn

`dashboard/lib/lw-charts/FootprintRenderer.ts` — the `draw()` method, per-bar inner loop.

For each price level in a bar, the renderer:
1. Computes the cell's top/bottom Y coordinates from the LW Charts price axis
2. Splits the cell width into left half (bid) and right half (ask), with 2px gutters from the `×` separator
3. Fills the cell background with the imbalance or POC color (or a grey tone derived from `totalVol / maxTotalVol`)
4. Calls `ctx.fillText(bidVol, bidHalfRight - 2, cellCenterY)` right-aligned in the bid half
5. Calls `ctx.fillText(askVol, askHalfLeft + 2, cellCenterY)` left-aligned in the ask half

### How colors are decided

Per-row color resolution happens in a single function `cellBackground(bidVol, askVol, totalVol, maxTotal, isPOC)`:

```
if isPOC                          → C_AMBER
else if askVol / bidVol >= 3.0    → C_ASK  (green, buy imbalance)
else if bidVol / askVol >= 3.0    → C_BID  (red, sell imbalance)
else                              → grey interpolated by totalVol / maxTotal
```

Imbalance cells render at 100% opacity; neutral cells render at an opacity of `0.15 + 0.45 * (totalVol / maxTotal)` (so high-volume neutral rows are darker grey than low-volume ones).

The stacked imbalance run detector (3+ consecutive same-direction cells) is a post-pass over the per-bar cell array, drawing a vertical lime line on the imbalance side after all cells are rendered.

---

## 7. Future Work

**Cluster / profile variations.** A common extension to the Numbers Bar is the "cluster footprint" (ATAS terminology) — grouping multiple price levels per cell when zoomed out, so each cell shows `bid×ask` for a range of ticks (e.g., one cell per point instead of one cell per tick). The renderer already supports variable row heights; the grouping logic needs a `clusterSize` option in `FootprintSeriesOptions`.

**Per-trader mode persistence.** The mode toggle currently persists to `localStorage`. For multi-session replay and multi-user deployments (Phase 12+ backend), mode preference should migrate to the user profile API and be loaded from there on mount. The `localStorage` key `deep6.footprintMode` is the migration source.

**Smooth-transition animations when switching modes.** Currently, toggling from Numbers Bar to Wings mode is an immediate canvas clear + re-render. A cross-fade via `ctx.globalAlpha` decay (500ms, 16ms rAF steps) would make the transition feel deliberate rather than abrupt. This is purely cosmetic — defer until after the Numbers Bar stabilizes under live load.

**Volume profile coloring.** The sidebar volume profile currently uses a single-color histogram. In the Numbers Bar context, splitting each profile bar into bid (left, `--bid`) and ask (right, `--ask`) portions provides the same decomposition as the cell view — showing *where* buyers vs sellers dominated across the session at a glance. The data is already available in `BarAccumulator`; only the render call needs updating.
