/**
 * VolumeProfileRenderer — pure rendering logic for the volume profile sidebar.
 *
 * Draws a horizontal histogram showing cumulative bid/ask volume at each price
 * level across all visible bars in the ring buffer. Positioned LEFT of the
 * footprint — 60px wide, full chart height.
 *
 * Color tokens match globals.css exactly (cannot use CSS vars in canvas).
 */

// ── Color tokens (UI-SPEC v2 §1) ─────────────────────────────────────────────
const C_BID   = '#ff2e63';  // --bid  (sellers)
const C_ASK   = '#00ff88';  // --ask  (buyers)
const C_AMBER = '#ffd60a';  // --amber (POC)
const C_VOID  = '#000000';  // --void (background)
const C_RULE  = '#1f1f1f';  // --rule (border)

const PROFILE_WIDTH_CSS = 60;   // CSS pixels
const BID_ASK_OPACITY   = 0.6;  // 60% opacity per spec
const MIN_VOL_PCT       = 0.05; // skip rows < 5% of max (noise guard)
const FONT_FAMILY       = '"JetBrains Mono", monospace';
const FONT_SIZE_POC     = 9;    // px — tiny label at POC
const FONT_SIZE_RATIO   = 8;    // px — Σ ratio footer

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
  cumBid:     number;            // sum of all bid vol
  cumAsk:     number;            // sum of all ask vol
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
    return { levels: [], maxTotal: 0, pocPrice: 0, cumBid: 0, cumAsk: 0 };
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

  return { levels, maxTotal, pocPrice, cumBid, cumAsk };
}

// ── Rendering ─────────────────────────────────────────────────────────────────

export interface DrawProfileOptions {
  ctx:       CanvasRenderingContext2D;
  profile:   ProfileData;
  priceMin:  number;   // visible price range bottom
  priceMax:  number;   // visible price range top
  canvasW:   number;   // CSS px width of the canvas (= PROFILE_WIDTH_CSS)
  canvasH:   number;   // CSS px height
  tickSize:  number;   // price increment per tick (0.25 for NQ)
}

export function drawProfile(opts: DrawProfileOptions): void {
  const { ctx, profile, priceMin, priceMax, canvasW, canvasH, tickSize } = opts;

  ctx.clearRect(0, 0, canvasW, canvasH);

  if (profile.levels.length === 0) return;

  const priceRange = priceMax - priceMin;
  if (priceRange <= 0) return;

  // Draw subtle background panel
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
  // We want a rectangle per tick that aligns with the price axis.
  const rowH = Math.max(1, (tickSize / priceRange) * canvasH);

  // Helper: convert price → Y coordinate (top = high price)
  const priceToY = (price: number): number =>
    ((priceMax - price) / priceRange) * canvasH;

  const maxBarW = canvasW - 2;  // leave 1px each side for border

  // Build bid/ask colors with opacity
  const bidColor = hexWithAlpha(C_BID, BID_ASK_OPACITY);
  const askColor = hexWithAlpha(C_ASK, BID_ASK_OPACITY);

  let pocRowY: number | null = null;

  for (const lv of profile.levels) {
    if (lv.price < priceMin - tickSize || lv.price > priceMax + tickSize) continue;
    if (lv.total < minVolThreshold) continue;

    const y = priceToY(lv.price);
    // rowH slightly overshoots on exact boundaries — clip to canvas
    const drawY = Math.max(0, y - rowH);
    const drawH = Math.min(rowH, canvasH - drawY);

    if (drawH <= 0) continue;

    const barW = (lv.total / profile.maxTotal) * maxBarW;
    const bidW = lv.total > 0 ? (lv.bidVol / lv.total) * barW : 0;
    const askW = barW - bidW;

    // Draw bid portion (left)
    if (bidW > 0) {
      ctx.fillStyle = bidColor;
      ctx.fillRect(1, drawY, bidW, drawH);
    }

    // Draw ask portion (right, adjacent to bid)
    if (askW > 0) {
      ctx.fillStyle = askColor;
      ctx.fillRect(1 + bidW, drawY, askW, drawH);
    }

    // Track POC row for outline pass
    if (lv.price === profile.pocPrice) {
      pocRowY = drawY;
    }
  }

  // POC outline — crisp 1px amber rect, no glow
  if (pocRowY !== null) {
    const barW = (profile.maxTotal / profile.maxTotal) * maxBarW;
    const drawH = Math.max(1, Math.min(rowH, canvasH - pocRowY));
    ctx.strokeStyle = C_AMBER;
    ctx.lineWidth = 1;
    ctx.strokeRect(1.5, pocRowY + 0.5, barW - 1, drawH - 1);

    // "POC" label at left edge of profile
    ctx.font = `${FONT_SIZE_POC}px ${FONT_FAMILY}`;
    ctx.fillStyle = C_AMBER;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText('POC', 3, pocRowY + drawH / 2);
  }

  // Σ ratio footer: only if there's room (profile height > 80px)
  if (canvasH > 80 && (profile.cumBid + profile.cumAsk) > 0) {
    const total   = profile.cumBid + profile.cumAsk;
    const askPct  = Math.round((profile.cumAsk / total) * 100);
    const bidPct  = 100 - askPct;
    const label   = `\u03A3 ${askPct}/${bidPct}`;  // Σ ask/bid

    ctx.font = `${FONT_SIZE_RATIO}px ${FONT_FAMILY}`;
    ctx.fillStyle = '#4a4a4a';  // --text-mute, subtle
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillText(label, canvasW / 2, canvasH - 2);
  }
}

// ── Utility ───────────────────────────────────────────────────────────────────

/** Convert a 6-digit hex color to rgba with the given alpha (0–1). */
function hexWithAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
