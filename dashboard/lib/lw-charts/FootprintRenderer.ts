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
// Exact hex values matching the CSS custom properties in globals.css.
const C_BID       = '#ff2e63';   // --bid  (sellers; bearish delta)
const C_ASK       = '#00ff88';   // --ask  (buyers; bullish delta)
const C_LIME      = '#a3ff00';   // --lime (stacked imbalance run)
const C_AMBER     = '#ffd60a';   // --amber (POC row)
const C_CYAN      = '#00d9ff';   // --cyan  (TYPE_C marker)
const C_RULE      = '#1f1f1f';   // --rule  (separator lines)
const C_TEXT_DIM  = '#8a8a8a';   // --text-dim (neutral row text)
const C_TEXT_MUTE = '#4a4a4a';   // --text-mute (empty state, dim chrome)
const C_VOID      = '#000000';   // --void  (background)
const C_TEXT      = '#f5f5f5';   // --text  (imbalance row text, primary)

// Imbalance threshold ratio (3× side dominance)
const IMBALANCE_THRESHOLD = 3.0;

// Minimum consecutive rows for stacked imbalance marker
const STACKED_RUN_MIN = 3;

// Row height in CSS pixels (spec: 18px — readability wins over density)
const ROW_HEIGHT_CSS = 18;

// Font for volume numbers and chrome
const FONT_FAMILY = '"JetBrains Mono", monospace';

// text-xs (11px CSS) for cell text; scaled by vpr for Retina
const FONT_SIZE_CSS = 11;

// Min cell height (CSS px) to render text; below this → color-only mode
const MIN_ROW_H_FOR_TEXT_CSS = 14;

// Min column width (CSS px) to render full "bid × ask" label
// Below this → show only the larger side (abbreviated)
const MIN_COL_W_FOR_FULL_LABEL_CSS = 60;

// Min column width to render timestamp header
const HEADER_MIN_COL_W_CSS = 60;

// POC dot marker: 4×4px amber square on left edge of column
const POC_DOT_SIZE_CSS = 4;

// Stacked imbalance line width (CSS px)
const STACKED_LINE_W_CSS = 3;

// Delta footer constants
const DELTA_FONT_SIZE_CSS  = 11;
const DELTA_BAR_H_CSS      = 3;
const DELTA_GAP_CSS        = 6;    // gap between last row and delta label
const DELTA_LEFT_PAD_CSS   = 4;    // left margin within column

// DoS guards
const MAX_DISPLAY_VOL = 99999;
const MAX_BARS_CAP    = 500;

// Empty state text
const EMPTY_TEXT     = 'NO FOOTPRINT DATA';
const EMPTY_SUB_TEXT = 'waiting for stream\u2026';

// Unicode multiply sign for "bid × ask" display
const UNICODE_TIMES = '\u00d7';
// Unicode minus for negative delta
const UNICODE_MINUS = '\u2212';

// ── Text width cache ──────────────────────────────────────────────────────────
// Pre-cache measured widths for numbers 0-999 to avoid repeated measureText
// calls in the hot path. Key is `${fontSize}:${n}` → width in bitmap pixels.
const _textWidthCache = new Map<string, number>();

function _cachedTextWidth(
  ctx:      CanvasRenderingContext2D,
  n:        number,
  font:     string,
  fontSize: number,
): number {
  const key = `${fontSize}:${n}`;
  let w = _textWidthCache.get(key);
  if (w !== undefined) return w;
  // Measure — font must already be set on ctx
  ctx.font = font;
  w = ctx.measureText(String(Math.min(n, MAX_DISPLAY_VOL))).width;
  if (_textWidthCache.size < 4000) _textWidthCache.set(key, w);   // bounded cache
  return w;
}

// ── Row analysis ──────────────────────────────────────────────────────────────

interface RowInfo {
  price:          number;
  yBitmap:        number;
  bidVol:         number;
  askVol:         number;
  isImbalanceBid: boolean;   // bid/ask ≥ 3× and bid dominates
  isImbalanceAsk: boolean;   // ask/bid ≥ 3× and ask dominates
}

// ── Renderer ──────────────────────────────────────────────────────────────────

export class FootprintRenderer implements ICustomSeriesPaneRenderer {
  private _data: PaneRendererCustomData<Time, FootprintBarLW> | null = null;
  private _options: FootprintSeriesOptions | null = null;

