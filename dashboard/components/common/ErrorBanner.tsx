/**
 * ErrorBanner.tsx — Top-of-page error surface.
 *
 * Surfaces three states using exact strings from UI-SPEC §Copywriting Contract:
 *   1. Replay error (session not found): "Session not found. Select a date from history."
 *   2. WebSocket disconnected: "Connection lost. Reconnecting..."
 *   3. Feed stalled: "Feed stalled — no updates in 10s. Check backend."
 *
 * Priority: replay errors > connection lost > feed stalled.
 * Returns null when no error condition is active.
 *
 * Feed staleness is evaluated reactively: if status.lastTs is older than 10s
 * and we're in live mode, the feedStale flag in tradingStore drives the message.
 */
'use client';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';

export function ErrorBanner() {
  const status = useTradingStore((s) => s.status);
  const replayError = useReplayStore((s) => s.error);
  const replayMode = useReplayStore((s) => s.mode);

  let msg: string | null = null;

  if (replayError) {
    msg = replayError;
  } else if (replayMode === 'live' && !status.connected) {
    msg = 'Connection lost. Reconnecting...';
  } else if (status.feedStale) {
    msg = 'Feed stalled — no updates in 10s. Check backend.';
  }

  if (!msg) return null;

  return (
    <div
      role="alert"
      className="text-[13px] px-4 py-2"
      style={{
        background: 'rgba(239, 68, 68, 0.15)',
        color: 'var(--destructive)',
        borderBottom: '1px solid rgba(239, 68, 68, 0.40)',
      }}
    >
      {msg}
    </div>
  );
}
