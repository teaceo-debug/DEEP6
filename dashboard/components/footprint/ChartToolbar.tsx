'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useChartModeStore, hydrateChartMode, type ChartMode } from '@/store/chartModeStore';

// ── Mode chip config ───────────────────────────────────────────────────────────

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

// ── Legend data ────────────────────────────────────────────────────────────────

interface LegendRow {
  type: 'color' | 'symbol';
  color?: string;
  glyph?: string;
  glyphColor?: string;
  label: string;
  desc: string;
}

const LEGEND_ROWS: LegendRow[] = [
  { type: 'color',  color: 'var(--amber)',     label: 'POC',               desc: 'highest volume price level' },
  { type: 'color',  color: 'var(--ask)',        label: 'BUY imbalance',     desc: 'ask > 3× bid at level' },
  { type: 'color',  color: 'var(--bid)',        label: 'SELL imbalance',    desc: 'bid > 3× ask at level' },
  { type: 'color',  color: 'var(--text-mute)',  label: 'Neutral',           desc: 'grey = total volume' },
  { type: 'symbol', glyph: '║', glyphColor: 'var(--lime)',     label: 'Stacked imbalance', desc: 'run of 3+ consecutive levels' },
  { type: 'symbol', glyph: '▲', glyphColor: 'var(--amber)',    label: 'Signal marker',     desc: 'tier color indicates strength' },
  { type: 'symbol', glyph: 'Δ', glyphColor: 'var(--text-dim)', label: 'Bar delta',          desc: 'ask vol − bid vol' },
  { type: 'symbol', glyph: 'VP', glyphColor: 'var(--cyan)',    label: 'Volume profile',    desc: 'left sidebar histogram' },
];

// ── Sub-components ─────────────────────────────────────────────────────────────

function Swatch({ row }: { row: LegendRow }) {
  if (row.type === 'color') {
    return (
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: 2,
          flexShrink: 0,
          background: row.color,
        }}
      />
    );
  }
  return (
    <div
      style={{
        width: 10,
        height: 10,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 9,
        fontFamily: 'var(--font-jetbrains-mono), monospace',
        color: row.glyphColor ?? 'var(--text-dim)',
        lineHeight: 1,
      }}
    >
      {row.glyph}
    </div>
  );
}

function InfoIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.25" />
      <rect x="5.375" y="5" width="1.25" height="4" rx="0.5" fill="currentColor" />
      <circle cx="6" cy="3.25" r="0.75" fill="currentColor" />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <line x1="4" y1="1" x2="4" y2="11" stroke="currentColor" strokeWidth="1.1" />
      <line x1="8" y1="1" x2="8" y2="11" stroke="currentColor" strokeWidth="1.1" />
      <line x1="1" y1="4" x2="11" y2="4" stroke="currentColor" strokeWidth="1.1" />
      <line x1="1" y1="8" x2="11" y2="8" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}

function Divider() {
  return (
    <div
      style={{
        width: 1,
        height: 16,
        background: 'var(--rule)',
        flexShrink: 0,
        alignSelf: 'center',
      }}
    />
  );
}

// ── ChartToolbar ───────────────────────────────────────────────────────────────

/**
 * ChartToolbar — unified top-left floating strip consolidating:
 *   • Mode chips (N / W / H) — replaces ChartModeSelector
 *   • Info icon with slide-down legend panel — replaces ChartLegend
 *   • Grid toggle stub
 *
 * Positioning: absolute top:8 left:8 z-index:10
 * Height: 28px, bg --surface-2, border --rule-bright, radius 4px
 */
