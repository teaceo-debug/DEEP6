'use client';
import { useRef, useEffect } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import type { FootprintBar } from '@/types/deep6';

/**
 * useFootprintData — subscribes to lastBarVersion and returns a stable ref
 * containing the latest N bars from the ring buffer.
 *
 * Used by consumers that need a snapshot without triggering React re-renders
 * (Canvas-based renderers should use store.subscribe directly instead).
 *
 * @param windowSize Number of bars to retain (default 30 for 30-row footprint window).
 */
export function useFootprintData(windowSize = 30): React.RefObject<FootprintBar[]> {
  const barsRef = useRef<FootprintBar[]>([]);

  useEffect(() => {
    // Initial snapshot — RingBuffer.toArray() is oldest→newest; take the newest N.
    barsRef.current = useTradingStore.getState().bars.toArray().slice(-windowSize);

    const unsub = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      () => {
        barsRef.current = useTradingStore.getState().bars.toArray().slice(-windowSize);
      },
    );

    return unsub;
  }, [windowSize]);

  return barsRef;
}