  update(
    data: PaneRendererCustomData<Time, FootprintBarLW>,
    options: FootprintSeriesOptions,
  ): void {
    this._data    = data;
    this._options = options;
  }

  draw(
    target: CanvasRenderingTarget2D,
    priceToCoordinate: PriceToCoordinateConverter,
  ): void {
    const data    = this._data;
    const options = this._options;
    if (!data || !options) return;

    target.useBitmapCoordinateSpace((scope) => {
      const ctx     = scope.context;
      const hpr     = scope.horizontalPixelRatio;
      const vpr     = scope.verticalPixelRatio;
      const canvasW = scope.bitmapSize.width;
      const canvasH = scope.bitmapSize.height;

      // Full clear — pure black background (--void)
      ctx.fillStyle = C_VOID;
      ctx.fillRect(0, 0, canvasW, canvasH);

      const range = data.visibleRange;

      // ── Empty state ───────────────────────────────────────────────────────
      if (!range || data.bars.length === 0) {
        _drawEmptyState(ctx, canvasW, canvasH, vpr);
        return;
      }

      // Derived dimensions in bitmap pixels
      const rowH    = Math.max(1, Math.round(ROW_HEIGHT_CSS * vpr));
      const fontSize = Math.max(6, Math.round(FONT_SIZE_CSS * vpr));
      const font     = `400 ${fontSize}px ${FONT_FAMILY}`;

      // Column width in bitmap pixels (barSpacing is in media/CSS pixels)
      const colW = Math.round(data.barSpacing * hpr);

      // Inner column bounds — 1px gap each side for the column separator
      const GAP_BITMAP = Math.max(1, Math.round(1 * hpr));
      const innerW     = Math.max(2, colW - GAP_BITMAP * 2);

      const to = Math.min(range.to, data.bars.length - 1, MAX_BARS_CAP - 1);

      // ── Compute cross-bar maxima for scaling ──────────────────────────────
      // max_abs_delta: for delta bar scaling
      // max_total_vol: for neutral cell alpha scaling
      let maxAbsDelta  = 1;
      let maxTotalVol  = 1;

      for (let i = range.from; i <= to; i++) {
        const bar = data.bars[i];
        if (!bar?.originalData) continue;
        const absDelta = Math.abs(bar.originalData.bar_delta ?? 0);
        if (absDelta > maxAbsDelta) maxAbsDelta = absDelta;

        if (bar.originalData.levels) {
          for (const key of Object.keys(bar.originalData.levels)) {
            const lv = bar.originalData.levels[key];
            if (!lv) continue;
            const tv = clampVol(lv.bid_vol) + clampVol(lv.ask_vol);
            if (tv > maxTotalVol) maxTotalVol = tv;
          }
        }
      }

      // ── Per-bar render ────────────────────────────────────────────────────
      for (let i = range.from; i <= to; i++) {
        const bar = data.bars[i];
        if (!bar) continue;
        const d = bar.originalData;
        if (!d || !d.levels) continue;

        // Bar center in bitmap pixels
        const xC = Math.round(bar.x * hpr);

        // Column left edge
        const colLeft  = xC - Math.floor(innerW / 2);
        const colRight = colLeft + innerW;

        // ── 1. Column separator (1px --rule line at left edge of column) ──
        ctx.fillStyle = C_RULE;
        ctx.fillRect(colLeft - GAP_BITMAP, 0, Math.max(1, GAP_BITMAP), canvasH);

        const levelKeys = Object.keys(d.levels);
        if (levelKeys.length === 0) continue;

        // ── 2. Find POC price + per-bar max total volume ──────────────────
        let pocPrice:   number | null = null;
        let pocVolMax   = 0;

        if (d.poc_price && Number.isFinite(d.poc_price)) {
          pocPrice = d.poc_price;
        }

        let barMaxTotalVol = 1;
        for (const key of levelKeys) {
          const lv = d.levels[key];
          if (!lv) continue;
          const tv = clampVol(lv.bid_vol) + clampVol(lv.ask_vol);
          if (tv > barMaxTotalVol) barMaxTotalVol = tv;
          if (pocPrice === null && tv > pocVolMax) {
            pocVolMax = tv;
            pocPrice  = Number(key) * 0.25;
          }
        }

        // ── 3. Build sorted row array (high price → low price = top → bottom) ──
        const rows: RowInfo[] = [];
        for (const tickKey of levelKeys) {
          const tick = Number(tickKey);
          if (!Number.isFinite(tick)) continue;
          const price  = tick * 0.25;     // NQ tick size = 0.25 pts
          const yMedia = priceToCoordinate(price);
          if (yMedia === null) continue;
          const yBitmap = Math.round(yMedia * vpr);

          const lv = d.levels[tickKey];
          if (!lv) continue;

          const bidVol = clampVol(lv.bid_vol);
          const askVol = clampVol(lv.ask_vol);
          const imbRatio = askVol / Math.max(bidVol, 1);

          rows.push({
            price,
            yBitmap,
            bidVol,
            askVol,
            isImbalanceBid: options.showImbalance && imbRatio <= (1 / IMBALANCE_THRESHOLD),
            isImbalanceAsk: options.showImbalance && imbRatio >= IMBALANCE_THRESHOLD,
          });
        }

        // Sort price descending (higher price → top of chart → lower yBitmap)
        rows.sort((a, b) => b.price - a.price);

        // ── 4. Clip to this column — prevents overflow into neighbors ────────
        ctx.save();
        ctx.beginPath();
        ctx.rect(colLeft, 0, innerW, canvasH);
        ctx.clip();

        // ── 5. Draw all cell backgrounds + text ────────────────────────────
        const colWCss = innerW / hpr;

        for (const row of rows) {
          const isPoc = pocPrice !== null && Math.abs(row.price - pocPrice) < 0.01;
          _drawNumberCell(
            ctx, row, colLeft, innerW, rowH, fontSize, font,
            hpr, vpr, isPoc, barMaxTotalVol, colWCss,
          );
        }

        ctx.restore();   // clip ends

        // ── 6. Stacked imbalance run lines (drawn outside clip so they sit
        //       exactly on the column edge without being clipped away) ──────
        if (options.showImbalance && rows.length >= STACKED_RUN_MIN) {
          _drawStackedRunLines(ctx, rows, rowH, colLeft, colRight, hpr, vpr);
        }

        // ── 7. POC dot marker — 4×4 amber square on left edge at POC row ──
        if (pocPrice !== null) {
          const yPocMedia = priceToCoordinate(pocPrice);
          if (yPocMedia !== null) {
            const yPoc   = Math.round(yPocMedia * vpr);
            const dotSzB = Math.max(2, Math.round(POC_DOT_SIZE_CSS * hpr));
            const dotH   = Math.max(2, Math.round(POC_DOT_SIZE_CSS * vpr));
            ctx.fillStyle = C_AMBER;
            ctx.fillRect(
              colLeft - dotSzB,
              yPoc - Math.floor(dotH / 2),
              dotSzB,
              dotH,
            );
          }
        }

        // ── 8. Delta footer ───────────────────────────────────────────────
        if (options.showDelta) {
          // Find the bottom-most row Y
          let bottomY = 0;
          for (const row of rows) {
            const rowBottom = row.yBitmap + Math.ceil(rowH / 2);
            if (rowBottom > bottomY) bottomY = rowBottom;
          }
          if (bottomY === 0) {
            bottomY = canvasH - Math.round((DELTA_GAP_CSS + DELTA_FONT_SIZE_CSS + 8) * vpr);
          }

          _drawDeltaFooter(
            ctx, d.bar_delta ?? 0, maxAbsDelta,
            colLeft, innerW, bottomY, hpr, vpr,
          );
        }

        // ── 9. Bar timestamp header ───────────────────────────────────────
        // Only when column is wide enough
        if (colWCss > HEADER_MIN_COL_W_CSS) {
          let topRowY = canvasH;
          for (const row of rows) {
            const rowTop = row.yBitmap - Math.floor(rowH / 2);
            if (rowTop < topRowY) topRowY = rowTop;
          }
          _drawTimestamp(ctx, xC, topRowY, d.time, hpr, vpr);
        }

        // ── 10. Signal marker ─────────────────────────────────────────────
        const sigType = (d as FootprintBarLW & { __signalType?: string }).__signalType;
        if (sigType && sigType !== 'QUIET') {
          const markerColor =
            sigType === 'TYPE_A' ? C_LIME  :
            sigType === 'TYPE_B' ? C_AMBER :
            sigType === 'TYPE_C' ? C_CYAN  : null;

          if (markerColor) {
            const yHighMedia = priceToCoordinate(d.high);
            if (yHighMedia !== null) {
              _drawSignalMarker(ctx, xC, Math.round(yHighMedia * vpr), markerColor, hpr, vpr);
            }
          }
        }
      }
    });
  }
}

