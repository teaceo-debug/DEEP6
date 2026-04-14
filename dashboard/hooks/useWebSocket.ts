'use client';
import { useEffect, useRef } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import type { LiveMessage } from '@/types/deep6';

const BACKOFF_SEQUENCE = [1000, 2000, 4000, 8000, 16000, 30000] as const;

export function useWebSocket(url: string) {
  const reconnectAttempt = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedIntentionallyRef = useRef(false);
  const reconnectingRef = useRef(false);

  useEffect(() => {
    closedIntentionallyRef.current = false;

    const connect = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        // Do not connect while tab is hidden (per UI-SPEC §WebSocket Protocol Contract)
        return;
      }
      reconnectingRef.current = false;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
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

      ws.onclose = () => {
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
        // Park until tab becomes visible again
        return;
      }
      reconnectingRef.current = true;
      const delay = BACKOFF_SEQUENCE[Math.min(reconnectAttempt.current, BACKOFF_SEQUENCE.length - 1)];
      reconnectAttempt.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    const onVis = () => {
      if (
        document.visibilityState === 'visible' &&
        (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED)
      ) {
        reconnectAttempt.current = 0;
        connect();
      }
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVis);
    }

    connect();

    return () => {
      closedIntentionallyRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVis);
      }
    };
  }, [url]);
}
