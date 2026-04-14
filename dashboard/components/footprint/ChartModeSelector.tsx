'use client';

import { useEffect } from 'react';
import { useChartModeStore, hydrateChartMode, type ChartMode } from '@/store/chartModeStore';

// ── Chip config ───────────────────────────────────────────────────────────────

interface ModeChip {
  mode: ChartMode;
  label: string;
  tooltip: string;
}

const CHIPS: ModeChip[] = [
  { mode: 'numbers', label: 'N', tooltip: 'Numbers Bar style' },
  { mode: 'wings',   label: 'W', tooltip: 'Volume Wings style' },
  { mode: 'heatmap', label: 'H', tooltip: 'Heatmap style' },
];

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * ChartModeSelector — 3-chip toggle overlay for the footprint chart.
 *
 * Positioned absolute top-left (z-10) so it floats above the LW Charts canvas.
 * Uses UI-SPEC v2 tokens via CSS custom properties.
 *
 * The active chip lights in --lime; inactive chips use --surface-2 / --text-dim.
 * Hovering an inactive chip transitions to --surface-1 / --text over 150ms.
 *
 * Persists selection to localStorage via chartModeStore.setMode().
 * The renderer can read the current mode via:
 *   import { useChartModeStore } from '@/store/chartModeStore';
 *   const { mode } = useChartModeStore.getState();  // safe outside React
 */
export function ChartModeSelector() {
  const mode    = useChartModeStore((s) => s.mode);
  const setMode = useChartModeStore((s) => s.setMode);

  // Restore persisted preference on first client mount.
  useEffect(() => {
    hydrateChartMode();
  }, []);

  return (
    <div
      style={{
        position: 'absolute',
        top: 8,
        left: 8,
        zIndex: 10,
        display: 'flex',
        gap: 4,
      }}
      aria-label="Chart rendering mode"
      role="toolbar"
    >
      {CHIPS.map(({ mode: chipMode, label, tooltip }) => {
        const isActive = mode === chipMode;
        return (
          <button
            key={chipMode}
            onClick={() => setMode(chipMode)}
            title={tooltip}
            aria-pressed={isActive}
            aria-label={tooltip}
            style={{
              width: 24,
              height: 24,
              borderRadius: 4,
              border: isActive ? 'none' : '1px solid var(--rule)',
              background: isActive ? 'var(--lime)' : 'var(--surface-2)',
              color: isActive ? 'var(--void)' : 'var(--text-dim)',
              fontFamily: 'var(--font-jetbrains-mono), monospace',
              fontSize: 11,
              fontWeight: 600,
              lineHeight: 1,
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              // Lime glow when active
              boxShadow: isActive
                ? '0 0 6px color-mix(in oklch, var(--lime) 70%, transparent)'
                : 'none',
              // 150ms transition for background/color/box-shadow
              transition: 'background 150ms, color 150ms, box-shadow 150ms, border-color 150ms',
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                const btn = e.currentTarget;
                btn.style.background = 'var(--surface-1)';
                btn.style.color = 'var(--text)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                const btn = e.currentTarget;
                btn.style.background = 'var(--surface-2)';
                btn.style.color = 'var(--text-dim)';
              }
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
