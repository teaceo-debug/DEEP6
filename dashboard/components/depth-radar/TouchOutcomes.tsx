'use client';
/**
 * TouchOutcomes.tsx — BOUNCE / BREAK / CHURN outcome stats for DepthRadar.
 *
 * Displays outcome counts, percentages, and a horizontal breakdown bar.
 * Uses the terminal noir design system: --ask for BOUNCE, --bid for BREAK,
 * --amber for CHURN.
 */
import { useMemo } from 'react';
import type { DepthRadarTouch, TouchOutcome } from '@/types/deep6';

// ── Outcome color map (maps to DEEP6 neon palette) ──────────────────────────

const OUTCOME_COLORS: Record<TouchOutcome, string> = {
  BOUNCE: 'var(--ask)',    // green — wall held, price bounced
  BREAK: 'var(--bid)',     // red — wall broken, price continued through
  CHURN: 'var(--amber)',   // amber — indecisive, absorbed but no clear resolution
};

const OUTCOME_GLOW: Record<TouchOutcome, string> = {
  BOUNCE: 'rgba(0, 255, 136, 0.25)',
  BREAK: 'rgba(255, 46, 99, 0.25)',
  CHURN: 'rgba(255, 214, 10, 0.25)',
};

// ── Outcome card ─────────────────────────────────────────────────────────────

function OutcomeCard({
  outcome,
  count,
  percent,
}: {
  outcome: TouchOutcome;
  count: number;
  percent: number;
}) {
  const color = OUTCOME_COLORS[outcome];
  const glow = OUTCOME_GLOW[outcome];

  return (
    <div
      data-testid={`outcome-${outcome.toLowerCase()}`}
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '2px',
        padding: '8px 4px',
        background: `linear-gradient(180deg, ${glow} 0%, transparent 100%)`,
        borderRadius: '2px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Bottom accent line */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          bottom: 0,
          left: '15%',
          right: '15%',
          height: '1px',
          background: `linear-gradient(to right, transparent, ${color}, transparent)`,
        }}
      />

      {/* Count */}
      <span
        style={{
          fontSize: '22px',
          fontWeight: 700,
          fontVariantNumeric: 'tabular-nums',
          color,
          lineHeight: 1.0,
        }}
      >
        {count}
      </span>

      {/* Percentage */}
      <span
        style={{
          fontSize: '11px',
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--text-dim)',
          fontWeight: 500,
        }}
      >
        {percent.toFixed(1)}%
      </span>

      {/* Label */}
      <span
        style={{
          fontSize: '9px',
          color,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontWeight: 700,
          marginTop: '2px',
        }}
      >
        {outcome}
      </span>
    </div>
  );
}

// ── Breakdown bar ────────────────────────────────────────────────────────────

function BreakdownBar({ distribution }: { distribution: Record<TouchOutcome, number> }) {
  const total = distribution.BOUNCE + distribution.BREAK + distribution.CHURN;
  if (total === 0) return null;

  const segments: { outcome: TouchOutcome; pct: number }[] = [
    { outcome: 'BOUNCE', pct: (distribution.BOUNCE / total) * 100 },
    { outcome: 'BREAK', pct: (distribution.BREAK / total) * 100 },
    { outcome: 'CHURN', pct: (distribution.CHURN / total) * 100 },
  ];

  return (
    <div
      style={{
        display: 'flex',
        height: '4px',
        borderRadius: '1px',
        overflow: 'hidden',
        background: 'var(--surface-2)',
        margin: '0 8px',
      }}
    >
      {segments.map(({ outcome, pct }) => {
        if (pct === 0) return null;
        return (
          <div
            key={outcome}
            style={{
              width: `${pct}%`,
              background: OUTCOME_COLORS[outcome],
              transition: 'width 300ms ease',
            }}
          />
        );
      })}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export interface TouchOutcomesProps {
  touches: DepthRadarTouch[];
  loading: boolean;
}

export function TouchOutcomes({ touches, loading }: TouchOutcomesProps) {
  const distribution = useMemo(() => {
    const counts: Record<TouchOutcome, number> = { BOUNCE: 0, BREAK: 0, CHURN: 0 };
    for (const t of touches) {
      if (t.outcome in counts) {
        counts[t.outcome] += 1;
      }
    }
    return counts;
  }, [touches]);

  const total = distribution.BOUNCE + distribution.BREAK + distribution.CHURN;

  const pct = (outcome: TouchOutcome): number =>
    total > 0 ? (distribution[outcome] / total) * 100 : 0;

  if (loading) {
    return (
      <div
        style={{
          padding: '16px 8px',
          color: 'var(--text-mute)',
          fontSize: '11px',
          fontStyle: 'italic',
        }}
      >
        tabulating outcomes...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '8px 0' }}>
      {/* Outcome cards row */}
      <div style={{ display: 'flex', gap: '4px', padding: '0 8px' }}>
        <OutcomeCard outcome="BOUNCE" count={distribution.BOUNCE} percent={pct('BOUNCE')} />
        <OutcomeCard outcome="BREAK" count={distribution.BREAK} percent={pct('BREAK')} />
        <OutcomeCard outcome="CHURN" count={distribution.CHURN} percent={pct('CHURN')} />
      </div>

      {/* Breakdown bar */}
      <BreakdownBar distribution={distribution} />

      {/* Total count */}
      <div
        style={{
          textAlign: 'center',
          fontSize: '10px',
          color: 'var(--text-mute)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {total} total touches
      </div>
    </div>
  );
}
