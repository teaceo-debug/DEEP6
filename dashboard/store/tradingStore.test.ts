import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  useTradingStore,
  BAR_CAPACITY,
  SIGNAL_CAPACITY,
  TAPE_CAPACITY,
  selectPnl,
  selectConnected,
  selectCircuitBreakerActive,
  selectTotalScore,
  selectTier,
  selectKronosBias,
  selectLastBarVersion,
  selectLastSignalVersion,
  selectLastTapeVersion,
} from './tradingStore';
import { RingBuffer } from './ringBuffer';
import type {
  FootprintBar,
  SignalEvent,
  TapeEntry,
  LiveBarMessage,
  LiveSignalMessage,
  LiveScoreMessage,
  LiveStatusMessage,
  LiveMessage,
} from '@/types/deep6';

// Minimal FootprintBar factory
function makeBar(bar_index: number): FootprintBar {
  return {
    session_id: 'test-session',
    bar_index,
    ts: Date.now() / 1000,
    open: 21000,
    high: 21010,
    low: 20990,
    close: 21005,
    total_vol: 100,
    bar_delta: 10,
    cvd: 5,
    poc_price: 21000,
    bar_range: 20,
    running_delta: 5,
    max_delta: 20,
    min_delta: -5,
    levels: {},
  };
}

function makeSignal(): SignalEvent {
  return {
    ts: Date.now() / 1000,
    bar_index_in_session: 1,
    total_score: 75,
    tier: 'TYPE_B',
    direction: 1,
    engine_agreement: 0.8,
    category_count: 3,
    categories_firing: ['absorption', 'delta'],
    gex_regime: 'NEUTRAL',
    kronos_bias: 60,
  };
}

// Reset store before each test
const INIT_SCORE = {
  totalScore: 0,
  tier: 'QUIET',
  direction: 0,
  categoriesFiring: [],
  categoryScores: {},
  kronosBias: 0,
  kronosDirection: 'NEUTRAL',
  gexRegime: 'NEUTRAL',
};

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
  lastError: null,
  errorCount: 0,
  errorCode: null,
  connectionHistory: [],
  reconnectSuccessToast: false,
  disconnectedAt: null,
};

beforeEach(() => {
  useTradingStore.setState({
    bars: new RingBuffer<FootprintBar>(BAR_CAPACITY),
    signals: new RingBuffer<SignalEvent>(SIGNAL_CAPACITY),
    tape: new RingBuffer<TapeEntry>(TAPE_CAPACITY),
    score: INIT_SCORE,
    status: INIT_STATUS,
    lastBarVersion: 0,
    lastSignalVersion: 0,
  });
});

describe('TradingStore dispatcher', () => {
  it('Test 6: initial state — bars.size 0, signals.size 0, lastBarVersion 0, status.connected false', () => {
    const s = useTradingStore.getState();
    expect(s.bars.size).toBe(0);
    expect(s.signals.size).toBe(0);
    expect(s.lastBarVersion).toBe(0);
    expect(s.status.connected).toBe(false);
  });

  it('Test 7: dispatch bar message — pushes bar to ring, increments lastBarVersion', () => {
    const s = useTradingStore.getState();
    const msg: LiveBarMessage = {
      type: 'bar',
      session_id: 'test-session',
      bar_index: 0,
      bar: makeBar(0),
    };
    s.dispatch(msg);
    expect(useTradingStore.getState().bars.size).toBe(1);
    expect(useTradingStore.getState().lastBarVersion).toBe(1);
  });

  it('Test 8: dispatch signal message — pushes to signals ring', () => {
    const s = useTradingStore.getState();
    const msg: LiveSignalMessage = {
      type: 'signal',
      event: makeSignal(),
      narrative: 'ABSORBED @VAH',
    };
    s.dispatch(msg);
    expect(useTradingStore.getState().signals.size).toBe(1);
  });

  it('Test 9: dispatch score message — updates score.totalScore and score.tier', () => {
    const msg: LiveScoreMessage = {
      type: 'score',
      total_score: 82,
      tier: 'TYPE_A',
      direction: 1,
      categories_firing: ['absorption'],
      category_scores: { absorption: 25 },
      kronos_bias: 70,
      kronos_direction: 'LONG',
      gex_regime: 'POSITIVE',
    };
    useTradingStore.getState().dispatch(msg);
    const s = useTradingStore.getState();
    expect(s.score.totalScore).toBe(82);
    expect(s.score.tier).toBe('TYPE_A');
  });

  it('Test 10: dispatch status message — updates status.connected and status.pnl', () => {
    const msg: LiveStatusMessage = {
      type: 'status',
      connected: true,
      pnl: 42.5,
      circuit_breaker_active: false,
      feed_stale: false,
      ts: Date.now() / 1000,
    };
    useTradingStore.getState().dispatch(msg);
    const s = useTradingStore.getState();
    expect(s.status.connected).toBe(true);
    expect(s.status.pnl).toBe(42.5);
  });

  it('Test 11: dispatch unknown type — does not throw, warns once, state unchanged', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const v0 = useTradingStore.getState().lastBarVersion;

    useTradingStore.getState().dispatch({ type: 'unknown_type' } as unknown as LiveMessage);

    expect(warnSpy).toHaveBeenCalledOnce();
    expect(useTradingStore.getState().lastBarVersion).toBe(v0);
    warnSpy.mockRestore();
  });

  it('Test 12: push 501 bars — ring retains last 500, oldest evicted', () => {
    const s = useTradingStore.getState();
    for (let i = 0; i < 501; i++) {
      s.pushBar(makeBar(i));
    }
    const state = useTradingStore.getState();
    expect(state.bars.size).toBe(500);
    // toArray() is insertion order (oldest first, newest last)
    // bar_index 0 is evicted; oldest retained is bar_index 1 at arr[0]
    const arr = state.bars.toArray();
    expect(arr[0].bar_index).toBe(1); // oldest retained
    expect(arr[arr.length - 1].bar_index).toBe(500); // newest
  });
});

