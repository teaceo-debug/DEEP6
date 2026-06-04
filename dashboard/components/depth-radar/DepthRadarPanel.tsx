'use client';
/**
 * DepthRadarPanel.tsx — Main DepthRadar panel for the DEEP6 dashboard.
 *
 * Three sections stacked vertically:
 *   1. Active Walls Table — live wall classifications with intent color-coding
 *   2. Episode Summary   — completed episodes with intent distribution
 *   3. Touch Outcomes     — BOUNCE / BREAK / CHURN statistics
 *
 * Data flows from useDepthRadar hooks (REST polling) or demo fixtures.
 * Terminal noir aesthetic — matches DEEP6 design system exactly.
 */
import { useState } from 'react';
import { ActiveWallsTable } from './ActiveWallsTable';
import { EpisodeSummary } from './EpisodeSummary';
import { TouchOutcomes } from './TouchOutcomes';
import {
  useDepthRadarWalls,
  useDepthRadarEpisodes,
  useDepthRadarTouches,
} from '@/hooks/useDepthRadar';
import type { DepthRadarWall, DepthRadarEpisode, DepthRadarTouch } from '@/types/deep6';

// ── Demo fixtures — used when DEMO_MODE=true or backend unreachable ─────────

const DEMO_WALLS: DepthRadarWall[] = [
  { id: 'w1', price: 21850.00, side: 'BID', size: 342, max_size: 410, intent: 'PASSIVE_REAL', state: 'ESTABLISHED', confidence: 0.87, age_seconds: 245, first_seen_ts: Date.now() / 1000 - 245 },
  { id: 'w2', price: 21875.25, side: 'ASK', size: 228, max_size: 228, intent: 'SPOOF_LIKE', state: 'FRESH', confidence: 0.72, age_seconds: 12, first_seen_ts: Date.now() / 1000 - 12 },
  { id: 'w3', price: 21842.50, side: 'BID', size: 195, max_size: 310, intent: 'RESERVE_REFRESH', state: 'UNDER_ATTACK', confidence: 0.64, age_seconds: 530, first_seen_ts: Date.now() / 1000 - 530 },
  { id: 'w4', price: 21890.00, side: 'ASK', size: 156, max_size: 156, intent: 'MIGRATORY', state: 'DEFENDING', confidence: 0.55, age_seconds: 88, first_seen_ts: Date.now() / 1000 - 88 },
  { id: 'w5', price: 21835.75, side: 'BID', size: 98, max_size: 280, intent: 'PASSIVE_REAL', state: 'EXHAUSTED', confidence: 0.91, age_seconds: 1200, first_seen_ts: Date.now() / 1000 - 1200 },
];

const DEMO_EPISODES: DepthRadarEpisode[] = [
  { id: 'e1', wall_id: 'w10', price: 21860.00, side: 'BID', intent: 'PASSIVE_REAL', final_state: 'EXHAUSTED', duration_seconds: 340, max_size: 400, touch_count: 5, started_at: Date.now() / 1000 - 3600, ended_at: Date.now() / 1000 - 3260 },
  { id: 'e2', wall_id: 'w11', price: 21875.50, side: 'ASK', intent: 'SPOOF_LIKE', final_state: 'STALE', duration_seconds: 22, max_size: 180, touch_count: 0, started_at: Date.now() / 1000 - 3200, ended_at: Date.now() / 1000 - 3178 },
  { id: 'e3', wall_id: 'w12', price: 21845.00, side: 'BID', intent: 'RESERVE_REFRESH', final_state: 'ESTABLISHED', duration_seconds: 890, max_size: 320, touch_count: 8, started_at: Date.now() / 1000 - 2800, ended_at: Date.now() / 1000 - 1910 },
  { id: 'e4', wall_id: 'w13', price: 21892.25, side: 'ASK', intent: 'MIGRATORY', final_state: 'STALE', duration_seconds: 65, max_size: 140, touch_count: 1, started_at: Date.now() / 1000 - 1800, ended_at: Date.now() / 1000 - 1735 },
  { id: 'e5', wall_id: 'w14', price: 21855.75, side: 'BID', intent: 'PASSIVE_REAL', final_state: 'DEFENDING', duration_seconds: 1200, max_size: 500, touch_count: 12, started_at: Date.now() / 1000 - 1500, ended_at: Date.now() / 1000 - 300 },
];

const DEMO_TOUCHES: DepthRadarTouch[] = [
  { id: 't1', episode_id: 'e1', price: 21860.00, outcome: 'BOUNCE', aggressor_volume: 120, defender_volume: 340, ts: Date.now() / 1000 - 3500 },
  { id: 't2', episode_id: 'e1', price: 21860.00, outcome: 'BOUNCE', aggressor_volume: 85, defender_volume: 310, ts: Date.now() / 1000 - 3400 },
  { id: 't3', episode_id: 'e1', price: 21860.00, outcome: 'BREAK', aggressor_volume: 450, defender_volume: 200, ts: Date.now() / 1000 - 3300 },
  { id: 't4', episode_id: 'e3', price: 21845.00, outcome: 'BOUNCE', aggressor_volume: 90, defender_volume: 280, ts: Date.now() / 1000 - 2700 },
  { id: 't5', episode_id: 'e3', price: 21845.00, outcome: 'CHURN', aggressor_volume: 150, defender_volume: 160, ts: Date.now() / 1000 - 2500 },
  { id: 't6', episode_id: 'e3', price: 21845.00, outcome: 'BOUNCE', aggressor_volume: 110, defender_volume: 300, ts: Date.now() / 1000 - 2300 },
  { id: 't7', episode_id: 'e5', price: 21855.75, outcome: 'BOUNCE', aggressor_volume: 200, defender_volume: 480, ts: Date.now() / 1000 - 1200 },
  { id: 't8', episode_id: 'e5', price: 21855.75, outcome: 'BREAK', aggressor_volume: 520, defender_volume: 300, ts: Date.now() / 1000 - 900 },
  { id: 't9', episode_id: 'e5', price: 21855.75, outcome: 'CHURN', aggressor_volume: 180, defender_volume: 190, ts: Date.now() / 1000 - 600 },
];

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// ── Tab type ─────────────────────────────────────────────────────────────────

