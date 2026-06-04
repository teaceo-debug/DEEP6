'use client';
/**
 * IntelligenceRail.tsx — DOM intelligence summary rail for DEEP6 dashboard.
 *
 * Renders: signal count, current tier-1 active detectors, score summary.
 * Input: structured IntelligenceRailState from API SSE endpoint — no detector imports.
 */
import { useMemo } from 'react';
import type { IntelligenceRailState, ActiveDetectorSummary, DetectorTier } from '@/types/deep6';

// ── Helpers ──────────────────────────────────────────────────────────────────

const TIER_COLORS: Record<DetectorTier, string> = {
  MECHANICAL: '#26a69a',
  HEURISTIC: '#ffa726',
  DISCRETIONARY_OVERLAY: '#78909c',
};

const TIER_LABELS: Record<DetectorTier, string> = {
  MECHANICAL: 'M',
  HEURISTIC: 'H',
  DISCRETIONARY_OVERLAY: 'D',
};

function directionLabel(dir: -1 | 0 | 1): string {
  if (dir === 1) return 'LONG';
  if (dir === -1) return 'SHORT';
  return 'FLAT';
}

function directionColor(dir: -1 | 0 | 1): string {
  if (dir === 1) return '#26a69a';
  if (dir === -1) return '#ef5350';
  return '#78909c';
}

// ── Sub-components ───────────────────────────────────────────────────────────

function DetectorRow({ det }: { det: ActiveDetectorSummary }) {
  return (
    <div
      data-testid={`detector-${det.detector_id}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '2px 0',
        fontSize: '11px',
        fontFamily: 'var(--font-mono, monospace)',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          width: '14px',
          height: '14px',
          lineHeight: '14px',
          textAlign: 'center',
          borderRadius: '2px',
          background: TIER_COLORS[det.tier],
          color: '#111',
          fontSize: '9px',
          fontWeight: 700,
        }}
      >
        {TIER_LABELS[det.tier]}
      </span>
      <span style={{ flex: 1, color: 'var(--text-primary, #ddd)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {det.name}
      </span>
      <span style={{ color: directionColor(det.last_direction), minWidth: '36px', textAlign: 'right' }}>
        {directionLabel(det.last_direction)}
      </span>
      <span style={{ color: 'var(--text-mute, #888)', minWidth: '24px', textAlign: 'right' }}>
        {det.fire_count}
      </span>
      <span style={{ color: 'var(--text-mute, #888)', minWidth: '32px', textAlign: 'right' }}>
        {(det.last_confidence * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export interface IntelligenceRailProps {
  state: IntelligenceRailState;
}

export function IntelligenceRail({ state }: IntelligenceRailProps) {
  const mechanicalCount = useMemo(
    () => state.active_detectors.filter((d) => d.tier === 'MECHANICAL').length,
    [state.active_detectors],
  );

  const heuristicCount = useMemo(
    () => state.active_detectors.filter((d) => d.tier === 'HEURISTIC').length,
    [state.active_detectors],
  );

  return (
    <div
      className="intelligence-rail"
      role="complementary"
      aria-label="DOM Intelligence Rail"
      style={{
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: '11px',
        padding: '8px',
        width: '100%',
      }}
    >
      {/* Score summary header */}
      <div
        data-testid="score-summary"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '4px 0 6px',
          borderBottom: '1px solid var(--border-mute, #333)',
          marginBottom: '6px',
        }}
      >
        <div>
          <span style={{ color: 'var(--text-mute, #888)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Direction
          </span>
          <div
            data-testid="overall-direction"
            style={{
              color: directionColor(state.score_summary.overall_direction),
              fontSize: '14px',
              fontWeight: 700,
            }}
          >
            {directionLabel(state.score_summary.overall_direction)}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ color: '#26a69a' }}>
            M: {state.score_summary.mechanical_score.toFixed(2)}
          </div>
          <div style={{ color: '#ffa726' }}>
            H: {state.score_summary.heuristic_score.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Counts */}
      <div
        data-testid="event-counts"
        style={{
          display: 'flex',
          gap: '12px',
          padding: '2px 0 6px',
          color: 'var(--text-mute, #888)',
          fontSize: '10px',
        }}
      >
        <span>Events: {state.total_events}</span>
        <span>Mech: {mechanicalCount}</span>
        <span>Heur: {heuristicCount}</span>
      </div>

      {/* Active detectors list */}
      <div>
        {state.active_detectors.length === 0 ? (
          <div style={{ color: 'var(--text-mute, #555)', fontStyle: 'italic', padding: '8px 0' }}>
            No active detectors
          </div>
        ) : (
          state.active_detectors.map((det) => (
            <DetectorRow key={det.detector_id} det={det} />
          ))
        )}
      </div>
    </div>
  );
}

export default IntelligenceRail;
