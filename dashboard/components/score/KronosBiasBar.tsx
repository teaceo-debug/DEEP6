'use client';

// ── Component ─────────────────────────────────────────────────────────────────

interface KronosBiasBarProps {
  direction: 'LONG' | 'SHORT' | 'NEUTRAL' | string;
  bias: number; // 0-100
}

export function KronosBiasBar({ direction, bias }: KronosBiasBarProps) {
  const clampedBias = Math.max(0, Math.min(100, bias));

  const fillColor =
    direction === 'LONG'  ? '#22c55e' :
    direction === 'SHORT' ? '#ef4444' :
    '#6b7280';

  const labelColor =
    direction === 'LONG'  ? 'text-ask' :
    direction === 'SHORT' ? 'text-bid' :
    'text-muted';

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[12px]">
        <span className={`font-semibold ${labelColor}`}>{direction || 'NEUTRAL'}</span>
        <span className="font-mono text-muted">{Math.round(clampedBias)}%</span>
      </div>
      <div
        className="rounded-full overflow-hidden"
        style={{ height: '6px', background: 'var(--border-subtle)' }}
      >
        <div
          className="h-full rounded-full motion-safe:transition-all motion-safe:duration-300"
          style={{
            width: `${clampedBias}%`,
            background: fillColor,
          }}
        />
      </div>
    </div>
  );
}
