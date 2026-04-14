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

// Wing max reach: 45% of halfBarW at full volume (Bookmap-style proportional wings)
const WING_MAX_RATIO = 0.45;

// Signal marker dimensions (CSS px)
const MARKER_ABOVE_CSS = 8;
const MARKER_SQ_CSS    = 6;

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

        // ── 4. Background grid rows (every 5 ticks, --rule at 50% alpha) ──
        _drawBackgroundGrid(ctx, rows, rowH, colLeft, colRight, canvasH, vpr);

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

        // ── 8. POC amber glow line (spans entire column width) ───────────
        if (pocPrice !== null) {
          const yPocMedia = priceToCoordinate(pocPrice);
          if (yPocMedia !== null) {
            const yPoc  = Math.round(yPocMedia * vpr);
            const lineH = Math.max(1, Math.round(POC_LINE_H * vpr));

            ctx.save();
            // Double-pass bloom for maximum amber presence
            ctx.shadowColor = C_AMBER;
            ctx.shadowBlur  = Math.round(12 * vpr);
            ctx.fillStyle   = C_AMBER;
            ctx.globalAlpha = 1;
            ctx.fillRect(colLeft, yPoc - Math.floor(lineH / 2), halfBarW * 2, lineH);
            ctx.shadowBlur  = Math.round(4 * vpr);
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

        // ── 10. CVD dot (right edge of column) ───────────────────────────
        {
          // Compare this bar's CVD with the previous bar's CVD
          const prevBar = i > range.from ? data.bars[i - 1] : null;
          const prevCvd = prevBar?.originalData?.cvd ?? null;
          const thisCvd = d.cvd ?? null;

          if (thisCvd !== null) {
            const cvdDot = prevCvd === null
              ? C_GREY
              : thisCvd > prevCvd
                ? C_ASK
                : thisCvd < prevCvd
                  ? C_BID
                  : C_GREY;

            // Find midpoint of bar rows for vertical centering of CVD dot
            let topRowY    = Infinity;
            let bottomRowY = -Infinity;
            for (const row of rows) {
              if (row.yBitmap < topRowY)    topRowY    = row.yBitmap;
              if (row.yBitmap > bottomRowY) bottomRowY = row.yBitmap;
            }
            const dotY = topRowY === Infinity
              ? Math.round(canvasH / 2)
              : Math.round((topRowY + bottomRowY) / 2);

            _drawCvdDot(ctx, xC + halfBarW - Math.round(2 * hpr), dotY, cvdDot, hpr, vpr);
          }
        }

        // ── 11. Signal marker ─────────────────────────────────────────────
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
// v3: TRUE volume-proportional wings (width ∝ volume) + dual-dimension encoding.
//
// Wing behavior:
//   - Width: (volume / maxVol) * WING_MAX_RATIO * halfBarW
//     → at full volume, wing reaches 45% of halfBarW (not the full halfBarW)
//     → cells with zero volume render no wing
//   - Opacity: 0.5 + (volRatio * 0.5) — always min 0.5 so low-vol cells still pop
//   - Imbalance override: full 45% width + full opacity + white outline
//   - POC override: both wings at full 45% + amber glow overlay

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
  // Base: proportional — volume/maxVol * 45% of halfBarW
  // Imbalance override: full 45% regardless of volume
  // POC override: full 45% regardless of volume
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
  // Floor at 0.5 so even the thinnest wings are clearly visible.
  // Imbalance and POC: pinned at 1.0 for maximum authority.
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
    ctx.shadowBlur  = Math.round(12 * vpr);
    ctx.fillStyle   = C_AMBER;
    ctx.globalAlpha = 0.08;
    ctx.fillRect(xC - halfBarW, cellTop, halfBarW * 2, cellH);
    ctx.restore();
  }

  // ── Bid wing (left of centerline, extending left) ─────────────────────────
  if (bidWingW > 0 && bidAlpha > 0) {
    ctx.globalAlpha = bidAlpha;
    ctx.fillStyle   = C_BID;
    ctx.fillRect(xC - bidWingW, cellTop, bidWingW, cellH);
    ctx.globalAlpha = 1;

    // Imbalance: crisp white outline + bloom
    if (isImbalanceBid) {
      ctx.save();
      ctx.shadowColor = C_WHITE;
      ctx.shadowBlur  = 0;   // outline stays crisp — no bloom on outline itself
      ctx.strokeStyle = C_WHITE;
      ctx.lineWidth   = Math.max(1, Math.round(hpr));
      ctx.globalAlpha = 0.9;
      ctx.strokeRect(xC - bidWingW + 0.5, cellTop + 0.5, bidWingW - 1, cellH - 1);
      ctx.restore();
    }
  }

  // ── Ask wing (right of centerline, extending right) ───────────────────────
  if (askWingW > 0 && askAlpha > 0) {
    ctx.globalAlpha = askAlpha;
    ctx.fillStyle   = C_ASK;
    ctx.fillRect(xC, cellTop, askWingW, cellH);
    ctx.globalAlpha = 1;

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

  // ── Volume numbers ────────────────────────────────────────────────────────
  // Only render when: column is wide enough AND row is tall enough
  const bidWingWCss = bidWingW / hpr;
  const rowHCss     = rowH / vpr;
  if (rowHCss < MIN_ROW_H_CSS) return;   // row too short — skip all numbers

  ctx.font         = `400 ${fontSize}px ${FONT_FAMILY}`;
  ctx.textBaseline = 'middle';

  const textY = yBitmap;
  const PAD   = Math.round(2 * hpr);

  if (bidVol > 0) {
    const label = String(Math.min(MAX_DISPLAY_VOL, bidVol));
    if (bidWingWCss >= MIN_INSIDE_W_CSS) {
      // Render inside wing, right-aligned, semi-transparent white
      ctx.fillStyle  = 'rgba(255,255,255,0.75)';
      ctx.textAlign  = 'right';
      ctx.fillText(label, xC - PAD, textY);
    }
  }

  if (askVol > 0) {
    const label = String(Math.min(MAX_DISPLAY_VOL, askVol));
    const askWingWCss = askWingW / hpr;
    if (askWingWCss >= MIN_INSIDE_W_CSS) {
      // Render inside wing, left-aligned, semi-transparent white
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
  ctx.fillStyle   = C_RULE;
  ctx.globalAlpha = 0.5;

  for (const row of rows) {
    const tickIndex = Math.round(row.price / 0.25);
    if (tickIndex % 5 !== 0) continue;

    const lineY = row.yBitmap - Math.floor(rowH / 2);
    const lineH = Math.max(1, 1);

    ctx.fillRect(0, lineY, canvasH > 0 ? 99999 : colRight - colLeft, lineH);
  }

  ctx.globalAlpha = 1;

  // Suppress unused-variable lint
  void colLeft;
  void colRight;
}

// ── Stacked imbalance run lines ───────────────────────────────────────────────
// 3+ consecutive same-side imbalanced cells → 2px vertical --lime line on that
// edge spanning the run, with glow + 3×3 dot at each imbalanced row edge.

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

  // Collect imbalanced row indices for this side (for dot markers)
  const imbalancedRows: number[] = [];

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
    // Enhanced bloom — shadowBlur 8 for visibility
    ctx.shadowColor = C_LIME;
    ctx.shadowBlur  = Math.round(8 * vpr);

    if (side === 'bid') {
      ctx.fillRect(xC - halfBarW, topY, lineW, runH);
    } else {
      ctx.fillRect(xC + halfBarW - lineW, topY, lineW, runH);
    }
    ctx.restore();

    // Draw 3×3 lime dot at each imbalanced row's run edge
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
      imbalancedRows.push(i);
    } else {
      flush(i);
      runStart = -1;
      runLen   = 0;
    }
  }
  flush(rows.length);

  // Suppress lint
  void imbalancedRows;
}

// ── Delta footer ──────────────────────────────────────────────────────────────
// Below the last price row: a proportional colored bar showing bar_delta.
// Width ∝ |bar_delta| / max(|delta| across visible bars).
// Below the bar: the delta value in JetBrains Mono.

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

  // Delta value text
  const label = barDelta > 0
    ? `+${barDelta}`
    : barDelta < 0
      ? `${barDelta}`
      : '0';

  ctx.font         = `400 ${textSzPx}px ${FONT_FAMILY}`;
  ctx.fillStyle    = color;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'top';
  ctx.globalAlpha  = 0.9;
  ctx.fillText(label, xC, textY);
  ctx.globalAlpha  = 1;
}

// ── CVD dot ───────────────────────────────────────────────────────────────────
// Tiny 3px-radius dot on the right edge of the bar column.
// Green if CVD increased from prior bar, red if decreased, grey if flat/unknown.

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

  // Suppress unused-variable lint on C_TEXT and C_CYAN
  void C_TEXT;
  void C_CYAN;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function clampVol(v: number | undefined | null): number {
  if (v === undefined || v === null || !Number.isFinite(v)) return 0;
  return Math.min(MAX_DISPLAY_VOL, Math.max(0, v));
}
