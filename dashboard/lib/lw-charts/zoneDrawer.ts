import type { ZoneRef } from '@/types/deep6';

// ── UI-SPEC v2 §1 tokens — strict semantic owners ─────────────────────────────
// --cyan   #00d9ff  → LVN zone (dashed stroke, 6% fill)
// --amber  #ffd60a  → HVN zone (solid stroke, 6% fill)
// --lime   #a3ff00  → ABSORPTION (solid, 8% fill) / EXHAUSTION (dashed, 4% fill)
// --bid    #ff2e63  → GEX_PUT (dashed, 8% fill)
// --ask    #00ff88  → GEX_CALL (dashed, 8% fill)
// --magenta #ff00aa → GEX label color (per UI-SPEC §4.2)

const C_CYAN    = '#00d9ff';
const C_AMBER   = '#ffd60a';
const C_LIME    = '#a3ff00';
const C_BID     = '#ff2e63';
const C_ASK     = '#00ff88';
const C_MAGENTA = '#ff00aa';
const C_TEXT_DIM = '#8a8a8a';  // --text-dim (VAH/VAL)

// ── Zone style table ──────────────────────────────────────────────────────────

interface ZoneStyle {
  fill: string;
  stroke: string;
  strokeWidth: number;
  dash: number[];
  label?: {
    color: string;
    dash: number[];  // line dash pattern for the labelled line
  };
}

const ZONE_STYLES: Record<string, ZoneStyle> = {
  LVN: {
    fill:   hexWithAlpha(C_CYAN, 0.06),
    stroke: C_CYAN,
    strokeWidth: 1,
    dash:   [4, 4],
  },
  HVN: {
    fill:   hexWithAlpha(C_AMBER, 0.06),
    stroke: C_AMBER,
    strokeWidth: 1,
    dash:   [],  // solid per UI-SPEC §4.2
  },
  ABSORPTION: {
    fill:   hexWithAlpha(C_LIME, 0.08),
    stroke: C_LIME,
    strokeWidth: 1,
    dash:   [],  // solid
  },
  EXHAUSTION: {
    fill:   hexWithAlpha(C_LIME, 0.04),
    stroke: C_LIME,
    strokeWidth: 1,
    dash:   [4, 4],  // dashed
  },
  GEX_CALL: {
    fill:   hexWithAlpha(C_ASK, 0.08),
    stroke: C_MAGENTA,
    strokeWidth: 1,
    dash:   [10, 5],  // 10px dash pattern per UI-SPEC §4.2
    label: {
      color: C_MAGENTA,
      dash:  [10, 5],
    },
  },
  GEX_PUT: {
    fill:   hexWithAlpha(C_BID, 0.08),
    stroke: C_MAGENTA,
    strokeWidth: 1,
    dash:   [10, 5],
    label: {
      color: C_MAGENTA,
      dash:  [10, 5],
    },
  },
  // VAH / VAL — 1px dashed --text-dim, no fill
  VAH: {
    fill:   'transparent',
    stroke: C_TEXT_DIM,
    strokeWidth: 1,
    dash:   [4, 4],
  },
  VAL: {
    fill:   'transparent',
    stroke: C_TEXT_DIM,
    strokeWidth: 1,
    dash:   [4, 4],
  },
};

/** Convert a hex color + alpha 0–1 into rgba(...) string */
function hexWithAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * Draw zone bands onto `ctx` using `priceToCoordinate` for y-projection.
 * Spans the full `chartWidth`.
 * Pure function — no side-effects outside the canvas context.
 */
export function drawZones(
  ctx: CanvasRenderingContext2D,
  zones: ZoneRef[],
  priceToCoordinate: (price: number) => number | null,
  chartWidth: number,
): void {
  if (!zones.length) return;

  for (const zone of zones) {
    const style = ZONE_STYLES[zone.kind];
    if (!style) continue;

    const yHigh = priceToCoordinate(zone.priceHigh);
    const yLow  = priceToCoordinate(zone.priceLow);
    if (yHigh === null || yLow === null) continue;

    const top    = Math.min(yHigh, yLow);
    const height = Math.abs(yLow - yHigh);
    if (height <= 0) continue;

    ctx.save();

    // Fill band
    if (style.fill !== 'transparent') {
      ctx.fillStyle = style.fill;
      ctx.fillRect(0, top, chartWidth, height);
    }

    // Top border line
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = style.strokeWidth;
    ctx.setLineDash(style.dash);

    ctx.beginPath();
    ctx.moveTo(0, top);
    ctx.lineTo(chartWidth, top);
    ctx.stroke();

    // Bottom border line
    ctx.beginPath();
    ctx.moveTo(0, top + height);
    ctx.lineTo(chartWidth, top + height);
    ctx.stroke();

    // GEX labels: "call wall" / "put wall" at right edge, text-xs --magenta
    if (style.label) {
      const labelText = zone.kind === 'GEX_CALL' ? 'CALL WALL' :
                        zone.kind === 'GEX_PUT'  ? 'PUT WALL' : zone.kind;
      ctx.setLineDash([]);  // reset dash before text
      ctx.fillStyle = style.label.color;
      ctx.font = '400 11px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(labelText, chartWidth - 4, top + height / 2);
    }

    ctx.restore();
  }
}
