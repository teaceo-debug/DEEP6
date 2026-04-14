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
const C_AMBER     = '#ffd60a';   // --amber (POC line)
const C_CYAN      = '#00d9ff';   // --cyan  (TYPE_C marker)
const C_RULE      = '#1f1f1f';   // --rule  (separator lines, grid)
const C_TEXT      = '#f5f5f5';   // --text  (labels)
const C_TEXT_MUTE = '#4a4a4a';   // --text-mute (empty state)
const C_VOID      = '#000000';   // --void  (background)
const C_WHITE     = '#ffffff';   // pure white (imbalance outline, vol numbers)

// Imbalance threshold ratio (3× side dominance)
const IMBALANCE_THRESHOLD = 3.0;

// Minimum consecutive rows for a stacked run line
const STACKED_RUN_MIN = 3;

// Row height in CSS pixels (UI-SPEC §3: 16px density target)
const ROW_HEIGHT_CSS = 16;

// Font for volume numbers and empty state
const FONT_FAMILY = '"JetBrains Mono", monospace';
const FONT_SIZE_CSS = 10;   // text-xs (was 11 — slightly tighter for density)

// Min bar fill width (CSS px) to render volume number inside the bar
const MIN_INSIDE_W_CSS = 40;

// Min row height (CSS px) to render any volume number at all
const MIN_ROW_H_CSS = 14;

// POC line height (bitmap px) — taller than 1px for presence
const POC_LINE_H = 1.5;

// Signal marker dimensions (CSS px)
const MARKER_ABOVE_CSS = 8;
const MARKER_SQ_CSS    = 6;

// DoS guards
const MAX_DISPLAY_VOL = 99999;
const MAX_BARS_CAP    = 500;

// Empty state
const EMPTY_TEXT           = 'AWAITING NQ FOOTPRINT';
const EMPTY_LETTER_SPACING = 0.16;  // em

// ── Row analysis ──────────────────────────────────────────────────────────────

interface RowInfo {
  price:           number;
  yBitmap:         number;
  bidVol:          number;
  askVol:          number;
  isImbalanceBid:  boolean;   // bid/ask ≥ 3× and bid dominates
  isImbalanceAsk:  boolean;   // ask/bid ≥ 3× and ask dominates
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
      const ctx  = scope.context;
      const hpr  = scope.horizontalPixelRatio;
      const vpr  = scope.verticalPixelRatio;
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

      // Derived dimensions (bitmap pixels)
      const rowH   = Math.max(1, Math.round(ROW_HEIGHT_CSS * vpr));
      const fontSize = Math.max(6, Math.round(FONT_SIZE_CSS * vpr));

      // ─ barSpacing from LW Charts (media pixels) → bitmap pixels ─────────
      // data.barSpacing is in media pixels; each column's full bitmap width.
      const colW = Math.round(data.barSpacing * hpr);

      // Column inner width: full column minus 2px gap each side → clean separator
      // halfBarW = usable half-width in bitmap pixels, clamped to [2, ∞)
      const GAP_EACH_SIDE = Math.round(2 * hpr);   // 2px CSS gap → bitmap
      const halfBarW = Math.max(2, Math.floor((colW - GAP_EACH_SIDE * 2) / 2));

      const to = Math.min(range.to, data.bars.length - 1, MAX_BARS_CAP - 1);

