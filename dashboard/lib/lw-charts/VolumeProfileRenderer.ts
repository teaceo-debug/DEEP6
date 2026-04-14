/**
 * VolumeProfileRenderer — pure rendering logic for the volume profile sidebar.
 *
 * Draws a horizontal histogram showing cumulative bid/ask volume at each price
 * level across all visible bars in the ring buffer. Positioned LEFT of the
 * footprint — 70px wide, full chart height.
 *
 * Color tokens match globals.css exactly (cannot use CSS vars in canvas).
 *
 * v2 changes:
 *  - Opacity dialed to 40% (secondary data layer)
 *  - Width expanded to 70px
 *  - POC: amber tint + "POC" label at right edge
 *  - VAH/VAL: dashed lines + edge labels
 *  - Σ ratio moved to top, reformatted
 *  - Heat index vertical bar in top-right corner
 *  - Animation: 200ms fade-in on profile update
 *  - Click-to-row stub (handled in VolumeProfile.tsx)
 */

// ── Color tokens (UI-SPEC v2 §1) ─────────────────────────────────────────────
const C_BID      = '#ff2e63';  // --bid  (sellers)
const C_ASK      = '#00ff88';  // --ask  (buyers)
const C_AMBER    = '#ffd60a';  // --amber (POC)
const C_CYAN     = '#00d9ff';  // --cyan  (spread / heat index cool)
const C_VOID     = '#000000';  // --void (background)
const C_RULE     = '#1f1f1f';  // --rule (border / row gap)
const C_TEXT_DIM = '#4a4a4a';  // --text-mute / --text-dim

export const PROFILE_WIDTH_CSS = 70;    // CSS pixels (exported for VolumeProfile.tsx)
const BID_ASK_OPACITY         = 0.40;  // 40% — secondary layer
const MIN_VOL_PCT             = 0.05;  // skip rows < 5% of max (noise guard)
const FONT_FAMILY             = '"JetBrains Mono", monospace';
const FONT_SIZE_POC           = 9;     // px — tiny label at POC
const FONT_SIZE_RATIO         = 10;    // px — Σ ratio header
const FONT_SIZE_VAH_VAL       = 8;     // px — VAH/VAL edge labels

// Bar area = full width minus 1px border each side
const BAR_AREA_W = PROFILE_WIDTH_CSS - 2;   // 68px
// Reserve ~5px on the right for the "POC" label in the POC row
const MAX_BAR_W  = BAR_AREA_W - 5;          // 63px ≈ spec's 65 minus trim
const HEAT_W     = 5;                        // heat index bar width (right edge)
const HEAT_H_MAX = 40;                       // heat index max height (px)

// VAH/VAL: 70% of total volume defines the value area
const VALUE_AREA_PCT = 0.70;

// ── Aggregation types ─────────────────────────────────────────────────────────

export interface LevelAggregate {
  price:   number;
  bidVol:  number;
  askVol:  number;
  total:   number;
}

export interface ProfileData {
  levels:     LevelAggregate[];  // sorted by price ascending
  maxTotal:   number;            // highest total across all levels
  pocPrice:   number;            // price of peak total
  vahPrice:   number;            // top of 70% value area
  valPrice:   number;            // bottom of 70% value area
  cumBid:     number;            // sum of all bid vol
  cumAsk:     number;            // sum of all ask vol
  /** Concentration metric 0–1 (0 = perfectly spread, 1 = all at one level) */
  concentration: number;
}

// ── Aggregation ───────────────────────────────────────────────────────────────

/**
 * Aggregates bid/ask volume per price tick across all bars.
 * Levels keys are stringified tick integers; price = tick * 0.25.
 */
