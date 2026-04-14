import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { RingBuffer } from './ringBuffer';
import type {
  LiveMessage,
  FootprintBar,
  SignalEvent,
  TapeEntry,
  LiveScoreMessage,
  LiveStatusMessage,
  LiveTapeMessage,
} from '@/types/deep6';

export const BAR_CAPACITY = 500;
export const SIGNAL_CAPACITY = 200;
export const TAPE_CAPACITY = 50;

export interface ScoreSlice {
  totalScore: number;
  tier: string;
  direction: number;
  categoriesFiring: string[];
  categoryScores: Record<string, number>;
  kronosBias: number;
  kronosDirection: string;
  gexRegime: string;
}

export interface StatusSlice {
  connected: boolean;
  pnl: number;
  circuitBreakerActive: boolean;
  feedStale: boolean;
  lastTs: number;
}

export interface TradingState {
  bars: RingBuffer<FootprintBar>;
  signals: RingBuffer<SignalEvent>;
  tape: RingBuffer<TapeEntry>;
  score: ScoreSlice;
  status: StatusSlice;
  lastBarVersion: number;
  lastSignalVersion: number;
  lastTapeVersion: number;
  // Actions
  pushBar: (b: FootprintBar) => void;
  pushSignal: (s: SignalEvent) => void;
  pushTape: (t: TapeEntry) => void;
  setScore: (s: LiveScoreMessage) => void;
  setStatus: (s: LiveStatusMessage) => void;
  dispatch: (msg: LiveMessage) => void;
}

const INIT_SCORE: ScoreSlice = {
  totalScore: 0,
  tier: 'QUIET',
  direction: 0,
  categoriesFiring: [],
  categoryScores: {},
  kronosBias: 0,
  kronosDirection: 'NEUTRAL',
  gexRegime: 'NEUTRAL',
};

const INIT_STATUS: StatusSlice = {
  connected: false,
  pnl: 0,
  circuitBreakerActive: false,
  feedStale: false,
  lastTs: 0,
};

export const useTradingStore = create<TradingState>()(
  subscribeWithSelector((set, get) => ({
    bars: new RingBuffer<FootprintBar>(BAR_CAPACITY),
    signals: new RingBuffer<SignalEvent>(SIGNAL_CAPACITY),
    tape: new RingBuffer<TapeEntry>(TAPE_CAPACITY),
    score: INIT_SCORE,
    status: INIT_STATUS,
    lastBarVersion: 0,
    lastSignalVersion: 0,
    lastTapeVersion: 0,

    pushBar: (b) => {
      get().bars.push(b);
      set((s) => ({ lastBarVersion: s.lastBarVersion + 1 }));
    },

    pushSignal: (sig) => {
      get().signals.push(sig);
      set((s) => ({ lastSignalVersion: s.lastSignalVersion + 1 }));
    },

    pushTape: (t) => {
      get().tape.push(t);
      set((s) => ({ lastTapeVersion: s.lastTapeVersion + 1 }));
    },

    setScore: (m) =>
      set({
        score: {
          totalScore: m.total_score,
          tier: m.tier,
          direction: m.direction,
          categoriesFiring: m.categories_firing,
          categoryScores: m.category_scores,
          kronosBias: m.kronos_bias,
          kronosDirection: m.kronos_direction,
          gexRegime: m.gex_regime,
        },
      }),

    setStatus: (m) =>
      set({
        status: {
          connected: m.connected,
          pnl: m.pnl,
          circuitBreakerActive: m.circuit_breaker_active,
          feedStale: m.feed_stale,
          lastTs: m.ts,
        },
      }),

    dispatch: (msg) => {
      const g = get();
      switch (msg.type) {
        case 'bar':
          g.pushBar(msg.bar);
          break;
        case 'signal':
          g.pushSignal(msg.event);
          break;
        case 'score':
          g.setScore(msg);
          break;
        case 'status':
          g.setStatus(msg);
          break;
        case 'tape': {
          const m = msg as LiveTapeMessage;
          g.pushTape({
            ts:     m.event.ts,
            price:  m.event.price,
            size:   m.event.size,
            side:   m.event.side,
            marker: m.event.marker,
          });
          break;
        }
        default: {
          // T-11-07: unknown message type — log and drop, do not mutate state
          // eslint-disable-next-line no-console
          console.warn(
            '[tradingStore] unknown message type',
            (msg as { type?: string }).type,
          );
        }
      }
    },
  })),
);

/**
 * dispatchLiveMessage — convenience function for use outside React components.
 * Equivalent to useTradingStore.getState().dispatch(msg).
 */
export function dispatchLiveMessage(msg: LiveMessage): void {
  useTradingStore.getState().dispatch(msg);
}
