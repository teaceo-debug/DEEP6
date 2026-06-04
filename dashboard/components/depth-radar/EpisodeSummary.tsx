'use client';
/**
 * EpisodeSummary.tsx — Episode summary cards for DepthRadar.
 *
 * Shows: total episodes, intent distribution bar, avg duration.
 * Most recent episodes in a scrollable list with intent + final state.
 */
import { useMemo } from 'react';
import type { DepthRadarEpisode, WallIntent } from '@/types/deep6';

// ── Intent color map (shared constant — mirrors ActiveWallsTable) ────────────

const INTENT_COLORS: Record<WallIntent, string> = {
  PASSIVE_REAL: '#2B8CFF',
  SPOOF_LIKE: '#FF3B5C',
  RESERVE_REFRESH: '#00D4AA',
  MIGRATORY: '#FFB347',
  UNKNOWN: 'var(--text-mute)',
};

const INTENT_LABELS: Record<WallIntent, string> = {
  PASSIVE_REAL: 'PASSIVE',
  SPOOF_LIKE: 'SPOOF',
  RESERVE_REFRESH: 'RESERVE',
  MIGRATORY: 'MIGRATE',
  UNKNOWN: '?',
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ── Intent distribution bar ──────────────────────────────────────────────────

function IntentBar({ episodes }: { episodes: DepthRadarEpisode[] }) {
  const distribution = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const ep of episodes) {
      counts[ep.intent] = (counts[ep.intent] ?? 0) + 1;
    }
    return counts;
  }, [episodes]);

  const total = episodes.length || 1;
  const intents: WallIntent[] = ['PASSIVE_REAL', 'RESERVE_REFRESH', 'SPOOF_LIKE', 'MIGRATORY'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {/* Stacked bar */}
      <div
        style={{
          display: 'flex',
          height: '6px',
          borderRadius: '1px',
          overflow: 'hidden',
          background: 'var(--surface-2)',
        }}
      >
        {intents.map((intent) => {
          const count = distribution[intent] ?? 0;
          if (count === 0) return null;
          return (
            <div
              key={intent}
              style={{
                width: `${(count / total) * 100}%`,
                background: INTENT_COLORS[intent],
                transition: 'width 300ms ease',
              }}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          fontSize: '9px',
          color: 'var(--text-mute)',
          flexWrap: 'wrap',
        }}
      >
        {intents.map((intent) => {
          const count = distribution[intent] ?? 0;
          if (count === 0) return null;
          return (
            <span key={intent} style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
              <span
                style={{
                  display: 'inline-block',
                  width: '6px',
                  height: '6px',
                  borderRadius: '1px',
                  background: INTENT_COLORS[intent],
                  flexShrink: 0,
                }}
              />
              <span style={{ color: INTENT_COLORS[intent], fontWeight: 600 }}>
                {INTENT_LABELS[intent]}
              </span>
              <span>{count}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ── Stat card ────────────────────────────────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '2px',
        padding: '6px 8px',
        background: 'var(--surface-2)',
        borderRadius: '2px',
        flex: 1,
        minWidth: 0,
      }}
    >
      <span
        style={{
          fontSize: '18px',
          fontWeight: 700,
          fontVariantNumeric: 'tabular-nums',
          color: color ?? 'var(--text)',
          lineHeight: 1.1,
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: '9px',
          color: 'var(--text-mute)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          fontWeight: 600,
        }}
      >
        {label}
      </span>
    </div>
  );
}

// ── Episode row ──────────────────────────────────────────────────────────────

function EpisodeRow({ episode }: { episode: DepthRadarEpisode }) {
  return (
    <div
      data-testid={`episode-${episode.id}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 8px',
        fontSize: '11px',
        fontVariantNumeric: 'tabular-nums',
        borderBottom: '1px solid var(--rule)',
      }}
    >
      {/* Time */}
      <span style={{ width: '56px', flexShrink: 0, color: 'var(--text-mute)', fontSize: '10px' }}>
        {formatTime(episode.started_at)}
      </span>
      {/* Price */}
      <span style={{ width: '60px', flexShrink: 0, textAlign: 'right', color: 'var(--text)' }}>
        {episode.price.toFixed(2)}
      </span>
      {/* Side */}
      <span
        style={{
          width: '32px',
          flexShrink: 0,
          color: episode.side === 'BID' ? 'var(--bid)' : 'var(--ask)',
          fontWeight: 600,
          fontSize: '10px',
        }}
      >
        {episode.side}
      </span>
      {/* Intent */}
      <span
        style={{
          flex: 1,
          minWidth: 0,
          color: INTENT_COLORS[episode.intent],
          fontWeight: 600,
          fontSize: '10px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {INTENT_LABELS[episode.intent]}
      </span>
      {/* Duration */}
      <span style={{ width: '44px', flexShrink: 0, textAlign: 'right', color: 'var(--text-dim)' }}>
        {formatDuration(episode.duration_seconds)}
      </span>
      {/* Touches */}
      <span style={{ width: '24px', flexShrink: 0, textAlign: 'right', color: 'var(--cyan)' }}>
        {episode.touch_count}
      </span>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export interface EpisodeSummaryProps {
  episodes: DepthRadarEpisode[];
  loading: boolean;
}

export function EpisodeSummary({ episodes, loading }: EpisodeSummaryProps) {
  const stats = useMemo(() => {
    if (episodes.length === 0) return { total: 0, avgDuration: 0 };
    const totalDuration = episodes.reduce((acc, ep) => acc + ep.duration_seconds, 0);
    return {
      total: episodes.length,
      avgDuration: totalDuration / episodes.length,
    };
  }, [episodes]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Summary strip */}
      <div style={{ padding: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* KPI row */}
        <div style={{ display: 'flex', gap: '4px' }}>
          <StatCard label="Episodes" value={String(stats.total)} color="var(--cyan)" />
          <StatCard label="Avg Duration" value={formatDuration(stats.avgDuration)} />
        </div>

        {/* Intent distribution */}
        {episodes.length > 0 && <IntentBar episodes={episodes} />}
      </div>

      {/* Episode list header */}
      <div
        style={{
          display: 'flex',
          gap: '6px',
          padding: '4px 8px',
          borderTop: '1px solid var(--rule)',
          borderBottom: '1px solid var(--rule)',
          fontSize: '9px',
          color: 'var(--text-mute)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          fontWeight: 600,
        }}
      >
        <span style={{ width: '56px', flexShrink: 0 }}>Time</span>
        <span style={{ width: '60px', flexShrink: 0, textAlign: 'right' }}>Price</span>
        <span style={{ width: '32px', flexShrink: 0 }}>Side</span>
        <span style={{ flex: 1, minWidth: 0 }}>Intent</span>
        <span style={{ width: '44px', flexShrink: 0, textAlign: 'right' }}>Dur</span>
        <span style={{ width: '24px', flexShrink: 0, textAlign: 'right' }}>T</span>
      </div>

      {/* Episode list */}
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
            loading episodes...
          </div>
        ) : episodes.length === 0 ? (
          <div
            style={{
              padding: '16px 8px',
              color: 'var(--text-mute)',
              fontSize: '11px',
              textAlign: 'center',
            }}
          >
            no episodes recorded
          </div>
        ) : (
          episodes.map((ep) => <EpisodeRow key={ep.id} episode={ep} />)
        )}
      </div>
    </div>
  );
}
