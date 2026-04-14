'use client';
import { useTradingStore } from '@/store/tradingStore';
import { ScrollArea } from '@/components/ui/scroll-area';
import { TapeRow } from './TapeRow';
import type { TapeEntry } from '@/types/deep6';

// ── Component ─────────────────────────────────────────────────────────────────
// Per UI-SPEC §Tape & Sales: 50 rows max, newest first, 200px height, auto-scroll to top always.

export function TapeScroll() {
  // Reactive on tape changes — tape updates come from TapeEntry pushes.
  // No separate tapeVersion in store (pushTape doesn't bump a version),
  // so we subscribe to lastBarVersion as a coarse trigger for tape refresh.
  // Wave 3 can add a dedicated tapeVersion if needed.
  const _lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  void _lastBarVersion;

  const tape: TapeEntry[] = useTradingStore.getState().tape.toArray();
  // RingBuffer.toArray() returns oldest→newest; reverse for newest-first
  const displayTape = [...tape].reverse().slice(0, 50);

  if (displayTape.length === 0) {
    return (
      <div
        className="flex items-start p-3 text-[12px] text-muted"
        style={{ height: '200px', borderTop: '1px solid var(--border-subtle)' }}
      >
        No trades yet.
      </div>
    );
  }

  return (
    <ScrollArea
      style={{ height: '200px', borderTop: '1px solid var(--border-subtle)' }}
    >
      {displayTape.map((entry, idx) => (
        <TapeRow key={`${entry.ts}-${idx}`} entry={entry} />
      ))}
    </ScrollArea>
  );
}