// ---------------------------------------------------------------------------
// Scoped selector tests (perf-r5)
// ---------------------------------------------------------------------------

describe('Scoped selectors', () => {
  it('selectPnl returns status.pnl', () => {
    const msg: LiveStatusMessage = {
      type: 'status',
      connected: true,
      pnl: 99.5,
      circuit_breaker_active: false,
      feed_stale: false,
      ts: 1000,
    };
    useTradingStore.getState().dispatch(msg);
    expect(selectPnl(useTradingStore.getState())).toBe(99.5);
  });

  it('selectConnected returns status.connected', () => {
    const msg: LiveStatusMessage = {
      type: 'status',
      connected: true,
      pnl: 0,
      circuit_breaker_active: false,
      feed_stale: false,
      ts: 1000,
    };
    useTradingStore.getState().dispatch(msg);
    expect(selectConnected(useTradingStore.getState())).toBe(true);
  });

  it('selectCircuitBreakerActive returns status.circuitBreakerActive', () => {
    const msg: LiveStatusMessage = {
      type: 'status',
      connected: true,
      pnl: 0,
      circuit_breaker_active: true,
      feed_stale: false,
      ts: 1000,
    };
    useTradingStore.getState().dispatch(msg);
    expect(selectCircuitBreakerActive(useTradingStore.getState())).toBe(true);
  });

  it('selectTotalScore + selectTier return correct score slice fields', () => {
    const msg: LiveScoreMessage = {
      type: 'score',
      total_score: 87,
      tier: 'TYPE_A',
      direction: 1,
      categories_firing: ['absorption'],
      category_scores: { absorption: 30 },
      kronos_bias: 65,
      kronos_direction: 'LONG',
      gex_regime: 'POSITIVE',
    };
    useTradingStore.getState().dispatch(msg);
    expect(selectTotalScore(useTradingStore.getState())).toBe(87);
    expect(selectTier(useTradingStore.getState())).toBe('TYPE_A');
  });

  it('selectKronosBias returns score.kronosBias', () => {
    const msg: LiveScoreMessage = {
      type: 'score',
      total_score: 60,
      tier: 'TYPE_B',
      direction: -1,
      categories_firing: [],
      category_scores: {},
      kronos_bias: 72,
      kronos_direction: 'SHORT',
      gex_regime: 'NEUTRAL',
    };
    useTradingStore.getState().dispatch(msg);
    expect(selectKronosBias(useTradingStore.getState())).toBe(72);
  });

  it('selectLastBarVersion increments on pushBar', () => {
    expect(selectLastBarVersion(useTradingStore.getState())).toBe(0);
    useTradingStore.getState().pushBar(makeBar(0));
    expect(selectLastBarVersion(useTradingStore.getState())).toBe(1);
  });

  it('selectLastSignalVersion increments on pushSignal', () => {
    expect(selectLastSignalVersion(useTradingStore.getState())).toBe(0);
    useTradingStore.getState().pushSignal(makeSignal());
    expect(selectLastSignalVersion(useTradingStore.getState())).toBe(1);
  });

  it('selectLastTapeVersion increments on pushTape', () => {
    expect(selectLastTapeVersion(useTradingStore.getState())).toBe(0);
    useTradingStore.getState().pushTape({ ts: 1, price: 21000, size: 10, side: 'ASK', marker: '' });
    expect(selectLastTapeVersion(useTradingStore.getState())).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// RingBuffer.toArray() single-pass optimization (perf-r5)
// ---------------------------------------------------------------------------

describe('RingBuffer.toArray() optimized single-pass', () => {
  it('empty buffer returns []', () => {
    const rb = new RingBuffer<number>(4);
    expect(rb.toArray()).toEqual([]);
  });

  it('partial fill returns items in insertion order', () => {
    const rb = new RingBuffer<number>(4);
    rb.push(10);
    rb.push(20);
    rb.push(30);
    expect(rb.toArray()).toEqual([10, 20, 30]);
  });

  it('exact capacity fill returns all items in insertion order', () => {
    const rb = new RingBuffer<number>(4);
    rb.push(1); rb.push(2); rb.push(3); rb.push(4);
    expect(rb.toArray()).toEqual([1, 2, 3, 4]);
  });

  it('overflow (capacity+1) wraps correctly — oldest evicted', () => {
    const rb = new RingBuffer<number>(4);
    rb.push(1); rb.push(2); rb.push(3); rb.push(4); rb.push(5);
    expect(rb.toArray()).toEqual([2, 3, 4, 5]);
  });

  it('overflow (2x capacity) wraps correctly — retains newest N', () => {
    const rb = new RingBuffer<number>(4);
    for (let i = 1; i <= 8; i++) rb.push(i);
    expect(rb.toArray()).toEqual([5, 6, 7, 8]);
  });

  it('toArray result length equals size', () => {
    const rb = new RingBuffer<number>(4);
    rb.push(1); rb.push(2); rb.push(3);
    expect(rb.toArray().length).toBe(rb.size);
  });
});