// ── Numbers Bar cell ──────────────────────────────────────────────────────────
// The core of the Numbers Bar style: full-width cell with colored background
// and centered "bid × ask" text (or abbreviated form when narrow).

function _drawNumberCell(
  ctx:           CanvasRenderingContext2D,
  row:           RowInfo,
  colLeft:       number,
  innerW:        number,
  rowH:          number,
  fontSize:      number,
  font:          string,
  hpr:           number,
  vpr:           number,
  isPoc:         boolean,
  barMaxTotalVol: number,
  colWCss:       number,
): void {
  const { yBitmap, bidVol, askVol, isImbalanceBid, isImbalanceAsk } = row;

  const cellTop = yBitmap - Math.floor(rowH / 2);
  const cellH   = Math.max(1, rowH - 1);   // 1px inter-row gap

  // ── Background color ──────────────────────────────────────────────────────
  let bgColor: string;
  let textColor: string;

  const imbRatio = askVol / Math.max(bidVol, 1);

  if (isPoc) {
    // POC override — amber background, black text, max priority
    bgColor   = 'rgba(255, 214, 10, 0.35)';
    textColor = '#000000';
  } else if (isImbalanceAsk || imbRatio >= IMBALANCE_THRESHOLD) {
    // BUY imbalance — ask dominates
    bgColor   = 'rgba(0, 255, 136, 0.22)';
    textColor = C_TEXT;
  } else if (isImbalanceBid || imbRatio <= (1 / IMBALANCE_THRESHOLD)) {
    // SELL imbalance — bid dominates
    bgColor   = 'rgba(255, 46, 99, 0.22)';
    textColor = C_TEXT;
  } else {
    // Neutral — slight alpha scaled by volume activity
    const totalVol   = bidVol + askVol;
    const totalRatio = barMaxTotalVol > 0 ? totalVol / barMaxTotalVol : 0;
    const alpha      = 0.02 + totalRatio * 0.06;
    bgColor   = `rgba(255, 255, 255, ${alpha.toFixed(3)})`;
    textColor = C_TEXT_DIM;
  }

  // Fill cell background
  ctx.fillStyle = bgColor;
  ctx.fillRect(colLeft, cellTop, innerW, cellH);

  // ── Text rendering ────────────────────────────────────────────────────────
  const rowHCss = rowH / vpr;
  if (rowHCss < MIN_ROW_H_FOR_TEXT_CSS) return;   // color-only mode

  ctx.save();
  ctx.font         = font;
  ctx.textBaseline = 'middle';
  ctx.fillStyle    = textColor;

  const textY  = yBitmap;
  const centerX = colLeft + Math.floor(innerW / 2);

  const bidLabel = String(Math.min(MAX_DISPLAY_VOL, bidVol));
  const askLabel = String(Math.min(MAX_DISPLAY_VOL, askVol));

  if (colWCss < MIN_COL_W_FOR_FULL_LABEL_CSS) {
    // Abbreviated: show only the dominant side with arrow prefix
    const showAsk = askVol >= bidVol;
    const abbrev  = showAsk ? `\u2191${askLabel}` : `\u2193${bidLabel}`;
    ctx.textAlign = 'center';
    ctx.fillText(abbrev, centerX, textY);
  } else {
    // Full "bid × ask" label centered in cell
    const label = `${bidLabel} ${UNICODE_TIMES} ${askLabel}`;
    ctx.textAlign = 'center';
    ctx.fillText(label, centerX, textY);

    // Measure for the cache side-effect only (warms cache for common values)
    _cachedTextWidth(ctx, bidVol, font, fontSize);
    _cachedTextWidth(ctx, askVol, font, fontSize);
  }

  ctx.restore();
}