export function aggregateProfile(bars: Array<{
  levels: Record<string, { bid_vol: number; ask_vol: number }>;
}>): ProfileData {
  const map = new Map<number, { bid: number; ask: number }>();

  for (const bar of bars) {
    for (const [tickStr, lv] of Object.entries(bar.levels)) {
      const price = parseInt(tickStr, 10) * 0.25;
      const entry = map.get(price);
      if (entry) {
        entry.bid += lv.bid_vol;
        entry.ask += lv.ask_vol;
      } else {
        map.set(price, { bid: lv.bid_vol, ask: lv.ask_vol });
      }
    }
  }

  if (map.size === 0) {
    return {
      levels: [], maxTotal: 0, pocPrice: 0,
      vahPrice: 0, valPrice: 0,
      cumBid: 0, cumAsk: 0, concentration: 0,
    };
  }

  let maxTotal  = 0;
  let pocPrice  = 0;
  let cumBid    = 0;
  let cumAsk    = 0;

  const levels: LevelAggregate[] = [];

  for (const [price, { bid, ask }] of map.entries()) {
    const total = bid + ask;
    levels.push({ price, bidVol: bid, askVol: ask, total });
    cumBid += bid;
    cumAsk += ask;
    if (total > maxTotal) {
      maxTotal = total;
      pocPrice = price;
    }
  }

  // Sort ascending by price (bottom → top)
  levels.sort((a, b) => a.price - b.price);

  // ── Value Area (VAH / VAL) ────────────────────────────────────────────────
  // Start from POC, expand outward until 70% of total volume is captured.
  const grandTotal    = cumBid + cumAsk;
  const targetVol     = grandTotal * VALUE_AREA_PCT;
  const pocIdx        = levels.findIndex(l => l.price === pocPrice);

  let vahPrice = pocPrice;
  let valPrice = pocPrice;
  let accumulated = levels[pocIdx]?.total ?? 0;
  let hi = pocIdx;
  let lo = pocIdx;

  while (accumulated < targetVol && (hi < levels.length - 1 || lo > 0)) {
    const nextHiVol = hi < levels.length - 1 ? levels[hi + 1].total : 0;
    const nextLoVol = lo > 0                  ? levels[lo - 1].total : 0;
    if (nextHiVol >= nextLoVol && hi < levels.length - 1) {
      hi++;
      accumulated += levels[hi].total;
      vahPrice = levels[hi].price;
    } else if (lo > 0) {
      lo--;
      accumulated += levels[lo].total;
      valPrice = levels[lo].price;
    } else {
      hi++;
      accumulated += levels[hi].total;
      vahPrice = levels[hi].price;
    }
  }

  // ── Concentration (Gini-like metric) ──────────────────────────────────────
  // concentration = sum of squared shares = HHI-like index (0 = uniform, 1 = single)
  // We normalize against the single-level worst case.
  let sumSq = 0;
  if (grandTotal > 0) {
    for (const lv of levels) {
      const share = lv.total / grandTotal;
      sumSq += share * share;
    }
  }
  const n = levels.length;
  // Normalize: (HHI - 1/n) / (1 - 1/n)  → 0 when uniform, 1 when concentrated
  const concentration = n > 1 ? (sumSq - 1 / n) / (1 - 1 / n) : 1;

  return {
    levels, maxTotal, pocPrice,
    vahPrice, valPrice,
    cumBid, cumAsk,
    concentration: Math.max(0, Math.min(1, concentration)),
  };
}

// ── Rendering ─────────────────────────────────────────────────────────────────

export interface DrawProfileOptions {
  ctx:        CanvasRenderingContext2D;
  profile:    ProfileData;
  priceMin:   number;    // visible price range bottom
  priceMax:   number;    // visible price range top
  canvasW:    number;    // CSS px width of the canvas (= PROFILE_WIDTH_CSS)
  canvasH:    number;    // CSS px height
  tickSize:   number;    // price increment per tick (0.25 for NQ)
  /** 0–1: fade-in alpha (1 = fully opaque). Caller drives animation. */
  fadeAlpha?: number;
}

