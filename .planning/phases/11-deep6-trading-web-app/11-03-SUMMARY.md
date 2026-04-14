---
phase: 11-deep6-trading-web-app
plan: "03"
subsystem: dashboard-frontend
tags: [lw-charts, custom-series, websocket, zustand, canvas, footprint, signals]
dependency_graph:
  requires: ["11-01", "11-02"]
  provides: ["live-monitoring-ui", "footprint-custom-series", "signal-feed", "score-widget"]
  affects: ["dashboard"]
tech_stack:
  added:
    - "FootprintSeries (ICustomSeriesPaneView) + FootprintRenderer (ICustomSeriesPaneRenderer) — LW Charts v5.1 custom series"
    - "ZoneOverlay — sibling canvas with priceScale.getVisibleRange() coordinate mapping"
    - "useWebSocket — exponential backoff reconnect (1s→30s), visibility-aware"
    - "shadcn: button, badge, select, input, tooltip, separator, scroll-area"
  patterns:
    - "useBitmapCoordinateSpace + hpr/vpr multiplication for Retina-correct canvas rendering"
    - "Zustand lastBarVersion/lastSignalVersion version-counter pattern — zero React re-renders on hot path"
    - "store.subscribe(selector, listener) for Canvas redraw without component re-render"
key_files:
  created:
    - dashboard/hooks/useWebSocket.ts
    - dashboard/hooks/useWebSocket.test.ts
    - dashboard/hooks/useFootprintData.ts
    - dashboard/lib/lw-charts/FootprintSeries.ts
    - dashboard/lib/lw-charts/FootprintRenderer.ts
    - dashboard/lib/lw-charts/FootprintSeries.test.ts
    - dashboard/lib/lw-charts/zoneDrawer.ts
    - dashboard/components/footprint/FootprintChart.tsx
    - dashboard/components/footprint/ZoneOverlay.tsx
    - dashboard/components/signals/SignalFeed.tsx
    - dashboard/components/signals/SignalFeedRow.tsx
    - dashboard/components/tape/TapeScroll.tsx
    - dashboard/components/tape/TapeRow.tsx
    - dashboard/components/score/ScoreWidget.tsx
    - dashboard/components/score/KronosBiasBar.tsx
    - dashboard/components/layout/HeaderStrip.tsx
    - dashboard/components/ui/button.tsx (shadcn)
    - dashboard/components/ui/badge.tsx (shadcn)
    - dashboard/components/ui/select.tsx (shadcn)
    - dashboard/components/ui/input.tsx (shadcn)
    - dashboard/components/ui/tooltip.tsx (shadcn)
    - dashboard/components/ui/separator.tsx (shadcn)
    - dashboard/components/ui/scroll-area.tsx (shadcn)
  modified:
    - dashboard/app/page.tsx
decisions:
  - "ZoneOverlay uses priceScale('right').getVisibleRange() (returns IRange<number> = {from,to}) not the non-existent getVisiblePriceRange — corrected from plan pseudocode"
  - "FootprintChart toLWData: RingBuffer.toArray() returns oldest→newest (insertion order) which is what LW Charts needs — no reverse needed (linter caught this)"
  - "Test 2 backoff verification: timing-window approach (999ms → no new WS, 1ms more → WS appears) is more robust than mocking setTimeout which causes TypeScript mockImplementation return-type conflicts"
  - "TapeScroll subscribes to lastBarVersion as coarse trigger since no dedicated tapeVersion exists in store; Wave 3 can add one"
metrics:
  duration: "~45 minutes"
  completed: "2026-04-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 23
  files_modified: 1
  tests_added: 11
  tests_total: 23
---

# Phase 11 Plan 03: Live UI Components Summary

**One-liner:** Real-time WebSocket hook with exponential backoff feeding LW Charts v5.1 custom footprint series, zone overlay canvas, signal feed with TYPE_A pulse animation, T&S tape, and 28px JetBrains Mono confluence score widget.

---

## What Was Built

### File Tree

```
dashboard/
├── hooks/
│   ├── useWebSocket.ts          ← reconnecting WS hook, exponential backoff 1s→30s
│   ├── useWebSocket.test.ts     ← 5 tests (all green)
│   └── useFootprintData.ts      ← ring buffer ref hook for 30-bar window
├── lib/
│   └── lw-charts/
│       ├── FootprintSeries.ts   ← ICustomSeriesPaneView implementation
│       ├── FootprintRenderer.ts ← ICustomSeriesPaneRenderer — full Canvas2D drawing
│       ├── FootprintSeries.test.ts ← 6 tests (all green)
│       └── zoneDrawer.ts        ← pure drawZones() function
├── components/
│   ├── layout/
│   │   └── HeaderStrip.tsx      ← 40px fixed header, connection dot + E10 + GEX
│   ├── footprint/
│   │   ├── FootprintChart.tsx   ← LW Charts host + series + lastBarVersion subscription
│   │   └── ZoneOverlay.tsx      ← sibling canvas, priceScale sync, ResizeObserver
│   ├── signals/
│   │   ├── SignalFeed.tsx        ← ScrollArea, newest-first, justArrived tracking
│   │   └── SignalFeedRow.tsx     ← 48px row, tier colors, TYPE_A pulse, score/agreement
│   ├── tape/
│   │   ├── TapeScroll.tsx       ← 200px fixed, 50-row cap, newest-first
│   │   └── TapeRow.tsx          ← 20px row, 4 columns, oversized wash
│   ├── score/
│   │   ├── ScoreWidget.tsx      ← 28px score (primary focal point), category bars, GEX
│   │   └── KronosBiasBar.tsx    ← directional bias progress bar
│   └── ui/                      ← shadcn: button, badge, select, input, tooltip, separator, scroll-area
└── app/
    └── page.tsx                 ← 3-column layout, all components wired
```