// ── Stacked imbalance run lines ───────────────────────────────────────────────
// When 3+ consecutive rows imbalanced in the same direction:
// draw a 3px crisp vertical lime line on the imbalance-side edge.
// Left edge for SELL (bid) imbalance, right edge for BUY (ask) imbalance.

function _drawStackedRunLines(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  colLeft:  number,
  colRight: number,
  hpr:      number,
  _vpr:     number,
): void {
  const lineW = Math.max(2, Math.round(STACKED_LINE_W_CSS * hpr));
  _scanAndDrawRun(ctx, rows, rowH, colLeft, colRight, lineW, 'bid');
  _scanAndDrawRun(ctx, rows, rowH, colLeft, colRight, lineW, 'ask');
}

function _scanAndDrawRun(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  colLeft:  number,
  colRight: number,
  lineW:    number,
  side:     'bid' | 'ask',
): void {
  let runStart = -1;
  let runLen   = 0;

  const flush = (endIdx: number) => {
    if (runLen < STACKED_RUN_MIN) return;
    const startRow = rows[runStart];
    const endRow   = rows[endIdx - 1];
    const topY     = Math.min(startRow.yBitmap, endRow.yBitmap) - Math.floor(rowH / 2);
    const botY     = Math.max(startRow.yBitmap, endRow.yBitmap) + Math.ceil(rowH / 2);
    const runH     = botY - topY;

    // Crisp line — no shadow/blur
    ctx.save();
    ctx.fillStyle = C_LIME;
    const lineX   = side === 'bid' ? colLeft : colRight - lineW;
    ctx.fillRect(lineX, topY, lineW, runH);
    ctx.restore();
  };

  for (let i = 0; i < rows.length; i++) {
    const match = side === 'bid' ? rows[i].isImbalanceBid : rows[i].isImbalanceAsk;
    if (match) {
      if (runLen === 0) runStart = i;
      runLen++;
    } else {
      flush(i);
      runStart = -1;
      runLen   = 0;
    }
  }
  flush(rows.length);
}

