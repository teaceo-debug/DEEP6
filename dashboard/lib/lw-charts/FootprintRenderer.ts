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
const C_GREY      = '#666666';   // CVD flat indicator

// Imbalance threshold ratio (3× side dominance)
const IMBALANCE_THRESHOLD = 3.0;

// Minimum consecutive rows for a stacked run SOLID line (≥4); 3-row runs get dashed
const STACKED_RUN_SOLID_MIN = 4;
// Still detect runs starting at 3
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

// Wing max reach: 45% of halfBarW at full volume (Bookmap-style proportional wings)
const WING_MAX_RATIO = 0.45;

// Signal marker dimensions (CSS px)
const MARKER_ABOVE_CSS = 8;
const MARKER_SQ_CSS    = 5;   // 5×5 (was 6×6)

// Delta footer height below each bar (CSS px)
const DELTA_FOOTER_H_CSS  = 6;
const DELTA_FOOTER_GAP_CSS = 2;   // gap between last row and footer bar
const DELTA_TEXT_SIZE_CSS  = 10;

// CVD dot radius (CSS px)
const CVD_DOT_R_CSS = 1.5;

// DoS guards
const MAX_DISPLAY_VOL = 99999;
const MAX_BARS_CAP    = 500;

// Empty state
const EMPTY_TEXT           = 'AWAITING NQ FOOTPRINT';
const EMPTY_SUB_TEXT       = 'waiting for websocket stream\u2026';   // …
const EMPTY_LETTER_SPACING = 0.16;  // em

// Unicode minus for negative delta display (U+2212)
const UNICODE_MINUS = '\u2212';

// ── Row analysis ──────────────────────────────────────────────────────────────

interface RowInfo {
  price:           number;
  yBitmap:         number;
  bidVol:          number;
  askVol:          number;
  isImbalanceBid:  boolean;   // bid/ask ≥ 3× and bid dominates
  isImbalanceAsk:  boolean;   // ask/bid ≥ 3× and ask dominates
}

// CVD dot info collected per bar for trend line pass
interface CvdDotInfo {
  x:     number;
  y:     number;
  color: string;
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
      const rowH    = Math.max(1, Math.round(ROW_HEIGHT_CSS * vpr));
      const fontSize = Math.max(6, Math.round(FONT_SIZE_CSS * vpr));

      // ─ barSpacing from LW Charts (media pixels) → bitmap pixels ─────────
      // data.barSpacing is in media pixels; each column's full bitmap width.
      const colW = Math.round(data.barSpacing * hpr);

      // Column inner width: full column minus 2px gap each side → clean separator
      // halfBarW = usable half-width in bitmap pixels, clamped to [2, ∞)
      const GAP_EACH_SIDE = Math.round(2 * hpr);   // 2px CSS gap → bitmap
      const halfBarW = Math.max(2, Math.floor((colW - GAP_EACH_SIDE * 2) / 2));

      const to = Math.min(range.to, data.bars.length - 1, MAX_BARS_CAP - 1);

      // ── Compute max |bar_delta| across visible range for footer scaling ──
      let maxAbsDelta = 1;
      for (let i = range.from; i <= to; i++) {
        const bar = data.bars[i];
        if (!bar?.originalData) continue;
        const absDelta = Math.abs(bar.originalData.bar_delta ?? 0);
        if (absDelta > maxAbsDelta) maxAbsDelta = absDelta;
      }

      // ── Collect CVD dot positions for trend line rendering ────────────────
      const cvdDots: CvdDotInfo[] = [];

      // ── Per-bar render ────────────────────────────────────────────────────
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
        ctx.fillStyle = C_RULE;
        ctx.fillRect(colLeft - GAP_EACH_SIDE, 0, 1, canvasH);

        const levelKeys = Object.keys(d.levels);
        if (levelKeys.length === 0) continue;

