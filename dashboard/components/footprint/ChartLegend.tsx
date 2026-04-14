'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';

// ── Legend data ────────────────────────────────────────────────────────────────

interface LegendRow {
  type: 'color' | 'symbol';
  /** CSS color string or CSS variable reference */
  color?: string;
  /** Text glyph shown instead of a color swatch */
  glyph?: string;
  glyphColor?: string;
  label: string;
  desc: string;
}

const LEGEND_ROWS: LegendRow[] = [
  {
    type: 'color',
    color: 'var(--amber)',
    label: 'POC',
    desc: 'highest volume price level',
  },
  {
    type: 'color',
    color: 'var(--ask)',
    label: 'BUY imbalance',
    desc: 'ask > 3× bid at level',
  },
  {
    type: 'color',
    color: 'var(--bid)',
    label: 'SELL imbalance',
    desc: 'bid > 3× ask at level',
  },
  {
    type: 'color',
    color: 'var(--text-mute)',
    label: 'Neutral',
    desc: 'grey = total volume',
  },
  {
    type: 'symbol',
    glyph: '║',
    glyphColor: 'var(--lime)',
    label: 'Stacked imbalance',
    desc: 'run of 3+ consecutive levels',
  },
  {
    type: 'symbol',
    glyph: '▲',
    glyphColor: 'var(--amber)',
    label: 'Signal marker',
    desc: 'tier color indicates strength',
  },
  {
    type: 'symbol',
    glyph: 'Δ',
    glyphColor: 'var(--text-dim)',
    label: 'Bar delta',
    desc: 'ask vol − bid vol',
  },
  {
    type: 'symbol',
    glyph: 'VP',
    glyphColor: 'var(--cyan)',
    label: 'Volume profile',
    desc: 'left sidebar histogram',
  },
];

// ── Swatch ─────────────────────────────────────────────────────────────────────

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

// ── InfoIcon ───────────────────────────────────────────────────────────────────

function InfoIcon({ dimmed }: { dimmed: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{
        color: dimmed ? 'var(--text-dim)' : 'var(--text)',
        transition: 'color 150ms ease',
        flexShrink: 0,
      }}
    >
      <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.25" />
      <rect x="5.375" y="5" width="1.25" height="4" rx="0.5" fill="currentColor" />
      <circle cx="6" cy="3.25" r="0.75" fill="currentColor" />
    </svg>
  );
}

// ── ChartLegend ────────────────────────────────────────────────────────────────

export function ChartLegend() {
  const [open, setOpen] = useState(false);
  const [btnHovered, setBtnHovered] = useState(false);

  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const scheduleClose = useCallback(() => {
    closeTimerRef.current = setTimeout(() => {
      setOpen(false);
    }, 300);
  }, []);

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  // Click-outside to close
  useEffect(() => {
    if (!open) return;
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [open]);

  // Cleanup timer on unmount
  useEffect(() => () => { if (closeTimerRef.current) clearTimeout(closeTimerRef.current); }, []);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute',
        bottom: 8,
        left: 8,
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 0,
      }}
      onMouseLeave={scheduleClose}
      onMouseEnter={cancelClose}
    >
      {/* Legend panel — rendered above the icon */}
      <AnimatePresence>
        {open && (
          <motion.div
            key="legend-panel"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ type: 'spring', stiffness: 380, damping: 30, duration: 0.2 }}
            style={{
              marginBottom: 6,
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
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 7,
                  }}
                >
                  <Swatch row={row} />
                  <span
                    style={{
                      fontSize: 11,
                      color: 'var(--text)',
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {row.label}
                  </span>
                  <span
                    style={{
                      fontSize: 11,
                      color: 'var(--text-dim)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    — {row.desc}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Info icon button */}
      <button
        type="button"
        aria-label="Show footprint legend"
        aria-expanded={open}
        onMouseEnter={() => {
          setBtnHovered(true);
          cancelClose();
          setOpen(true);
        }}
        onMouseLeave={() => setBtnHovered(false)}
        onClick={() => setOpen((v) => !v)}
        style={{
          width: 22,
          height: 22,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: 4,
          border: '1px solid var(--rule-bright)',
          background: btnHovered ? 'var(--surface-1)' : 'var(--surface-2)',
          cursor: 'pointer',
          transition: 'background 150ms ease',
          padding: 0,
          outline: 'none',
        }}
      >
        <InfoIcon dimmed={!btnHovered} />
      </button>
    </div>
  );
}
