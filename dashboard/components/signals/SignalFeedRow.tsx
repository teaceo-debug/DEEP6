'use client';
import type { SignalEvent } from '@/types/deep6';

// ── Color maps ────────────────────────────────────────────────────────────────

const BORDER_COLOR: Record<string, string> = {
  TYPE_A: 'border-l-type-a',
  TYPE_B: 'border-l-type-b',
  TYPE_C: 'border-l-type-c',
  QUIET:  'border-l-muted',
};

const BADGE_COLOR: Record<string, string> = {
  TYPE_A: 'bg-type-a/20 text-type-a',
  TYPE_B: 'bg-type-b/20 text-type-b',
  TYPE_C: 'bg-type-c/20 text-type-c',
  QUIET:  'bg-muted/20 text-muted',
};

// ── Component ─────────────────────────────────────────────────────────────────

interface SignalFeedRowProps {
  sig: SignalEvent;
  narrative?: string;
  /** Pass true for 1s pulse animation on TYPE_A arrival. */
  justArrived?: boolean;
}

export function SignalFeedRow({ sig, narrative, justArrived }: SignalFeedRowProps) {
  const tier = sig.tier ?? 'QUIET';
  const borderClass = BORDER_COLOR[tier] ?? BORDER_COLOR.QUIET;
  const badgeClass  = BADGE_COLOR[tier]  ?? BADGE_COLOR.QUIET;

  const scoreColor =
    sig.total_score >= 80 ? 'text-type-a' :
    sig.total_score >= 50 ? 'text-type-b' :
    'text-muted';

  // TYPE_A pulse: applied via className — CSS keyframe restarts on remount.
  // See globals.css .signal-type-a-pulse + @keyframes typeAPulse.
  const pulseClass = tier === 'TYPE_A' && justArrived ? 'signal-type-a-pulse' : '';

  const timeStr = new Date(sig.ts * 1000).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const agreementStr = sig.categories_firing?.length
    ? sig.categories_firing.join('+') + ' agree'
    : '';

  return (
    <div
      className={[
        'h-12 pl-3 pr-2 border-l-4',
        borderClass,
        pulseClass,
        'flex flex-col justify-center border-b border-border-subtle',
      ].join(' ')}
    >
      {/* Row 1: badge + narrative + time */}
      <div className="flex items-center gap-2 text-[13px]">
        <span className={`px-1.5 py-0.5 rounded text-[12px] font-semibold ${badgeClass}`}>
          {tier}
        </span>
        <span className="text-fg truncate flex-1">{narrative || ''}</span>
        <span className="font-mono text-[12px] text-muted shrink-0">{timeStr}</span>
      </div>

      {/* Row 2: score + engine agreement */}
      <div className="flex items-center gap-2 text-[12px] text-muted min-w-0">
        <span className={`font-mono shrink-0 ${scoreColor}`}>
          Score: {Math.round(sig.total_score)}
        </span>
        {agreementStr && (
          <>
            <span className="shrink-0">·</span>
            <span className="truncate">{agreementStr}</span>
          </>
        )}
      </div>
    </div>
  );
}
