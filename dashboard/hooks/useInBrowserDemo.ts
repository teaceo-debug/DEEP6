'use client';
import { useEffect, useRef } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import { createDemoState, runDemoTick } from '@/lib/in-browser-demo';
import type { DemoState } from '@/lib/in-browser-demo';

const TICK_MS = 500; // 500ms = rate 2x equivalent of the Python 1s loop

/**
 * useInBrowserDemo — runs the in-browser demo loop when `enabled` is true.
 *
 * On mount (when enabled):
 *   - Creates PriceModel, ScoreModel, SignalScheduler via createDemoState()
 *   - Sets a 500ms interval that calls runDemoTick() each fire
 *   - Dispatches all returned LiveMessages directly to useTradingStore
 *
 * When enabled=false this hook is a no-op (no interval, no store mutations).
 * Cleanup cancels the interval on unmount or when enabled toggles to false.
 */
export function useInBrowserDemo(enabled: boolean): void {
  const stateRef = useRef<DemoState | null>(null);

  useEffect(() => {
    if (!enabled) return;

    stateRef.current = createDemoState();

    const id = setInterval(() => {
      const s = stateRef.current;
      if (!s) return;
      const messages = runDemoTick(s);
      const dispatch = useTradingStore.getState().dispatch;
      for (const msg of messages) {
        dispatch(msg);
      }
    }, TICK_MS);

    return () => {
      clearInterval(id);
      stateRef.current = null;
    };
  }, [enabled]);
}
