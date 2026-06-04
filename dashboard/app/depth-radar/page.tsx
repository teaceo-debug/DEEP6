'use client';
/**
 * Depth Radar page — wall classification, episodes, and touch outcomes.
 *
 * Layout follows the DOM Intelligence page pattern:
 *   top: DEEP6 header strip
 *   main: full-height DepthRadar panel
 *
 * Demo mode: renders fixture data without backend dependency.
 * Live mode: polls REST endpoints for wall/episode/touch data.
 */
import { DepthRadarPanel } from '@/components/depth-radar/DepthRadarPanel';

export default function DepthRadarPage() {
  return (
    <div
      data-testid="depth-radar-layout"
      style={{
        display: 'grid',
        gridTemplateRows: 'auto 1fr',
        height: '100vh',
        background: 'var(--void)',
        color: 'var(--text)',
      }}
    >
      {/* Top: Header strip */}
      <div
        data-testid="header-strip"
        style={{
          background: 'var(--surface-1)',
          borderBottom: '1px solid var(--rule)',
          padding: '4px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          fontFamily: 'var(--font-jetbrains-mono, monospace)',
          fontSize: '11px',
        }}
      >
        <span style={{ fontWeight: 700, color: 'var(--text)' }}>DEEP6</span>
        <span style={{ color: 'var(--text-mute)' }}>NQ</span>
        <span style={{ color: 'var(--cyan)', fontWeight: 600 }}>Depth Radar</span>
        {/* Live indicator */}
        <span
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '9px',
            color: 'var(--text-mute)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          <span
            className="animate-pulse-dot"
            style={{
              display: 'inline-block',
              width: '5px',
              height: '5px',
              borderRadius: '50%',
              background: 'var(--cyan)',
            }}
          />
          MBO
        </span>
      </div>

      {/* Main content — DepthRadar panel fills viewport */}
      <main
        style={{
          overflow: 'hidden',
          display: 'flex',
        }}
      >
        {/* Panel takes full width */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <DepthRadarPanel />
        </div>
      </main>
    </div>
  );
}
