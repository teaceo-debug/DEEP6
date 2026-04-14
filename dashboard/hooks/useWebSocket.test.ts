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
  onclose: (() => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    MockWS.instances.push(this);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
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

  it('Test 2: reconnects with exponential backoff 1s→2s→4s (verified via timing windows)', () => {
    // Verify backoff via fake timers: each successive reconnect fires at the
    // expected delay (1000→2000→4000ms) without calling fireOpen() so the
    // attempt counter is not reset.
    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));

    // ws1 is created immediately on mount; close it without firing open
    const ws1 = MockWS.instances[0];
    expect(MockWS.instances.length).toBe(1);
    ws1.close(); // schedules reconnect at 1000ms

    // Nothing new yet
    expect(MockWS.instances.length).toBe(1);

    // Advance 999ms — still no new WS
    vi.advanceTimersByTime(999);
    expect(MockWS.instances.length).toBe(1);

    // Advance 1ms to hit the 1000ms mark — ws2 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(2);
    const ws2 = MockWS.instances[1];
    ws2.close(); // schedules reconnect at 2000ms

    // Advance 1999ms — still only ws2
    vi.advanceTimersByTime(1999);
    expect(MockWS.instances.length).toBe(2);

    // Advance 1ms to hit the 2000ms mark — ws3 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(3);
    const ws3 = MockWS.instances[2];
    ws3.close(); // schedules reconnect at 4000ms

    // Advance 3999ms — still only ws3
    vi.advanceTimersByTime(3999);
    expect(MockWS.instances.length).toBe(3);

    // Advance 1ms to hit the 4000ms mark — ws4 should appear
    vi.advanceTimersByTime(1);
    expect(MockWS.instances.length).toBe(4);

    unmount();
  });

  it('Test 3: no reconnect scheduled when document is hidden at disconnect', () => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });

    const { unmount } = renderHook(() => useWebSocket('ws://test/ws/live'));
    // connect() bails out when hidden
    expect(MockWS.instances.length).toBe(0);

    // Restore visible and fire visibilitychange
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(MockWS.instances.length).toBe(1);

    const ws = MockWS.instances[0];
    ws.fireOpen();

    // Go hidden, then disconnect — should NOT schedule reconnect
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    ws.close();

    const timedCalls = setTimeoutSpy.mock.calls.filter(c => typeof c[1] === 'number');
    expect(timedCalls.length).toBe(0);

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
});
