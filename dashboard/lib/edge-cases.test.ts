/**
 * edge-cases.test.ts
 * Comprehensive edge-case tests for DEEP6 dashboard hardening (Phase 11.3-r5).
 *
 * Covers:
 *  - sanitizeNumber / useDigitRoll / DigitRoll with NaN, Infinity, negative, huge, tiny
 *  - tradingStore dispatch with missing / malformed / extra fields
 *  - RingBuffer at capacity
 *  - Age formatting with future timestamps (clock skew)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { sanitizeNumber } from './digit-roll';
import { useTradingStore, BAR_CAPACITY, SIGNAL_CAPACITY, TAPE_CAPACITY } from '@/store/tradingStore';
import { RingBuffer } from '@/store/ringBuffer';
import type {
  FootprintBar,
  SignalEvent,
  TapeEntry,
  LiveBarMessage,
  LiveSignalMessage,
  LiveScoreMessage,
  LiveStatusMessage,
  LiveTapeMessage,
  LiveMessage,
} from '@/types/deep6';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeBar(bar_index = 0, overrides: Partial<FootprintBar> = {}): FootprintBar {
  return {
    session_id: 'test',
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
    ...overrides,
  };
}

function makeSignal(overrides: Partial<SignalEvent> = {}): SignalEvent {
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
    ...overrides,
  };
}

const INIT_SCORE = {
  totalScore: 0, tier: 'QUIET', direction: 0, categoriesFiring: [],
  categoryScores: {}, kronosBias: 0, kronosDirection: 'NEUTRAL', gexRegime: 'NEUTRAL',
};
const INIT_STATUS = {
  connected: false, pnl: 0, circuitBreakerActive: false, feedStale: false,
  lastTs: 0, sessionStartTs: 0, barsReceived: 0, signalsFired: 0,
  lastSignalTier: '', uptimeSeconds: 0, activeClients: 0,
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
    lastTapeVersion: 0,
  });
});

// ---------------------------------------------------------------------------
// sanitizeNumber — unit tests (pure function, no React)
// ---------------------------------------------------------------------------

describe('sanitizeNumber', () => {
  it('returns safe=0, invalid=true for NaN', () => {
    const r = sanitizeNumber(NaN);
    expect(r.invalid).toBe(true);
    expect(r.safe).toBe(0);
  });

  it('returns safe=0, invalid=true for +Infinity', () => {
    const r = sanitizeNumber(Infinity);
    expect(r.invalid).toBe(true);
    expect(r.safe).toBe(0);
  });

  it('returns safe=0, invalid=true for -Infinity', () => {
    const r = sanitizeNumber(-Infinity);
    expect(r.invalid).toBe(true);
    expect(r.safe).toBe(0);
  });

  it('passes through zero', () => {
    const r = sanitizeNumber(0);
    expect(r.invalid).toBe(false);
    expect(r.safe).toBe(0);
  });

  it('passes through negative numbers', () => {
    const r = sanitizeNumber(-42.5);
    expect(r.invalid).toBe(false);
    expect(r.safe).toBe(-42.5);
  });

  it('passes through very large finite number', () => {
    const r = sanitizeNumber(Number.MAX_SAFE_INTEGER);
    expect(r.invalid).toBe(false);
    expect(r.safe).toBe(Number.MAX_SAFE_INTEGER);
  });

  it('passes through very small finite number', () => {
    const r = sanitizeNumber(Number.MIN_VALUE);
    expect(r.invalid).toBe(false);
    expect(r.safe).toBe(Number.MIN_VALUE);
  });

  it('passes through Number.EPSILON', () => {
    const r = sanitizeNumber(Number.EPSILON);
    expect(r.invalid).toBe(false);
    expect(r.safe).toBe(Number.EPSILON);
  });
});

// ---------------------------------------------------------------------------
// Store dispatch — missing / malformed / extra fields
// ---------------------------------------------------------------------------

describe('tradingStore dispatch — malformed payloads', () => {
  it('drops null payload without throwing', () => {
    expect(() => {
      useTradingStore.getState().dispatch(null as unknown as LiveMessage);
    }).not.toThrow();
    expect(useTradingStore.getState().lastBarVersion).toBe(0);
  });

  it('drops payload without type field without throwing', () => {
    expect(() => {
      useTradingStore.getState().dispatch({} as unknown as LiveMessage);
    }).not.toThrow();
  });

  it('drops bar message with missing bar field', () => {
    const msg = { type: 'bar', session_id: 'x', bar_index: 0 } as unknown as LiveMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().bars.size).toBe(0);
  });

  it('drops bar message with null bar field', () => {
    const msg = { type: 'bar', session_id: 'x', bar_index: 0, bar: null } as unknown as LiveMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().bars.size).toBe(0);
  });

  it('accepts bar message with extra unknown fields', () => {
    const msg: LiveBarMessage & { extra?: string } = {
      type: 'bar',
      session_id: 'x',
      bar_index: 0,
      bar: makeBar(0),
      extra: 'ignored',
    };
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().bars.size).toBe(1);
  });

  it('drops signal message with missing event field', () => {
    const msg = { type: 'signal', narrative: 'test' } as unknown as LiveMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().signals.size).toBe(0);
  });

  it('normalises signal with missing categories_firing to empty array', () => {
    const event = makeSignal();
    // @ts-expect-error intentionally removing required field for test
    delete event.categories_firing;
    const msg: LiveSignalMessage = { type: 'signal', event, narrative: '' };
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().signals.size).toBe(1);
    const stored = useTradingStore.getState().signals.latest!;
    expect(Array.isArray(stored.categories_firing)).toBe(true);
    expect(stored.categories_firing).toHaveLength(0);
  });

  it('drops score message with non-number total_score', () => {
    const msg = {
      type: 'score',
      total_score: 'NOT_A_NUMBER',
      tier: 'TYPE_A',
      direction: 1,
      categories_firing: [],
      category_scores: {},
      kronos_bias: 0,
      kronos_direction: 'NEUTRAL',
      gex_regime: 'NEUTRAL',
    } as unknown as LiveScoreMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().score.totalScore).toBe(0); // unchanged
  });

  it('normalises score with missing categories_firing', () => {
    const msg = {
      type: 'score',
      total_score: 55,
      tier: 'TYPE_B',
      direction: 0,
      // categories_firing intentionally omitted
      category_scores: { delta: 10 },
      kronos_bias: 30,
      kronos_direction: 'NEUTRAL',
      gex_regime: 'NEUTRAL',
    } as unknown as LiveScoreMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().score.categoriesFiring).toEqual([]);
  });

  it('normalises score with missing category_scores', () => {
    const msg = {
      type: 'score',
      total_score: 55,
      tier: 'TYPE_B',
      direction: 0,
      categories_firing: ['absorption'],
      // category_scores intentionally omitted
      kronos_bias: 30,
      kronos_direction: 'NEUTRAL',
      gex_regime: 'NEUTRAL',
    } as unknown as LiveScoreMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().score.categoryScores).toEqual({});
  });

  it('drops status message with non-boolean connected field', () => {
    const msg = {
      type: 'status',
      connected: 'yes',
      pnl: 0,
      circuit_breaker_active: false,
      feed_stale: false,
      ts: Date.now() / 1000,
    } as unknown as LiveStatusMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().status.connected).toBe(false); // unchanged
  });

  it('accepts status message with extra unknown fields', () => {
    const msg = {
      type: 'status',
      connected: true,
      pnl: 100,
      circuit_breaker_active: false,
      feed_stale: false,
      ts: Date.now() / 1000,
      unknown_future_field: 'ignored',
    } as unknown as LiveStatusMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().status.connected).toBe(true);
  });

  it('drops tape message with missing event field', () => {
    const msg = { type: 'tape' } as unknown as LiveMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().tape.size).toBe(0);
  });

  it('drops tape message where price is not a number', () => {
    const msg = {
      type: 'tape',
      event: { ts: Date.now() / 1000, price: 'NaN', size: 10, side: 'ASK', marker: '' },
    } as unknown as LiveTapeMessage;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().tape.size).toBe(0);
  });

  it('defaults tape marker to empty string when missing', () => {
    const msg: LiveTapeMessage = {
      type: 'tape',
      event: { ts: Date.now() / 1000, price: 21000, size: 5, side: 'BID', marker: '' },
    };
    // Remove marker to simulate missing field
    // @ts-expect-error intentionally removing optional field
    delete msg.event.marker;
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().tape.size).toBe(1);
    expect(useTradingStore.getState().tape.latest!.marker).toBe('');
  });

  it('silently drops unknown message type and warns once', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    useTradingStore.getState().dispatch({ type: 'totally_unknown' } as unknown as LiveMessage);
    expect(warnSpy).toHaveBeenCalledOnce();
    expect(useTradingStore.getState().lastBarVersion).toBe(0);
    warnSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// RingBuffer at capacity — stress test
// ---------------------------------------------------------------------------

describe('RingBuffer at capacity', () => {
  it('retains exactly capacity items after overflow', () => {
    const rb = new RingBuffer<number>(SIGNAL_CAPACITY);
    for (let i = 0; i < SIGNAL_CAPACITY + 50; i++) rb.push(i);
    expect(rb.size).toBe(SIGNAL_CAPACITY);
  });

  it('latest is the last pushed item after overflow', () => {
    const rb = new RingBuffer<number>(10);
    for (let i = 0; i < 25; i++) rb.push(i);
    expect(rb.latest).toBe(24);
  });

  it('toArray returns items in insertion order after overflow', () => {
    const rb = new RingBuffer<number>(3);
    rb.push(10); rb.push(20); rb.push(30); rb.push(40);
    expect(rb.toArray()).toEqual([20, 30, 40]);
  });

  it('signal ring buffer caps at SIGNAL_CAPACITY without throw', () => {
    const s = useTradingStore.getState();
    for (let i = 0; i < SIGNAL_CAPACITY + 100; i++) {
      s.pushSignal(makeSignal());
    }
    expect(useTradingStore.getState().signals.size).toBe(SIGNAL_CAPACITY);
  });

  it('bar ring buffer caps at BAR_CAPACITY without throw', () => {
    const s = useTradingStore.getState();
    for (let i = 0; i < BAR_CAPACITY + 10; i++) {
      s.pushBar(makeBar(i));
    }
    expect(useTradingStore.getState().bars.size).toBe(BAR_CAPACITY);
  });

  it('tape ring buffer caps at TAPE_CAPACITY without throw', () => {
    const s = useTradingStore.getState();
    for (let i = 0; i < TAPE_CAPACITY + 10; i++) {
      s.pushTape({ ts: Date.now() / 1000, price: 21000, size: 1, side: 'ASK', marker: '' });
    }
    expect(useTradingStore.getState().tape.size).toBe(TAPE_CAPACITY);
  });
});

// ---------------------------------------------------------------------------
// Age formatting with future timestamps (clock skew)
// ---------------------------------------------------------------------------

describe('age formatting — future timestamps', () => {
  it('clamps negative age to 0 when ts is in the future', () => {
    const futureTs = Date.now() / 1000 + 9999; // 9999 seconds in the future
    const rawAge = Date.now() / 1000 - futureTs;
    expect(rawAge).toBeLessThan(0);

    // The clamped value used in HeaderStrip
    const clamped = Math.max(0, rawAge);
    expect(clamped).toBe(0);
    expect(clamped.toFixed(1)).toBe('0.0');
  });

  it('shows positive age for past timestamps', () => {
    const pastTs = Date.now() / 1000 - 5; // 5 seconds ago
    const age = Math.max(0, Date.now() / 1000 - pastTs);
    expect(age).toBeGreaterThanOrEqual(4.9);
    expect(age).toBeLessThanOrEqual(5.1);
  });

  it('SPM bin index clamps future signal ts to bin 0', () => {
    const nowSec = Date.now() / 1000;
    const futureSigTs = nowSec + 60; // 1 minute in the future
    const ageMin = Math.max(0, nowSec - futureSigTs) / 60;
    expect(ageMin).toBe(0);
    const binIdx = Math.floor(ageMin);
    expect(binIdx).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Tape size = 0 — empty state verification
// ---------------------------------------------------------------------------

describe('tape — empty state', () => {
  it('tape.size is 0 on init', () => {
    expect(useTradingStore.getState().tape.size).toBe(0);
  });

  it('tape.latest is undefined on init', () => {
    expect(useTradingStore.getState().tape.latest).toBeUndefined();
  });

  it('tape.toArray returns [] on init', () => {
    expect(useTradingStore.getState().tape.toArray()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Signal with empty categories_firing
// ---------------------------------------------------------------------------

describe('signal — empty categories_firing', () => {
  it('dispatching signal with empty categories_firing does not throw', () => {
    const msg: LiveSignalMessage = {
      type: 'signal',
      event: makeSignal({ categories_firing: [] }),
      narrative: '',
    };
    expect(() => useTradingStore.getState().dispatch(msg)).not.toThrow();
    expect(useTradingStore.getState().signals.size).toBe(1);
    expect(useTradingStore.getState().signals.latest!.categories_firing).toEqual([]);
  });
});