export function drawProfile(opts: DrawProfileOptions): void {
  const {
    ctx, profile, priceMin, priceMax,
    canvasW, canvasH, tickSize,
    fadeAlpha = 1,
  } = opts;

  ctx.clearRect(0, 0, canvasW, canvasH);

  if (profile.levels.length === 0) return;

  const priceRange = priceMax - priceMin;
  if (priceRange <= 0) return;

  // Apply global fade for animation
  ctx.save();
  ctx.globalAlpha = fadeAlpha;

  // ── Background panel ───────────────────────────────────────────────────────
  ctx.fillStyle = C_VOID;
  ctx.fillRect(0, 0, canvasW, canvasH);

  // Thin right border to separate from main chart
  ctx.strokeStyle = C_RULE;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(canvasW - 0.5, 0);
  ctx.lineTo(canvasW - 0.5, canvasH);
  ctx.stroke();

  const minVolThreshold = profile.maxTotal * MIN_VOL_PCT;

  // Row height = (tickSize / priceRange) * canvasH
  const rowH = Math.max(1, (tickSize / priceRange) * canvasH);

  // Helper: convert price → Y coordinate (top = high price)
  const priceToY = (price: number): number =>
    ((priceMax - price) / priceRange) * canvasH;

  // Build bid/ask colors with opacity
  const bidColor   = hexWithAlpha(C_BID,   BID_ASK_OPACITY);
  const askColor   = hexWithAlpha(C_ASK,   BID_ASK_OPACITY);
  const amberColor = hexWithAlpha(C_AMBER, 0.60);

  let pocRowY:  number | null = null;
  let vahRowY:  number | null = null;
  let valRowY:  number | null = null;

  // ── Pass 1: bars ──────────────────────────────────────────────────────────
  for (const lv of profile.levels) {
    if (lv.price < priceMin - tickSize || lv.price > priceMax + tickSize) continue;
    if (lv.total < minVolThreshold) continue;

    const y     = priceToY(lv.price);
    const drawY = Math.max(0, y - rowH + 1);   // +1 for 1px row gap
    const drawH = Math.min(rowH - 1, canvasH - drawY);

    if (drawH <= 0) continue;

    const isPOC = lv.price === profile.pocPrice;
    const barW  = (lv.total / profile.maxTotal) * MAX_BAR_W;
    const bidW  = lv.total > 0 ? (lv.bidVol / lv.total) * barW : 0;
    const askW  = barW - bidW;

    if (isPOC) {
      // Amber tint across full width at POC
      ctx.fillStyle = hexWithAlpha(C_AMBER, 0.12);
      ctx.fillRect(0, drawY, canvasW - 1, drawH);
      // POC bar: amber at 60%
      ctx.fillStyle = amberColor;
      ctx.fillRect(1, drawY, barW, drawH);
      pocRowY = drawY;
    } else {
      if (bidW > 0) {
        ctx.fillStyle = bidColor;
        ctx.fillRect(1, drawY, bidW, drawH);
      }
      if (askW > 0) {
        ctx.fillStyle = askColor;
        ctx.fillRect(1 + bidW, drawY, askW, drawH);
      }
    }

    // Track VAH / VAL
    if (lv.price === profile.vahPrice) vahRowY = drawY;
    if (lv.price === profile.valPrice) valRowY = drawY;
  }

  // ── Pass 2: POC label ─────────────────────────────────────────────────────
  if (pocRowY !== null) {
    const drawH = Math.max(1, Math.min(rowH - 1, canvasH - pocRowY));
    ctx.font          = `${FONT_SIZE_POC}px ${FONT_FAMILY}`;
    ctx.fillStyle     = C_AMBER;
    ctx.textAlign     = 'right';
    ctx.textBaseline  = 'middle';
    ctx.fillText('POC', canvasW - HEAT_W - 3, pocRowY + drawH / 2);
  }

  // ── Pass 3: VAH / VAL dashed lines + labels ───────────────────────────────
  ctx.setLineDash([3, 3]);
  ctx.strokeStyle = C_TEXT_DIM;
  ctx.lineWidth   = 1;

  if (vahRowY !== null) {
    ctx.beginPath();
    ctx.moveTo(0,        vahRowY + 0.5);
    ctx.lineTo(canvasW,  vahRowY + 0.5);
    ctx.stroke();
    ctx.font         = `${FONT_SIZE_VAH_VAL}px ${FONT_FAMILY}`;
    ctx.fillStyle    = C_TEXT_DIM;
    ctx.textAlign    = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('VAH', 2, vahRowY);
  }

  if (valRowY !== null) {
    const drawH = Math.max(1, Math.min(rowH - 1, canvasH - valRowY));
    ctx.beginPath();
    ctx.moveTo(0,       valRowY + drawH + 0.5);
    ctx.lineTo(canvasW, valRowY + drawH + 0.5);
    ctx.stroke();
    ctx.font         = `${FONT_SIZE_VAH_VAL}px ${FONT_FAMILY}`;
    ctx.fillStyle    = C_TEXT_DIM;
    ctx.textAlign    = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('VAL', 2, valRowY + drawH);
  }

  ctx.setLineDash([]);  // reset dash

  // ── Pass 4: Σ ratio header (top of profile) ───────────────────────────────
  if (canvasH > 40 && (profile.cumBid + profile.cumAsk) > 0) {
    const total   = profile.cumBid + profile.cumAsk;
    const bidPct  = Math.round((profile.cumBid / total) * 100);
    const askPct  = 100 - bidPct;

    const bidHeavy = bidPct > 55;
    const askHeavy = askPct > 55;

    ctx.font         = `${FONT_SIZE_RATIO}px ${FONT_FAMILY}`;
    ctx.textBaseline = 'top';
    ctx.textAlign    = 'left';

    const prefix = '\u03A3 BID ';     // Σ BID
    const sep    = '\u00B7 ASK ';     // · ASK
    const bidStr = `${bidPct}%`;
    const askStr = `${askPct}%`;

    const prefixW = ctx.measureText(prefix).width;
    const bidW_px = ctx.measureText(bidStr + ' ').width;

    ctx.fillStyle = C_TEXT_DIM;
    ctx.fillText(prefix, 3, 3);

    ctx.fillStyle = bidHeavy ? C_BID : C_TEXT_DIM;
    ctx.fillText(bidStr, 3 + prefixW, 3);

    const sepX = 3 + prefixW + bidW_px;
    ctx.fillStyle = C_TEXT_DIM;
    ctx.fillText(sep, sepX, 3);

    const sepW  = ctx.measureText(sep).width;
    ctx.fillStyle = askHeavy ? C_ASK : C_TEXT_DIM;
    ctx.fillText(askStr, sepX + sepW, 3);
  }

  // ── Pass 5: Heat index vertical bar (top-right corner) ───────────────────
  // concentration 0 = spread (cyan, full bar), 1 = concentrated (amber, empty)
  // We invert: spread → full bar height, concentrated → short bar.
  const heatFill  = Math.max(0, 1 - profile.concentration);  // 1=spread, 0=concentrated
  const heatH     = Math.round(heatFill * HEAT_H_MAX);
  const heatX     = canvasW - HEAT_W - 1;
  const heatY0    = HEAT_H_MAX + 3;  // bottom of the heat bar area (below ratio header)

  // Draw track (empty bar background)
  ctx.fillStyle = hexWithAlpha(C_RULE, 0.8);
  ctx.fillRect(heatX, heatY0 - HEAT_H_MAX, HEAT_W - 1, HEAT_H_MAX);

  // Draw filled portion — gradient from cyan (bottom/spread) to amber (top/concentrated)
  if (heatH > 0) {
    const grad = ctx.createLinearGradient(0, heatY0 - heatH, 0, heatY0);
    grad.addColorStop(0, hexWithAlpha(C_AMBER, 0.8));  // top = concentrated end
    grad.addColorStop(1, hexWithAlpha(C_CYAN,  0.8));  // bottom = spread end
    ctx.fillStyle = grad;
    ctx.fillRect(heatX, heatY0 - heatH, HEAT_W - 1, heatH);
  }

  ctx.restore();  // end fadeAlpha
}

// ── Utility ───────────────────────────────────────────────────────────────────

/** Convert a 6-digit hex color to rgba with the given alpha (0–1). */
function hexWithAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * Given a Y coordinate from a canvas click event (CSS pixels),
 * return the nearest profile price level, or null if no levels are visible.
 */
export function yToPrice(
  clickY:    number,
  priceMin:  number,
  priceMax:  number,
  canvasH:   number,
  tickSize:  number,
): number | null {
  const priceRange = priceMax - priceMin;
  if (priceRange <= 0 || canvasH <= 0) return null;

  // Invert priceToY: price = priceMax - (y / canvasH) * priceRange
  const rawPrice = priceMax - (clickY / canvasH) * priceRange;

  // Snap to nearest tick
  const snapped = Math.round(rawPrice / tickSize) * tickSize;
  return snapped;
}