        // ── 2. Compute per-bar max volume (cluster-local, not global) ──────
        // Scale to THIS bar's max so no overflow into neighbors.
        let maxVol = 1;
        // Also track which price has the highest total volume (POC detection)
        let pocTick    = -1;
        let pocVolMax  = 0;
        for (const key of levelKeys) {
          const lv = d.levels[key];
          if (!lv) continue;
          const b = clampVol(lv.bid_vol);
          const a = clampVol(lv.ask_vol);
          const t = b + a;
          if (Number.isFinite(t) && t > maxVol) maxVol = t;
          if (t > pocVolMax) {
            pocVolMax = t;
            pocTick   = Number(key);
          }
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

        // ── 4. Background grid rows (major every 10, minor every 5 ticks) ──
        _drawBackgroundGrid(ctx, rows, rowH, colLeft, colRight, canvasH, vpr);

        // ── 4b. Subtle column presence fill for all rows in this bar ────────
        _drawColumnPresence(ctx, rows, rowH, colLeft, halfBarW);

        // ── 5. POC row special treatment (pre-compute for _drawRow) ────────
        // The POC is the tick with highest total volume — matches d.poc_price
        // when available, falls back to our local pocTick computation.
        let pocPrice: number | null = null;
        if (d.poc_price && Number.isFinite(d.poc_price)) {
          pocPrice = d.poc_price;
        } else if (pocTick >= 0) {
          pocPrice = pocTick * 0.25;
        }

        // ── 6. Per-row volume bars (with clip enforcing column containment) ─
        ctx.save();

        // Clip to this column's usable area — prevents any draw (including
        // bloom glow) from escaping into adjacent columns.
        ctx.beginPath();
        ctx.rect(colLeft, 0, halfBarW * 2, canvasH);
        ctx.clip();

        for (const row of rows) {
          const isPoc = pocPrice !== null && Math.abs(row.price - pocPrice) < 0.01;
          _drawRow(ctx, row, xC, halfBarW, maxVol, rowH, fontSize, hpr, vpr, isPoc);
        }

        ctx.restore();   // clip ends

        // ── 7. Stacked imbalance run lines (drawn AFTER clip restore so the
        //       2px line sits exactly on the column edge, not clipped) ──────
        if (options.showImbalance && rows.length >= STACKED_RUN_MIN) {
          _drawStackedRunLines(ctx, rows, rowH, xC, halfBarW, hpr, vpr);
        }

        // ── 8. POC amber line — dialed down bloom ────────────────────────
        if (pocPrice !== null) {
          const yPocMedia = priceToCoordinate(pocPrice);
          if (yPocMedia !== null) {
            const yPoc  = Math.round(yPocMedia * vpr);
            const lineH = Math.max(1, Math.round(POC_LINE_H * vpr));

            ctx.save();
            // Dialed-down bloom: 5/2 (was 12/4), dimmer amber color
            ctx.shadowColor = C_AMBER;
            ctx.shadowBlur  = Math.round(5 * vpr);
            ctx.fillStyle   = 'rgba(255, 214, 10, 0.85)';   // slightly dimmer
            ctx.globalAlpha = 1;
            ctx.fillRect(colLeft, yPoc - Math.floor(lineH / 2), halfBarW * 2, lineH);
            ctx.shadowBlur  = Math.round(2 * vpr);
            ctx.fillRect(colLeft, yPoc - Math.floor(lineH / 2), halfBarW * 2, lineH);
            ctx.restore();
          }
        }

        // ── 9. Delta footer below each bar ────────────────────────────────
        if (options.showDelta) {
          // Find the bottom-most row y position
          let bottomY = 0;
          for (const row of rows) {
            const rowBottom = row.yBitmap + Math.ceil(rowH / 2);
            if (rowBottom > bottomY) bottomY = rowBottom;
          }
          if (bottomY === 0) {
            // Fallback: use canvas bottom area
            bottomY = canvasH - Math.round((DELTA_FOOTER_H_CSS + DELTA_TEXT_SIZE_CSS + 4) * vpr);
          }

          _drawDeltaFooter(ctx, d.bar_delta ?? 0, maxAbsDelta, xC, halfBarW, bottomY, hpr, vpr);
        }

        // ── 10. CVD dot — repositioned above delta footer ─────────────────
        {
          const prevBar = i > range.from ? data.bars[i - 1] : null;
          const prevCvd = prevBar?.originalData?.cvd ?? null;
          const thisCvd = d.cvd ?? null;

          if (thisCvd !== null) {
            const cvdColor = prevCvd === null
              ? C_GREY
              : thisCvd > prevCvd
                ? C_ASK
                : thisCvd < prevCvd
                  ? C_BID
                  : C_GREY;

            // Position CVD dot just above the delta footer area
            // Find bottomY of the bar rows
            let bottomY = 0;
            for (const row of rows) {
              const rowBottom = row.yBitmap + Math.ceil(rowH / 2);
              if (rowBottom > bottomY) bottomY = rowBottom;
            }
            if (bottomY === 0) bottomY = canvasH - Math.round(20 * vpr);

            // Place dot between last row and delta footer
            const dotY = bottomY + Math.round(DELTA_FOOTER_GAP_CSS * vpr / 2);

            _drawCvdDot(ctx, xC, dotY, cvdColor, hpr, vpr);
            cvdDots.push({ x: xC, y: dotY, color: cvdColor });
          }
        }

        // ── 11. Signal marker ─────────────────────────────────────────────
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

      // ── 12. CVD trend line — connecting consecutive CVD dots ─────────────
      if (cvdDots.length >= 2) {
        _drawCvdTrendLine(ctx, cvdDots, vpr);
      }

      // ── 13. Delta footer baseline ribbon (delta=0 horizontal line) ───────
      if (options.showDelta) {
        _drawDeltaBaseline(ctx, data, range, to, hpr, vpr, priceToCoordinate, rowH);
      }
    });
  }
}

