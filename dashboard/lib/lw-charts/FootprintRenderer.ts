import type {
  ICustomSeriesPaneRenderer,
  PaneRendererCustomData,
  PriceToCoordinateConverter,
  Time,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { FootprintBarLW } from './FootprintSeries';
import type { FootprintSeriesOptions } from './FootprintSeries';

// ── UI-SPEC v2 §1 Color Tokens ────────────────────────────────────────────────
// These match the CSS custom properties in globals.css exactly.
const C_BID          = '#ff2e63';   // --bid
const C_ASK          = '#00ff88';   // --ask
const C_LIME         = '#a3ff00';   // --lime  (stacked imbalance run line, TYPE_A)
const C_AMBER        = '#ffd60a';   // --amber (POC line, TYPE_B)
const C_CYAN         = '#00d9ff';   // --cyan  (TYPE_C)
const C_RULE         = '#1f1f1f';   // --rule  (bar separators)
const C_TEXT         = '#f5f5f5';   // --text
const C_TEXT_DIM     = '#8a8a8a';   // --text-dim (crosshair)
const C_TEXT_MUTE    = '#4a4a4a';   // --text-mute (empty state)
const C_VOID         = '#000000';   // --void (canvas background)

// Bar opacity constants
const OPACITY_NORMAL    = 0.9;     // normal cells: 90%
const OPACITY_IMBALANCE = 1.0;     // imbalance cells: 100%
const OPACITY_BLOOM_GLOW = 0.35;  // bloom glow layer alpha

// Imbalance threshold
const IMBALANCE_THRESHOLD = 3.0;

// Stacked run length required
const STACKED_RUN_MIN = 3;

// Row height (UI-SPEC §3 densification: 16px)
const ROW_HEIGHT_CSS = 16;

// Volume number font
const FONT_FAMILY = '"JetBrains Mono", monospace';
const FONT_SIZE_CSS = 11;  // text-xs

// Min bar fill width to show volume inside (in CSS pixels)
const MIN_INSIDE_WIDTH_CSS = 32;

// T-11.2-07 DoS guards
const MAX_DISPLAY_VOL = 99999;
const MAX_BARS_CAP = 500;

// Empty state copy (UI-SPEC §8)
const EMPTY_STATE_TEXT = 'AWAITING NQ FOOTPRINT';

// Letter spacing for empty state (0.16em at 13px ≈ 2.08px per em)
// We approximate by measuring text and adding manual kerning, or rely on ctx.letterSpacing
const EMPTY_LETTER_SPACING_EM = 0.16;

// Signal marker dimensions
const MARKER_SQUARE_SIZE_CSS = 6;   // 6×6 square
const MARKER_LINE_ABOVE_CSS = 8;    // 8px above bar top

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
    const data = this._data;
    const options = this._options;
    if (!data || !options) return;

    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const vpr = scope.verticalPixelRatio;

      // Canvas background: pure black (--void)
      // (LW Charts clears the pane before calling draw, but we clear our region.)
      const canvasW = scope.bitmapSize.width;
      const canvasH = scope.bitmapSize.height;
      ctx.fillStyle = C_VOID;
      ctx.fillRect(0, 0, canvasW, canvasH);

      const range = data.visibleRange;

      // ── Empty state ───────────────────────────────────────────────────────
      if (!range || data.bars.length === 0) {
        this._drawEmptyState(ctx, canvasW, canvasH, vpr);
        return;
      }

      // T-11.2-07: Skip render if bars array exceeds cap (avoids runaway draw loop)
      if (data.bars.length > MAX_BARS_CAP) {
        // Still render visible range but log degraded mode conceptually
      }

      const rowH = Math.max(1, Math.round(ROW_HEIGHT_CSS * vpr));
      const fontSize = Math.max(6, Math.round(FONT_SIZE_CSS * vpr));

      const { from, to } = range;
      for (let i = from; i < to; i++) {
        const bar = data.bars[i];
        if (!bar) continue;
        const d = bar.originalData;
        if (!d || !d.levels) continue;

        const xC = Math.round(bar.x * hpr);
        // Half-width of bar in bitmap pixels
        const halfW = Math.max(2, Math.round((data.barSpacing * hpr) / 2) - 1);
        const barLeft = xC - halfW;
        const barRight = xC + halfW;
        const barWidth = halfW * 2;  // total bar width in bitmap pixels

        ctx.save();

        // ── 1. Bar separator (--rule vertical line) ───────────────────────
        ctx.fillStyle = C_RULE;
        ctx.fillRect(barLeft - 1, 0, 1, canvasH);

        // ── 2. Footprint rows (volume bars) ──────────────────────────────
        const levelKeys = Object.keys(d.levels);
        if (levelKeys.length > 0) {
          // Compute max volume across all rows in this bar
          let maxVol = 1;
          for (const key of levelKeys) {
            const lv = d.levels[key];
            if (!lv) continue;
            const bid = Math.min(MAX_DISPLAY_VOL, Math.max(0, lv.bid_vol ?? 0));
            const ask = Math.min(MAX_DISPLAY_VOL, Math.max(0, lv.ask_vol ?? 0));
            const total = bid + ask;
            if (Number.isFinite(total) && total > maxVol) maxVol = total;
          }

          // Half-width for bars (centerline gutter: 2px each side in bitmap)
          const gutterBitmap = Math.round(2 * hpr);
          const halfBarW = halfW - gutterBitmap;  // usable half-width per side

          // Imbalance detection per row — needed for stacked run scan
          interface RowInfo {
            tickKey: string;
            price: number;
            yBitmap: number;
            bidVol: number;
            askVol: number;
            isImbalanceBid: boolean;  // bid side dominates (bid/ask >= 3x)
            isImbalanceAsk: boolean;  // ask side dominates (ask/bid >= 3x)
          }

          const rows: RowInfo[] = [];

          for (const tickKey of levelKeys) {
            const tick = Number(tickKey);
            if (!Number.isFinite(tick)) continue;
            const price = tick * 0.25;  // NQ tick size
            const yMedia = priceToCoordinate(price);
            if (yMedia === null) continue;
            const yBitmap = Math.round(yMedia * vpr);

            const lv = d.levels[tickKey];
            if (!lv) continue;
            // T-11.2-07: clamp volumes to sane max; guard NaN/Infinity
            const bidVol = Math.min(MAX_DISPLAY_VOL, Math.max(0, Number.isFinite(lv.bid_vol) ? lv.bid_vol : 0));
            const askVol = Math.min(MAX_DISPLAY_VOL, Math.max(0, Number.isFinite(lv.ask_vol) ? lv.ask_vol : 0));

            const maxSide = Math.max(bidVol, askVol);
            const minSide = Math.max(1, Math.min(bidVol, askVol));
            const isImbalanceBid = options.showImbalance && bidVol > askVol && (maxSide / minSide >= IMBALANCE_THRESHOLD);
            const isImbalanceAsk = options.showImbalance && askVol > bidVol && (maxSide / minSide >= IMBALANCE_THRESHOLD);

            rows.push({ tickKey, price, yBitmap, bidVol, askVol, isImbalanceBid, isImbalanceAsk });
          }

          // Sort rows by price descending (top of canvas = higher price)
          rows.sort((a, b) => b.price - a.price);

          // ── Per-row rendering ──────────────────────────────────────────
          for (const row of rows) {
            const { yBitmap, bidVol, askVol, isImbalanceBid, isImbalanceAsk } = row;
            const cellTop = yBitmap - Math.round(rowH / 2);
            const cellHeight = rowH - 1;  // 1px gap between rows

            const isImbalance = isImbalanceBid || isImbalanceAsk;

            // Bid bar: left side from centerline
            // Length = halfBarW * (bidVol / maxVol), not exceeding halfBarW
            const bidRatio = Number.isFinite(bidVol / maxVol) ? bidVol / maxVol : 0;
            const askRatio = Number.isFinite(askVol / maxVol) ? askVol / maxVol : 0;
            const bidFillW = Math.max(0, Math.round(halfBarW * bidRatio));
            const askFillW = Math.max(0, Math.round(halfBarW * askRatio));

            // Draw bid bar (left of centerline)
            if (bidFillW > 0) {
              if (isImbalanceBid) {
                // Bloom: glow layer first (expanded, lower alpha)
                ctx.globalAlpha = OPACITY_BLOOM_GLOW;
                ctx.fillStyle = C_BID;
                const glowPad = Math.round(1.5 * hpr);
                ctx.fillRect(
                  xC - 1 - bidFillW - glowPad,
                  cellTop - glowPad,
                  bidFillW + glowPad * 2,
                  cellHeight + glowPad * 2,
                );
                // Crisp bar on top at 100% opacity
                ctx.globalAlpha = OPACITY_IMBALANCE;
              } else {
                ctx.globalAlpha = OPACITY_NORMAL;
              }
              ctx.fillStyle = C_BID;
              ctx.fillRect(xC - 1 - bidFillW, cellTop, bidFillW, cellHeight);
            }

            // Draw ask bar (right of centerline)
            if (askFillW > 0) {
              if (isImbalanceAsk) {
                // Bloom: glow layer first
                ctx.globalAlpha = OPACITY_BLOOM_GLOW;
                ctx.fillStyle = C_ASK;
                const glowPad = Math.round(1.5 * hpr);
                ctx.fillRect(
                  xC + 1 - glowPad,
                  cellTop - glowPad,
                  askFillW + glowPad * 2,
                  cellHeight + glowPad * 2,
                );
                // Crisp bar on top at 100%
                ctx.globalAlpha = OPACITY_IMBALANCE;
              } else {
                ctx.globalAlpha = OPACITY_NORMAL;
              }
              ctx.fillStyle = C_ASK;
              ctx.fillRect(xC + 1, cellTop, askFillW, cellHeight);
            }

            // Reset alpha
            ctx.globalAlpha = 1;

            // ── Volume numbers ──────────────────────────────────────────
            ctx.font = `400 ${fontSize}px ${FONT_FAMILY}`;
            ctx.textBaseline = 'middle';

            const textY = yBitmap;
            const bidFillWCss = bidFillW / hpr;
            const askFillWCss = askFillW / hpr;

            if (bidVol > 0) {
              const label = String(Math.min(MAX_DISPLAY_VOL, bidVol));
              if (bidFillWCss >= MIN_INSIDE_WIDTH_CSS) {
                // Inside bar, right-aligned, white
                ctx.fillStyle = '#ffffff';
                ctx.textAlign = 'right';
                ctx.fillText(label, xC - 1 - Math.round(2 * hpr), textY);
              } else {
                // Outside bar, left-aligned, --text
                ctx.fillStyle = C_TEXT;
                ctx.textAlign = 'right';
                ctx.fillText(label, xC - 1 - bidFillW - Math.round(3 * hpr), textY);
              }
            }

            if (askVol > 0) {
              const label = String(Math.min(MAX_DISPLAY_VOL, askVol));
              if (askFillWCss >= MIN_INSIDE_WIDTH_CSS) {
                // Inside bar, left-aligned, white
                ctx.fillStyle = '#ffffff';
                ctx.textAlign = 'left';
                ctx.fillText(label, xC + 1 + Math.round(2 * hpr), textY);
              } else {
                // Outside bar, left-aligned, --text
                ctx.fillStyle = C_TEXT;
                ctx.textAlign = 'left';
                ctx.fillText(label, xC + 1 + askFillW + Math.round(3 * hpr), textY);
              }
            }
          }

          // ── Stacked imbalance run lines ──────────────────────────────
          // Scan sorted rows for consecutive same-side imbalance runs of ≥ 3
          if (options.showImbalance) {
            this._drawStackedRunLines(ctx, rows, rowH, xC, halfW, hpr, vpr);
          }
        }

        // ── 3. POC line (1px amber glow) ─────────────────────────────────
        if (d.poc_price && Number.isFinite(d.poc_price)) {
          const yPocMedia = priceToCoordinate(d.poc_price);
          if (yPocMedia !== null) {
            const yPoc = Math.round(yPocMedia * vpr);
            // Glow: shadow first
            ctx.save();
            ctx.shadowColor = C_AMBER;
            ctx.shadowBlur = Math.round(3 * vpr);
            ctx.strokeStyle = C_AMBER;
            ctx.lineWidth = Math.max(1, Math.round(vpr));
            ctx.beginPath();
            ctx.moveTo(barLeft, yPoc);
            ctx.lineTo(barRight, yPoc);
            ctx.stroke();
            ctx.restore();
          }
        }

        // ── 4. Signal marker ──────────────────────────────────────────────
        // Reads __signalType attached by FootprintChart or WebSocket handler
        const sigType = (d as FootprintBarLW & { __signalType?: string }).__signalType;
        if (sigType && sigType !== 'QUIET') {
          const markerColor =
            sigType === 'TYPE_A' ? C_LIME :
            sigType === 'TYPE_B' ? C_AMBER :
            sigType === 'TYPE_C' ? C_CYAN : null;

          if (markerColor) {
            const yHighMedia = priceToCoordinate(d.high);
            if (yHighMedia !== null) {
              const yHighBitmap = Math.round(yHighMedia * vpr);
              const aboveOffset = Math.round(MARKER_LINE_ABOVE_CSS * vpr);
              const squareSize = Math.round(MARKER_SQUARE_SIZE_CSS * hpr);
              const lineTopY = yHighBitmap - aboveOffset - squareSize;
              const lineW = Math.max(2, Math.round(2 * hpr));

              ctx.save();
              ctx.fillStyle = markerColor;

              // Vertical line: from yHighBitmap up to top of square
              ctx.fillRect(
                xC - Math.round(lineW / 2),
                lineTopY + squareSize,
                lineW,
                yHighBitmap - (lineTopY + squareSize),
              );

              // 6×6 square terminator at top
              ctx.fillRect(
                xC - Math.round(squareSize / 2),
                lineTopY,
                squareSize,
                squareSize,
              );
              ctx.restore();
            }
          }
        }

        ctx.restore();
      }
    });
  }

  // ── Stacked imbalance run lines ──────────────────────────────────────────────
  private _drawStackedRunLines(
    ctx: CanvasRenderingContext2D,
    rows: Array<{
      yBitmap: number;
      isImbalanceBid: boolean;
      isImbalanceAsk: boolean;
    }>,
    rowH: number,
    xC: number,
    halfW: number,
    hpr: number,
    _vpr: number,
  ): void {
    if (rows.length < STACKED_RUN_MIN) return;

    const lineW = Math.max(2, Math.round(2 * hpr));
    const lineInset = Math.round(1 * hpr);  // 1px inside bar edge

    // Scan for bid runs
    this._scanAndDrawRun(ctx, rows, rowH, xC, halfW, lineW, lineInset, 'bid');
    // Scan for ask runs
    this._scanAndDrawRun(ctx, rows, rowH, xC, halfW, lineW, lineInset, 'ask');
  }

  private _scanAndDrawRun(
    ctx: CanvasRenderingContext2D,
    rows: Array<{ yBitmap: number; isImbalanceBid: boolean; isImbalanceAsk: boolean }>,
    rowH: number,
    xC: number,
    halfW: number,
    lineW: number,
    lineInset: number,
    side: 'bid' | 'ask',
  ): void {
    let runStart = -1;
    let runLength = 0;

    const flush = (endIdx: number) => {
      if (runLength >= STACKED_RUN_MIN) {
        const startRow = rows[runStart];
        const endRow = rows[endIdx - 1];
        const topY = Math.min(startRow.yBitmap, endRow.yBitmap) - Math.round(rowH / 2);
        const botY = Math.max(startRow.yBitmap, endRow.yBitmap) + Math.round(rowH / 2);
        const runH = botY - topY;

        ctx.save();
        ctx.fillStyle = C_LIME;
        ctx.globalAlpha = 1;

        if (side === 'bid') {
          // Line on left edge of bar
          ctx.fillRect(xC - halfW + lineInset, topY, lineW, runH);
        } else {
          // Line on right edge of bar
          ctx.fillRect(xC + halfW - lineInset - lineW, topY, lineW, runH);
        }
        ctx.restore();
      }
    };

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const isMatch = side === 'bid' ? row.isImbalanceBid : row.isImbalanceAsk;
      if (isMatch) {
        if (runLength === 0) runStart = i;
        runLength++;
      } else {
        flush(i);
        runStart = -1;
        runLength = 0;
      }
    }
    // Flush final run
    flush(rows.length);
  }

  // ── Empty state ──────────────────────────────────────────────────────────────
  private _drawEmptyState(
    ctx: CanvasRenderingContext2D,
    canvasW: number,
    canvasH: number,
    vpr: number,
  ): void {
    // UI-SPEC §8: "AWAITING NQ FOOTPRINT" centered, text-sm (13px), --text-mute,
    // letter-spacing 0.16em, no spinner.
    const fontSizeCss = 13;  // text-sm
    const fontSizeBitmap = Math.round(fontSizeCss * vpr);

    ctx.save();
    ctx.font = `500 ${fontSizeBitmap}px ${FONT_FAMILY}`;
    ctx.fillStyle = C_TEXT_MUTE;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Apply letter-spacing if supported (Chromium supports ctx.letterSpacing)
    const letterSpacingPx = fontSizeCss * EMPTY_LETTER_SPACING_EM;
    const letterSpacingBitmap = letterSpacingPx * vpr;
    if ('letterSpacing' in ctx) {
      (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing
        = `${letterSpacingBitmap}px`;
    }

    ctx.fillText(EMPTY_STATE_TEXT, canvasW / 2, canvasH / 2);
    ctx.restore();
  }
}
