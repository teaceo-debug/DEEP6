'use client';
import { useEffect, useRef, useCallback } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import type { LiveMessage } from '@/types/deep6';

// First retry is intentionally fast (300ms); subsequent retries follow exponential backoff.
const BACKOFF_SEQUENCE = [300, 1000, 2000, 4000, 8000, 16000, 30000] as const;

export function useWebSocket(url: string): { reconnectNow: () => void } {
  const reconnectAttempt = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedIntentionallyRef = useRef(false);
  const reconnectingRef = useRef(false);

  // reconnectNow is a stable reference exposed to callers for forced reconnection.
  const reconnectNowRef = useRef<() => void>(() => undefined);
  const reconnectNow = useCallback(() => reconnectNowRef.current(), []);

  useEffect(() => {
    // Reset intentional-close flag at the start of every effect run (e.g. HMR, url change).
    closedIntentionallyRef.current = false;

    const connect = () => {
      // NOTE: We intentionally do NOT bail out when the tab is hidden on initial load.
      // WebSocket connections survive backgrounded tabs in real browsers.
      // Visibility is only used to park *reconnect backoff* (scheduleReconnect).
      console.debug('[useWebSocket] connect() called at', Date.now(), 'url=', url);

      reconnectingRef.current = false;

      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.debug('[useWebSocket] onopen at', Date.now());
        reconnectAttempt.current = 0;
        reconnectingRef.current = false;
        useTradingStore.getState().setStatus({
          type: 'status',
          connected: true,
          pnl: useTradingStore.getState().status.pnl,
          circuit_breaker_active: useTradingStore.getState().status.circuitBreakerActive,
          feed_stale: false,
          ts: Date.now() / 1000,
        });
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as LiveMessage;
          if (!msg || typeof (msg as { type?: unknown }).type !== 'string') return;
          useTradingStore.getState().dispatch(msg);
        } catch {
          // T-11-11: drop malformed payload silently, do not crash hook or stale store
        }
      };

      ws.onerror = () => {
        // handled by onclose
      };

      ws.onclose = (ev?: CloseEvent) => {
        console.debug(
          '[useWebSocket] onclose at',
          Date.now(),
          'code=',
          ev?.code,
          'reason=',
          ev?.reason,
          'wasClean=',
          ev?.wasClean,
        );
        useTradingStore.getState().setStatus({
          type: 'status',
          connected: false,
          pnl: useTradingStore.getState().status.pnl,
          circuit_breaker_active: useTradingStore.getState().status.circuitBreakerActive,
          feed_stale: false,
          ts: Date.now() / 1000,
        });
        if (closedIntentionallyRef.current) return;
        scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        // Park until tab becomes visible again; onVis will reset attempt counter and call connect().
        return;
      }
      reconnectingRef.current = true;
      const delay =
        BACKOFF_SEQUENCE[Math.min(reconnectAttempt.current, BACKOFF_SEQUENCE.length - 1)];
      reconnectAttempt.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    const onVis = () => {
      if (document.visibilityState !== 'visible') return;

      const ws = wsRef.current;
      if (ws !== null) {
        if (
          ws.readyState === WebSocket.OPEN ||
          ws.readyState === WebSocket.CONNECTING
        ) {
          // Already healthy — nothing to do.
          return;
        }
        // CLOSED or CLOSING: explicitly clean up, clear any parked timer,
        // reset backoff, then reconnect immediately.
        ws.close();
      }

      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      reconnectAttempt.current = 0;
      connect();
    };

    // Wire reconnectNow to the current effect's connect() so the stable callback
    // always delegates to the latest closure.
    reconnectNowRef.current = () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      reconnectAttempt.current = 0;
      connect();
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVis);
    }

    connect();

    return () => {
      // Mark closure as intentional so onclose does not trigger reconnect logic.
      closedIntentionallyRef.current = true;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      wsRef.current?.close();
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVis);
      }
    };
  }, [url]);

  return { reconnectNow };
}