// ── Column presence fill ──────────────────────────────────────────────────────
// For all rows in a bar's column (even 0-vol rows), add a 2% opacity fill of
// --text-mute to give the column a subtle "presence" so empty rows don't float.

function _drawColumnPresence(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  colLeft:  number,
  halfBarW: number,
): void {
  if (rows.length === 0) return;

  ctx.fillStyle   = C_TEXT_MUTE;
  ctx.globalAlpha = 0.02;

  for (const row of rows) {
    const cellTop = row.yBitmap - Math.floor(rowH / 2);
    const cellH   = rowH - 1;
    ctx.fillRect(colLeft, cellTop, halfBarW * 2, cellH);
  }

  ctx.globalAlpha = 1;
}

// ── Per-row draw helper ───────────────────────────────────────────────────────
// v4: volume-proportional wings + tiny-dot at ratio<0.05 + high-vol inner edge highlight

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
  isPoc:     boolean,
): void {
  const { yBitmap, bidVol, askVol, isImbalanceBid, isImbalanceAsk } = row;

  // Cell bounds
  const cellTop = yBitmap - Math.floor(rowH / 2);
  const cellH   = rowH - 1;   // 1px inter-row gap

  // Volume ratios [0, 1]
  const bidRatio = maxVol > 0 && Number.isFinite(bidVol / maxVol) ? bidVol / maxVol : 0;
  const askRatio = maxVol > 0 && Number.isFinite(askVol / maxVol) ? askVol / maxVol : 0;

  // ── Wing widths ──────────────────────────────────────────────────────────
  const maxWingPx = Math.max(1, Math.floor(halfBarW * WING_MAX_RATIO));

  const bidWingW = isPoc || isImbalanceBid
    ? maxWingPx
    : bidVol > 0
      ? Math.max(1, Math.round(maxWingPx * bidRatio))
      : 0;

  const askWingW = isPoc || isImbalanceAsk
    ? maxWingPx
    : askVol > 0
      ? Math.max(1, Math.round(maxWingPx * askRatio))
      : 0;

  // ── Opacity: dual-dimension encoding ─────────────────────────────────────
  const bidAlpha = (isPoc || isImbalanceBid)
    ? 1.0
    : bidVol > 0
      ? Math.min(1.0, 0.5 + bidRatio * 0.5)
      : 0;

  const askAlpha = (isPoc || isImbalanceAsk)
    ? 1.0
    : askVol > 0
      ? Math.min(1.0, 0.5 + askRatio * 0.5)
      : 0;

  // ── POC: amber glow overlay behind the row ────────────────────────────────
  if (isPoc) {
    ctx.save();
    ctx.shadowColor = C_AMBER;
    ctx.shadowBlur  = Math.round(8 * vpr);   // dialed down from 12
    ctx.fillStyle   = C_AMBER;
    ctx.globalAlpha = 0.08;
    ctx.fillRect(xC - halfBarW, cellTop, halfBarW * 2, cellH);
    ctx.restore();
  }

  // ── Bid wing (left of centerline, extending left) ─────────────────────────
  if (bidWingW > 0 && bidAlpha > 0) {
    // Tiny-dot rendering for very low volume (ratio < 0.05)
    if (bidRatio < 0.05 && !isPoc && !isImbalanceBid) {
      // 2×2 dot at center of the bid side
      const dotX = xC - Math.round(maxWingPx / 2) - 1;
      const dotY = yBitmap - 1;
      ctx.fillStyle   = C_BID;
      ctx.globalAlpha = 0.4;
      ctx.fillRect(dotX, dotY, 2, 2);
      ctx.globalAlpha = 1;
    } else {
      ctx.globalAlpha = bidAlpha;
      ctx.fillStyle   = C_BID;
      ctx.fillRect(xC - bidWingW, cellTop, bidWingW, cellH);
      ctx.globalAlpha = 1;

      // High-vol inner edge highlight (ratio > 0.8): 1px lighter line on inner edge
      if (bidRatio > 0.8 && !isImbalanceBid) {
        ctx.save();
        ctx.strokeStyle = 'rgba(255, 100, 120, 0.5)';   // lighter bid shade
        ctx.lineWidth   = Math.max(1, Math.round(hpr));
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        ctx.moveTo(xC - bidWingW + Math.floor(ctx.lineWidth / 2), cellTop);
        ctx.lineTo(xC - bidWingW + Math.floor(ctx.lineWidth / 2), cellTop + cellH);
        ctx.stroke();
        ctx.restore();
      }

      // Imbalance: crisp white outline
      if (isImbalanceBid) {
        ctx.save();
        ctx.shadowColor = C_WHITE;
        ctx.shadowBlur  = 0;
        ctx.strokeStyle = C_WHITE;
        ctx.lineWidth   = Math.max(1, Math.round(hpr));
        ctx.globalAlpha = 0.9;
        ctx.strokeRect(xC - bidWingW + 0.5, cellTop + 0.5, bidWingW - 1, cellH - 1);
        ctx.restore();
      }
    }
  }

  // ── Ask wing (right of centerline, extending right) ───────────────────────
  if (askWingW > 0 && askAlpha > 0) {
    // Tiny-dot rendering for very low volume (ratio < 0.05)
    if (askRatio < 0.05 && !isPoc && !isImbalanceAsk) {
      const dotX = xC + Math.round(maxWingPx / 2) - 1;
      const dotY = yBitmap - 1;
      ctx.fillStyle   = C_ASK;
      ctx.globalAlpha = 0.4;
      ctx.fillRect(dotX, dotY, 2, 2);
      ctx.globalAlpha = 1;
    } else {
      ctx.globalAlpha = askAlpha;
      ctx.fillStyle   = C_ASK;
      ctx.fillRect(xC, cellTop, askWingW, cellH);
      ctx.globalAlpha = 1;

      // High-vol inner edge highlight (ratio > 0.8): 1px lighter line on inner edge
      if (askRatio > 0.8 && !isImbalanceAsk) {
        ctx.save();
        ctx.strokeStyle = 'rgba(100, 255, 160, 0.5)';   // lighter ask shade
        ctx.lineWidth   = Math.max(1, Math.round(hpr));
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        ctx.moveTo(xC + askWingW - Math.floor(ctx.lineWidth / 2), cellTop);
        ctx.lineTo(xC + askWingW - Math.floor(ctx.lineWidth / 2), cellTop + cellH);
        ctx.stroke();
        ctx.restore();
      }

      // Imbalance outline
      if (isImbalanceAsk) {
        ctx.save();
        ctx.strokeStyle = C_WHITE;
        ctx.lineWidth   = Math.max(1, Math.round(hpr));
        ctx.globalAlpha = 0.9;
        ctx.strokeRect(xC + 0.5, cellTop + 0.5, askWingW - 1, cellH - 1);
        ctx.restore();
      }
    }
  }

  // ── Volume numbers ────────────────────────────────────────────────────────
  const bidWingWCss = bidWingW / hpr;
  const rowHCss     = rowH / vpr;
  if (rowHCss < MIN_ROW_H_CSS) return;

  ctx.font         = `400 ${fontSize}px ${FONT_FAMILY}`;
  ctx.textBaseline = 'middle';

  const textY = yBitmap;
  const PAD   = Math.round(2 * hpr);

  if (bidVol > 0) {
    const label = String(Math.min(MAX_DISPLAY_VOL, bidVol));
    if (bidWingWCss >= MIN_INSIDE_W_CSS) {
      ctx.fillStyle  = 'rgba(255,255,255,0.75)';
      ctx.textAlign  = 'right';
      ctx.fillText(label, xC - PAD, textY);
    }
  }

  if (askVol > 0) {
    const label = String(Math.min(MAX_DISPLAY_VOL, askVol));
    const askWingWCss = askWingW / hpr;
    if (askWingWCss >= MIN_INSIDE_W_CSS) {
      ctx.fillStyle  = 'rgba(255,255,255,0.75)';
      ctx.textAlign  = 'left';
      ctx.fillText(label, xC + PAD, textY);
    }
  }
}