type TabId = 'walls' | 'episodes' | 'touches';

interface Tab {
  id: TabId;
  label: string;
  dotColor?: string;
}

const TABS: Tab[] = [
  { id: 'walls', label: 'WALLS', dotColor: '#2B8CFF' },
  { id: 'episodes', label: 'EPISODES', dotColor: 'var(--cyan)' },
  { id: 'touches', label: 'TOUCHES', dotColor: 'var(--amber)' },
];

// ── Section header — matches existing DOM Intelligence pattern ───────────────

function SectionHeader({ title }: { title: string }) {
  return (
    <div
      style={{
        padding: '6px 8px',
        fontSize: '10px',
        color: 'var(--text-mute)',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        fontWeight: 600,
        borderBottom: '1px solid var(--rule)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      {/* Radar icon — concentric arcs */}
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden>
        <circle cx="6" cy="6" r="2" stroke="var(--cyan)" strokeWidth="1" opacity="0.8" />
        <path d="M6 1.5A4.5 4.5 0 0 1 10.5 6" stroke="var(--cyan)" strokeWidth="0.8" opacity="0.5" strokeLinecap="round" />
        <path d="M6 0.5A5.5 5.5 0 0 1 11.5 6" stroke="var(--cyan)" strokeWidth="0.6" opacity="0.3" strokeLinecap="round" />
        <circle cx="6" cy="6" r="1" fill="var(--cyan)" opacity="0.9" />
      </svg>
      <span>{title}</span>
    </div>
  );
}

// ── Tab strip ────────────────────────────────────────────────────────────────

function TabStrip({
  activeTab,
  onTabChange,
  wallCount,
}: {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  wallCount: number;
}) {
  return (
    <div
      style={{
        display: 'flex',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--surface-1)',
      }}
    >
      {TABS.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            style={{
              flex: 1,
              padding: '6px 4px',
              fontSize: '10px',
              fontFamily: 'var(--font-jetbrains-mono, monospace)',
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: isActive ? 'var(--text)' : 'var(--text-mute)',
              background: isActive ? 'var(--surface-2)' : 'transparent',
              border: 'none',
              borderBottom: isActive ? '1px solid var(--cyan)' : '1px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
              transition: 'color 150ms ease, background 150ms ease',
            }}
          >
            {/* Dot indicator */}
            <span
              style={{
                display: 'inline-block',
                width: '5px',
                height: '5px',
                borderRadius: '50%',
                background: isActive ? tab.dotColor : 'var(--rule-bright)',
                transition: 'background 150ms ease',
              }}
            />
            {tab.label}
            {/* Wall count badge on walls tab */}
            {tab.id === 'walls' && wallCount > 0 && (
              <span
                style={{
                  fontSize: '9px',
                  fontWeight: 700,
                  color: 'var(--void)',
                  background: '#2B8CFF',
                  borderRadius: '2px',
                  padding: '0 3px',
                  lineHeight: '14px',
                  minWidth: '14px',
                  textAlign: 'center',
                }}
              >
                {wallCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────

export function DepthRadarPanel() {
  const [activeTab, setActiveTab] = useState<TabId>('walls');

  // Data hooks — return empty when in demo mode (enabled=false)
  const { data: liveWalls, loading: wallsLoading } = useDepthRadarWalls();
  const { data: liveEpisodes, loading: episodesLoading } = useDepthRadarEpisodes();
  const { data: liveTouches, loading: touchesLoading } = useDepthRadarTouches();

  // Use demo data when backend is unreachable or in demo mode
  const walls = liveWalls ?? (DEMO_MODE ? DEMO_WALLS : []);
  const episodes = liveEpisodes ?? (DEMO_MODE ? DEMO_EPISODES : []);
  const touches = liveTouches ?? (DEMO_MODE ? DEMO_TOUCHES : []);

  return (
    <div
      data-testid="depth-radar-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--void)',
        fontFamily: 'var(--font-jetbrains-mono, monospace)',
        color: 'var(--text)',
      }}
    >
      {/* Panel header */}
      <SectionHeader title="Depth Radar" />

      {/* Tab strip */}
      <TabStrip
        activeTab={activeTab}
        onTabChange={setActiveTab}
        wallCount={walls.length}
      />

      {/* Tab content */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {activeTab === 'walls' && (
          <ActiveWallsTable
            walls={walls}
            loading={wallsLoading && !DEMO_MODE}
          />
        )}
        {activeTab === 'episodes' && (
          <EpisodeSummary
            episodes={episodes}
            loading={episodesLoading && !DEMO_MODE}
          />
        )}
        {activeTab === 'touches' && (
          <TouchOutcomes
            touches={touches}
            loading={touchesLoading && !DEMO_MODE}
          />
        )}
      </div>
    </div>
  );
}