// ── Delta footer ──────────────────────────────────────────────────────────────
// Below the last row: "Δ +250" label (mono, colored by sign) +
// a tiny horizontal bar showing |delta| / max_abs_delta.

function _drawDeltaFooter(
  ctx:         CanvasRenderingContext2D,
  barDelta:    number,
  maxAbsDelta: number,
  colLeft:     number,
  innerW:      number,
  bottomRowY:  number,
  hpr:         number,
  vpr:         number,
): void {
  if (!Number.isFinite(barDelta) || maxAbsDelta <= 0) return;

  const gapH      = Math.round(DELTA_GAP_CSS * vpr);
  const fontSzPx  = Math.max(6, Math.round(DELTA_FONT_SIZE_CSS * vpr));
  const barH      = Math.max(2, Math.round(DELTA_BAR_H_CSS * vpr));
  const leftPadB  = Math.round(DELTA_LEFT_PAD_CSS * hpr);

  const color = barDelta > 0 ? C_ASK : barDelta < 0 ? C_BID : C_TEXT_MUTE;

  // Delta label: "Δ +250" or "Δ −250"
  const absVal = Math.abs(barDelta);
  const sign   = barDelta > 0 ? '+' : barDelta < 0 ? UNICODE_MINUS : '';
  const label  = `\u0394 ${sign}${absVal}`;

  const labelY = bottomRowY + gapH;

  ctx.save();
  ctx.font         = `400 ${fontSzPx}px ${FONT_FAMILY}`;
  ctx.fillStyle    = color;
  ctx.textAlign    = 'left';
  ctx.textBaseline = 'top';
  ctx.globalAlpha  = 0.85;
  ctx.fillText(label, colLeft + leftPadB, labelY);

  // Mini horizontal bar below label
  const ratio  = Math.min(1, Math.abs(barDelta) / maxAbsDelta);
  const barW   = Math.max(2, Math.round(innerW * ratio));
  const miniY  = labelY + fontSzPx + Math.round(2 * vpr);

  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.70;
  ctx.fillRect(colLeft + leftPadB, miniY, barW - leftPadB, barH);
  ctx.restore();

  void hpr;
}

// ── Bar timestamp header ──────────────────────────────────────────────────────
// "HH:MM" in 10px mono --text-mute at top-center of each column.

