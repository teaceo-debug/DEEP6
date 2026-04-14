# Lightweight Charts v5.1 Custom Series — Reference

Target: `lightweight-charts@5.1.0`. Verified against the v5.x API docs and the
`plugin-examples/src/plugins/stacked-bars-series` source in the upstream repo.
Anything unverified is flagged at the bottom.

## 1. The two-interface contract

A custom series is two objects: a **pane view** (metadata + data router) and a
**renderer** (canvas drawing). Both are imported from `lightweight-charts`.

### `ICustomSeriesPaneView<HorzScaleItem, TData, TSeriesOptions>`

| Method | Called | Purpose |
|---|---|---|
| `renderer(): ICustomSeriesPaneRenderer` | Every paint | Return the renderer instance (usually cached in a field). |
| `update(data: PaneRendererCustomData<Time, TData>, options: TSeriesOptions): void` | Before each paint, after data/options change | Push the latest `bars`, `barSpacing`, `visibleRange` to the renderer. |
| `priceValueBuilder(plotRow: TData): CustomSeriesPricePlotValues` | On data add/update | Return `[min, max]` (or `[min, avg, max]`) price values so the price scale auto-fits and crosshair snaps. |
| `isWhitespace(data): data is CustomSeriesWhitespaceData<HorzScaleItem>` | On every datum | Type guard — return `true` when the row lacks drawable values. |
| `defaultOptions(): TSeriesOptions` | On `addCustomSeries` | Initial options merged with user overrides. |
| `destroy?(): void` | On series removal | Drop timers/listeners. Optional. |
| `conflationReducer?(a, b): TData` | On zoom-out conflation | Optional aggregator. |

### `ICustomSeriesPaneRenderer`

Only one required method:

```ts
draw(target: CanvasRenderingTarget2D, priceConverter: PriceToCoordinateConverter): void
```

Called on: visible-range changes, data updates, crosshair moves that touch the
pane, chart resize, and theme changes. Do **not** assume a fixed cadence; treat
`draw` as idempotent over `(data, options, visibleRange, dpr)`.

## 2. `CanvasRenderingTarget2D` — bitmap vs media space

`target` comes from the `fancy-canvas` package. You never call `getContext`
yourself. Instead you enter one of two scopes:

- `target.useBitmapCoordinateSpace(scope => { ... })` — coordinates are raw
  device pixels. `scope.context` is the 2D context, and `scope` exposes
  `horizontalPixelRatio` and `verticalPixelRatio` (both typically 2 on Retina).
  **This is the correct mode for footprint rendering.**
- `target.useMediaCoordinateSpace(scope => { ... })` — coordinates in CSS
  pixels. Simpler but blurry on Retina if you draw thin lines or small text.

**#1 gotcha — Retina blurriness.** `priceConverter` returns media-space Y
values. Inside `useBitmapCoordinateSpace` you must multiply by
`scope.verticalPixelRatio` before using them as canvas Y. Same for X widths
(multiply by `horizontalPixelRatio`). The stacked-bars example uses a helper
`positionsBox(y1, y2, verticalPixelRatio)` that returns `{position, length}`
already scaled. Replicate that pattern.

Integer-align bitmap coordinates (`Math.round`) to avoid sub-pixel smear.

## 3. `PriceToCoordinateConverter`

Signature: `(price: number) => number | null`. Returns a **media-space** Y
coordinate (CSS pixels, origin = top of pane), or `null` when the price is
off-scale. Always null-check: `priceConverter(p) ?? 0`. To use inside bitmap
space: `const yBitmap = (priceConverter(p) ?? 0) * scope.verticalPixelRatio`.

The X side is already bitmap-ready: `PaneRendererCustomData.bars[i].x` is
provided in media pixels, so you also multiply by `horizontalPixelRatio` (or
use the `calculateColumnPositionsInPlace` helper from the plugin-examples).

`PaneRendererCustomData<Time, TData>` fields you get in `update()`:
- `bars: { x: number; originalData: TData; ... }[]`
- `barSpacing: number` (media px per bar)
- `visibleRange: { from: number; to: number } | null` — indices into `bars`;
  skip out-of-range bars for perf.

## 4. Wiring into a chart

```ts
const series = chart.addCustomSeries(new MyPaneView(), { /* options */ }, paneIndex);
series.setData(rows);          // full replace
series.update(row);            // append/replace last
```

Signature:
```ts
addCustomSeries<TData, TOptions, TPartialOptions>(
  paneView: ICustomSeriesPaneView<Time, TData, TOptions>,
  options?: DeepPartial<TOptions & SeriesOptionsCommon>,
  paneIndex?: number
): ISeriesApi<'Custom', Time, TData | WhitespaceData<Time>, TOptions, TPartialOptions>
```

`TData` must include a `time` field (the horizontal scale item). For the
footprint: `{ time, open, high, low, close, cells: {price, bid, ask}[], poc?, signals?[] }`.

## 5. Perf patterns

- Keep the renderer stateless outside `_data`/`_options`. LW Charts handles
  caching; don't add another layer.
