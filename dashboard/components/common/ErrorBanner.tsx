/**
 * ErrorBanner.tsx — per UI-SPEC v2 §8
 *
 * Copy (exact):
 *   disconnected → "LINK DOWN. RETRYING…"           --bid color
 *   stale        → "STALE — last tick {N}s ago"      --amber color
 *   replay_404   → "SESSION NOT FOUND. SELECT FROM HISTORY."  --amber color
 *
 * Container: bg --surface-1, border-bottom 1px in reason-color at 40% opacity,
 * padding 6px 16px, text-sm, .label-tracked
 *
 * Trigger logic (store fields) unchanged — only copy + visual updated.
 */
'use client';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';

export function ErrorBanner() {
  const status = useTradingStore((s) => s.status);
  const replayError = useReplayStore((s) => s.error);
  const replayMode = useReplayStore((s) => s.mode);

  // Determine message + accent color
  let msg: string | null = null;
  let accentColor = 'var(--bid)';

  if (replayError) {
    // Session-not-found is the primary replay error surfaced by useReplayController
    msg = 'SESSION NOT FOUND. SELECT FROM HISTORY.';
    accentColor = 'var(--amber)';
  } else if (replayMode === 'live' && !status.connected) {
    msg = 'LINK DOWN. RETRYING\u2026';
    accentColor = 'var(--bid)';
  } else if (status.feedStale) {
    const staleSecs = status.lastTs > 0
      ? Math.round((Date.now() / 1000) - status.lastTs)
      : 0;
    msg = `STALE \u2014 last tick ${staleSecs}s ago`;
    accentColor = 'var(--amber)';
  }

  if (!msg) return null;

  return (
    <div
      role="alert"
      className="text-sm label-tracked"
      style={{
        background: 'var(--surface-1)',
        borderBottom: `1px solid color-mix(in srgb, ${accentColor} 40%, transparent)`,
        padding: '6px 16px',
        color: accentColor,
      }}
    >
      {msg}
    </div>
  );
}