function _drawTimestamp(
  ctx:      CanvasRenderingContext2D,
  xC:       number,
  topRowY:  number,
  barTime:  Time,
  _hpr:     number,
  vpr:      number,
): void {
  const fontSzPx = Math.max(5, Math.round(10 * vpr));
  const gapY     = Math.round(3 * vpr);

  let timeStr = '';
  if (typeof barTime === 'number') {
    const dt = new Date(barTime * 1000);
    const hh = String(dt.getUTCHours()).padStart(2, '0');
    const mm = String(dt.getUTCMinutes()).padStart(2, '0');
    timeStr = `${hh}:${mm}`;
  } else if (typeof barTime === 'string') {
    timeStr = (barTime as string).length >= 16
      ? (barTime as string).slice(11, 16)
      : (barTime as string);
  }

  if (!timeStr) return;

  ctx.save();
  ctx.font         = `400 ${fontSzPx}px ${FONT_FAMILY}`;
  ctx.fillStyle    = C_TEXT_MUTE;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'bottom';
  ctx.globalAlpha  = 0.7;
  ctx.fillText(timeStr, xC, topRowY - gapY);
  ctx.restore();
}

// ── Signal marker ─────────────────────────────────────────────────────────────
// 2px vertical tier-color line above bar + 6×6 square + halo circle.
// Preserved from prior renderer (valuable visual anchor).

function _drawSignalMarker(
  ctx:         CanvasRenderingContext2D,
  xC:          number,
  yHighBitmap: number,
  color:       string,
  hpr:         number,
  vpr:         number,
): void {
  const aboveOffset = Math.round(8 * vpr);
  const squareSize  = Math.round(6 * hpr);
  const lineW       = Math.max(2, Math.round(2 * hpr));

  const squareTopY = yHighBitmap - aboveOffset - squareSize;
  const lineTopY   = squareTopY + squareSize;
  const lineH      = yHighBitmap - lineTopY;

  ctx.save();

  // Halo circle behind square
  const haloR = Math.round((squareSize / 2) + 2 * hpr);
  ctx.beginPath();
  ctx.arc(xC, squareTopY + Math.floor(squareSize / 2), haloR, 0, Math.PI * 2);
  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.3;
  ctx.fill();

  ctx.globalAlpha = 1;
  ctx.fillStyle   = color;

  // Vertical line
  if (lineH > 0) {
    ctx.fillRect(xC - Math.floor(lineW / 2), lineTopY, lineW, lineH);
  }

  // 6×6 filled square
  ctx.fillRect(xC - Math.floor(squareSize / 2), squareTopY, squareSize, squareSize);

  ctx.restore();
}

// ── Empty state ───────────────────────────────────────────────────────────────
// "NO FOOTPRINT DATA" + italic subtitle in --text-mute.

function _drawEmptyState(
  ctx:     CanvasRenderingContext2D,
  canvasW: number,
  canvasH: number,
  vpr:     number,
): void {
  const fontSzPx    = Math.round(13 * vpr);
  const subFontSzPx = Math.round(11 * vpr);
  const lsBitmap    = 13 * 0.1 * vpr;   // 0.1em letter-spacing

  const centerX = canvasW / 2;
  const centerY = canvasH / 2;

  ctx.save();
  ctx.fillStyle    = C_TEXT_MUTE;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';

  // Primary line: letter-spaced
  ctx.font = `500 ${fontSzPx}px ${FONT_FAMILY}`;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing
      = `${lsBitmap}px`;
  }
  ctx.fillText(EMPTY_TEXT, centerX, centerY);

  // Secondary line: italic, smaller
  ctx.font = `italic 400 ${subFontSzPx}px ${FONT_FAMILY}`;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = '0px';
  }
  ctx.globalAlpha = 0.6;
  ctx.fillText(EMPTY_SUB_TEXT, centerX, centerY + fontSzPx + Math.round(4 * vpr));

  ctx.restore();

  // Suppress unused-variable lint
  void C_CYAN;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function clampVol(v: number | undefined | null): number {
  if (v === undefined || v === null || !Number.isFinite(v)) return 0;
  return Math.min(MAX_DISPLAY_VOL, Math.max(0, v));
}