export function ChartToolbar() {
  // ── Mode state ───────────────────────────────────────────────────────────────
  const mode    = useChartModeStore((s) => s.mode);
  const setMode = useChartModeStore((s) => s.setMode);

  useEffect(() => {
    hydrateChartMode();
  }, []);

  // ── Legend open/close state ──────────────────────────────────────────────────
  const [legendOpen,  setLegendOpen]  = useState(false);
  const [infoHovered, setInfoHovered] = useState(false);
  const [gridActive,  setGridActive]  = useState(false);

  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef  = useRef<HTMLDivElement | null>(null);

  const scheduleClose = useCallback(() => {
    closeTimerRef.current = setTimeout(() => setLegendOpen(false), 300);
  }, []);

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  // Click-outside to close legend panel
  useEffect(() => {
    if (!legendOpen) return;
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setLegendOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [legendOpen]);

  // Cleanup timer on unmount
  useEffect(() => () => { if (closeTimerRef.current) clearTimeout(closeTimerRef.current); }, []);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute',
        top: 8,
        left: 8,
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
      }}
    >
      {/* ── Toolbar strip ─────────────────────────────────────────────────────── */}
      <div
        role="toolbar"
        aria-label="Chart controls"
        style={{
          height: 28,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '0 4px',
          background: 'var(--surface-2)',
          border: '1px solid var(--rule-bright)',
          borderRadius: 4,
        }}
      >
        {/* Mode chips */}
        {CHIPS.map(({ mode: chipMode, label, tooltip }) => {
          const isActive = mode === chipMode;
          return (
            <button
              key={chipMode}
              type="button"
              onClick={() => setMode(chipMode)}
              title={tooltip}
              aria-pressed={isActive}
              aria-label={tooltip}
              style={{
                width: 24,
                height: 20,
                borderRadius: 3,
                border: isActive ? 'none' : '1px solid var(--rule)',
                background: isActive ? 'var(--lime)' : 'var(--surface-1)',
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
                boxShadow: isActive
                  ? '0 0 6px color-mix(in oklch, var(--lime) 70%, transparent)'
                  : 'none',
                transition: 'background 150ms, color 150ms, box-shadow 150ms, border-color 150ms',
                flexShrink: 0,
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'var(--surface-2)';
                  e.currentTarget.style.color = 'var(--text)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'var(--surface-1)';
                  e.currentTarget.style.color = 'var(--text-dim)';
                }
              }}
            >
              {label}
            </button>
          );
        })}

        <Divider />

        {/* Info icon — hover opens legend panel */}
        <button
          type="button"
          aria-label="Show footprint legend"
          aria-expanded={legendOpen}
          onMouseEnter={() => {
            setInfoHovered(true);
            cancelClose();
            setLegendOpen(true);
          }}
          onMouseLeave={() => {
            setInfoHovered(false);
            scheduleClose();
          }}
          onClick={() => setLegendOpen((v) => !v)}
          style={{
            width: 20,
            height: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 3,
            border: '1px solid transparent',
            background: legendOpen || infoHovered ? 'var(--surface-1)' : 'transparent',
            color: infoHovered || legendOpen ? 'var(--text)' : 'var(--text-dim)',
            cursor: 'pointer',
            transition: 'background 150ms, color 150ms',
            padding: 0,
            outline: 'none',
            flexShrink: 0,
          }}
        >
          <InfoIcon />
        </button>

        <Divider />

        {/* Grid toggle (stub) */}
        <button
          type="button"
          aria-label="Toggle grid lines"
          aria-pressed={gridActive}
          title="Toggle grid lines"
          onClick={() => setGridActive((v) => !v)}
          style={{
            width: 20,
            height: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 3,
            border: '1px solid transparent',
            background: gridActive ? 'var(--surface-1)' : 'transparent',
            color: gridActive ? 'var(--text)' : 'var(--text-dim)',
            cursor: 'pointer',
            transition: 'background 150ms, color 150ms',
            padding: 0,
            outline: 'none',
            flexShrink: 0,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--surface-1)';
            e.currentTarget.style.color = 'var(--text)';
          }}
          onMouseLeave={(e) => {
            if (!gridActive) {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--text-dim)';
            }
          }}
        >
          <GridIcon />
        </button>
      </div>

      {/* ── Legend panel — slides down below toolbar ───────────────────────────── */}
      <AnimatePresence>
        {legendOpen && (
          <motion.div
            key="legend-panel"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ type: 'spring', stiffness: 380, damping: 30, duration: 0.2 }}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
            style={{
              marginTop: 4,
              width: 220,
              background: 'var(--surface-2)',
              border: '1px solid var(--rule-bright)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
              borderRadius: 4,
              padding: '10px 10px 8px',
              fontFamily: 'var(--font-jetbrains-mono), monospace',
            }}
          >
            {/* Header */}
            <div
              style={{
                fontSize: 9,
                fontWeight: 600,
                letterSpacing: '0.1em',
                color: 'var(--text-dim)',
                marginBottom: 8,
              }}
            >
              FOOTPRINT LEGEND
            </div>

            {/* Rows */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {LEGEND_ROWS.map((row) => (
                <div
                  key={row.label}
                  style={{ display: 'flex', alignItems: 'center', gap: 7 }}
                >
                  <Swatch row={row} />
                  <span style={{ fontSize: 11, color: 'var(--text)', fontWeight: 500, whiteSpace: 'nowrap' }}>
                    {row.label}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    — {row.desc}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
