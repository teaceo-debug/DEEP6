import type {
  ICustomSeriesPaneRenderer,
  PaneRendererCustomData,
  PriceToCoordinateConverter,
  Time,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { FootprintBarLW } from './FootprintSeries';
import type { FootprintSeriesOptions } from './FootprintSeries';

// ── Constants ─────────────────────────────────────────────────────────────────
const BID_FILL   = 'rgba(239,68,68,0.15)';
const ASK_FILL   = 'rgba(34,197,94,0.15)';
const IMBALANCE_WASH = 'rgba(163,230,53,0.25)';
const BULL_BODY  = '#22c55e';
const BEAR_BODY  = '#ef4444';
const DELTA_POS  = '#22c55e';
const DELTA_NEG  = '#ef4444';
const MARKER_TYPE_A = '#a3e635';
const MARKER_TYPE_B = '#facc15';
const MARKER_TYPE_C = '#38bdf8';
const IMBALANCE_THRESHOLD = 3.0;

// ── Renderer ──────────────────────────────────────────────────────────────────

export class FootprintRenderer implements ICustomSeriesPaneRenderer {
  private _data: PaneRendererCustomData<Time, FootprintBarLW> | null = null;
  private _options: FootprintSeriesOptions | null = null;

  update(
    data: PaneRendererCustomData<Time, FootprintBarLW>,
    options: FootprintSeriesOptions,
  ): void {
    this._data = data;
    this._options = options;
  }

  draw(
    target: CanvasRenderingTarget2D,
    priceToCoordinate: PriceToCoordinateConverter,
  ): void {
    // DPR invariant: all ctx.font sizes and coordinate values are in bitmap pixels.
    // CSS px values must be multiplied by scope.verticalPixelRatio (vpr) before use.
    // priceToCoordinate() returns media-space Y → multiply by vpr before drawing.
    const data = this._data;
    const options = this._options;
    if (!data || !options) return;
    const range = data.visibleRange;
    if (!range) return;

    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const vpr = scope.verticalPixelRatio;
      const halfW = Math.max(2, (data.barSpacing * hpr) / 2 - 1);

      const { from, to } = range;
      for (let i = from; i < to; i++) {
        const bar = data.bars[i];
        if (!bar) continue;
        const d = bar.originalData;
        if (!d || !d.levels) continue;

        const xC = Math.round(bar.x * hpr);
        const rowH = Math.max(1, Math.round(options.rowHeight * vpr));

        ctx.save();

        // ── 1. Candlestick body ───────────────────────────────────────────
        const yOpen  = (priceToCoordinate(d.open)  ?? 0) * vpr;
        const yClose = (priceToCoordinate(d.close) ?? 0) * vpr;
        const yHigh  = (priceToCoordinate(d.high)  ?? 0) * vpr;
        const yLow   = (priceToCoordinate(d.low)   ?? 0) * vpr;

        const bodyTop    = Math.round(Math.min(yOpen, yClose));
        const bodyBottom = Math.round(Math.max(yOpen, yClose));
        const bodyH      = Math.max(1, bodyBottom - bodyTop);

        ctx.fillStyle = d.close >= d.open ? BULL_BODY : BEAR_BODY;
        ctx.fillRect(xC - Math.round(halfW / 2), bodyTop, Math.round(halfW), bodyH);

        // Wicks
        ctx.fillRect(xC - 1, Math.round(yHigh), 2, bodyTop - Math.round(yHigh));
        ctx.fillRect(xC - 1, bodyBottom, 2, Math.round(yLow) - bodyBottom);

        // ── 2. Footprint cell grid ────────────────────────────────────────
        const levelKeys = Object.keys(d.levels);
        if (levelKeys.length > 0) {
          // Compute max volume for proportional fill scaling
          let maxLevelVol = 1;
          for (const key of levelKeys) {
            const lv = d.levels[key];
            const total = (lv.bid_vol ?? 0) + (lv.ask_vol ?? 0);
            if (total > maxLevelVol) maxLevelVol = total;
          }

          const fullW = Math.round(halfW * 2);

          for (const tickKey of levelKeys) {
            // T-11-13: skip malformed tick keys
            const tick = Number(tickKey);
            if (!Number.isFinite(tick)) continue;
            const price = tick * 0.25; // NQ tick size
            const yMedia = priceToCoordinate(price);
            if (yMedia === null) continue;
            const yBitmap = Math.round(yMedia * vpr);

            const lv = d.levels[tickKey];
            const bidVol = lv.bid_vol ?? 0;
            const askVol = lv.ask_vol ?? 0;
            const cellTop  = yBitmap - Math.round(rowH / 2);

            // Imbalance detection (T-11-13 guard included)
            const maxV = Math.max(bidVol, askVol);
            const minV = Math.max(1, Math.min(bidVol, askVol));
            const isImbalance = options.showImbalance && (maxV / minV >= IMBALANCE_THRESHOLD);

            if (isImbalance) {
              ctx.fillStyle = IMBALANCE_WASH;
              ctx.fillRect(xC - Math.round(halfW), cellTop, fullW, rowH);
            } else {
              // Proportional bid fill (left half)
              const bidRatio  = bidVol / maxLevelVol;
              const askRatio  = askVol / maxLevelVol;
              const bidWidth  = Math.round((fullW / 2) * bidRatio);
              const askWidth  = Math.round((fullW / 2) * askRatio);

              if (bidWidth > 0) {
                ctx.fillStyle = BID_FILL;
                ctx.fillRect(xC - Math.round(halfW), cellTop, bidWidth, rowH);
              }
              if (askWidth > 0) {
                ctx.fillStyle = ASK_FILL;
                ctx.fillRect(xC, cellTop, askWidth, rowH);
              }
            }

            // Volume text — clip to cell bounds to prevent bleed
            const fontSize = Math.max(8, Math.round(12 * vpr));
            ctx.font = `${fontSize}px "JetBrains Mono", monospace`;
            ctx.save();
            ctx.beginPath();
            ctx.rect(xC - Math.round(halfW), cellTop, fullW, rowH);
            ctx.clip();

            if (bidVol > 0) {
              ctx.fillStyle = '#ef4444';
              ctx.textAlign = 'left';
              ctx.textBaseline = 'middle';
              ctx.fillText(String(bidVol), xC - Math.round(halfW) + 2, yBitmap);
            }
            if (askVol > 0) {
              ctx.fillStyle = '#22c55e';
              ctx.textAlign = 'right';
              ctx.textBaseline = 'middle';
              ctx.fillText(String(askVol), xC + Math.round(halfW) - 2, yBitmap);
            }
            ctx.restore();
          }
        }

        // ── 3. POC line ───────────────────────────────────────────────────
        if (d.poc_price) {
          const yPoc = priceToCoordinate(d.poc_price);
          if (yPoc !== null) {
            const yPocBitmap = Math.round(yPoc * vpr);
            ctx.strokeStyle = options.pocLineColor;
            ctx.lineWidth = Math.max(1, vpr);
            ctx.beginPath();
            ctx.moveTo(xC - Math.round(halfW), yPocBitmap);
            ctx.lineTo(xC + Math.round(halfW), yPocBitmap);
            ctx.stroke();
          }
        }

        // ── 4. Delta footer ───────────────────────────────────────────────
        if (options.showDelta && d.bar_delta !== undefined) {
          const yDeltaBase = Math.round(yLow) + Math.round(8 * vpr);
          const deltaFontSize = Math.max(8, Math.round(12 * vpr));
          ctx.font = `${deltaFontSize}px "JetBrains Mono", monospace`;
          ctx.fillStyle = d.bar_delta >= 0 ? DELTA_POS : DELTA_NEG;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(
            (d.bar_delta >= 0 ? '+' : '') + String(d.bar_delta),
            xC,
            yDeltaBase,
          );
        }

        // ── 5. Signal marker ──────────────────────────────────────────────
        const sigType = (d as FootprintBarLW & { __signalType?: string }).__signalType;
        if (sigType) {
          const markerColor =
            sigType === 'TYPE_A' ? MARKER_TYPE_A :
            sigType === 'TYPE_B' ? MARKER_TYPE_B :
            sigType === 'TYPE_C' ? MARKER_TYPE_C : null;

          if (markerColor) {
            const yMarkerBase = Math.round(yHigh) - Math.round(12 * vpr);
            const markerSize = Math.round(8 * vpr);
            ctx.fillStyle = markerColor;
            ctx.beginPath();
            // Upward triangle above the high
            ctx.moveTo(xC, yMarkerBase - markerSize);
            ctx.lineTo(xC - markerSize, yMarkerBase);
            ctx.lineTo(xC + markerSize, yMarkerBase);
            ctx.closePath();
            ctx.fill();
          }
        }

        ctx.restore();
      }
    });
  }
}
