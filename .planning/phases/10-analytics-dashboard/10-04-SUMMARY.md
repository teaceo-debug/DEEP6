---
phase: 10-analytics-dashboard
plan: 04
subsystem: ui
tags: [lightweight-charts, footprint-chart, custom-series, canvas, react, nextjs, orderflow]

requires:
  - phase: 10-analytics-dashboard
    plan: 02
    provides: Next.js shell, Zustand store (useLiveStore), WS client infrastructure
  - phase: 10-analytics-dashboard
    plan: 03
    provides: LiveTab layout with footprint-chart-mount div, RegimePanel, SignalFeed

provides:
  - FootprintSeriesPlugin: ICustomSeriesPaneView v5.1 custom series rendering bid/ask cells per price level
  - FootprintData / FootprintOptions / FootprintLevel TypeScript interfaces
  - chart-overlays.ts: addZoneOverlays() for LVN/HVN/absorption/exhaustion bands + GEX dashed lines
  - FootprintChart.tsx: mounted React component with ResizeObserver + dynamic(ssr:false)
  - LiveTab.tsx: replaces placeholder div with live FootprintChart component

affects: [10-analytics-dashboard, phase-11-live-feed, phase-5-backtest]

tech-stack:
  added:
    - "lightweight-charts 5.1.0 (already installed) — custom series via addCustomSeries()"
    - "fancy-canvas (LW Charts peer dep) — CanvasRenderingTarget2D + BitmapCoordinatesRenderingScope"
  patterns:
    - "ICustomSeriesPaneView pattern: plugin class + renderer class separation"
    - "useBitmapCoordinateSpace for retina-correct canvas drawing (pixelRatio scaling)"
    - "anchor series + createPriceLine for horizontal overlay bands (no area series needed)"
    - "dynamic(ssr:false) for any component using ResizeObserver or canvas"
    - "addZoneOverlays() returns cleanup function — call in useEffect return"

key-files:
  created:
    - dashboard/src/lib/footprint-series.ts
    - dashboard/src/lib/chart-overlays.ts
    - dashboard/src/components/FootprintChart.tsx
  modified:
    - dashboard/src/components/LiveTab.tsx

key-decisions:
  - "ICustomSeriesPaneView<UTCTimestamp, FootprintData, FootprintOptions>: FootprintOptions extends CustomSeriesOptions (required by LW Charts generic constraint) via spread of customSeriesDefaultOptions"
  - "CanvasRenderingTarget2D imported from fancy-canvas (peer dep) not from lightweight-charts — LW Charts declares it locally but does not export it"
  - "Overlay strategy: anchor series (invisible LineSeries) + createPriceLine per band edge — simpler than area series, no data needed"
  - "addZoneOverlays() returns cleanup function instead of series refs array — encapsulates removeSeries loop, safer on chart destroy"
  - "stale .next Turbopack cache caused false TS error on pre-existing files — cleared with rm -rf .next; build clean"

patterns-established:
  - "Pattern: LW Charts custom series plugin = ICustomSeriesPaneView wrapper + ICustomSeriesPaneRenderer with update()/draw() — renderer holds data/options, plugin holds renderer"
  - "Pattern: pixelRatio = bitmapSize.width / mediaSize.width inside useBitmapCoordinateSpace — all canvas coords multiplied by this"
  - "Pattern: effectiveBarSpacing = conflationFactor * barSpacing for correct bar width in draw()"

requirements-completed: [DASH-06]

duration: 22min
completed: 2026-04-14
---

# Phase 10 Plan 04: Footprint Chart Summary

**LW Charts v5.1 custom series footprint plugin rendering bid/ask volume cells per price level with LVN/HVN/GEX zone overlays, mounted in the LIVE tab via dynamic SSR-safe import**

## Performance

