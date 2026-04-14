'use client';
import { useRef } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import { ScrollArea } from '@/components/ui/scroll-area';
import { SignalFeedRow } from './SignalFeedRow';
import type { SignalEvent } from '@/types/deep6';

// ── Component ─────────────────────────────────────────────────────────────────

export function SignalFeed() {
  // Reactive: re-renders when lastSignalVersion changes (new signal arrives)
  const lastSignalVersion = useTradingStore((s) => s.lastSignalVersion);
  // Read the actual signal array non-reactively via getState to avoid extra render
  const signals: SignalEvent[] = useTradingStore.getState().signals.toArray();

  // Track which signal is "just arrived" for TYPE_A animation.
  const prevVersionRef = useRef(lastSignalVersion);
  const justArrivedRef = useRef(false);

  if (lastSignalVersion !== prevVersionRef.current) {
    prevVersionRef.current = lastSignalVersion;
    justArrivedRef.current = true;
  } else {
    justArrivedRef.current = false;
  }

  // RingBuffer.toArray() returns oldest→newest; reverse for newest-first display.
  // Cap at 12 visible rows per UI-SPEC §4.3 (threat T-11.2-09 cap).
  const displaySignals = [...signals].reverse().slice(0, 12);

  if (displaySignals.length === 0) {
    return (
      <div
        className="flex-1 flex flex-col items-center justify-center gap-1"
        style={{ padding: '16px' }}
      >
        <p className="text-sm" style={{ color: 'var(--text-mute)' }}>
          [ NO SIGNALS ]
        </p>
        <p
          className="text-xs"
          style={{ color: 'var(--text-mute)', fontStyle: 'italic' }}
        >
          tail -f /dev/orderflow
        </p>
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1">
      {displaySignals.map((sig, idx) => (
        <SignalFeedRow
          key={`${sig.ts}-${sig.bar_index_in_session}-${idx}`}
          sig={sig}
          justArrived={idx === 0 && justArrivedRef.current}
        />
      ))}
    </ScrollArea>
  );
}
