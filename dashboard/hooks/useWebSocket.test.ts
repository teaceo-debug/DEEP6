import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTradingStore } from '@/store/tradingStore';

// --- MockWebSocket -------------------------------------------------------
// Must be defined before importing the hook module
class MockWS {
  static instances: MockWS[] = [];
  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e?: { code?: number; reason?: string; wasClean?: boolean }) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    MockWS.instances.push(this);
  }
  close(code?: number, reason?: string) {
    this.readyState = 3;
    this.onclose?.({ code: code ?? 1000, reason: reason ?? '', wasClean: code === 1000 });
  }
  fireClose(code: number, reason = '') {
    this.readyState = 3;
    this.onclose?.({ code, reason, wasClean: false });
  }
  fireError() {
    this.onerror?.(new Event('error'));
  }
  fireOpen() {
    this.readyState = 1;
    this.onopen?.();
  }
  fireMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}
// Patch WebSocket globally before the module is loaded
(globalThis as { WebSocket?: unknown }).WebSocket = MockWS as unknown;

// Import AFTER patching
import { useWebSocket } from './useWebSocket';

// -------------------------------------------------------------------------
const INIT_STATUS = {
  connected: false,
  pnl: 0,
  circuitBreakerActive: false,
  feedStale: false,
  lastTs: 0,
  sessionStartTs: 0,
  barsReceived: 0,
  signalsFired: 0,
  lastSignalTier: '',
  uptimeSeconds: 0,
  activeClients: 0,
  // Phase 11.3-r9 rich error state
  lastError: null,
  errorCount: 0,
  errorCode: null,
  connectionHistory: [],
  reconnectSuccessToast: false,
  disconnectedAt: null,
};

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWS.instances.length = 0;
    useTradingStore.setState({ status: INIT_STATUS });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    // Restore visibilityState
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
  });

  it('Test 1: dispatches status message to store when server sends connected:true', () => {
    renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];
    expect(ws).toBeDefined();

    ws.fireOpen();
    ws.fireMessage({ type: 'status', connected: true, pnl: 0, circuit_breaker_active: false, feed_stale: false, ts: 1234567890 });

    expect(useTradingStore.getState().status.connected).toBe(true);
  });

  it('Test 2: reconnects with 300ms fast-first retry then exponential backoff 1s→2s→4s', () => {
    // BACKOFF_SEQUENCE is now [300, 1000, 2000, 4000, 8000, 16000, 30000].
    // First disconnect → 300ms, second → 1000ms, third → 2000ms, fourth → 4000ms.
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));

    // ws1 is created immediately on mount; close it without firing open
    const ws1 = MockWS.instances[0];
    expect(MockWS.instances.length).toBe(1);
    ws1.close(); // schedules reconnect at 300ms (attempt 0)

    // Nothing new yet
    expect(MockWS.instances.length).toBe(1);

    // Advance 299ms — still no new WS
    vi.advanceTimersByTime(299);
    expect(MockWS.instances.length).toBe(1);

    // Advance 1ms to hit the 300ms mark — ws2 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(2);
    const ws2 = MockWS.instances[1];
    ws2.close(); // schedules reconnect at 1000ms (attempt 1)

    // Advance 999ms — still only ws2
    vi.advanceTimersByTime(999);
    expect(MockWS.instances.length).toBe(2);

    // Advance 1ms to hit the 1000ms mark — ws3 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(3);
    const ws3 = MockWS.instances[2];
    ws3.close(); // schedules reconnect at 2000ms (attempt 2)

    // Advance 1999ms — still only ws3
    vi.advanceTimersByTime(1999);
    expect(MockWS.instances.length).toBe(3);

    // Advance 1ms to hit the 2000ms mark — ws4 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(4);
    const ws4 = MockWS.instances[3];
    ws4.close(); // schedules reconnect at 4000ms (attempt 3)

    // Advance 3999ms — still only ws4
    vi.advanceTimersByTime(3999);
    expect(MockWS.instances.length).toBe(4);

    // Advance 1ms to hit the 4000ms mark — ws5 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(5);

    unmount();
  });

  it('Test 3: initial connect always attempted regardless of visibility; reconnect parked when hidden', () => {
    // New semantics: connect() no longer bails out when the tab is hidden on
    // initial mount. Only scheduleReconnect() parks when hidden.
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });

    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    // connect() runs unconditionally — ws1 must exist even though tab is hidden
    expect(MockWS.instances.length).toBe(1);
    const ws = MockWS.instances[0];

    ws.fireOpen();

    // While hidden, disconnect — scheduleReconnect should park (no setTimeout)
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    ws.close();

    const timedCalls = setTimeoutSpy.mock.calls.filter(c => typeof c[1] === 'number');
    expect(timedCalls.length).toBe(0);

    // Restore visible and fire visibilitychange — onVis resets attempt and connects
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(MockWS.instances.length).toBe(2);
    MockWS.instances[1].fireOpen();

    unmount();
  });

  it('Test 4: sets connected=false on close, connected=true on open', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    ws.fireOpen();
    expect(useTradingStore.getState().status.connected).toBe(true);

    ws.close();
    expect(useTradingStore.getState().status.connected).toBe(false);

    unmount();
  });

  it('Test 5: malformed JSON is dropped without throwing (T-11-11)', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];
    ws.fireOpen();

    // Malformed payload must not crash the hook
    expect(() => {
      ws.onmessage?.({ data: 'NOT_JSON{{{' });
    }).not.toThrow();

    // Store remains stable after malformed message
    expect(useTradingStore.getState().status.connected).toBe(true);

    unmount();
  });

  it('Test 6: close code 1006 sets lastError with CONNECTION DROPPED message', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    ws.fireOpen();
    expect(useTradingStore.getState().status.connected).toBe(true);

    ws.fireClose(1006);

    const status = useTradingStore.getState().status;
    expect(status.connected).toBe(false);
    expect(status.errorCode).toBe(1006);
    expect(status.lastError).toContain('CONNECTION DROPPED');
    expect(status.errorCount).toBeGreaterThan(0);

    unmount();
  });

  it('Test 7: close code 1011 sets lastError with BACKEND ERROR and includes reason', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    ws.fireOpen();
    ws.fireClose(1011, 'internal server error');

    const status = useTradingStore.getState().status;
    expect(status.errorCode).toBe(1011);
    expect(status.lastError).toContain('BACKEND ERROR');
    expect(status.lastError).toContain('internal server error');

    unmount();
  });

  it('Test 8: onerror before open sets BACKEND OFFLINE error', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    // Never fire open — simulate connection refused
    ws.fireError();

    const status = useTradingStore.getState().status;
    expect(status.lastError).toContain('BACKEND OFFLINE');

    unmount();
  });

  it('Test 9: rapid fail (3+ within 100ms) sets SERVER REJECTING error', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));

    // Three rapid disconnects (never opened → aliveMs = Infinity? No — openedAtRef stays 0)
    // We need to simulate: open immediately then close within 100ms for each
    // Use fake timers already set up; advance 0ms between open+close
    for (let i = 0; i < 3; i++) {
      const ws = MockWS.instances[MockWS.instances.length - 1];
      ws.fireOpen();
      // Close immediately (0ms elapsed — aliveMs < RAPID_FAIL_MS=100)
      ws.fireClose(1006);
      // Advance past backoff to get next ws
      vi.advanceTimersByTime(6000);
    }

    const status = useTradingStore.getState().status;
    expect(status.lastError).toContain('SERVER REJECTING');

    unmount();
  });

  it('Test 10: reconnectNow() triggers a new WebSocket connection', () => {
    const { result, unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    ws.fireOpen();
    ws.fireClose(1006);

    // At this point a reconnect timer is pending; call reconnectNow() to force immediate reconnect
    const before = MockWS.instances.length;
    result.current.reconnectNow();

    expect(MockWS.instances.length).toBe(before + 1);

    unmount();
  });

  it('Test 11: long-disconnect recovery (>30s) sets reconnectSuccessToast', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    ws.fireOpen();
    ws.fireClose(1006);

    // Simulate 31 seconds passing
    vi.advanceTimersByTime(31_000);

    // New ws should be created; fire open on it
    const ws2 = MockWS.instances[MockWS.instances.length - 1];
    ws2.fireOpen();

    expect(useTradingStore.getState().status.reconnectSuccessToast).toBe(true);

    unmount();
  });

  it('Test 12: connection history is populated on open and close', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    const ws = MockWS.instances[0];

    ws.fireOpen();
    ws.fireClose(1006);

    const history = useTradingStore.getState().status.connectionHistory;
    expect(history.length).toBeGreaterThanOrEqual(2);
    expect(history.some((e) => e.state === 'connected')).toBe(true);
    expect(history.some((e) => e.state === 'disconnected')).toBe(true);

    unmount();
  });
});
