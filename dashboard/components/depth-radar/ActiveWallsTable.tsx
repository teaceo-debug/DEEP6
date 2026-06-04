'use client';
/**
 * ActiveWallsTable.tsx — Live wall classification table for DepthRadar.
 *
 * Columns: Price, Side, Size, Max, Intent, State, Confidence, Age
 * Intent color-coding: PASSIVE_REAL=blue, SPOOF_LIKE=red, RESERVE_REFRESH=teal, MIGRATORY=amber
 * State badges with semantic colors and animation for UNDER_ATTACK.
 * Sorted by size descending.
 */
import { useMemo } from 'react';
import type { DepthRadarWall, WallIntent, WallState, WallSide } from '@/types/deep6';

// ── Intent color map ─────────────────────────────────────────────────────────

const INTENT_COLORS: Record<WallIntent, string> = {
  PASSIVE_REAL: '#2B8CFF',
  SPOOF_LIKE: '#FF3B5C',
  RESERVE_REFRESH: '#00D4AA',
  MIGRATORY: '#FFB347',
  UNKNOWN: 'var(--text-mute)',
};

const INTENT_BG: Record<WallIntent, string> = {
  PASSIVE_REAL: 'rgba(43, 140, 255, 0.08)',
  SPOOF_LIKE: 'rgba(255, 59, 92, 0.08)',
  RESERVE_REFRESH: 'rgba(0, 212, 170, 0.08)',
  MIGRATORY: 'rgba(255, 179, 71, 0.08)',
  UNKNOWN: 'transparent',
};

// ── State badge styling ──────────────────────────────────────────────────────

interface StateBadgeStyle {
  bg: string;
  fg: string;
  animation?: string;
  opacity?: number;
}

const STATE_STYLES: Record<WallState, StateBadgeStyle> = {
  FRESH: { bg: 'rgba(138, 138, 138, 0.15)', fg: 'var(--text-dim)' },
  ESTABLISHED: { bg: 'rgba(0, 255, 136, 0.12)', fg: 'var(--ask)' },
  UNDER_ATTACK: {
    bg: 'rgba(255, 179, 71, 0.18)',
    fg: '#FFB347',
    animation: 'pulse-breathe 1500ms ease-in-out infinite',
  },
  DEFENDING: { bg: 'rgba(43, 140, 255, 0.12)', fg: '#2B8CFF' },
  EXHAUSTED: { bg: 'rgba(255, 46, 99, 0.08)', fg: 'var(--bid)', opacity: 0.6 },
  STALE: { bg: 'rgba(74, 74, 74, 0.1)', fg: 'var(--text-mute)', opacity: 0.5 },
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function sideLabel(side: WallSide): { text: string; color: string } {
  return side === 'BID'
    ? { text: 'BID', color: 'var(--bid)' }
    : { text: 'ASK', color: 'var(--ask)' };
}

// ── Column header ────────────────────────────────────────────────────────────

const COLUMNS = ['Price', 'Side', 'Size', 'Max', 'Intent', 'State', 'Conf', 'Age'] as const;
const COL_WIDTHS = ['72px', '44px', '60px', '60px', '96px', '92px', '48px', '44px'] as const;
const COL_ALIGN: Record<number, string> = { 0: 'right', 2: 'right', 3: 'right', 6: 'right', 7: 'right' };

function ColHeader() {
  return (
    <div
      style={{
        display: 'flex',
        gap: '4px',
        padding: '4px 8px',
        borderBottom: '1px solid var(--rule)',
        fontSize: '10px',
        color: 'var(--text-mute)',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        fontWeight: 600,
      }}
    >
      {COLUMNS.map((col, i) => (
        <span
          key={col}
          style={{
            width: COL_WIDTHS[i],
            flexShrink: 0,
            textAlign: (COL_ALIGN[i] as CanvasTextAlign) ?? 'left',
          }}
        >
          {col}
        </span>
      ))}
    </div>
  );
}

// ── State badge ──────────────────────────────────────────────────────────────

function StateBadge({ state }: { state: WallState }) {
  const s = STATE_STYLES[state];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 5px',
        borderRadius: '2px',
        background: s.bg,
        color: s.fg,
        fontSize: '9px',
        fontWeight: 600,
        letterSpacing: '0.04em',
        animation: s.animation,
        opacity: s.opacity ?? 1,
        whiteSpace: 'nowrap',
      }}
    >
      {state.replace('_', ' ')}
    </span>
  );
}