- **Duration:** 22 min
- **Started:** 2026-04-14T00:40:00Z
- **Completed:** 2026-04-14T01:02:50Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `FootprintSeriesPlugin` implements all 4 required `ICustomSeriesPaneView` methods (`priceValueBuilder`, `isWhitespace`, `renderer`, `update`, `defaultOptions`) — full LW Charts v5.1 compliance
- `FootprintSeriesRenderer.draw()` uses `priceConverter(price)` for y-coordinates (not hardcoded pixels), bid cells on left half (blue #2563eb), ask cells on right half (red #dc2626), POC amber outline, TYPE_A amber glow, volume text labels when cell wide enough
- `addZoneOverlays()` supports LVN (gray), HVN (blue), absorption (red), exhaustion (orange) bands + GEX call wall (green dashed), put wall (red dashed), gamma flip (amber dashed), HVL (purple dashed) — all via `createPriceLine` on invisible anchor series
- `FootprintChart.tsx` mounts with `createChart()`, seeds 5 demo NQ bars via `generateDemoBars()`, applies GEX/LVN/HVN demo overlays, and cleans up ResizeObserver + overlay series + chart on unmount (T-10-10 mitigated)
- `LiveTab.tsx` replaces placeholder div with `<FootprintChart />` via `dynamic(() => import('./FootprintChart'), { ssr: false })` — required for ResizeObserver/canvas browser APIs

## Task Commits

1. **Task 1: Footprint custom series plugin** - `9d70582` (feat)
2. **Task 2: Chart overlays + FootprintChart + LiveTab** - `dbd4879` (feat)

## Files Created/Modified

- `dashboard/src/lib/footprint-series.ts` — ICustomSeriesPaneView plugin: FootprintSeriesPlugin + FootprintSeriesRenderer, FootprintData/FootprintOptions/FootprintLevel exports
- `dashboard/src/lib/chart-overlays.ts` — addZoneOverlays() helper: LVN/HVN/absorption/exhaustion bands + GEX dashed lines via createPriceLine
- `dashboard/src/components/FootprintChart.tsx` — React component: createChart + addCustomSeries + seed data + ResizeObserver + cleanup
- `dashboard/src/components/LiveTab.tsx` — replaced footprint-chart-mount placeholder with dynamic FootprintChart import

## Decisions Made

- `FootprintOptions` extends `CustomSeriesOptions` (required by LW Charts generic `TSeriesOptions extends CustomSeriesOptions` constraint) and spreads `customSeriesDefaultOptions` in `defaultOptions()` to satisfy the full `SeriesOptionsCommon` shape.
- `CanvasRenderingTarget2D` imported from `fancy-canvas` (LW Charts peer dep) not from `lightweight-charts` — LW Charts declares it locally but does not re-export it, causing TS2459 if imported from there.
- Overlay approach: invisible `LineSeries` anchor + `createPriceLine()` per band edge. Simpler than area series (no time data required). Cleanup via returned function calling `chart.removeSeries()`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Stale .next Turbopack cache reporting false TS errors**
- **Found during:** Task 2 (build verification)
- **Issue:** `npm run build` reported TS errors in `ParamImportanceChart.tsx` at line 120 with a function signature that didn't match the current file content — stale Turbopack cache showing old compiled output
- **Fix:** `rm -rf .next` then rebuilt clean — build passed with zero errors
- **Files modified:** none (cache deletion)
- **Verification:** `npm run build` exits 0, TypeScript finished cleanly
- **Committed in:** dbd4879 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — stale cache)
**Impact on plan:** Cache issue was environmental, no code changes required. Build is clean.

## Issues Encountered

- LW Charts v5.1 changed from `chart.addLineSeries()` to `chart.addSeries(LineSeries, opts)` — required checking typings before writing overlay code
- `CanvasRenderingTarget2D` not exported from `lightweight-charts` package despite being used in its interfaces — must import from `fancy-canvas` peer dependency directly

## Known Stubs

- `generateDemoBars()` generates synthetic NQ demo data (base price 17000, random volumes). This is intentional for v1 — real bar data from Rithmic feed wired in Phase 11 when `footprintSeries.update(bar)` is called from WebSocket events.
- GEX overlay values in `FootprintChart.tsx` are hardcoded demo values (callWall: 17200, putWall: 16800, gammaFlip: 17000). Phase 11 will wire from `useLiveStore` signal events.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- FootprintChart renders in the LIVE tab with demo footprint data immediately on load
- Plugin architecture is extensible: Phase 11 calls `footprintSeries.update(bar)` for live bars
- GEX overlay wiring: `addZoneOverlays(chart, { gexLevels: { ... } })` accepts numeric values from signals store
- ResizeObserver T-10-10 mitigation is in place — no memory leaks on tab navigation

---
*Phase: 10-analytics-dashboard*
*Completed: 2026-04-14*
