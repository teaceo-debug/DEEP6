/**
 * replayStore.test.ts — 9 behavioral tests per Plan 11-04 Task 1.
 * Run: npm run test -- replayStore
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useReplayStore } from './replayStore';
import { fetchSessionRange } from '@/lib/replayClient';

// ── Reset store before each test ──────────────────────────────────────────────

beforeEach(() => {
  useReplayStore.setState({
    mode: 'live',
    sessionId: null,
    currentBarIndex: 0,
    totalBars: 0,
    speed: '1x',
    playing: false,
    error: null,
    userHasPanned: false,
  });
  vi.restoreAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('replayStore', () => {
  // Test 1: initial mode is 'live'
  it('T1: initial mode is live', () => {
    expect(useReplayStore.getState().mode).toBe('live');
  });

  // Test 2: setMode('replay', '2026-04-13') sets mode, sessionId, resets currentBarIndex=0, playing=false, error=null
  it('T2: setMode sets mode, sessionId, resets barIndex/playing/error', () => {
    // Set some state first
    useReplayStore.setState({ currentBarIndex: 10, playing: true, error: 'previous error' });
    useReplayStore.getState().setMode('replay', '2026-04-13');
    const s = useReplayStore.getState();
    expect(s.mode).toBe('replay');
    expect(s.sessionId).toBe('2026-04-13');
    expect(s.currentBarIndex).toBe(0);
    expect(s.playing).toBe(false);
    expect(s.error).toBeNull();
  });

  // Test 3: advanceBar() increments unless at end
  it('T3: advanceBar increments and clamps at totalBars-1', () => {
    useReplayStore.setState({ currentBarIndex: 0, totalBars: 3 });
    useReplayStore.getState().advanceBar();
    expect(useReplayStore.getState().currentBarIndex).toBe(1);

    // Advance past end — should stop playing, not exceed totalBars-1
    useReplayStore.setState({ currentBarIndex: 2, totalBars: 3, playing: true });
    useReplayStore.getState().advanceBar();
    expect(useReplayStore.getState().currentBarIndex).toBe(2); // clamped
    expect(useReplayStore.getState().playing).toBe(false);     // stopped
  });

  // Test 4: rewindBar() decrements, clamp at 0
  it('T4: rewindBar decrements and clamps at 0', () => {
    useReplayStore.setState({ currentBarIndex: 5, totalBars: 10 });
    useReplayStore.getState().rewindBar();
    expect(useReplayStore.getState().currentBarIndex).toBe(4);

    // Clamp at 0
    useReplayStore.setState({ currentBarIndex: 0, totalBars: 10 });
    useReplayStore.getState().rewindBar();
    expect(useReplayStore.getState().currentBarIndex).toBe(0);
  });

  // Test 5: setSpeed stores speed
  it('T5: setSpeed stores speed', () => {
    useReplayStore.getState().setSpeed('2x');
    expect(useReplayStore.getState().speed).toBe('2x');
  });

  // Test 6: jumpToBar clamps to 0..totalBars-1
  it('T6: jumpToBar sets index clamped to valid range', () => {
    useReplayStore.setState({ totalBars: 100 });
    useReplayStore.getState().jumpToBar(42);
    expect(useReplayStore.getState().currentBarIndex).toBe(42);

    // Clamp high
    useReplayStore.getState().jumpToBar(999);
    expect(useReplayStore.getState().currentBarIndex).toBe(99);

    // Clamp low
    useReplayStore.getState().jumpToBar(-5);
    expect(useReplayStore.getState().currentBarIndex).toBe(0);
  });

  // Test 7: setError stores error verbatim
  it('T7: setError stores the UI-SPEC-locked copy verbatim', () => {
    const msg = 'Session not found. Select a date from history.';
    useReplayStore.getState().setError(msg);
    expect(useReplayStore.getState().error).toBe(msg);
  });

  // Test 8: fetchSessionRange calls correct URL
  it('T8: fetchSessionRange calls GET /api/replay/{session}?start=0&end=100', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      json: async () => ({
        session_id: '2026-04-13',
        total_bars: 100,
        bars: [],
      }),
    };
    const fetchMock = vi.fn(async () => mockResponse);
    vi.stubGlobal('fetch', fetchMock);

    // Override BASE to empty string for predictable URL
    const result = await fetchSessionRange('2026-04-13', 0, 100);

    expect(fetchMock).toHaveBeenCalledOnce();
    const calledUrl = (fetchMock.mock.calls[0] as unknown[])[0] as string;
    expect(calledUrl).toContain('/api/replay/2026-04-13');
    expect(calledUrl).toContain('start=0');
    expect(calledUrl).toContain('end=100');
    expect(result.session_id).toBe('2026-04-13');
    expect(result.total_bars).toBe(100);
  });

  // Test 9: manual advance loop simulation (fake timers out of scope per plan note)
  // Plan says: verify advance loop by calling advanceBar() manually inside vi.useFakeTimers
  // and measuring total-bar-count progression.
  it('T9: advanceBar called N times increments currentBarIndex N times', () => {
    useReplayStore.setState({ currentBarIndex: 0, totalBars: 10, playing: true });
    // Simulate 3 advance ticks
    useReplayStore.getState().advanceBar();
    useReplayStore.getState().advanceBar();
    useReplayStore.getState().advanceBar();
    expect(useReplayStore.getState().currentBarIndex).toBe(3);
  });
});