// ── Background grid rows ──────────────────────────────────────────────────────
// Major every 10 ticks: --rule at 60% alpha, 1px
// Minor every 5 ticks (not 10): rgba rule-bright-dimmed at 15% opacity

function _drawBackgroundGrid(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  _colLeft: number,
  _colRight: number,
  canvasH:  number,
  _vpr:     number,
): void {
  for (const row of rows) {
    const tickIndex = Math.round(row.price / 0.25);
    const isMajor   = tickIndex % 40 === 0;   // 10 ticks × 0.25 = 2.5pts → mod 40
    const isMinor   = tickIndex % 20 === 0;   // 5 ticks × 0.25 = 1.25pts → mod 20

    if (!isMajor && !isMinor) continue;

    const lineY = row.yBitmap - Math.floor(rowH / 2);

    if (isMajor) {
      // Major: #1f1f1f at 60% opacity, 1px
      ctx.fillStyle   = C_RULE;
      ctx.globalAlpha = 0.6;
    } else {
      // Minor: semi-transparent rule at 15% opacity
      ctx.fillStyle   = 'rgba(80, 80, 80, 0.15)';
      ctx.globalAlpha = 1;
    }

    ctx.fillRect(0, lineY, canvasH > 0 ? 99999 : 1, 1);
  }

  ctx.globalAlpha = 1;
}

