'use client';
import type { TapeEntry } from '@/types/deep6';

// ── Component ─────────────────────────────────────────────────────────────────

interface TapeRowProps {
  entry: TapeEntry;
  /** Oversized trade threshold — default 50 contracts per UI-SPEC §Tape & Sales */
  oversizeThreshold?: number;
}

export function TapeRow({ entry, oversizeThreshold = 50 }: TapeRowProps) {
  const isOversized = entry.size >= oversizeThreshold;

  const sideColor = entry.side === 'ASK' ? 'text-ask' : 'text-bid';
  const sideLabel = entry.side === 'ASK' ? 'ASK' : 'BID';

  const timeStr = new Date(entry.ts * 1000).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div
      className={[
        'h-5 flex items-center px-2 gap-0 font-mono text-[12px]',
        isOversized ? 'bg-type-b/10' : '',
      ].join(' ')}
    >
      {/* Time — 56px */}
      <span className="text-muted" style={{ width: '56px', flexShrink: 0 }}>
        {timeStr}
      </span>

      {/* Price — 72px */}
      <span className="text-fg-strong" style={{ width: '72px', flexShrink: 0 }}>
        {entry.price.toFixed(2)}
      </span>

      {/* Size — 48px */}
      <span
        className={isOversized ? 'text-type-b font-semibold' : 'text-fg'}
        style={{ width: '48px', flexShrink: 0 }}
      >
        {entry.size}
      </span>

      {/* Side — 40px */}
      <span className={`${sideColor} font-semibold`} style={{ width: '40px', flexShrink: 0 }}>
        {sideLabel}
      </span>
    </div>
  );
}
