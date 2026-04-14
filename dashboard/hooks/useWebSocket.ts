'use client';
import { useEffect, useRef, useCallback } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import type { LiveMessage } from '@/types/deep6';

// First retry is intentionally fast (300ms); subsequent retries follow exponential backoff.
// After RAPID_FAIL_THRESHOLD rapid disconnects (closed within RAPID_FAIL_MS of opening),
// the sequence switches to a more aggressive backoff starting at RAPID_FAIL_DELAY_MS.
const BACKOFF_SEQUENCE = [300, 1000, 2000, 4000, 8000, 16000, 30000] as const;
const RAPID_FAIL_MS = 100;           // connection alive < 100ms → counts as rapid fail
const RAPID_FAIL_THRESHOLD = 3;      // after 3 rapid fails, use aggressive backoff
const RAPID_FAIL_DELAY_MS = 5000;    // first retry delay after rapid-fail detection

export function useWebSocket(url: string): { reconnectNow: () => void } {
  const reconnectAttempt = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedIntentionallyRef = useRef(false);
  const reconnectingRef = useRef(false);
  // Rapid-disconnect detection: track consecutive opens that closed within RAPID_FAIL_MS
  const rapidFailCountRef = useRef(0);
  const openedAtRef = useRef<number>(0);

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
        const nowMs = Date.now();
        console.debug('[useWebSocket] onopen at', nowMs);
        openedAtRef.current = nowMs;
        reconnectAttempt.current = 0;
        reconnectingRef.current = false;

        const store = useTradingStore.getState();

        // Check if this is a long-disconnect recovery (>30s)
        const disconnectedAt = store.status.disconnectedAt;
        const wasLongDisconnect =
          disconnectedAt !== null && nowMs - disconnectedAt > 30_000;

        store.clearConnectionError();
        store.pushConnectionHistory({ ts: nowMs, state: 'connected' });
        store.setDisconnectedAt(null);

        if (wasLongDisconnect) {
          store.setReconnectSuccessToast(true);
        }

        store.setStatus({
          type: 'status',
          connected: true,
          pnl: store.status.pnl,
          circuit_breaker_active: store.status.circuitBreakerActive,
          feed_stale: false,
          ts: nowMs / 1000,
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
        // onerror always fires before onclose when the connection cannot be established.
        // We use it to flag a "connection refused" scenario (WS never opened).
        // The actual error message is set in onclose once we know the close code.
        if (openedAtRef.current === 0) {
          // Never opened — likely ECONNREFUSED or CORS pre-flight failure
          useTradingStore.getState().setConnectionError(
            'BACKEND OFFLINE \u2014 start uvicorn on :8000',
            null,
          );
        }
      };

      ws.onclose = (ev?: CloseEvent) => {
        const nowMs = Date.now();
        const code = ev?.code ?? null;
        const reason = ev?.reason ?? '';
        console.debug(
          '[useWebSocket] onclose at',
          nowMs,
          'code=',
          code,
          'reason=',
          reason,
          'wasClean=',
          ev?.wasClean,
        );

        const store = useTradingStore.getState();

        // Derive human-readable error based on WS close code
        if (!closedIntentionallyRef.current) {
          let errorMsg: string;
          if (openedAtRef.current === 0) {
            // Connection never opened — onerror already set msg, but also handle here
            errorMsg = 'BACKEND OFFLINE \u2014 start uvicorn on :8000';
          } else if (code === 1006) {
            errorMsg = 'CONNECTION DROPPED \u2014 CHECK BACKEND LOG';
          } else if (code === 1011) {
            errorMsg = reason
              ? `BACKEND ERROR \u2014 ${reason}`
              : 'BACKEND ERROR \u2014 SERVER RETURNED 1011';
          } else if (code === 1000) {
            errorMsg = 'CONNECTION CLOSED NORMALLY';
          } else {
            errorMsg = reason
              ? `DISCONNECTED \u2014 ${reason}`
              : 'LINK DOWN \u2014 RECONNECTING\u2026';
          }
          store.setConnectionError(errorMsg, code);
        }

        store.pushConnectionHistory({
          ts: nowMs,
          state: 'disconnected',
          code: code ?? undefined,
          reason: reason || undefined,
        });
        store.setDisconnectedAt(nowMs);

        store.setStatus({
          type: 'status',
          connected: false,
          pnl: store.status.pnl,
          circuit_breaker_active: store.status.circuitBreakerActive,
          feed_stale: false,
          ts: nowMs / 1000,
        });
        if (closedIntentionallyRef.current) return;

        // Rapid-disconnect detection: if the connection died within RAPID_FAIL_MS of opening,
        // increment the rapid-fail counter. After RAPID_FAIL_THRESHOLD consecutive rapid fails,
        // override the next backoff delay to avoid flooding the backend.
        const aliveMs = openedAtRef.current > 0 ? nowMs - openedAtRef.current : Infinity;
        if (aliveMs < RAPID_FAIL_MS) {
          rapidFailCountRef.current += 1;
          console.debug(
            '[useWebSocket] rapid disconnect detected',
            rapidFailCountRef.current,
            '/', RAPID_FAIL_THRESHOLD,
            'alive=', aliveMs, 'ms',
          );
          if (rapidFailCountRef.current >= RAPID_FAIL_THRESHOLD) {
            useTradingStore.getState().setConnectionError(
              'SERVER REJECTING CONNECTIONS \u2014 BACKEND MAY BE CRASHING',
              code,
            );
          }
        } else {
          // Healthy connection duration — reset rapid-fail counter
          rapidFailCountRef.current = 0;
        }
        openedAtRef.current = 0;

        scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        // Park until tab becomes visible again; onVis will reset attempt counter and call connect().
        return;
      }
      reconnectingRef.current = true;
      // If we have seen too many rapid failures, override the backoff to RAPID_FAIL_DELAY_MS
      // regardless of where we are in the normal backoff sequence.
      let delay: number;
      if (rapidFailCountRef.current >= RAPID_FAIL_THRESHOLD) {
        delay = RAPID_FAIL_DELAY_MS;
        console.debug('[useWebSocket] rapid-fail backoff applied, delay=', delay, 'ms');
      } else {
        delay = BACKOFF_SEQUENCE[Math.min(reconnectAttempt.current, BACKOFF_SEQUENCE.length - 1)];
      }
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