// ── Stacked imbalance run lines ───────────────────────────────────────────────
// ≥4 consecutive rows → solid 2px --lime line
// 3-row runs → dashed 2px --lime line

function _drawStackedRunLines(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  xC:       number,
  halfBarW: number,
  hpr:      number,
  vpr:      number,
): void {
  const lineW = Math.max(2, Math.round(2 * hpr));

  _scanAndDrawRun(ctx, rows, rowH, xC, halfBarW, lineW, 'bid', vpr);
  _scanAndDrawRun(ctx, rows, rowH, xC, halfBarW, lineW, 'ask', vpr);
}

function _scanAndDrawRun(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  xC:       number,
  halfBarW: number,
  lineW:    number,
  side:     'bid' | 'ask',
  vpr:      number,
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
    const isSolid = runLen >= STACKED_RUN_SOLID_MIN;

    ctx.save();
    ctx.fillStyle   = C_LIME;
    ctx.globalAlpha = 1;
    ctx.shadowColor = C_LIME;
    ctx.shadowBlur  = Math.round(8 * vpr);

    const lineX = side === 'bid' ? xC - halfBarW : xC + halfBarW - lineW;

    if (isSolid) {
      // Solid run line
      ctx.fillRect(lineX, topY, lineW, runH);
    } else {
      // Dashed run line for 3-row runs
      ctx.shadowBlur = Math.round(4 * vpr);   // softer glow for dashed
      const dashLen  = Math.max(3, Math.round(4 * vpr));
      const gapLen   = Math.max(2, Math.round(3 * vpr));
      let y = topY;
      while (y < botY) {
        const segH = Math.min(dashLen, botY - y);
        ctx.fillRect(lineX, y, lineW, segH);
        y += dashLen + gapLen;
      }
    }
    ctx.restore();

    // Dot markers at each imbalanced row edge
    const dotSize = Math.max(3, Math.round(3 * (vpr > 1 ? vpr : 1)));
    ctx.save();
    ctx.fillStyle   = C_LIME;
    ctx.globalAlpha = 0.9;
    ctx.shadowColor = C_LIME;
    ctx.shadowBlur  = Math.round(4 * vpr);

    for (let ri = runStart; ri < endIdx; ri++) {
      const r = rows[ri];
      const dotY = r.yBitmap - Math.floor(dotSize / 2);
      if (side === 'bid') {
        ctx.fillRect(xC - halfBarW - Math.floor(dotSize / 2), dotY, dotSize, dotSize);
      } else {
        ctx.fillRect(xC + halfBarW - Math.floor(dotSize / 2), dotY, dotSize, dotSize);
      }
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

// ── Delta footer ──────────────────────────────────────────────────────────────
// Below the last price row: proportional colored bar + delta value.
// Uses Unicode minus (U+2212) for negative values.

function _drawDeltaFooter(
  ctx:          CanvasRenderingContext2D,
  barDelta:     number,
  maxAbsDelta:  number,
  xC:           number,
  halfBarW:     number,
  bottomRowY:   number,
  hpr:          number,
  vpr:          number,
): void {
  if (!Number.isFinite(barDelta) || maxAbsDelta <= 0) return;

  const footerH   = Math.max(2, Math.round(DELTA_FOOTER_H_CSS * vpr));
  const gapH      = Math.round(DELTA_FOOTER_GAP_CSS * vpr);
  const textSzPx  = Math.max(6, Math.round(DELTA_TEXT_SIZE_CSS * vpr));

  const barY      = bottomRowY + gapH;
  const textY     = barY + footerH + Math.round(2 * vpr);

  const ratio     = Math.min(1, Math.abs(barDelta) / maxAbsDelta);
  const barW      = Math.max(2, Math.round(halfBarW * 2 * ratio));
  const barX      = xC - Math.floor(barW / 2);

  const color     = barDelta > 0 ? C_ASK : barDelta < 0 ? C_BID : C_GREY;

  // Colored width bar
  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.85;
  ctx.fillRect(barX, barY, barW, footerH);
  ctx.globalAlpha = 1;

  // Delta value text — Unicode minus for negative, + prefix for positive
  const absVal = Math.abs(barDelta);
  const label = barDelta > 0
    ? `+${absVal}`
    : barDelta < 0
      ? `${UNICODE_MINUS}${absVal}`
      : '0';

  ctx.font         = `400 ${textSzPx}px ${FONT_FAMILY}`;
  ctx.fillStyle    = color;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'top';
  ctx.globalAlpha  = 0.9;
  ctx.fillText(label, xC, textY);
  ctx.globalAlpha  = 1;

  void hpr;
}

// ── Delta baseline ribbon ─────────────────────────────────────────────────────
// 1px horizontal line at the delta=0 position connecting all delta footer bars.
// Drawn as a single pass after all bars are rendered.

function _drawDeltaBaseline(
  ctx:               CanvasRenderingContext2D,
  data:              PaneRendererCustomData<Time, FootprintBarLW>,
  range:             { from: number; to: number },
  to:                number,
  hpr:               number,
  vpr:               number,
  priceToCoordinate: PriceToCoordinateConverter,
  rowH:              number,
): void {
  // Find the common bottomY across all visible bars by scanning prices
  // We use the lowest price level across visible bars to find a consistent baseline Y
  let lowestPrice: number | null = null;

  for (let i = range.from; i <= to; i++) {
    const bar = data.bars[i];
    if (!bar?.originalData?.levels) continue;
    for (const key of Object.keys(bar.originalData.levels)) {
      const price = Number(key) * 0.25;
      if (lowestPrice === null || price < lowestPrice) lowestPrice = price;
    }
  }

  if (lowestPrice === null) return;

  const yMedia = priceToCoordinate(lowestPrice);
  if (yMedia === null) return;

  // Baseline sits just below the lowest row + gap
  const baselineY = Math.round(yMedia * vpr)
    + Math.ceil(rowH / 2)
    + Math.round(DELTA_FOOTER_GAP_CSS * vpr)
    + Math.max(2, Math.round(DELTA_FOOTER_H_CSS * vpr));

  // Draw full-width 1px line across the canvas at this Y
  ctx.save();
  ctx.fillStyle   = C_RULE;
  ctx.globalAlpha = 0.5;
  ctx.fillRect(0, baselineY, 99999, Math.max(1, Math.round(hpr)));
  ctx.restore();
}

// ── CVD dot ───────────────────────────────────────────────────────────────────
// Tiny dot repositioned above the delta footer (within bar column).

function _drawCvdDot(
  ctx:   CanvasRenderingContext2D,
  x:     number,
  y:     number,
  color: string,
  _hpr:  number,
  vpr:   number,
): void {
  const r = Math.max(1.5, CVD_DOT_R_CSS * vpr);

  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.8;
  ctx.fill();
  ctx.restore();

  void _hpr;
}

// ── CVD trend line ────────────────────────────────────────────────────────────
// Thin 1px line connecting consecutive CVD dots across bars.
// Color: mix of the two endpoint dot colors.

function _drawCvdTrendLine(
  ctx:     CanvasRenderingContext2D,
  dots:    CvdDotInfo[],
  vpr:     number,
): void {
  ctx.save();
  ctx.lineWidth   = Math.max(1, Math.round(vpr));
  ctx.globalAlpha = 0.35;

  for (let i = 1; i < dots.length; i++) {
    const prev = dots[i - 1];
    const curr = dots[i];

    // Simple color: use the current dot's color as the segment color
    ctx.strokeStyle = curr.color;

    ctx.beginPath();
    ctx.moveTo(prev.x, prev.y);
    ctx.lineTo(curr.x, curr.y);
    ctx.stroke();
  }

  ctx.restore();
}

// ── Signal marker ─────────────────────────────────────────────────────────────
// 1.5px vertical line above bar + 5×5 square + 4px circle halo behind square.

function _drawSignalMarker(
  ctx:         CanvasRenderingContext2D,
  xC:          number,
  yHighBitmap: number,
  color:       string,
  hpr:         number,
  vpr:         number,
): void {
  const aboveOffset = Math.round(MARKER_ABOVE_CSS * vpr);
  const squareSize  = Math.round(MARKER_SQ_CSS * hpr);   // 5×5
  const lineW       = Math.max(1, Math.round(1.5 * hpr)); // 1.5px (was 2px)

  // Square sits above the gap
  const squareTopY  = yHighBitmap - aboveOffset - squareSize;
  const lineTopY    = squareTopY + squareSize;
  const lineH       = yHighBitmap - lineTopY;

  ctx.save();

  // ── Halo circle behind square (4px larger than square, 30% opacity) ──────
  const haloR = Math.round((squareSize / 2) + 2 * hpr);
  const haloX = xC;
  const haloY = squareTopY + Math.floor(squareSize / 2);

  ctx.beginPath();
  ctx.arc(haloX, haloY, haloR, 0, Math.PI * 2);
  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.3;
  ctx.fill();

  ctx.fillStyle   = color;
  ctx.globalAlpha = 1;

  // Vertical line from bar top to square bottom
  if (lineH > 0) {
    ctx.fillRect(xC - Math.floor(lineW / 2), lineTopY, lineW, lineH);
  }

  // 5×5 filled square
  ctx.fillRect(xC - Math.floor(squareSize / 2), squareTopY, squareSize, squareSize);

  ctx.restore();
}

// ── Empty state ───────────────────────────────────────────────────────────────
// Primary: "AWAITING NQ FOOTPRINT" in --text-mute
// Secondary: "waiting for websocket stream…" in --text-mute italic text-xs below

function _drawEmptyState(
  ctx:     CanvasRenderingContext2D,
  canvasW: number,
  canvasH: number,
  vpr:     number,
): void {
  const fontSizeBitmap    = Math.round(13 * vpr);   // text-sm
  const subFontSizeBitmap = Math.round(10 * vpr);   // text-xs

  const centerX = canvasW / 2;
  const centerY = canvasH / 2;

  ctx.save();
  ctx.fillStyle    = C_TEXT_MUTE;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';

  // Primary line
  ctx.font = `500 ${fontSizeBitmap}px ${FONT_FAMILY}`;

  const lsBitmap = 13 * EMPTY_LETTER_SPACING * vpr;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing
      = `${lsBitmap}px`;
  }

  ctx.fillText(EMPTY_TEXT, centerX, centerY);

  // Secondary line — italic, smaller, --text-mute
  ctx.font = `italic 400 ${subFontSizeBitmap}px ${FONT_FAMILY}`;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = '0px';
  }
  ctx.globalAlpha = 0.6;
  ctx.fillText(EMPTY_SUB_TEXT, centerX, centerY + fontSizeBitmap + Math.round(4 * vpr));

  ctx.restore();

  // Suppress unused-variable lint on C_TEXT and C_CYAN
  void C_TEXT;
  void C_CYAN;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function clampVol(v: number | undefined | null): number {
  if (v === undefined || v === null || !Number.isFinite(v)) return 0;
  return Math.min(MAX_DISPLAY_VOL, Math.max(0, v));
}
