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
const C_TEXT_DIM  = '#8a8a8a';   // --text-dim (neutral medium volume)
const C_TEXT_MUTE = '#4a4a4a';   // --text-mute (neutral low volume, empty state)
const C_VOID      = '#000000';   // --void  (background)
const C_TEXT      = '#f5f5f5';   // --text  (imbalance row text, primary, high volume)

// ── Imbalance threshold ───────────────────────────────────────────────────────
// Cells where ask/bid (or bid/ask) ratio >= this value are colored as imbalance.
// 2.5 catches more edge cells than the traditional 3× — makes imbalance pop.
// Change this constant to tune sensitivity without touching any other logic.
const IMBALANCE_THRESHOLD = 2.5;

// Minimum consecutive rows for stacked imbalance marker
const STACKED_RUN_MIN = 3;

// Row height in CSS pixels (spec §3: 18px — readability wins over density)
const ROW_HEIGHT_CSS = 18;

// Font for volume numbers and chrome — quoted name required for canvas ctx.font
// (otherwise browser may fall back to system monospace if the face isn't loaded)
const FONT_FAMILY = '"JetBrains Mono", monospace';

// text-xs (11px CSS) for cell text at normal column widths; scaled by vpr for Retina
const FONT_SIZE_NORMAL_CSS = 11;

// text-xs at narrow column widths (<70px)
const FONT_SIZE_SMALL_CSS = 10;

// Column width thresholds (CSS px) controlling display mode
const COL_W_FULL_LABEL_CSS   = 70;   // ≥70 → full "bid × ask", 11px
const COL_W_ABBREV_LABEL_CSS = 55;   // ≥55 → "bid × ask" at 10px
const COL_W_ARROW_LABEL_CSS  = 40;   // ≥40 → "↑256" abbreviated at 10px
// < 40 → color-only (no text)

// Min column width to render timestamp header
const HEADER_MIN_COL_W_CSS = 60;

// Min cell height (CSS px) to render any text; below this → color-only mode
const MIN_ROW_H_FOR_TEXT_CSS = 14;

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
// If this glyph doesn't render correctly in monospace at small sizes, swap
// UNICODE_TIMES for LATIN_X — checked at runtime via _resolveSeparator().
const UNICODE_TIMES = '\u00d7';   // × (U+00D7 multiplication sign)
const LATIN_X       = 'x';       // ASCII fallback

// Cached separator choice (set once after first canvas measureText probe)
let _separatorChar: string | null = null;

// Unicode minus for negative delta
const UNICODE_MINUS = '\u2212';

// ── prefers-reduced-motion — checked once at module load ─────────────────────
const REDUCED_MOTION: boolean =
  typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;

// ── Animation durations (ms) ─────────────────────────────────────────────────
const DUR_BAR_SWEEP        = 400;   // new bar column opacity ramp
const DUR_IMBALANCE_PULSE  = 300;   // newly-imbalanced cell bg flash
const DUR_POC_PULSE        = 500;   // POC row establishment pulse
const DUR_DELTA_TICK       = 300;   // delta footer flash
const DUR_STACKED_GROW     = 400;   // stacked run grow-in at 4+ milestone
const DUR_SEPARATOR_FADE   = 200;   // column separator fade-in

// ── Animation state types ────────────────────────────────────────────────────

interface TimedAnim {
  startTs:  number;
  duration: number;
}

interface DeltaTickAnim extends TimedAnim {
  fromBarW: number;   // previous proportional bar width [0,1] for smooth easing
}

// ── Module-level animation state maps ───────────────────────────────────────
// All keyed by barIndex (number) or composite string.

/** bar_index → bar arrival sweep */
const _barSweep    = new Map<number, TimedAnim>();
/** `${barIndex}:${tickKey}` → imbalance cell pulse */
const _cellPulse   = new Map<string, TimedAnim>();
/** bar_index → POC row pulse */
const _pocPulse    = new Map<number, TimedAnim>();
/** bar_index → delta footer tick */
const _deltaTick   = new Map<number, DeltaTickAnim>();
/** `${barIndex}:${side}` → stacked run grow-in */
const _stackedGrow = new Map<string, TimedAnim>();
/** bar_index → column separator fade-in */
const _sepFade     = new Map<number, TimedAnim>();