// ── Wall row ─────────────────────────────────────────────────────────────────

function WallRow({ wall }: { wall: DepthRadarWall }) {
  const side = sideLabel(wall.side);
  const intentColor = INTENT_COLORS[wall.intent];
  const intentBg = INTENT_BG[wall.intent];

  return (
    <div
      data-testid={`wall-${wall.id}`}
      style={{
        display: 'flex',
        gap: '4px',
        padding: '3px 8px',
        fontSize: '11px',
        fontFamily: 'var(--font-jetbrains-mono, monospace)',
        fontVariantNumeric: 'tabular-nums',
        background: intentBg,
        borderBottom: '1px solid var(--rule)',
        transition: 'background 150ms ease',
      }}
    >
      {/* Price */}
      <span style={{ width: COL_WIDTHS[0], flexShrink: 0, textAlign: 'right', color: 'var(--text)' }}>
        {wall.price.toFixed(2)}
      </span>
      {/* Side */}
      <span style={{ width: COL_WIDTHS[1], flexShrink: 0, color: side.color, fontWeight: 600, fontSize: '10px' }}>
        {side.text}
      </span>
      {/* Size */}
      <span style={{ width: COL_WIDTHS[2], flexShrink: 0, textAlign: 'right', color: 'var(--text)' }}>
        {wall.size.toLocaleString()}
      </span>
      {/* Max */}
      <span style={{ width: COL_WIDTHS[3], flexShrink: 0, textAlign: 'right', color: 'var(--text-dim)' }}>
        {wall.max_size.toLocaleString()}
      </span>
      {/* Intent */}
      <span style={{ width: COL_WIDTHS[4], flexShrink: 0, color: intentColor, fontWeight: 600, fontSize: '10px' }}>
        {wall.intent.replace('_', ' ')}
      </span>
      {/* State */}
      <span style={{ width: COL_WIDTHS[5], flexShrink: 0 }}>
        <StateBadge state={wall.state} />
      </span>
      {/* Confidence */}
      <span style={{ width: COL_WIDTHS[6], flexShrink: 0, textAlign: 'right', color: 'var(--text-dim)' }}>
        {(wall.confidence * 100).toFixed(0)}%
      </span>
      {/* Age */}
      <span style={{ width: COL_WIDTHS[7], flexShrink: 0, textAlign: 'right', color: 'var(--text-mute)' }}>
        {formatAge(wall.age_seconds)}
      </span>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export interface ActiveWallsTableProps {
  walls: DepthRadarWall[];
  loading: boolean;
}

export function ActiveWallsTable({ walls, loading }: ActiveWallsTableProps) {
  const sorted = useMemo(
    () => [...walls].sort((a, b) => b.size - a.size),
    [walls],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <ColHeader />

      <div
        className="scroll-terminal"
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {loading ? (
          <div
            style={{
              padding: '16px 8px',
              color: 'var(--text-mute)',
              fontSize: '11px',
              fontStyle: 'italic',
            }}
          >
            scanning order book...
          </div>
        ) : sorted.length === 0 ? (
          <div
            style={{
              padding: '16px 8px',
              color: 'var(--text-mute)',
              fontSize: '11px',
              textAlign: 'center',
            }}
          >
            <span style={{ color: 'var(--rule-bright)' }}>────────</span>
            <br />
            no active walls detected
            <br />
            <span style={{ color: 'var(--rule-bright)' }}>────────</span>
          </div>
        ) : (
          sorted.map((wall) => <WallRow key={wall.id} wall={wall} />)
        )}
      </div>
    </div>
  );
}
