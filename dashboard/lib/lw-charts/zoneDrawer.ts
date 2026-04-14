import type { ZoneRef } from '@/types/deep6';

// Per UI-SPEC §Zone Overlay Canvas Layer
const ZONE_STYLES: Record<string, { fill: string; stroke: string; dash: number[] }> = {
  LVN: {
    fill:   'rgba(56,189,248,0.08)',
    stroke: 'rgba(56,189,248,0.4)',
    dash:   [4, 4],
  },
  HVN: {
    fill:   'rgba(250,204,21,0.08)',
    stroke: 'rgba(250,204,21,0.4)',
    dash:   [4, 4],
  },
  ABSORPTION: {
    fill:   'rgba(163,230,53,0.12)',
    stroke: 'rgba(163,230,53,0.5)',
    dash:   [],
  },
  GEX_CALL: {
    fill:   'rgba(34,197,94,0.08)',
    stroke: 'rgba(34,197,94,0.5)',
    dash:   [4, 4],
  },
  GEX_PUT: {
    fill:   'rgba(239,68,68,0.08)',
    stroke: 'rgba(239,68,68,0.5)',
    dash:   [4, 4],
  },
};

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

    // Fill
    ctx.fillStyle = style.fill;
    ctx.fillRect(0, top, chartWidth, height);

    // Border top
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = 1;
    if (style.dash.length > 0) {
      ctx.setLineDash(style.dash);
    } else {
      ctx.setLineDash([]);
    }
    ctx.beginPath();
    ctx.moveTo(0, top);
    ctx.lineTo(chartWidth, top);
    ctx.stroke();

    // Border bottom
    ctx.beginPath();
    ctx.moveTo(0, top + height);
    ctx.lineTo(chartWidth, top + height);
    ctx.stroke();

    ctx.restore();
  }
}
