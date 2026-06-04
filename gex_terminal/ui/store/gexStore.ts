import { create } from 'zustand'
import type { GEXTerminalSnapshot } from '@/types/gex'

interface GEXStore {
  snapshot: GEXTerminalSnapshot | null
  connected: boolean
  lastUpdate: number | null
  version: number
  setSnapshot: (snapshot: GEXTerminalSnapshot) => void
  setConnected: (connected: boolean) => void
}

export const useGEXStore = create<GEXStore>((set) => ({
  snapshot: null,
  connected: false,
  lastUpdate: null,
  version: 0,
  setSnapshot: (snapshot) => set((state) => ({
    snapshot,
    lastUpdate: Date.now(),
    version: state.version + 1,
  })),
  setConnected: (connected) => set({ connected }),
}))