- Loop only over `visibleRange.from..visibleRange.to`, not the whole array.
- Precompute once per `update()` anything independent of dpr (e.g., bucket
  indexes). Re-scale inside `draw()` using the current `verticalPixelRatio`.
- Batch `fillStyle` by color: sort cells by color and issue contiguous
  `fillRect` calls to minimize state changes. At 40-level × N-bar footprints,
  this is the main perf lever.
- Use a single `Path2D` per stroke color for POC/level lines instead of
  per-segment `stroke()`.
- `draw()` fires on every crosshair move. If footprint rendering is heavy,
  gate on `_lastDrawKey` (visibleRange + data version) and short-circuit to
  a cached OffscreenCanvas blit. Only worth it if profiling shows >4ms/frame.

## 6. Coexistence with a standard series

Call `chart.addCandlestickSeries(...)` and `chart.addCustomSeries(...)` on the
same chart. By default both attach to the right price scale (`priceScaleId:
'right'`) and thus **share scale and auto-fit together**. To decouple,
assign the custom series an overlay scale: `priceScaleId: 'footprint'` (any
string not matching a built-in scale creates an overlay). For the footprint +
candle overlay case, you typically want them sharing the right scale so price
levels align — which is the default.

`paneIndex` lets you stack panes (e.g., footprint in pane 0, cumulative delta
histogram in pane 1).

## 7. Minimal working example (~40 lines)

```ts
import {
  CanvasRenderingTarget2D,
  BitmapCoordinatesRenderingScope,
} from 'fancy-canvas';
import {
  ICustomSeriesPaneView, ICustomSeriesPaneRenderer,
  PaneRendererCustomData, PriceToCoordinateConverter,
  CustomSeriesPricePlotValues, WhitespaceData, Time,
} from 'lightweight-charts';

interface BoxData { time: Time; low: number; high: number; color: string; }
interface BoxOptions { opacity: number; }
const defaults: BoxOptions = { opacity: 0.5 };

class BoxRenderer implements ICustomSeriesPaneRenderer {
  private _d: PaneRendererCustomData<Time, BoxData> | null = null;
  private _o: BoxOptions = defaults;
  update(d: PaneRendererCustomData<Time, BoxData>, o: BoxOptions) { this._d = d; this._o = o; }
  draw(target: CanvasRenderingTarget2D, p2c: PriceToCoordinateConverter) {
    target.useBitmapCoordinateSpace((s: BitmapCoordinatesRenderingScope) => {
      const d = this._d; if (!d || !d.visibleRange) return;
      const hpr = s.horizontalPixelRatio, vpr = s.verticalPixelRatio;
      const halfW = Math.max(1, (d.barSpacing * hpr) / 2);
      s.context.globalAlpha = this._o.opacity;
      for (let i = d.visibleRange.from; i < d.visibleRange.to; i++) {
        const bar = d.bars[i]; const row = bar.originalData;
        const xC = bar.x * hpr;
        const yT = (p2c(row.high) ?? 0) * vpr;
        const yB = (p2c(row.low)  ?? 0) * vpr;
        s.context.fillStyle = row.color;
        s.context.fillRect(Math.round(xC - halfW), Math.round(yT),
                           Math.round(halfW * 2), Math.round(yB - yT));
      }
      s.context.globalAlpha = 1;
    });
  }
}

export class BoxSeries implements ICustomSeriesPaneView<Time, BoxData, BoxOptions> {
  private _r = new BoxRenderer();
  renderer() { return this._r; }
  update(d: PaneRendererCustomData<Time, BoxData>, o: BoxOptions) { this._r.update(d, o); }
  priceValueBuilder(r: BoxData): CustomSeriesPricePlotValues { return [r.low, r.high]; }
  isWhitespace(d: BoxData | WhitespaceData): d is WhitespaceData {
    return (d as BoxData).low === undefined;
  }
  defaultOptions() { return defaults; }
}

// usage: const s = chart.addCustomSeries(new BoxSeries()); s.setData(rows);
```

## Unverified / flags

- `conflationReducer` exists in the v5 "next" API docs but I did not confirm it
  is stable in 5.1.0. Treat as optional and skip for the footprint plugin.
- Exact default price-scale sharing behavior (`priceScaleId: 'right'`) was
  inferred from v5 defaults applying to all series; cross-check by inspecting
  `series.priceScale().id()` in dev.
- `useMediaCoordinateSpace` scope fields are documented but not re-verified
  here — we only need `useBitmapCoordinateSpace` for the footprint.

## Sources

- https://tradingview.github.io/lightweight-charts/docs/plugins/custom_series
- https://tradingview.github.io/lightweight-charts/docs/next/api/interfaces/ICustomSeriesPaneView
- https://tradingview.github.io/lightweight-charts/docs/next/api/interfaces/IChartApi
- `plugin-examples/src/plugins/stacked-bars-series/{stacked-bars-series,renderer}.ts` in `tradingview/lightweight-charts` (canonical pattern for bar-width columns + bitmap space; our minimal example follows its structure).
