import type {
  ICustomSeriesPaneView,
  PaneRendererCustomData,
  CustomSeriesPricePlotValues,
  Time,
  CustomSeriesOptions,
} from 'lightweight-charts';
import { customSeriesDefaultOptions } from 'lightweight-charts';
import { FootprintRenderer } from './FootprintRenderer';
import type { FootprintBar } from '@/types/deep6';

// ── Options ──────────────────────────────────────────────────────────────────

export interface FootprintSeriesOptions extends CustomSeriesOptions {
  rowHeight: number;
  showDelta: boolean;
  showImbalance: boolean;
  pocLineColor: string;
}

export const footprintSeriesDefaults: FootprintSeriesOptions = {
  ...customSeriesDefaultOptions,
  rowHeight: 20,
  showDelta: true,
  showImbalance: true,
  pocLineColor: '#facc15',
};

// ── LW Charts data shape ──────────────────────────────────────────────────────
// LW Charts requires a `time` field on each row. We alias `ts` → `time` in
// FootprintChart before calling series.setData().

export interface FootprintBarLW extends FootprintBar {
  time: Time;
}

// ── Pane View ─────────────────────────────────────────────────────────────────

export class FootprintSeries
  implements ICustomSeriesPaneView<Time, FootprintBarLW, FootprintSeriesOptions>
{
  private _renderer: FootprintRenderer;

  constructor() {
    this._renderer = new FootprintRenderer();
  }

  /** Return the cached renderer instance. */
  renderer(): FootprintRenderer {
    return this._renderer;
  }

  /**
   * Called before each paint. Forward data + options to the renderer so it
   * can precompute per-bar values once rather than on every draw() call.
   */
  update(
    data: PaneRendererCustomData<Time, FootprintBarLW>,
    options: FootprintSeriesOptions,
  ): void {
    this._renderer.update(data, options);
  }

  /**
   * Return [low, high, last] so LW Charts auto-fits the price scale and
   * snaps the crosshair correctly.
   */
  priceValueBuilder(item: FootprintBarLW): CustomSeriesPricePlotValues {
    return [item.low, item.high, item.close];
  }

  /**
   * A bar is whitespace when it has no price levels (nothing to draw).
   */
  isWhitespace(
    item: FootprintBarLW | { time: Time },
  ): item is { time: Time } {
    const bar = item as FootprintBarLW;
    return !bar.levels || Object.keys(bar.levels).length === 0;
  }

  defaultOptions(): FootprintSeriesOptions {
    return footprintSeriesDefaults;
  }

  destroy(): void {
    // No persistent resources to release
  }
}