// ── Previous-frame state (change detection) ──────────────────────────────────
/** bar_index → last seen POC price */
const _lastPoc      = new Map<number, number>();
/** bar_index → last seen bar_delta value */
const _lastDelta    = new Map<number, number>();
/** bar_index → last seen delta proportional bar width [0,1] */
const _lastDeltaW   = new Map<number, number>();
/** `${barIndex}:${tickKey}` → last imbalance state */
const _lastImb      = new Map<string, 'ask' | 'bid' | 'none'>();
/** `${barIndex}:${side}` → set when stacked-grow milestone has fired */
const _stackedFired = new Set<string>();

// ── RAF invalidation ─────────────────────────────────────────────────────────
// LW Charts drives the draw() cycle. When animations are active we run a
// parallel RAF loop that calls the registered invalidate callback so LW Charts
// repaints on each browser frame.

let _rafHandle:    number | null  = null;
let _invalidateFn: (() => void) | null = null;

function _hasActiveAnims(): boolean {
  return (
    _barSweep.size > 0 || _cellPulse.size > 0 || _pocPulse.size > 0 ||
    _deltaTick.size > 0 || _stackedGrow.size > 0 || _sepFade.size > 0
  );
}

function _pruneExpired(now: number): void {
  for (const [k, a] of _barSweep)    { if (now - a.startTs >= a.duration) _barSweep.delete(k); }
  for (const [k, a] of _cellPulse)   { if (now - a.startTs >= a.duration) _cellPulse.delete(k); }
  for (const [k, a] of _pocPulse)    { if (now - a.startTs >= a.duration) _pocPulse.delete(k); }
  for (const [k, a] of _deltaTick)   { if (now - a.startTs >= a.duration) _deltaTick.delete(k); }
  for (const [k, a] of _stackedGrow) { if (now - a.startTs >= a.duration) _stackedGrow.delete(k); }
  for (const [k, a] of _sepFade)     { if (now - a.startTs >= a.duration) _sepFade.delete(k); }
}

function _startRafLoop(): void {
  if (_rafHandle !== null || REDUCED_MOTION) return;
  const tick = () => {
    _pruneExpired(performance.now());
    if (_hasActiveAnims()) {
      if (_invalidateFn) _invalidateFn();
      _rafHandle = requestAnimationFrame(tick);
    } else {
      _rafHandle = null;
    }
  };
  _rafHandle = requestAnimationFrame(tick);
}

function _scheduleAnim(): void {
  if (!REDUCED_MOTION) _startRafLoop();
}

// ── Easing helpers ────────────────────────────────────────────────────────────

/** Linear progress [0,1]. Returns 1 when expired. */
function _prog(a: TimedAnim, now: number): number {
  return Math.min(1, (now - a.startTs) / a.duration);
}

/** Triangle: 0 → 1 → 0 */
function _tri(t: number): number {
  return t < 0.5 ? t * 2 : (1 - t) * 2;
}

