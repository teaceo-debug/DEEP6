/**
 * Zustand store for live signal/trade events and WebSocket connection state.
 *
 * Per D-05: Zustand for state management.
 * Ring buffer: max 200 events, newest-first.
 * dailyPnl: sum of today's closed trade PnL.
 * regime: derived from latest signal's gex_regime field.
 */

import { create } from "zustand"
import type { WsStatus } from "@/lib/ws"

const MAX_EVENTS = 200

export interface SignalEvent {
  ts: number
  tier: string
  total_score: number
  direction: number
  engine_agreement: number
  category_count: number
  categories_firing: string[]
  gex_regime: string
  kronos_bias: number
  bar_index_in_session: number
}

export interface TradeEvent {
  ts: number
  position_id: string
  event_type: string
  side: string
  entry_price: number
  exit_price: number
  pnl: number
  bars_held: number
  signal_tier: string
  signal_score: number
  regime_label: string
}

interface LiveState {
  status: WsStatus
  signals: SignalEvent[]
  trades: TradeEvent[]
  regime: string
  dailyPnl: number
  setStatus: (s: WsStatus) => void
  addSignal: (e: SignalEvent) => void
  addTrade: (e: TradeEvent) => void
}

function isTodayUtc(ts: number): boolean {
  const now = new Date()
  const d = new Date(ts * 1000)
  return (
    d.getUTCFullYear() === now.getUTCFullYear() &&
    d.getUTCMonth() === now.getUTCMonth() &&
    d.getUTCDate() === now.getUTCDate()
  )
}

export const useLiveStore = create<LiveState>()((set) => ({
  status: "disconnected",
  signals: [],
  trades: [],
  regime: "NEUTRAL",
  dailyPnl: 0,

  setStatus: (s) => set({ status: s }),

  addSignal: (e) =>
    set((state) => {
      const signals = [e, ...state.signals].slice(0, MAX_EVENTS)
      // regime derived from latest signal
      const regime = e.gex_regime ?? state.regime
      return { signals, regime }
    }),

  addTrade: (e) =>
    set((state) => {
      const trades = [e, ...state.trades].slice(0, MAX_EVENTS)
      // recalculate today's PnL from all stored trades
      const dailyPnl = trades
        .filter((t) => isTodayUtc(t.ts))
        .reduce((sum, t) => sum + (t.pnl ?? 0), 0)
      return { trades, dailyPnl }
    }),
}))
