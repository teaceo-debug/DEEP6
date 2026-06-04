'use client';
/**
 * DOM Intelligence page — integrates DOMLadder + IntelligenceRail + SignalFeed.
 *
 * Layout per plan Phase 4:
 *   top: DEEP6 header strip
 *   left/center: footprint chart
 *   center/right: DOM ladder
 *   right rail: intelligence panel + signals
 *
 * All fixture-fed from dom-mock-state.ts for demo mode.
 * No detector logic in this component — structured state only.
 */
import { useState } from 'react';
import { DOMLadder } from '@/components/dom/DOMLadder';
import { IntelligenceRail } from '@/components/dom/IntelligenceRail';
import { SignalFeed } from '@/components/signals/SignalFeed';
import {
  MOCK_DOM_LADDER_STATE,
  MOCK_INTELLIGENCE_RAIL_STATE,
} from '@/lib/dom-mock-state';
import type { DOMLadderState, IntelligenceRailState } from '@/types/deep6';

export default function DOMIntelligencePage() {
  // In production, these would come from WebSocket / SSE.
  // For now, fixture-fed demo state.
  const [ladderState] = useState<DOMLadderState>(MOCK_DOM_LADDER_STATE);
  const [railState] = useState<IntelligenceRailState>(MOCK_INTELLIGENCE_RAIL_STATE);

  return (
    <div
      data-testid="dom-intelligence-layout"
      style={{
        display: 'grid',
        gridTemplateRows: 'auto 1fr',
        height: '100vh',
        background: 'var(--bg-surface, #111)',
        color: 'var(--text-primary, #ddd)',
      }}
    >
      {/* Top: Header strip */}
      <div
        data-testid="header-strip"
        style={{
          background: 'var(--bg-panel, #1a1a1a)',
          borderBottom: '1px solid var(--border-mute, #333)',
          padding: '4px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          fontFamily: 'var(--font-mono, monospace)',
          fontSize: '11px',
        }}
      >
        <span style={{ fontWeight: 700, color: 'var(--text-primary, #ddd)' }}>DEEP6</span>
        <span style={{ color: 'var(--text-mute, #888)' }}>NQ</span>
        <span style={{ color: 'var(--text-mute, #888)' }}>DOM Intelligence</span>
      </div>

      {/* Main content area */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 280px 260px',
          gap: '1px',
          overflow: 'hidden',
        }}
      >
        {/* Left: Chart area placeholder */}
        <div
          data-testid="chart-area"
          style={{
            background: 'var(--bg-panel, #1a1a1a)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-mute, #555)',
            fontSize: '13px',
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          Footprint Chart
        </div>

        {/* Center-right: DOM Ladder */}
        <div
          data-testid="ladder-panel"
          style={{
            background: 'var(--bg-panel, #1a1a1a)',
            borderLeft: '1px solid var(--border-mute, #333)',
            overflow: 'auto',
          }}
        >
          <div
            style={{
              padding: '6px 8px',
              fontSize: '10px',
              color: 'var(--text-mute, #888)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              borderBottom: '1px solid var(--border-mute, #333)',
            }}
          >
            DOM Ladder — NQ
          </div>
          <DOMLadder state={ladderState} maxRows={20} />
        </div>

        {/* Right: Intelligence Rail + Signal Feed */}
        <div
          data-testid="intel-panel"
          style={{
            background: 'var(--bg-panel, #1a1a1a)',
            borderLeft: '1px solid var(--border-mute, #333)',
            overflow: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              padding: '6px 8px',
              fontSize: '10px',
              color: 'var(--text-mute, #888)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              borderBottom: '1px solid var(--border-mute, #333)',
            }}
          >
            Intelligence
          </div>
          <IntelligenceRail state={railState} />

          {/* Signal Feed integration */}
          <div
            data-testid="signal-feed-section"
            style={{
              borderTop: '1px solid var(--border-mute, #333)',
              flex: 1,
              minHeight: 0,
              overflow: 'auto',
            }}
          >
            <div
              style={{
                padding: '6px 8px',
                fontSize: '10px',
                color: 'var(--text-mute, #888)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                borderBottom: '1px solid var(--border-mute, #333)',
              }}
            >
              Signals
            </div>
            <SignalFeed />
          </div>
        </div>
      </div>
    </div>
  );
}