/** Ease-out cubic */
function _easeOut(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Ease-in-out quad */
function _easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

// ── Thousand-separator formatter ──────────────────────────────────────────────
// Cached Intl.NumberFormat instance — created once, reused for every cell.
// Numbers >= 1000 format as "1,234"; smaller numbers format without separator.
const _numFmt = new Intl.NumberFormat('en-US', {
  useGrouping: true,
  maximumFractionDigits: 0,
});

function _formatVol(n: number): string {
  const clamped = Math.min(MAX_DISPLAY_VOL, n);
  if (clamped < 1000) return String(clamped);       // fast path — no separator needed
  return _numFmt.format(clamped);
}

// ── Text width cache ──────────────────────────────────────────────────────────
// Pre-cache measured widths for formatted volume strings to avoid repeated
// measureText calls in the hot path. Key = `${fontSize}:${formattedString}`.
// We key on the formatted string (not raw number) so "1,234" ≠ "1234".
const _textWidthCache = new Map<string, number>();

function _cachedTextWidth(
  ctx:      CanvasRenderingContext2D,
  text:     string,
  font:     string,
  fontSize: number,
): number {
  const key = `${fontSize}:${text}`;
  let w = _textWidthCache.get(key);
  if (w !== undefined) return w;
  ctx.font = font;
  w = ctx.measureText(text).width;
  if (_textWidthCache.size < 6000) _textWidthCache.set(key, w);
  return w;
}

// ── Separator character resolution ───────────────────────────────────────────
// Probe whether U+00D7 (×) renders at the expected width in JetBrains Mono.
// If it comes out narrower than a digit (indicating fallback to tofu/blank),
// use ASCII 'x' instead. We only probe once per session.
function _resolveSeparator(ctx: CanvasRenderingContext2D, font: string): string {
  if (_separatorChar !== null) return _separatorChar;
  ctx.font = font;
  const wTimes = ctx.measureText(UNICODE_TIMES).width;
  const wDigit = ctx.measureText('0').width;
  // In a proper monospace font, × should be at least 70% of a digit's width.
  _separatorChar = wTimes >= wDigit * 0.7 ? UNICODE_TIMES : LATIN_X;
  return _separatorChar;
}

// ── Neutral-cell text color by volume tier ────────────────────────────────────
// Three-tier contrast system for neutral (non-imbalance, non-POC) cells.
// barMaxTotalVol is the per-bar max so the scale is always relative.
function _neutralTextColor(totalVol: number, barMaxTotalVol: number): string {
  if (barMaxTotalVol <= 0) return C_TEXT_MUTE;
  const ratio = totalVol / barMaxTotalVol;
  if (ratio > 0.75) return C_TEXT;       // high volume — bright
  if (ratio > 0.25) return C_TEXT_DIM;   // medium volume
  return C_TEXT_MUTE;                    // low volume — very dim
}

// ── Row analysis ──────────────────────────────────────────────────────────────

interface RowInfo {
  price:          number;
  tickKey:        string;    // raw levels key — used as part of animation map keys
  yBitmap:        number;
  bidVol:         number;
  askVol:         number;
  isImbalanceBid: boolean;   // bid/ask ≥ IMBALANCE_THRESHOLD and bid dominates
  isImbalanceAsk: boolean;   // ask/bid ≥ IMBALANCE_THRESHOLD and ask dominates
}

// ── Renderer ──────────────────────────────────────────────────────────────────

export class FootprintRenderer implements ICustomSeriesPaneRenderer {
  private _data: PaneRendererCustomData<Time, FootprintBarLW> | null = null;
  private _options: FootprintSeriesOptions | null = null;
  /** bar_index of the newest bar seen on the previous draw pass */
  private _lastNewestBarIndex: number = -1;

  update(
    data: PaneRendererCustomData<Time, FootprintBarLW>,
    options: FootprintSeriesOptions,
  ): void {
    this._data    = data;
    this._options = options;
  }

  /**
   * Register an invalidation callback so the RAF animation loop can trigger
   * LW Charts redraws between its own paint cycles.
   * Typical usage after series creation:
   *   paneView.renderer().setInvalidateFn(() => series.update(series.data().at(-1)!))
   * Or more simply, any call that causes LW Charts to redraw.
   */
  setInvalidateFn(fn: () => void): void {
    _invalidateFn = fn;
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
      const rowH = Math.max(1, Math.round(ROW_HEIGHT_CSS * vpr));

      // Column width in bitmap pixels (barSpacing is in media/CSS pixels)
      const colW = Math.round(data.barSpacing * hpr);

      // CSS-space column width — used for threshold comparisons
      const colWCss = colW / hpr;

      // Inner column bounds — 1px gap each side for the column separator
      const GAP_BITMAP = Math.max(1, Math.round(1 * hpr));
      const innerW     = Math.max(2, colW - GAP_BITMAP * 2);

      // ── Font selection based on column width ─────────────────────────────
      // Pick font size in CSS px; then scale to bitmap px for crisp Retina text.
      const fontSizeCss = colWCss >= COL_W_FULL_LABEL_CSS
        ? FONT_SIZE_NORMAL_CSS
        : FONT_SIZE_SMALL_CSS;
      const fontSize = Math.max(6, Math.round(fontSizeCss * vpr));
      const font     = `400 ${fontSize}px ${FONT_FAMILY}`;

      // Resolve separator once we have a font string
      const sep = _resolveSeparator(ctx, font);

      const to = Math.min(range.to, data.bars.length - 1, MAX_BARS_CAP - 1);

      // ── Animation: snapshot current time once for the whole frame ────────
      const now = performance.now();

      // ── Anim §1 + §6: detect newest bar arrival ───────────────────────────
      // Compare bar_index of the rightmost visible bar. On first render or when
      // the chart is scrolled, _lastNewestBarIndex may already match — only fire
      // animations when a genuinely new bar has appeared.
      const newestD    = data.bars[to]?.originalData;
      const newestBidx = newestD?.bar_index ?? to;

      if (!REDUCED_MOTION && this._lastNewestBarIndex !== -1 && newestBidx !== this._lastNewestBarIndex) {
        // New bar arrived: sweep the new column in, fade the separator of the
        // column that just became "previous".
        _barSweep.set(newestBidx, { startTs: now, duration: DUR_BAR_SWEEP });
        _sepFade.set(newestBidx - 1, { startTs: now, duration: DUR_SEPARATOR_FADE });
        _scheduleAnim();
      }
      this._lastNewestBarIndex = newestBidx;

      // ── Compute cross-bar maxima for scaling ──────────────────────────────
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

        const barIdx = d.bar_index ?? i;

        // Bar center in bitmap pixels — keep as-is (LW Charts provides this)
        const xC = Math.round(bar.x * hpr);

        // Column left edge
        const colLeft  = xC - Math.floor(innerW / 2);
        const colRight = colLeft + innerW;

        // ── Anim §6: separator fade-in opacity ────────────────────────────
        const sepAnim  = !REDUCED_MOTION ? _sepFade.get(barIdx) : undefined;
        const sepAlpha = sepAnim ? _easeOut(_prog(sepAnim, now)) * 0.3 : undefined;

        // ── 1. Column separator (1px --rule line at left edge of column) ──
        ctx.save();
        if (sepAlpha !== undefined) ctx.globalAlpha = sepAlpha;
        ctx.fillStyle = C_RULE;
        ctx.fillRect(colLeft - GAP_BITMAP, 0, Math.max(1, GAP_BITMAP), canvasH);
        ctx.restore();

        const levelKeys = Object.keys(d.levels);
        if (levelKeys.length === 0) continue;

        // ── 2. Find POC price ─────────────────────────────────────────────
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

        // ── Anim §3: POC establishment detection ─────────────────────────
        if (!REDUCED_MOTION && pocPrice !== null) {
          const lastPoc = _lastPoc.get(barIdx);
          if (lastPoc !== undefined && Math.abs(lastPoc - pocPrice) > 0.01) {
            _pocPulse.set(barIdx, { startTs: now, duration: DUR_POC_PULSE });
            _scheduleAnim();
          }
          _lastPoc.set(barIdx, pocPrice);
        }

        // ── Anim §4: delta tick detection ─────────────────────────────────
        if (!REDUCED_MOTION && options.showDelta) {
          const curDelta = d.bar_delta ?? 0;
          const lastDelta = _lastDelta.get(barIdx);
          if (lastDelta !== undefined && lastDelta !== curDelta) {
            const prevW = _lastDeltaW.get(barIdx) ?? Math.min(1, Math.abs(lastDelta) / maxAbsDelta);
            _deltaTick.set(barIdx, { startTs: now, duration: DUR_DELTA_TICK, fromBarW: prevW });
            _scheduleAnim();
          }
          _lastDelta.set(barIdx, curDelta);
          _lastDeltaW.set(barIdx, Math.min(1, Math.abs(curDelta) / maxAbsDelta));
        }

        // ── 3. Single-column optimization (replay first bar or extreme zoom) ──
        // When only 1 bar is visible the chart feels empty; widen effective inner
        // width to fill the canvas and show richer info.
        const visibleBarCount = to - range.from + 1;
        const effectiveInnerW = visibleBarCount === 1
          ? Math.max(innerW, Math.round(200 * hpr))
          : innerW;
        const effectiveColLeft = visibleBarCount === 1
          ? xC - Math.floor(effectiveInnerW / 2)
          : colLeft;

        // ── 4. Build sorted row array (high price → low price = top → bottom) ──
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

          const isImbalanceBid = options.showImbalance && imbRatio <= (1 / IMBALANCE_THRESHOLD);
          const isImbalanceAsk = options.showImbalance && imbRatio >= IMBALANCE_THRESHOLD;

          // ── Anim §2: imbalance cell pulse detection ──────────────────────
          if (!REDUCED_MOTION) {
            const cellKey   = `${barIdx}:${tickKey}`;
            const curState: 'ask' | 'bid' | 'none' =
              isImbalanceAsk ? 'ask' : isImbalanceBid ? 'bid' : 'none';
            const lastState = _lastImb.get(cellKey) ?? 'none';
            if (curState !== 'none' && lastState === 'none') {
              _cellPulse.set(cellKey, { startTs: now, duration: DUR_IMBALANCE_PULSE });
              _scheduleAnim();
            }
            _lastImb.set(cellKey, curState);
          }

          rows.push({
            price,
            tickKey,
            yBitmap,
            bidVol,
            askVol,
            isImbalanceBid,
            isImbalanceAsk,
          });
        }

        // Sort price descending (higher price → top of chart → lower yBitmap)
        rows.sort((a, b) => b.price - a.price);

        // ── Anim §1: bar sweep opacity ────────────────────────────────────
        const sweepAnim    = !REDUCED_MOTION ? _barSweep.get(barIdx) : undefined;
        const sweepOpacity = sweepAnim ? 0.3 + _easeOut(_prog(sweepAnim, now)) * 0.7 : undefined;

        // ── 5. Clip to this column — prevents overflow into neighbors ─────
        ctx.save();
        if (sweepOpacity !== undefined) ctx.globalAlpha = sweepOpacity;
        ctx.beginPath();
        ctx.rect(effectiveColLeft, 0, effectiveInnerW, canvasH);
        ctx.clip();

        // ── 6. Draw all cell backgrounds + text ──────────────────────────
        for (const row of rows) {
          const isPoc    = pocPrice !== null && Math.abs(row.price - pocPrice) < 0.01;
          const cellKey  = `${barIdx}:${row.tickKey}`;
          const cellAnim = !REDUCED_MOTION ? _cellPulse.get(cellKey) : undefined;
          const pocAnim  = isPoc && !REDUCED_MOTION ? _pocPulse.get(barIdx) : undefined;
          _drawNumberCell(
            ctx, row, effectiveColLeft, effectiveInnerW, rowH, fontSize, font, sep,
            hpr, vpr, isPoc, barMaxTotalVol, colWCss, now, cellAnim, pocAnim,
          );
        }

        ctx.restore();   // clip + sweep opacity ends

        // ── 7. Stacked imbalance run lines (outside clip so they sit
        //       exactly on the column edge without being clipped away) ──────
        if (options.showImbalance && rows.length >= STACKED_RUN_MIN) {
          _drawStackedRunLines(ctx, rows, rowH, colLeft, colRight, hpr, vpr, barIdx, now);
        }

        // ── 8. POC dot marker — 4×4 amber square on left edge at POC row ──
        if (pocPrice !== null) {
          const yPocMedia = priceToCoordinate(pocPrice);
          if (yPocMedia !== null) {
            const yPoc    = Math.round(yPocMedia * vpr);
            const dotSzB  = Math.max(2, Math.round(POC_DOT_SIZE_CSS * hpr));
            const dotH    = Math.max(2, Math.round(POC_DOT_SIZE_CSS * vpr));
            const pocAnim = !REDUCED_MOTION ? _pocPulse.get(barIdx) : undefined;

            // Anim §3: dot scales 1.0 → 1.3 → 1.0 on POC shift
            const dotScale     = pocAnim ? 1.0 + _tri(_prog(pocAnim, now)) * 0.3 : 1.0;
            const scaledDotSzB = Math.round(dotSzB * dotScale);
            const scaledDotH   = Math.round(dotH   * dotScale);

            ctx.fillStyle = C_AMBER;
            ctx.fillRect(
              colLeft - scaledDotSzB,
              yPoc - Math.floor(scaledDotH / 2),
              scaledDotSzB,
              scaledDotH,
            );
          }
        }

        // ── 9. Delta footer ───────────────────────────────────────────────
        if (options.showDelta) {
          let bottomY = 0;
          for (const row of rows) {
            const rowBottom = row.yBitmap + Math.ceil(rowH / 2);
            if (rowBottom > bottomY) bottomY = rowBottom;
          }
          if (bottomY === 0) {
            bottomY = canvasH - Math.round((DELTA_GAP_CSS + DELTA_FONT_SIZE_CSS + 8) * vpr);
          }

          const deltaAnim = !REDUCED_MOTION ? _deltaTick.get(barIdx) : undefined;
          _drawDeltaFooter(
            ctx, d.bar_delta ?? 0, maxAbsDelta,
            colLeft, innerW, bottomY, hpr, vpr, now, deltaAnim,
          );
        }

        // ── 10. Bar timestamp header ──────────────────────────────────────
        if (colWCss > HEADER_MIN_COL_W_CSS) {
          let topRowY = canvasH;
          for (const row of rows) {
            const rowTop = row.yBitmap - Math.floor(rowH / 2);
            if (rowTop < topRowY) topRowY = rowTop;
          }
          _drawTimestamp(ctx, xC, topRowY, d.time, hpr, vpr);
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
    });
  }
}

