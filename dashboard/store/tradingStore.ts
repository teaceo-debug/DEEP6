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
  // Phase 11.3-r3 observability fields
  sessionStartTs: number;
  barsReceived: number;
  signalsFired: number;
  lastSignalTier: string;
  uptimeSeconds: number;
  activeClients: number;
  // Phase 11.3-r9 rich error state
  lastError: string | null;
  errorCount: number;
  errorCode: number | null;
  // Connection history: last 5 state changes with timestamps (for ErrorBanner expand)
  connectionHistory: Array<{ ts: number; state: 'connected' | 'disconnected'; code?: number; reason?: string }>;
  // Flag: show reconnect success toast (set true → auto-cleared after 3s by banner)
  reconnectSuccessToast: boolean;
  disconnectedAt: number | null;
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
  setConnectionError: (error: string, code: number | null) => void;
  clearConnectionError: () => void;
  pushConnectionHistory: (entry: { ts: number; state: 'connected' | 'disconnected'; code?: number; reason?: string }) => void;
  setReconnectSuccessToast: (val: boolean) => void;
  setDisconnectedAt: (ts: number | null) => void;
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
      set((s) => ({
        status: {
          // Preserve Phase 11.3-r9 error/history fields — setStatus only updates wire fields
          ...s.status,
          connected: m.connected,
          pnl: m.pnl,
          circuitBreakerActive: m.circuit_breaker_active,
          feedStale: m.feed_stale,
          lastTs: m.ts,
          // Phase 11.3-r3 observability fields (wire sends 0/'' defaults)
          sessionStartTs: m.session_start_ts ?? 0,
          barsReceived: m.bars_received ?? 0,
          signalsFired: m.signals_fired ?? 0,
          lastSignalTier: m.last_signal_tier ?? '',
          uptimeSeconds: m.uptime_seconds ?? 0,
          activeClients: m.active_clients ?? 0,
        },
      })),

    setConnectionError: (error, code) =>
      set((s) => ({
        status: {
          ...s.status,
          lastError: error,
          errorCode: code,
          errorCount: s.status.errorCount + 1,
        },
      })),

    clearConnectionError: () =>
      set((s) => ({
        status: { ...s.status, lastError: null, errorCode: null },
      })),

    pushConnectionHistory: (entry) =>
      set((s) => {
        const hist = [...s.status.connectionHistory, entry].slice(-5);
        return { status: { ...s.status, connectionHistory: hist } };
      }),

    setReconnectSuccessToast: (val) =>
      set((s) => ({ status: { ...s.status, reconnectSuccessToast: val } })),

    setDisconnectedAt: (ts) =>
      set((s) => ({ status: { ...s.status, disconnectedAt: ts } })),

    dispatch: (msg) => {
      // Guard: msg must be a non-null object with a string type field.
      if (!msg || typeof (msg as { type?: unknown }).type !== 'string') return;
      const g = get();
      switch (msg.type) {
        case 'bar': {
          // Drop silently if bar payload is missing or malformed
          const bar = msg?.bar;
          if (!bar || typeof bar !== 'object') break;
          g.pushBar(bar);
          break;
        }
        case 'signal': {
          const event = msg?.event;
          if (!event || typeof event !== 'object') break;
          // Ensure categories_firing is always an array (never undefined/null)
          if (!Array.isArray(event.categories_firing)) {
            event.categories_firing = [];
          }
          g.pushSignal(event);
          break;
        }
        case 'score': {
          // Guard all required score fields
          if (
            typeof msg.total_score !== 'number' ||
            typeof msg.tier !== 'string'
          ) break;
          // Ensure categories_firing is always an array
          if (!Array.isArray(msg.categories_firing)) {
            (msg as LiveScoreMessage).categories_firing = [];
          }
          if (!msg.category_scores || typeof msg.category_scores !== 'object') {
            (msg as LiveScoreMessage).category_scores = {};
          }
          g.setScore(msg);
          break;
        }
        case 'status': {
          // Guard required status fields
          if (typeof msg.connected !== 'boolean') break;
          g.setStatus(msg);
          break;
        }
        case 'tape': {
          const m = msg as LiveTapeMessage;
          const ev = m?.event;
          if (!ev || typeof ev !== 'object') break;
          // Guard individual tape fields
          if (
            typeof ev.ts !== 'number' ||
            typeof ev.price !== 'number' ||
            typeof ev.size !== 'number' ||
            typeof ev.side !== 'string'
          ) break;
          g.pushTape({
            ts:     ev.ts,
            price:  ev.price,
            size:   ev.size,
            side:   ev.side,
            marker: ev.marker ?? '',
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

// ---------------------------------------------------------------------------
// Scoped selector functions — import these instead of writing inline arrows.
//
// Why: Zustand re-renders a component when the selected value changes by
// reference equality. Inline arrow selectors like `s => s.status` cause a
// re-render on every status object replacement even when the observed fields
// haven't changed. Stable selector references exported here let components
// subscribe to exactly the fields they need.
//
// Usage:
//   import { selectPnl, selectConnected } from '@/store/tradingStore';
//   const pnl = useTradingStore(selectPnl);
//   const connected = useTradingStore(selectConnected);
// ---------------------------------------------------------------------------

// ── Status selectors ────────────────────────────────────────────────────────
export const selectPnl = (s: TradingState) => s.status.pnl;
export const selectCircuitBreakerActive = (s: TradingState) => s.status.circuitBreakerActive;
export const selectConnected = (s: TradingState) => s.status.connected;
export const selectFeedStale = (s: TradingState) => s.status.feedStale;
export const selectLastTs = (s: TradingState) => s.status.lastTs;
export const selectSessionStartTs = (s: TradingState) => s.status.sessionStartTs;
export const selectBarsReceived = (s: TradingState) => s.status.barsReceived;
export const selectSignalsFired = (s: TradingState) => s.status.signalsFired;
export const selectLastSignalTier = (s: TradingState) => s.status.lastSignalTier;
export const selectUptimeSeconds = (s: TradingState) => s.status.uptimeSeconds;
export const selectActiveClients = (s: TradingState) => s.status.activeClients;
export const selectLastError = (s: TradingState) => s.status.lastError;
export const selectErrorCount = (s: TradingState) => s.status.errorCount;
export const selectErrorCode = (s: TradingState) => s.status.errorCode;
export const selectConnectionHistory = (s: TradingState) => s.status.connectionHistory;
export const selectReconnectSuccessToast = (s: TradingState) => s.status.reconnectSuccessToast;
export const selectDisconnectedAt = (s: TradingState) => s.status.disconnectedAt;

// ── Score selectors ─────────────────────────────────────────────────────────
export const selectTotalScore = (s: TradingState) => s.score.totalScore;
export const selectTier = (s: TradingState) => s.score.tier;
export const selectDirection = (s: TradingState) => s.score.direction;
export const selectCategoriesFiring = (s: TradingState) => s.score.categoriesFiring;
export const selectCategoryScores = (s: TradingState) => s.score.categoryScores;
export const selectKronosBias = (s: TradingState) => s.score.kronosBias;
export const selectKronosDirection = (s: TradingState) => s.score.kronosDirection;
export const selectGexRegime = (s: TradingState) => s.score.gexRegime;

// ── Version selectors ───────────────────────────────────────────────────────
export const selectLastBarVersion = (s: TradingState) => s.lastBarVersion;
export const selectLastSignalVersion = (s: TradingState) => s.lastSignalVersion;
export const selectLastTapeVersion = (s: TradingState) => s.lastTapeVersion;
