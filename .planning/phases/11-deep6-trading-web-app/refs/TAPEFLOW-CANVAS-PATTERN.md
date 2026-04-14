# TapeFlow Canvas Pattern — Wave 2 Reference

Source: https://github.com/ianfigueroa/TapeFlow (verified 2026-04-13, main @ 3ea60eb)
Stack: React 18 + Vite + TypeScript + Zustand + flexlayout-react. **Pure Canvas2D** rendering.

## CRITICAL FINDING — flag before adopting

**TapeFlow does NOT use TradingView Lightweight Charts.** Despite the README stating it does, `frontend/package.json` has no `lightweight-charts` dependency. Every chart (`CandlestickChart.tsx`, `PriceChart.tsx`, `FootprintChart.tsx`, `HeatmapLayer.ts`) is rendered on a raw `<canvas>` using the 2D context. There is no sibling-canvas-over-LW-Charts pattern to copy. If DEEP6 wants LW Charts underneath a footprint overlay, that integration must be designed fresh — TapeFlow is only a reference for the pure-canvas path.

What TapeFlow actually proves: you can run 500+ trades/sec footprint + heatmap + DOM on plain Canvas2D at 60fps in React 18 without breaking a sweat.

## 1. Architecture Map

```
frontend/src/
  services/dataBuffer.ts    <- mutable ring buffer + pub/sub (core)
  engine/
    CanvasEngine.tsx        <- React wrapper; owns <canvas> + LayerManager
    LayerManager.ts         <- RAF loop, z-ordered layer dispatch, DPR setup
    RenderContext.ts        <- viewport + priceToY / timeToX projection
    Layer.ts                <- interface { update(data), render(ctx, rc), dispose() }
    layers/
      BackgroundLayer.ts    z=0   grid
      HeatmapLayer.ts       z=10  DOM depth heatmap (log10)
      FootprintLayer.ts     z=20  cluster footprint + OHLC overlay
      IndicatorLayer.ts     z=30  VWAP, zones
      OverlayLayer.ts       z=40  crosshair/tooltips
  components/
    FootprintChart.tsx      <- wraps CanvasEngine, registers layers
    DOMLadder.tsx           <- pure React DOM (not canvas)
```

## 2. Ring Buffer + Bypass-React Pattern (`services/dataBuffer.ts`)

Module-level `Map<symbol, TradeBuffer>` — no Zustand for hot data. Zustand (`useMarketStore`, `useSettingsStore`) is only for UI state/settings.

```ts
interface TradeBuffer { incoming: Trade[]; processed: TradeWithAnalytics[]; hasNewData: boolean }
const tradeBuffers = new Map<string, TradeBuffer>();

export function pushTrade(trade: Trade): void {
  const b = getTradeBuffer(trade.symbol);
  b.incoming.push(trade);           // mutate in place
  b.hasNewData = true;
  recordTradeLatency(trade.symbol, trade.timestamp);
  recordTradeRate(trade.symbol);
  notifyListeners(trade);            // observer pattern
  if (b.incoming.length > MAX_BUFFER /* 5000 */) b.incoming.shift();
}

// Observer — components subscribe outside React render cycle
const tradeListeners = new Set<(t: Trade) => void>();
export function subscribeToTrades(fn) { tradeListeners.add(fn); return () => tradeListeners.delete(fn); }
```

Consumer pattern (`FootprintChart.tsx`) — avoids re-renders:
```ts
const pendingTradesRef = useRef<Trade[]>([]);
useEffect(() => {
  const unsub = subscribeToTrades(trade => {
    if (trade.symbol !== symbol) return;
    pendingTradesRef.current.push(trade);   // ref mutation, no setState
  });
  return unsub;
}, [symbol]);

useEffect(() => {                            // drain via setInterval, not RAF
  const id = setInterval(() => {
    if (!pendingTradesRef.current.length) return;
    const batch = pendingTradesRef.current;
    pendingTradesRef.current = [];
    engine.updateData({ trades: batch.map(toTradeWithAnalytics), ... });
  }, 100);                                    // 10fps is plenty for footprint
  return () => clearInterval(id);
}, [isReady]);
```

Rate tracking uses sliding 1s window pruned to 10s of timestamps; rolling OPS avg sampled every 500ms via `setInterval`.

## 3. LayerManager — RAF + DPR

```ts
constructor(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width  = rect.width  * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);                      // done ONCE; layers draw in CSS px
}

private tick = () => {                      // single RAF for all layers
  if (!this.isRunning) return;
  ctx.clearRect(0, 0, width, height);
  for (const {layer, visible} of this.sortedLayers) {
    if (!visible) continue;
    ctx.save(); layer.render(ctx, rc); ctx.restore();
  }
  this.rafId = requestAnimationFrame(this.tick);
};

updateData(data) {                          // decoupled from render
  this.pendingData = data;
  for (const {layer} of this.sortedLayers) layer.update(data);
}
resize(w, h) {                              // also resets dpr transform
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
  ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr, dpr);
}
```

No offscreen canvas. Single 2D context. `ResizeObserver` on container drives `setDimensions`.

## 4. Price ↔ Pixel Projection (`RenderContext.ts`)

TapeFlow owns projection itself (no LW Charts `priceToCoordinate`):

```ts
priceToY(price) {
  const ratio = (price - priceMin) / (priceMax - priceMin);
  return height * (1 - ratio);
}
timeToX(ts) {
  const ratio = (ts - timeStart) / (timeEnd - timeStart);
  return width * ratio;
}
```

