/**
 * ReturnToLivePill.tsx — Pill shown when user has panned away from latest bar.
 *
 * Per UI-SPEC §Price Axis Auto-Center Behavior:
 *   - Shows when userHasPanned === true AND mode === 'live'.
 *   - Absolutely positioned top-right of the chart area.
 *   - Clicking resets pan (setPanned(false)) which triggers scrollToRealTime in FootprintChart.
 *
 * Copywriting per UI-SPEC §Copywriting Contract: "Return to live price"
 */
'use client';
import { useReplayStore } from '@/store/replayStore';

export function ReturnToLivePill() {
  const mode = useReplayStore((s) => s.mode);
  const userHasPanned = useReplayStore((s) => s.userHasPanned);

  if (mode !== 'live' || !userHasPanned) return null;

  return (
    <button
      onClick={() => useReplayStore.getState().setPanned(false)}
      className="absolute top-2 right-2 z-10 rounded px-2 py-1 text-[12px] font-semibold hover:opacity-80"
      style={{
        background: 'var(--bg-elevated)',
        color: 'var(--type-a)',
      }}
    >
      Return to live price
    </button>
  );
}
