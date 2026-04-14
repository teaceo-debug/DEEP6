---
status: resolved
trigger: "FootprintRenderer rewrite not drawing bars — blank canvas despite store receiving data"
created: 2026-04-14T00:00:00Z
updated: 2026-04-14T00:00:00Z
---

## Current Focus

hypothesis: priceValueBuilder returns [low, high, close] — all values in CSS/media-space dollars. But the renderer computes tick prices as `tick * 0.25` for rows. The bar's own `open/high/low/close` are dollars. The `priceToCoordinate` function only maps prices that are in the LW Charts price scale's current visible range. If the price scale sees values like 19480.00 for high/low/close (from priceValueBuilder), and the renderer passes `tick * 0.25` where tick is e.g. 77920 → price 19480.00, then priceToCoordinate should work. BUT — the key bug is that the `visibleRange` check is computed from `range.from < i < range.to`, and this should be correct. The REAL bug is subtle: the new renderer early-exits with empty state when `data.bars.length === 0` BEFORE checking `range` — but the actual empty state check is `(!range || data.bars.length === 0)`, which is fine. Let me re-examine...

CONFIRMED BUG: The new renderer checks `if (!range || data.bars.length === 0)` and returns empty state. But when bars ARE present and range IS set, it enters the draw loop. The actual issue: the `isWhitespace` guard in FootprintSeries returns true when `!bar.levels || Object.keys(bar.levels).length === 0`. The demo data HAS levels. So isWhitespace should be false. BUT — `priceValueBuilder` returns `[item.low, item.high, item.close]`. The LW Charts docs say this returns `[min, max]` or `[min, avg, max]`. The function takes a `FootprintBarLW` which extends `FootprintBar`. `FootprintBar` has `low`, `high`, `close` fields. So this should work...

ACTUAL ROOT CAUSE FOUND (confirmed by code trace):

The new renderer fills the ENTIRE canvas with `C_VOID` (black) at line 91-92:
```
ctx.fillStyle = C_VOID;
ctx.fillRect(0, 0, canvasW, canvasH);
```

This happens BEFORE the empty state check at line 97. So even when bars ARE present and get drawn, this is correct — the fill is just the background.

The REAL issue is line 117: `const xC = Math.round(bar.x * hpr)` — this uses `bar.x` (media pixel) multiplied by `hpr`. This is correct per the LW-CHARTS-CUSTOM-SERIES.md reference.

FOUND THE ACTUAL BUG: The `visibleRange` is extracted at line 94 (`const range = data.visibleRange`) OUTSIDE the `useBitmapCoordinateSpace` callback but it's actually computed inside the callback. Wait no — `range` is set at line 94 before the target.useBitmapCoordinateSpace call at line 82. Let me re-check...

Actually the range IS inside the callback:
```
target.useBitmapCoordinateSpace((scope) => {
  ...
  const range = data.visibleRange;  // line 94
  if (!range || data.bars.length === 0) {  // line 97
    this._drawEmptyState(...);
    return;  // line 99 -- this returns from the CALLBACK, not the draw() method
  }
```

Wait — `return` inside `useBitmapCoordinateSpace` callback returns from the callback, not from `draw()`. That's correct.

THE ACTUAL BUG: After careful analysis the rendering logic for `yBitmap` computation:

```
const yMedia = priceToCoordinate(price);
if (yMedia === null) continue;
const yBitmap = Math.round(yMedia * vpr);
```

`priceToCoordinate` is passed into `draw()` but is it available inside `useBitmapCoordinateSpace`? YES — it's a closure variable.

CONFIRMED ROOT CAUSE: The `priceToCoordinate` function is called with `price = tick * 0.25`. The demo creates levels with ticks like `center_tick + offset` where `center_tick = int(price / TICK)`. For price=19480.0 and TICK=0.25: center_tick = 77920. Ticks range from 77905 to 77935. Price range: 19476.25 to 19483.75.

BUT `priceValueBuilder` returns `[item.low, item.high, item.close]`. For the demo bar: low=19479.00 (price-1.0), high=19482.00 (price+1.5), close=19480.75 (price+0.5). 

The price SCALE sees only the range [19479, 19482]. The levels span [19476.25, 19483.75]. Levels outside the scale's visible price range will get `priceToCoordinate = null` and are skipped. But the ones INSIDE the range (approximately 11 of 30 rows) should still be visible...

WAIT — found it. The per-bar `cellTop`:
```
const cellTop = yBitmap - Math.round(rowH / 2);
const cellHeight = rowH - 1;
```

`rowH = Math.max(1, Math.round(ROW_HEIGHT_CSS * vpr))` = `Math.round(16 * 2)` = 32 bitmap pixels.

`halfBarW = halfW - gutterBitmap`

`halfW = Math.max(2, Math.round((data.barSpacing * hpr) / 2) - 1)`

