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

  // Track which signal is "just arrived" for the 1s TYPE_A pulse.
  // prevVersionRef lets us detect the frame when version increments by 1.
  const prevVersionRef = useRef(lastSignalVersion);
  const justArrivedRef = useRef(false);

  if (lastSignalVersion !== prevVersionRef.current) {
    prevVersionRef.current = lastSignalVersion;
    justArrivedRef.current = true;
  } else {
    justArrivedRef.current = false;
  }

  // RingBuffer.toArray() returns oldest→newest; reverse for newest-first display.
  const displaySignals = [...signals].reverse();

  if (displaySignals.length === 0) {
    return (
      <div className="flex-1 flex items-start p-4">
        <p className="text-[13px] text-muted">No signals yet. Waiting for market data.</p>
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
