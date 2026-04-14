"use client"

/**
 * KronosBiasGauge — SVG semi-circle gauge showing Kronos E10 directional bias.
 *
 * Per D-11: Right panel — Kronos bias gauge.
 * value: 0-100. 0 = bear (left), 50 = neutral (center), 100 = bull (right).
 * Arc sweeps 180°. Fill color changes at 40/60 thresholds.
 */

interface KronosBiasGaugeProps {
  value: number
  label?: string
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

// Compute SVG arc path for a partial circle on the top half (180° sweep).
// cx, cy: center. r: radius. startDeg: start angle in degrees (0=right).
// endDeg: end angle. Both measured clockwise from rightmost point.
function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  // Convert degrees to radians. 0° = right, increases clockwise.
  const toRad = (d: number) => (d * Math.PI) / 180
  const sx = cx + r * Math.cos(toRad(startDeg))
  const sy = cy + r * Math.sin(toRad(startDeg))
  const ex = cx + r * Math.cos(toRad(endDeg))
  const ey = cy + r * Math.sin(toRad(endDeg))
  const largeArc = endDeg - startDeg > 180 ? 1 : 0
  return `M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`
}

export default function KronosBiasGauge({ value, label }: KronosBiasGaugeProps) {
  const v = clamp(value, 0, 100)

  // Determine fill color
  let fillColor = "#71717a" // zinc-500 (neutral)
  if (v > 60) fillColor = "#4ade80" // green-400
  if (v < 40) fillColor = "#f87171" // red-400

  // SVG dimensions
  const W = 160
  const H = 90  // Only need top half + some padding for text
  const cx = W / 2
  const cy = H - 10  // Center near bottom so semicircle is in upper area
  const r = 65

  // Background arc: 180° from left (180°) to right (0°)
  // In SVG coords (y increases downward), 180° sweep from left to right through top:
  // Start at left: 180°, end at right: 0° (or 360°)
  // We draw from 180° to 0° going counterclockwise via top.
  // But SVG arc with sweep-flag=0 goes counterclockwise.
  // Actually: Let's use a different approach — place center at bottom-center,
  // arc goes from left to right through the top (upper hemisphere).

  // Angles in standard math coords (0=right, counterclockwise positive)
  // The arc goes from 180° (left) to 0° (right) counterclockwise = semicircle over top.
  // In SVG coords (y flipped), that's from 180° to 0° with sweep-flag=1 (clockwise in screen).

  // Background track: full 180° arc
  const bgStart = 180
  const bgEnd = 0  // We'll use 360 to avoid 0 == same point issue

  // Fill arc: value 0% = left endpoint, 100% = right endpoint
  // Fill sweep = value/100 * 180 degrees, starting from left
  const fillAngle = bgStart - (v / 100) * 180  // Goes from 180° toward 0°

  // Track path (background): 180° sweep
  const trackPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`

  // Fill path: partial arc from left
  const fillEndRad = (fillAngle * Math.PI) / 180
  const fillEndX = cx + r * Math.cos(fillEndRad)
  const fillEndY = cy + r * Math.sin(fillEndRad)
  const fillLargeArc = v > 50 ? 1 : 0
  const fillPath = `M ${cx - r} ${cy} A ${r} ${r} 0 ${fillLargeArc} 1 ${fillEndX} ${fillEndY}`

  // Needle position (thin line from center to arc at fill angle)
  const needleX = cx + (r - 8) * Math.cos(fillEndRad)
  const needleY = cy + (r - 8) * Math.sin(fillEndRad)

  // Label above value display
  const displayLabel = label ?? "KRONOS BIAS"

  // Direction text
  let dirText = "NEUTRAL"
  let dirColor = "#a1a1aa" // zinc-400
  if (v > 60) { dirText = "BULLISH"; dirColor = "#4ade80" }
  if (v < 40) { dirText = "BEARISH"; dirColor = "#f87171" }

  return (
    <div className="flex flex-col items-center" style={{ width: W }}>
      <svg width={W} height={H} style={{ overflow: "visible" }}>
        {/* Background track */}
        <path
          d={trackPath}
          fill="none"
          stroke="#3f3f46"
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Fill arc */}
        <path
          d={fillPath}
          fill="none"
          stroke={fillColor}
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleX}
          y2={needleY}
          stroke="#e4e4e7"
          strokeWidth={2}
          strokeLinecap="round"
        />
        {/* Center dot */}
        <circle cx={cx} cy={cy} r={4} fill="#e4e4e7" />
        {/* Min label */}
        <text x={cx - r + 2} y={cy + 16} fontSize={9} fill="#52525b" textAnchor="middle">0</text>
        {/* Max label */}
        <text x={cx + r - 2} y={cy + 16} fontSize={9} fill="#52525b" textAnchor="middle">100</text>
      </svg>
      {/* Numeric value */}
      <div className="text-2xl font-bold font-mono leading-none mt-1" style={{ color: fillColor }}>
        {v.toFixed(0)}
      </div>
      {/* Direction label */}
      <div className="text-xs font-semibold mt-0.5" style={{ color: dirColor }}>
        {dirText}
      </div>
      {/* Gauge label */}
      <div className="text-[10px] text-zinc-500 tracking-widest mt-1">
        {displayLabel}
      </div>
    </div>
  )
}