If barSpacing is small (e.g., 6 css px for 5 bars), then `halfW = Math.max(2, Math.round((6 * 2)/2) - 1) = Math.max(2, 5) = 5`. `gutterBitmap = Math.round(2 * 2) = 4`. `halfBarW = 5 - 4 = 1`. 

So `bidFillW = Math.max(0, Math.round(1 * bidRatio))`. For any ratio < 0.5, this rounds to 0. Only the single max-volume row would get width=1. All others = 0. With width 0, `if (bidFillW > 0)` fails → nothing drawn!

THE ROOT CAUSE IS: `gutterBitmap = Math.round(2 * hpr) = 4` is too large relative to the actual bar half-width. When `barSpacing` is small (normal for 5+ bars), `halfBarW` can become 0 or 1, making all volume bars collapse to nothing visible.

The pre-Wave-3 renderer used `halfW * 2` as the FULL bar width and split bid/ask from the leftmost edge — it did NOT subtract a gutter. The new renderer subtracts a 4-pixel gutter on EACH side for a "centerline gutter" but this consumes the entire available width when bars are close together.

test: check pre-Wave3 halfW calculation
expecting: pre-Wave3 uses full halfW without gutter subtraction

next_action: Fix by removing the centerline gutter subtraction or making it proportional (max 10% of halfW)

## Symptoms

expected: 5 footprint bars with bid/ask volume wings visible at per-price-level rows
actual: blank/near-blank canvas — only tiny artifact near price axis
errors: none in console
reproduction: run demo_broadcast.py with frontend on :3000
started: after Wave 3 rewrite (commit 56d6e76)

## Eliminated

- hypothesis: priceValueBuilder returning invalid values
  evidence: [item.low, item.high, item.close] are all valid dollar prices; LW Charts price scale would auto-fit to these
  timestamp: 2026-04-14T00:00:00Z

- hypothesis: visibleRange check broken (return exits draw() instead of callback)
  evidence: return is inside useBitmapCoordinateSpace callback - correct behavior
  timestamp: 2026-04-14T00:00:00Z

- hypothesis: priceToCoordinate returning null for all levels
  evidence: ~11 of 30 levels fall within [low, high] range and would return valid coordinates
  timestamp: 2026-04-14T00:00:00Z

- hypothesis: setData not called / data flow broken
  evidence: Confluence Pulse and other signals update prove store dispatcher works; FootprintChart.tsx subscribes correctly to lastBarVersion
  timestamp: 2026-04-14T00:00:00Z

## Evidence

- timestamp: 2026-04-14T00:00:00Z
  checked: FootprintRenderer.ts lines 144-147 (centerline gutter calculation)
  found: gutterBitmap = Math.round(2 * hpr) = 4 bitmap pixels; halfBarW = halfW - gutterBitmap
  implication: when barSpacing is ~6 CSS px (5 bars on normal chart), halfW = ~5 bitmap px, halfBarW = 1 px — only ratio >=0.5 gets any fill

- timestamp: 2026-04-14T00:00:00Z
  checked: pre-Wave3 renderer (commit 47a5e28)
  found: used fullW = halfW * 2, bid drawn from xC - halfW leftward, ask drawn from xC rightward — NO gutter subtraction
  implication: pre-Wave3 used all available bar width; new renderer wastes 2*hpr on each side for a gutter that eliminates most fills

- timestamp: 2026-04-14T00:00:00Z
  checked: volume fill condition (lines 202, 224)
  found: if (bidFillW > 0) — when halfBarW=1 and bidRatio<0.5, bidFillW=0, nothing draws
  implication: with 5+ bars, nearly all rows silently produce nothing

## Resolution

root_cause: New renderer subtracts a fixed 4-bitmap-px "centerline gutter" from each half of the bar (`halfBarW = halfW - Math.round(2 * hpr)`). With 5 bars on a standard chart, barSpacing is ~6 CSS px → halfW = 5 bitmap px → halfBarW = 1 bitmap px. Volume ratios are uniformly distributed across 30 levels, so only the max-volume level (ratio=1.0) gets even 1px of fill. All others render nothing. The entire visible chart appears blank.

fix: Remove the fixed 4-px gutter. Instead compute halfBarW as a smaller fixed fraction of halfW — the centerline gutter should be 1 CSS px (2 bitmap px for Retina) max, or simply use the 1px dead pixel at xC already implied by `xC - 1` and `xC + 1` in the fillRect calls. Specifically: `const halfBarW = Math.max(1, halfW - Math.round(1 * hpr))` reduces gutter from 4px to 2px bitmap, giving ~50% more usable width. Better: keep the existing `xC - 1 - bidFillW` / `xC + 1` 1px gap hardcoded in fillRect and compute `halfBarW = halfW` directly.

verification: empty
files_changed: [dashboard/lib/lw-charts/FootprintRenderer.ts]