      for (let i = range.from; i <= to; i++) {
        const bar = data.bars[i];
        if (!bar) continue;
        const d = bar.originalData;
        if (!d || !d.levels) continue;

        // Bar center in bitmap pixels
        const xC = Math.round(bar.x * hpr);

        // Precise column bounds (exclusive of gap)
        const colLeft  = xC - halfBarW;
        const colRight = xC + halfBarW;

        // ── 1. Column separator (--rule, 1px at boundary before this bar) ──
        // Draw at the left edge of the column's gap region.
        ctx.fillStyle = C_RULE;
        ctx.fillRect(colLeft - GAP_EACH_SIDE, 0, 1, canvasH);

        const levelKeys = Object.keys(d.levels);
        if (levelKeys.length === 0) continue;

        // ── 2. Compute per-bar max volume (cluster-local, not global) ──────
        // This matches TapeFlow's bug-fix: scale to THIS bar's max so no
        // overflow into neighbors. See TAPEFLOW-CANVAS-PATTERN.md §8.
        let maxVol = 1;
        for (const key of levelKeys) {
          const lv = d.levels[key];
          if (!lv) continue;
          const b = clampVol(lv.bid_vol);
          const a = clampVol(lv.ask_vol);
          const t = b + a;
          if (Number.isFinite(t) && t > maxVol) maxVol = t;
        }

        // ── 3. Build sorted row array ─────────────────────────────────────
        const rows: RowInfo[] = [];
        for (const tickKey of levelKeys) {
          const tick = Number(tickKey);
          if (!Number.isFinite(tick)) continue;
          const price   = tick * 0.25;     // NQ tick size = 0.25 pts
          const yMedia  = priceToCoordinate(price);
          if (yMedia === null) continue;
          const yBitmap = Math.round(yMedia * vpr);

          const lv = d.levels[tickKey];
          if (!lv) continue;

          const bidVol = clampVol(lv.bid_vol);
          const askVol = clampVol(lv.ask_vol);

          // Imbalance: dominant side ≥ 3× the other
          const maxSide = Math.max(bidVol, askVol);
          const minSide = Math.max(1, Math.min(bidVol, askVol));
          const ratio   = maxSide / minSide;

          rows.push({
            price,
            yBitmap,
            bidVol,
            askVol,
            isImbalanceBid: options.showImbalance && bidVol > askVol && ratio >= IMBALANCE_THRESHOLD,
            isImbalanceAsk: options.showImbalance && askVol > bidVol && ratio >= IMBALANCE_THRESHOLD,
          });
        }

        // Sort price descending (higher price = lower yBitmap = closer to top)
        rows.sort((a, b) => b.price - a.price);

        // ── 4. Background grid rows (every 5 ticks, --rule at 50% alpha) ──
        _drawBackgroundGrid(ctx, rows, rowH, colLeft, colRight, canvasH, vpr);

        // ── 5. Per-row volume bars (with clip enforcing column containment) ─
        ctx.save();

        // Clip to this column's usable area — prevents any draw (including
        // bloom glow) from escaping into adjacent columns.
        ctx.beginPath();
        ctx.rect(colLeft, 0, halfBarW * 2, canvasH);
        ctx.clip();

        for (const row of rows) {
          _drawRow(ctx, row, xC, halfBarW, maxVol, rowH, fontSize, hpr, vpr);
        }

        ctx.restore();   // clip ends

        // ── 6. Stacked imbalance run lines (drawn AFTER clip restore so the
        //       2px line sits exactly on the column edge, not clipped) ──────
        if (options.showImbalance && rows.length >= STACKED_RUN_MIN) {
          _drawStackedRunLines(ctx, rows, rowH, xC, halfBarW, hpr);
        }

        // ── 7. POC line (amber, glowing, drawn over entire column width) ──
        if (d.poc_price && Number.isFinite(d.poc_price)) {
          const yPocMedia = priceToCoordinate(d.poc_price);
          if (yPocMedia !== null) {
            const yPoc  = Math.round(yPocMedia * vpr);
            const lineH = Math.max(1, Math.round(POC_LINE_H * vpr));

            ctx.save();
            // Real bloom via double shadowBlur pass
            ctx.shadowColor = C_AMBER;
            ctx.shadowBlur  = Math.round(8 * vpr);
            ctx.fillStyle   = C_AMBER;
            ctx.globalAlpha = 1;
            ctx.fillRect(colLeft, yPoc - Math.floor(lineH / 2), halfBarW * 2, lineH);
            ctx.shadowBlur  = Math.round(3 * vpr);
            ctx.fillRect(colLeft, yPoc - Math.floor(lineH / 2), halfBarW * 2, lineH);
            ctx.restore();
          }
        }

        // ── 8. Signal marker ──────────────────────────────────────────────
        // TODO: wire signal_marker_tier from Zustand signals slice when
        // the signals store exposes per-bar tier data. For now reads the
        // __signalType duck-typed field attached by FootprintChart or the
        // WebSocket handler. Skip gracefully when absent.
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

// ── Per-row draw helper ───────────────────────────────────────────────────────

function _drawRow(
  ctx:       CanvasRenderingContext2D,
  row:       RowInfo,
  xC:        number,
  halfBarW:  number,
  maxVol:    number,
  rowH:      number,
  fontSize:  number,
  hpr:       number,
  vpr:       number,
): void {
  const { yBitmap, bidVol, askVol, isImbalanceBid, isImbalanceAsk } = row;

  // Cell bounds
  const cellTop = yBitmap - Math.floor(rowH / 2);
  const cellH   = rowH - 1;   // 1px inter-row gap

  // Volume ratios for fill width and opacity
  const bidRatio = Number.isFinite(bidVol / maxVol) ? bidVol / maxVol : 0;
  const askRatio = Number.isFinite(askVol / maxVol) ? askVol / maxVol : 0;

  // Fill widths in bitmap pixels, clamped to halfBarW
  const bidFillW = Math.min(halfBarW, Math.max(0, Math.round(halfBarW * bidRatio)));
  const askFillW = Math.min(halfBarW, Math.max(0, Math.round(halfBarW * askRatio)));

  // Opacity: Bookmap-style intensity — volume/maxVol drives saturation.
  // Floor at 0.15 so even thin volume is still visible; cap at 0.92.
  const bidAlpha = isImbalanceBid ? 1.0 : Math.max(0.15, Math.min(0.92, 0.2 + bidRatio * 0.72));
  const askAlpha = isImbalanceAsk ? 1.0 : Math.max(0.15, Math.min(0.92, 0.2 + askRatio * 0.72));

  // ── Bid bar (left of centerline) ─────────────────────────────────────────
  if (bidFillW > 0) {
    ctx.globalAlpha = bidAlpha;
    ctx.fillStyle   = C_BID;
    ctx.fillRect(xC - bidFillW, cellTop, bidFillW, cellH);
    ctx.globalAlpha = 1;

    // Imbalance: crisp 1px white outline on the dominant side's bar
    if (isImbalanceBid) {
      ctx.save();
      ctx.strokeStyle = C_WHITE;
      ctx.lineWidth   = Math.max(1, Math.round(hpr));
      ctx.globalAlpha = 0.9;
      ctx.strokeRect(xC - bidFillW + 0.5, cellTop + 0.5, bidFillW - 1, cellH - 1);
      ctx.restore();
    }
  }

  // ── Ask bar (right of centerline) ────────────────────────────────────────
  if (askFillW > 0) {
    ctx.globalAlpha = askAlpha;
    ctx.fillStyle   = C_ASK;
    ctx.fillRect(xC, cellTop, askFillW, cellH);
    ctx.globalAlpha = 1;

    // Imbalance outline
    if (isImbalanceAsk) {
      ctx.save();
      ctx.strokeStyle = C_WHITE;
      ctx.lineWidth   = Math.max(1, Math.round(hpr));
      ctx.globalAlpha = 0.9;
      ctx.strokeRect(xC + 0.5, cellTop + 0.5, askFillW - 1, cellH - 1);
      ctx.restore();
    }
  }

  // ── Volume numbers ────────────────────────────────────────────────────────
  // Only render when: column is wide enough AND row is tall enough
  const bidFillWCss = bidFillW / hpr;
  const rowHCss     = rowH / vpr;
  if (rowHCss < MIN_ROW_H_CSS) return;   // row too short — skip all numbers

  ctx.font         = `400 ${fontSize}px ${FONT_FAMILY}`;
  ctx.textBaseline = 'middle';

  const textY = yBitmap;
  const PAD   = Math.round(2 * hpr);

  if (bidVol > 0) {
    const label = String(Math.min(MAX_DISPLAY_VOL, bidVol));
    if (bidFillWCss >= MIN_INSIDE_W_CSS) {
      // Render inside bar, right-aligned, semi-transparent white
      ctx.fillStyle  = 'rgba(255,255,255,0.75)';
      ctx.textAlign  = 'right';
      ctx.fillText(label, xC - PAD, textY);
    }
    // else: skip — color intensity carries the data story on narrow columns
  }

  if (askVol > 0) {
    const label = String(Math.min(MAX_DISPLAY_VOL, askVol));
    const askFillWCss = askFillW / hpr;
    if (askFillWCss >= MIN_INSIDE_W_CSS) {
      // Render inside bar, left-aligned, semi-transparent white
      ctx.fillStyle  = 'rgba(255,255,255,0.75)';
      ctx.textAlign  = 'left';
      ctx.fillText(label, xC + PAD, textY);
    }
  }
}

// ── Background grid rows ──────────────────────────────────────────────────────
// Every 5 ticks draw a subtle horizontal rule in --rule at 50% alpha.
// This gives the eye horizontal anchors across the bar grid.

function _drawBackgroundGrid(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  colLeft:  number,
  colRight: number,
  canvasH:  number,
  _vpr:     number,
): void {
  // We only draw grid lines for rows that happen to fall on a 5-tick boundary.
  // Rows are already sorted by price desc. Tick index = round(price / 0.25).
  ctx.fillStyle   = C_RULE;
  ctx.globalAlpha = 0.5;

  for (const row of rows) {
    const tickIndex = Math.round(row.price / 0.25);
    if (tickIndex % 5 !== 0) continue;

    const lineY = row.yBitmap - Math.floor(rowH / 2);
    const lineH = Math.max(1, 1);

    // Draw the full width across all columns (we rely on caller iterating bars)
    // Actually draw full canvas width so the grid reads as a continuous line.
    ctx.fillRect(0, lineY, canvasH > 0 ? 99999 : colRight - colLeft, lineH);
  }

  ctx.globalAlpha = 1;

  // Suppress unused-variable lint
  void colLeft;
  void colRight;
}

// ── Stacked imbalance run lines ───────────────────────────────────────────────
// 3+ consecutive same-side imbalanced cells → 2px vertical --lime line on that
// edge spanning the run, with glow.

function _drawStackedRunLines(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  xC:       number,
  halfBarW: number,
  hpr:      number,
): void {
  const lineW    = Math.max(2, Math.round(2 * hpr));

  _scanAndDrawRun(ctx, rows, rowH, xC, halfBarW, lineW, 'bid');
  _scanAndDrawRun(ctx, rows, rowH, xC, halfBarW, lineW, 'ask');
}

function _scanAndDrawRun(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  xC:       number,
  halfBarW: number,
  lineW:    number,
  side:     'bid' | 'ask',
): void {
  let runStart = -1;
  let runLen   = 0;

  const flush = (endIdx: number) => {
    if (runLen < STACKED_RUN_MIN) return;
    const startRow = rows[runStart];
    const endRow   = rows[endIdx - 1];
    const topY  = Math.min(startRow.yBitmap, endRow.yBitmap) - Math.floor(rowH / 2);
    const botY  = Math.max(startRow.yBitmap, endRow.yBitmap) + Math.ceil(rowH / 2);
    const runH  = botY - topY;

    ctx.save();
    ctx.fillStyle   = C_LIME;
    ctx.globalAlpha = 1;
    ctx.shadowColor = C_LIME;
    ctx.shadowBlur  = 6;

    if (side === 'bid') {
      ctx.fillRect(xC - halfBarW, topY, lineW, runH);
    } else {
      ctx.fillRect(xC + halfBarW - lineW, topY, lineW, runH);
    }
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

// ── Signal marker ─────────────────────────────────────────────────────────────
// 2px vertical line above bar + 6×6 square terminator in tier color.

function _drawSignalMarker(
  ctx:         CanvasRenderingContext2D,
  xC:          number,
  yHighBitmap: number,
  color:       string,
  hpr:         number,
  vpr:         number,
): void {
  const aboveOffset = Math.round(MARKER_ABOVE_CSS * vpr);
  const squareSize  = Math.round(MARKER_SQ_CSS * hpr);
  const lineW       = Math.max(2, Math.round(2 * hpr));

  // Square sits above the gap
  const squareTopY  = yHighBitmap - aboveOffset - squareSize;
  const lineTopY    = squareTopY + squareSize;
  const lineH       = yHighBitmap - lineTopY;

  ctx.save();
  ctx.fillStyle = color;

  // Vertical line from bar top to square bottom
  if (lineH > 0) {
    ctx.fillRect(xC - Math.floor(lineW / 2), lineTopY, lineW, lineH);
  }

  // 6×6 filled square
  ctx.fillRect(xC - Math.floor(squareSize / 2), squareTopY, squareSize, squareSize);
  ctx.restore();
}

// ── Empty state ───────────────────────────────────────────────────────────────
// UI-SPEC §8: "AWAITING NQ FOOTPRINT", text-sm (13px), --text-mute,
// letter-spacing 0.16em, no spinner.

function _drawEmptyState(
  ctx:     CanvasRenderingContext2D,
  canvasW: number,
  canvasH: number,
  vpr:     number,
): void {
  const fontSizeBitmap = Math.round(13 * vpr);   // text-sm

  ctx.save();
  ctx.font         = `500 ${fontSizeBitmap}px ${FONT_FAMILY}`;
  ctx.fillStyle    = C_TEXT_MUTE;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';

  // Apply letter-spacing if supported (Chromium 99+)
  const lsBitmap = 13 * EMPTY_LETTER_SPACING * vpr;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing
      = `${lsBitmap}px`;
  }

  ctx.fillText(EMPTY_TEXT, canvasW / 2, canvasH / 2);
  ctx.restore();

  // Suppress unused-variable lint on C_TEXT
  void C_TEXT;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function clampVol(v: number | undefined | null): number {
  if (v === undefined || v === null || !Number.isFinite(v)) return 0;
  return Math.min(MAX_DISPLAY_VOL, Math.max(0, v));
}