---

## LW Charts Custom Series Learnings

### Deviations from RESEARCH.md sample

1. **`priceValueBuilder` return type:** The plan specified `[low, high, close]` (3 values). The LW Charts type `CustomSeriesPricePlotValues` accepts 2 or 3 values. Using `[low, high, close]` works correctly.

2. **`isWhitespace` signature:** TypeScript requires `item is { time: Time }` as the return type predicate, not just `boolean`. The implementation uses `(item: FootprintBarLW | { time: Time }) => item is { time: Time }`.

3. **`toLWData` ordering:** `RingBuffer.toArray()` returns oldest-first (insertion order). LW Charts requires ascending time order. No reverse needed — the linter caught and fixed an incorrect `.reverse()` in the initial implementation.

4. **`priceToCoordinate` in ZoneOverlay:** LW Charts v5 exposes `priceToCoordinate` only via a series ref, not on the chart or price scale directly. ZoneOverlay uses `chart.priceScale('right').getVisibleRange()` (returns `{ from: minPrice, to: maxPrice }`) to compute a linear approximation. The plan's pseudocode referenced the non-existent `getVisiblePriceRange()` — corrected via TypeScript error discovery.

5. **Retina multiplications:** All y-coordinates from `priceToCoordinate` multiplied by `scope.verticalPixelRatio`; all x-coordinates from `bar.x` multiplied by `scope.horizontalPixelRatio` inside `useBitmapCoordinateSpace`. Font sizes also scaled by `vpr`.

---

## Manual Smoke Test Transcript

**Not run** (no backend available in this environment). Expected behavior when running:

1. `cd /Users/teaceo/DEEP6 && uvicorn deep6.api.app:app --port 8000`
2. `cd /Users/teaceo/DEEP6/dashboard && npm run dev`
3. Open `http://localhost:3000`:
   - Header strip shows "DEEP6" + "NQ" + "—" + connection dot (red = disconnected until WS connects)
   - Footprint chart area renders (LW Charts canvas visible, dark bg `#0a0a0f`)
   - Signal feed shows "No signals yet. Waiting for market data."
   - Score widget shows `0` in muted color (below 50 threshold)
4. On WS connection: header dot turns green
5. On bar broadcast: chart renders candles + footprint cells; header shows price
6. On TYPE_A signal: lime left border + 1s pulse animation on first row

---

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| `__zones` field injection | `components/footprint/ZoneOverlay.tsx` | 15 | Zone data arrives from backend via bar payload field; real backend zone computation is Wave 3+. If no zones present, overlay draws nothing. |
| `__signalType` field injection | `lib/lw-charts/FootprintRenderer.ts` | 189 | Signal marker on footprint bar injected by FootprintChart from signal store. Wave 3 wires this by matching signal bar_index to bar ts. |
| No dedicated `tapeVersion` | `components/tape/TapeScroll.tsx` | 14 | TapeScroll subscribes to `lastBarVersion` as coarse trigger. A dedicated `tapeVersion` counter in the store would make tape updates independent of bar updates. |

---

## Wave 3 Prerequisites

1. **Replay mode store additions:** `isReplay: boolean`, `replayBarIndex: number`, `replaySpeed: '1x'|'2x'|'5x'|'auto'` in TradingState. `setReplayMode(mode: boolean)` action.
2. **Signal → Bar association for markers:** FootprintChart needs to inject `__signalType` onto bars by joining `signals.toArray()` by `bar_index_in_session`. Currently signal markers never render.
3. **Tape version counter:** Add `lastTapeVersion` to TradingState + bump in `pushTape` so TapeScroll subscribes independently of bar updates.
4. **ZoneOverlay series ref bridge:** For pixel-perfect zone y-coordinates, FootprintChart should pass its `seriesRef` down to ZoneOverlay so it can call `series.priceToCoordinate(price)` directly instead of the linear approximation.
5. **Replay endpoint integration:** `GET /api/replay/{session}/{bar_index}` from Phase 11-01 backend needs wiring to the replay controls strip.

---

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written with one correction:

**1. [Rule 1 - Bug] `getVisiblePriceRange` → `getVisibleRange` in ZoneOverlay**
- **Found during:** Task 2 typecheck
- **Issue:** Plan pseudocode called `chart.priceScale('right').getVisiblePriceRange?.()` which does not exist on `IPriceScaleApi` in LW Charts v5.1
- **Fix:** Used `chart.priceScale('right').getVisibleRange()` which returns `IRange<number>` = `{ from: minPrice, to: maxPrice }`
- **Files modified:** `dashboard/components/footprint/ZoneOverlay.tsx`
- **Commit:** 039663f

**2. [Rule 1 - Bug] Test 2 backoff mock caused TypeScript return-type error**
- **Found during:** Task 1 typecheck
- **Issue:** `vi.spyOn(globalThis, 'setTimeout').mockImplementation(fn)` requires return type matching vitest's `Timeout` but browser type is `number`
- **Fix:** Replaced mock approach with timing-window verification (advance 999ms → no new WS; advance 1ms more → WS appears) — tests the same behavior more robustly without type conflicts
- **Files modified:** `dashboard/hooks/useWebSocket.test.ts`
- **Commit:** 670f7db

---

## Threat Flags

None found. All files are frontend-only UI components. The `useWebSocket` hook dispatches to the store's discriminated-union dispatcher which validates message type before routing (T-11-11 coverage confirmed). The `FootprintRenderer` guards `Number.isFinite(price)` on all tick keys before rendering (T-11-13 coverage confirmed).

## Self-Check: PASSED