// ── Numbers Bar cell ──────────────────────────────────────────────────────────
// Core of the Numbers Bar style: full-width cell with colored background and
// centered volume text. Display mode adapts to column width:
//
//   colWCss ≥ 70 → full "bid × ask" at 11px (FONT_SIZE_NORMAL_CSS)
//   colWCss ≥ 55 → full "bid × ask" at 10px (FONT_SIZE_SMALL_CSS)
//   colWCss ≥ 40 → abbreviated "↑256" / "↓142" at 10px
//   colWCss <  40 → color-only (no text, cellH < MIN_ROW_H_FOR_TEXT_CSS also triggers this)
//
// Text coordinates are rounded to integer bitmap pixels to prevent
// sub-pixel blurriness on Retina displays (common with fractional metrics).

function _drawNumberCell(
  ctx:            CanvasRenderingContext2D,
  row:            RowInfo,
  colLeft:        number,
  innerW:         number,
  rowH:           number,
  fontSize:       number,
  font:           string,
  sep:            string,
  hpr:            number,
  vpr:            number,
  isPoc:          boolean,
  barMaxTotalVol: number,
  colWCss:        number,
  now:            number,
  cellAnim?:      TimedAnim,
  pocAnim?:       TimedAnim,
): void {
  const { yBitmap, bidVol, askVol, isImbalanceBid, isImbalanceAsk } = row;

  // Cell top: row center minus half row height.
  // We use Math.round on yBitmap (already rounded in the call site) and
  // integer floor/ceil to guarantee pixel-aligned rectangles.
  const cellTop = yBitmap - Math.floor(rowH / 2);
  const cellH   = Math.max(1, rowH - 1);   // 1px inter-row gap

  // ── Background color ──────────────────────────────────────────────────────
  let bgR: number, bgG: number, bgB: number, bgAlpha: number;
  let textColor: string;

  const totalVol = bidVol + askVol;
  const imbRatio = askVol / Math.max(bidVol, 1);

  if (isPoc) {
    // POC override — amber tint, black text (high contrast against amber)
    bgR = 255; bgG = 214; bgB = 10;
    bgAlpha = 0.35;
    // Anim §3: POC pulse — bg oscillates 0.35 → 0.60 → 0.35
    if (pocAnim) bgAlpha = 0.35 + _tri(_prog(pocAnim, now)) * 0.25;
    textColor = '#000000';
  } else if (isImbalanceAsk || imbRatio >= IMBALANCE_THRESHOLD) {
    // BUY imbalance — ask dominates — green tint
    bgR = 0; bgG = 255; bgB = 136;
    bgAlpha = 0.22;
    // Anim §2: newly-imbalanced cell pulse — bg oscillates 0.22 → 0.45 → 0.22
    if (cellAnim) bgAlpha = 0.22 + _tri(_prog(cellAnim, now)) * 0.23;
    textColor = C_TEXT;   // always white on imbalance cells
  } else if (isImbalanceBid || imbRatio <= (1 / IMBALANCE_THRESHOLD)) {
    // SELL imbalance — bid dominates — red tint
    bgR = 255; bgG = 46; bgB = 99;
    bgAlpha = 0.22;
    // Anim §2: newly-imbalanced cell pulse — bg oscillates 0.22 → 0.45 → 0.22
    if (cellAnim) bgAlpha = 0.22 + _tri(_prog(cellAnim, now)) * 0.23;
    textColor = C_TEXT;   // always white on imbalance cells
  } else {
    // Neutral — subtle tint scaled by volume activity
    const totalRatio = barMaxTotalVol > 0 ? totalVol / barMaxTotalVol : 0;
    bgR = 255; bgG = 255; bgB = 255;
    bgAlpha = 0.02 + totalRatio * 0.06;
    // Volume-tier text: low→mute, medium→dim, high→text
    textColor = _neutralTextColor(totalVol, barMaxTotalVol);
  }

  // Fill cell background
  ctx.fillStyle = `rgba(${bgR},${bgG},${bgB},${bgAlpha.toFixed(3)})`;
  ctx.fillRect(colLeft, cellTop, innerW, cellH);

  // ── Text rendering ────────────────────────────────────────────────────────
  // Skip text if the cell is too short or the column is too narrow.
  const rowHCss = rowH / vpr;
  if (rowHCss < MIN_ROW_H_FOR_TEXT_CSS) return;   // color-only: row too short
  if (colWCss < COL_W_ARROW_LABEL_CSS)  return;   // color-only: column too narrow

  ctx.save();
  ctx.font         = font;
  ctx.textBaseline = 'middle';
  ctx.fillStyle    = textColor;

  // ── Retina-safe centering ─────────────────────────────────────────────────
  // textAlign='center' measures from the bitmap center point. Math.round on
  // both axes prevents the half-pixel offset that causes 1px vertical drift
  // on 2× displays when row height is odd in bitmap pixels.
  const textY   = Math.round(yBitmap);                    // vertical center
  const centerX = Math.round(colLeft + innerW / 2);       // horizontal center

  const bidLabel = _formatVol(bidVol);
  const askLabel = _formatVol(askVol);

  if (colWCss < COL_W_ABBREV_LABEL_CSS) {
    // Abbreviated mode (≥40 and <55): show dominant side with arrow prefix.
    // No separator — too narrow for it.
    const showAsk = askVol >= bidVol;
    const abbrev  = showAsk ? `\u2191${askLabel}` : `\u2193${bidLabel}`;
    ctx.textAlign = 'center';
    ctx.fillText(abbrev, centerX, textY);
  } else {
    // Full "bid × ask" label (or "bid x ask" if × didn't render).
    // Format: "142 × 256" — space around separator reads naturally in mono.
    // At widths <70px we already use 10px font, so the space is still fine.
    const label = `${bidLabel} ${sep} ${askLabel}`;
    ctx.textAlign = 'center';
    ctx.fillText(label, centerX, textY);

    // Warm the width cache for these formatted strings — avoids re-measuring
    // the same values on subsequent frames.
    _cachedTextWidth(ctx, bidLabel, font, fontSize);
    _cachedTextWidth(ctx, askLabel, font, fontSize);
  }

  ctx.restore();

  void hpr;   // referenced indirectly via font
}

