import { create } from 'zustand';

export type ChartMode = 'numbers' | 'wings' | 'heatmap';

interface ChartModeState {
  mode: ChartMode;
  setMode: (mode: ChartMode) => void;
}

const STORAGE_KEY = 'deep6:chartMode';

function loadPersistedMode(): ChartMode {
  if (typeof window === 'undefined') return 'numbers';
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === 'numbers' || raw === 'wings' || raw === 'heatmap') return raw;
  } catch {
    // ignore localStorage errors (SSR / private browsing)
  }
  return 'numbers';
}

export const useChartModeStore = create<ChartModeState>()((set) => ({
  mode: 'numbers',  // default; overridden on client mount via useEffect in ChartModeSelector
  setMode: (mode) => {
    set({ mode });
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // ignore
    }
  },
}));

/** Call once on client mount to restore persisted preference. */
export function hydrateChartMode(): void {
  const persisted = loadPersistedMode();
  if (persisted !== useChartModeStore.getState().mode) {
    useChartModeStore.getState().setMode(persisted);
  }
}