Each layer computes its own viewport in `render()` and calls `rc.setViewport({priceMin, priceMax, timeStart, timeEnd})`. `FootprintLayer` pads the price domain 15% and reserves a fixed 65px y-axis gutter.

**For DEEP6:** if you layer on top of Lightweight Charts, replace `priceToY` with `series.priceToCoordinate(price)` and subscribe to `chart.timeScale().subscribeVisibleTimeRangeChange()` + `subscribeVisibleLogicalRangeChange()` to trigger overlay repaints on pan/zoom. TapeFlow does not demonstrate this sync — you are on your own for that bridge.

## 5. Footprint Cell Rendering (`engine/layers/FootprintLayer.ts`)

Data model per cluster:
```ts
interface FootprintCluster {
  timestamp: number; open, high, low, close: number;
  priceLevels: Map<number, { bid: number; ask: number }>;   // price -> volumes
  poc: number; totalVolume: number;
}
```

Cell pipeline (per cluster, per price level):
1. `roundToTick(price)` keyed into `priceLevels` Map; buy → `ask` slot (lifts ask), sell → `bid` slot.
2. Adaptive `rowHeight = clamp(availableHeight/numLevels, 18, 28)`.
3. `candleWidth = clamp(chartWidth/numClusters, 70, 120)` — fixed index positioning, not timeToX.
4. Per cell draws three rects: (a) heatmap bg `rgba(0,255,65,bgAlpha)` or `rgba(255,69,69,bgAlpha)` with `bgAlpha = 0.15 + intensity*0.35`; (b) left-side red bid bar; (c) right-side green ask bar. Bar widths scaled to **per-cluster max** (bug fix — see §7), then clamped to `halfWidth * 0.95`.
5. `intensity = sqrt(volume / globalMax90thPercentile)` so low volume stays visible.
6. POC: gold (`#FFD700`) stroke rect.
7. Labels: `ctx.save(); ctx.clip()` to cell bounds before drawing `bidStr×askStr`; imbalance arrow ▲/▼ drawn *outside* clip.
8. Finally draw candlestick wick + body on top of footprint.

Trades are batched: `FootprintLayer.update()` pushes to `pendingTrades[]` and flushes every 50ms.

## 6. Heatmap (`HeatmapLayer.ts`)

Snapshot buffer `MAX_SNAPSHOTS=100`, throttled 100ms. 40 price levels. Cell color by `log10(size+1) / maxLogSize` (EMA-smoothed: `maxLogSize = maxLogSize*0.99 + newMax*0.01`). Drawn as plain `ctx.fillRect(x, y, cellW+1, cellH+1)` — the +1 prevents seams.

## 7. Theme / "Matrix" Colors

No CSS vars — theme is a TS object in `engine/types.ts`, passed into `RenderContext.theme` and used as `ctx.fillStyle`:

```ts
export const DEFAULT_THEME: ThemeColors = {
  background: '#0a0a0a', grid: '#1a1a1a',
  text: '#ffffff', textMuted: '#666666',
  buy:  '#00FF41',   // matrix green
  sell: '#FF4545',
  vwap: '#F59E0B', poc: '#FACC15',
  heatmapLow: '#0d1b2a', heatmapMedium: '#1b4d72',
  heatmapHigh: '#f0b429', heatmapMax: '#ffffff',
};
```

FootprintLayer hardcodes `#00FF41` / `#FF4545` in some spots (not theme-driven — worth fixing in our port). Tailwind/Zustand handle DOM-side theming; canvas reads the theme object directly.

## 8. Recent Bug Fixes (verified in commits / code comments)

- `bc8ca49` "Fix UI bugs in charts and data visualization components"
- `73750f3` "Fix TypeScript errors in frontend build"
- `157f1b2` "fix nested button in symbol tab"
- In-code BUG FIX comments in `FootprintLayer.renderCluster`:
  1. Bar widths must scale to **this cluster's max**, not global max, to prevent overflow into adjacent candles when one candle dominates.
  2. Clamp bar width to `halfWidth * 0.95`.
  3. `ctx.clip()` around volume labels so text never bleeds into neighbor columns.
- Symbol change handling: keep a `lastSymbolRef`; on change call `layer.clear()` and reset `pendingTradesRef.current = []` to avoid stale-symbol trades corrupting new clusters.

## 9. What to Adapt for DEEP6 Wave 2 Executor

Adopt directly:
- Module-level ring-buffer + `subscribe()` observer in `lib/marketBuffer.ts` (Next.js: client component only, import with `'use client'`).
- `useRef` accumulator + `setInterval(..., 100)` drain to feed the renderer.
- LayerManager pattern: single RAF, z-ordered layers, DPR setup once, `ctx.scale(dpr,dpr)` + CSS-px coordinates.
- Adaptive row height (18-28px) and cluster-local max-volume scaling with clipping.
- Theme object passed as prop, not CSS vars, when writing to canvas.

Do **not** copy blindly:
- Price/time projection: if we use Lightweight Charts, replace `rc.priceToY` with `series.priceToCoordinate` and hook LW time-scale subscriptions. TapeFlow has no example of this.
- `setInterval` render cadence is fine for footprint aggregation, but Wave 2 DOM ladder should update via RAF throttled to actual DOM-callback rate.
- flexlayout-react is overkill for our layout; Next.js App Router + CSS grid is enough.