// ── Stacked imbalance run lines ───────────────────────────────────────────────
// When 3+ consecutive rows are imbalanced in the same direction:
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
  barIdx:   number,
  now:      number,
): void {
  const lineW = Math.max(2, Math.round(STACKED_LINE_W_CSS * hpr));
  _scanAndDrawRun(ctx, rows, rowH, colLeft, colRight, lineW, 'bid', barIdx, now);
  _scanAndDrawRun(ctx, rows, rowH, colLeft, colRight, lineW, 'ask', barIdx, now);
}

function _scanAndDrawRun(
  ctx:      CanvasRenderingContext2D,
  rows:     RowInfo[],
  rowH:     number,
  colLeft:  number,
  colRight: number,
  lineW:    number,
  side:     'bid' | 'ask',
  barIdx:   number,
  now:      number,
): void {
  let runStart = -1;
  let runLen   = 0;

  const flush = (endIdx: number) => {
    if (runLen < STACKED_RUN_MIN) return;
    const startRow = rows[runStart];
    const endRow   = rows[endIdx - 1];
    const topY     = Math.min(startRow.yBitmap, endRow.yBitmap) - Math.floor(rowH / 2);
    const botY     = Math.max(startRow.yBitmap, endRow.yBitmap) + Math.ceil(rowH / 2);
    const fullRunH = botY - topY;
    const lineX    = side === 'bid' ? colLeft : colRight - lineW;

    // Anim §5: grow-in when run first reaches 4+ rows (milestone)
    const growKey = `${barIdx}:${side}`;
    if (!REDUCED_MOTION && runLen >= 4 && !_stackedFired.has(growKey)) {
      _stackedFired.add(growKey);
      _stackedGrow.set(growKey, { startTs: now, duration: DUR_STACKED_GROW });
      _scheduleAnim();
    }
    const growAnim = !REDUCED_MOTION ? _stackedGrow.get(growKey) : undefined;

    ctx.save();
    ctx.fillStyle = C_LIME;
    if (growAnim) {
      // Reveal from topY downward over the animation duration
      const drawH = Math.round(fullRunH * _easeOut(_prog(growAnim, now)));
      ctx.beginPath();
      ctx.rect(lineX, topY, lineW, drawH);
      ctx.clip();
    }
    ctx.fillRect(lineX, topY, lineW, fullRunH);
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
  now:         number,
  deltaAnim?:  DeltaTickAnim,
): void {
  if (!Number.isFinite(barDelta) || maxAbsDelta <= 0) return;

  const gapH      = Math.round(DELTA_GAP_CSS * vpr);
  const fontSzPx  = Math.max(6, Math.round(DELTA_FONT_SIZE_CSS * vpr));
  const barH      = Math.max(2, Math.round(DELTA_BAR_H_CSS * vpr));
  const leftPadB  = Math.round(DELTA_LEFT_PAD_CSS * hpr);

  const color = barDelta > 0 ? C_ASK : barDelta < 0 ? C_BID : C_TEXT_MUTE;

  const absVal = Math.abs(barDelta);
  const sign   = barDelta > 0 ? '+' : barDelta < 0 ? UNICODE_MINUS : '';
  const label  = `\u0394 ${sign}${absVal}`;

  const labelY = bottomRowY + gapH;

  ctx.save();
  ctx.font         = `400 ${fontSzPx}px ${FONT_FAMILY}`;
  ctx.textAlign    = 'left';
  ctx.textBaseline = 'top';

  // Anim §4: on delta change, flash white at peak then fade back to delta-color.
  // We layer a white overdraw at triangle alpha on top of the normal colored text.
  if (deltaAnim) {
    const pulse = _tri(_prog(deltaAnim, now));
    if (pulse > 0.01) {
      ctx.fillStyle   = `rgba(255,255,255,${(pulse * 0.65).toFixed(3)})`;
      ctx.globalAlpha = 1.0;
      ctx.fillText(label, colLeft + leftPadB, labelY);
    }
  }

  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.85;
  ctx.fillText(label, colLeft + leftPadB, labelY);

  // Mini proportional bar — smoothly eases to new width during delta changes
  const targetRatio = Math.min(1, Math.abs(barDelta) / maxAbsDelta);
  let displayRatio  = targetRatio;
  if (deltaAnim) {
    const t = _easeInOut(_prog(deltaAnim, now));
    displayRatio = deltaAnim.fromBarW + (targetRatio - deltaAnim.fromBarW) * t;
  }

  const barW  = Math.max(2, Math.round(innerW * displayRatio));
  const miniY = labelY + fontSzPx + Math.round(2 * vpr);

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

  const haloR = Math.round((squareSize / 2) + 2 * hpr);
  ctx.beginPath();
  ctx.arc(xC, squareTopY + Math.floor(squareSize / 2), haloR, 0, Math.PI * 2);
  ctx.fillStyle   = color;
  ctx.globalAlpha = 0.3;
  ctx.fill();

  ctx.globalAlpha = 1;
  ctx.fillStyle   = color;

  if (lineH > 0) {
    ctx.fillRect(xC - Math.floor(lineW / 2), lineTopY, lineW, lineH);
  }

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

  ctx.font = `500 ${fontSzPx}px ${FONT_FAMILY}`;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing
      = `${lsBitmap}px`;
  }
  ctx.fillText(EMPTY_TEXT, centerX, centerY);

  ctx.font = `italic 400 ${subFontSzPx}px ${FONT_FAMILY}`;
  if ('letterSpacing' in ctx) {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = '0px';
  }
  ctx.globalAlpha = 0.6;
  ctx.fillText(EMPTY_SUB_TEXT, centerX, centerY + fontSzPx + Math.round(4 * vpr));

  ctx.restore();

  void C_CYAN;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function clampVol(v: number | undefined | null): number {
  if (v === undefined || v === null || !Number.isFinite(v)) return 0;
  return Math.min(MAX_DISPLAY_VOL, Math.max(0, v));
}
