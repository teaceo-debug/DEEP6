/**
 * replayStore.ts — Zustand store for replay-mode UI state.
 *
 * Separate from tradingStore. Tracks mode, selected session, current bar index,
 * playback speed, playing flag, and error state.
 *
 * Per D-13, D-14 (11-CONTEXT.md): replay reads from EventStore via FastAPI;
 * controls are Prev/Next/jump/speed per UI-SPEC.
 */
import { create } from 'zustand';

export type ReplayMode = 'live' | 'replay';
export type ReplaySpeed = '1x' | '2x' | '5x' | 'auto';

interface ReplayState {
  mode: ReplayMode;
  sessionId: string | null;
  currentBarIndex: number;
  totalBars: number;
  speed: ReplaySpeed;
  playing: boolean;
  error: string | null;
  userHasPanned: boolean;
  // Actions
  setMode: (mode: ReplayMode, sessionId?: string | null) => void;
  setTotalBars: (n: number) => void;
  advanceBar: () => void;
  rewindBar: () => void;
  jumpToBar: (n: number) => void;
  setSpeed: (s: ReplaySpeed) => void;
  play: () => void;
  pause: () => void;
  setError: (e: string | null) => void;
  setPanned: (v: boolean) => void;
}

export const useReplayStore = create<ReplayState>((set, get) => ({
  mode: 'live',
  sessionId: null,
  currentBarIndex: 0,
  totalBars: 0,
  speed: '1x',
  playing: false,
  error: null,
  userHasPanned: false,

  setMode: (mode, sessionId = null) =>
    set({ mode, sessionId, currentBarIndex: 0, playing: false, error: null }),

  setTotalBars: (n) => set({ totalBars: n }),

  advanceBar: () => {
    const { currentBarIndex, totalBars } = get();
    if (currentBarIndex < totalBars - 1) {
      set({ currentBarIndex: currentBarIndex + 1 });
    } else {
      set({ playing: false }); // stop at end
    }
  },

  rewindBar: () =>
    set((s) => ({ currentBarIndex: Math.max(0, s.currentBarIndex - 1) })),

  jumpToBar: (n) =>
    set((s) => ({
      currentBarIndex: Math.max(0, Math.min(s.totalBars - 1, n)),
    })),

  setSpeed: (speed) => set({ speed }),

  play: () => set({ playing: true }),

  pause: () => set({ playing: false }),

  setError: (error) => set({ error }),

  setPanned: (userHasPanned) => set({ userHasPanned }),
}));
