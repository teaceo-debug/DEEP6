'use client';

/**
 * ZoneList.tsx — Compact zone table (UI-SPEC v2 §4.6).
 *
 * 5 zone rows (24px each) with monogram tile, price, proximity mini-bar,
 * alert count badge, and delta distance column.
 *
 * Zone monogram tiles: POC/HVN → --amber, VAH/VAL → --text, LVN → --cyan,
 * GEX+ → --ask, GEX- → --bid.
 *
 * Mini-bar (80px): ● positioned at (distanceTicks + 5) / 10 of the width.
 * Zone's own color as thin vertical center line. Dot color:
 *   lime   = within ±1 tick (AT zone)
 *   amber  = within ±3 ticks (APPROACHING)
 *   muted  = beyond ±3 ticks
 *
 * NOTE: Store exposes poc_price from the latest bar. VAH/VAL are estimated
 * from bar range (close ± range*0.3). LVN/HVN have no backend data yet —
 * shown as placeholder rows. TODO: wire zone_registry when Phase 5+ arrives.
 */

import { useState } from 'react';
import { useTradingStore } from '@/store/tradingStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ZoneKind = 'POC' | 'VAH' | 'VAL' | 'LVN' | 'HVN' | 'GEX+' | 'GEX-';

interface ZoneRow {
  kind: ZoneKind;
  price: number | null; // null = pending / not available
  alertCount: number;
  distanceTicks: number; // signed: positive = above current price
  isPending: boolean;
}

const ZONE_TOOLTIPS: Record<ZoneKind, string> = {
  'POC':  'POC — Point of Control. Price level with highest volume in session.',
  'VAH':  'VAH — Value Area High. Top of the high-volume zone (~70% of session volume).',
  'VAL':  'VAL — Value Area Low. Bottom of the high-volume zone (~70% of session volume).',
  'LVN':  'LVN — Low Volume Node. Price range with thin volume; acts as a magnet.',
  'HVN':  'HVN — High Volume Node. Dense volume area; price tends to consolidate here.',
  'GEX+': 'GEX+ — Positive GEX level. Dealers sell rallies here; gamma resistance.',
  'GEX-': 'GEX- — Negative GEX level. Dealers buy dips here; gamma support.',
};

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

function tileColor(kind: ZoneKind): string {
  switch (kind) {
    case 'POC':
    case 'HVN':  return 'var(--amber)';
    case 'VAH':
    case 'VAL':  return 'var(--text)';
    case 'LVN':  return 'var(--cyan)';
    case 'GEX+': return 'var(--ask)';
    case 'GEX-': return 'var(--bid)';
  }
}

// Alert badge color
function alertColor(count: number): string {
  if (count >= 3)  return 'var(--lime)';
  if (count >= 1)  return 'var(--amber)';
  return 'var(--text-mute)';
}

// Dot color based on proximity
function dotColor(distanceTicks: number): string {
  const abs = Math.abs(distanceTicks);
  if (abs <= 1) return 'var(--lime)';
  if (abs <= 3) return 'var(--amber)';
  return 'var(--text-mute)';
}

// Delta distance display  (+0.25, -1.50, etc.)
function deltaLabel(ticks: number, price: number | null): string {
  if (price === null) return '—';
  const points = ticks * 0.25;
  if (points === 0) return '0.00';
  return (points > 0 ? '+' : '') + points.toFixed(2);
}

function deltaColor(ticks: number): string {
  if (ticks > 0) return 'var(--ask)';
  if (ticks < 0) return 'var(--bid)';
  return 'var(--text-dim)';
}

// ---------------------------------------------------------------------------
// Tile label — abbreviate to fit 14×14
// ---------------------------------------------------------------------------
function tileLabel(kind: ZoneKind): string {
  switch (kind) {
    case 'GEX+': return 'G+';
    case 'GEX-': return 'G-';
    default:     return kind.slice(0, 3);
  }
}

// ---------------------------------------------------------------------------
// MiniBar component (80px wide)
// ---------------------------------------------------------------------------

interface MiniBarProps {
  distanceTicks: number;
  kind: ZoneKind;
  isPending: boolean;
}

function MiniBar({ distanceTicks, kind, isPending }: MiniBarProps) {
  // position = (distanceTicks + 5) / 10, clamped [0, 1]
  // zone is at center (50%), dot moves left/right around it
  const position = Math.max(0, Math.min(1, (distanceTicks + 5) / 10));
  const dotLeftPct = position * 100;
  const zoneColor = tileColor(kind);
  const dColor = isPending ? 'var(--text-mute)' : dotColor(distanceTicks);

  return (
    <div
      style={{
        width: '80px',
        height: '12px',
        background: 'color-mix(in srgb, var(--rule) 60%, transparent)',
        borderRadius: '1px',
        position: 'relative',
        flexShrink: 0,
        boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.6)',
      }}
    >
      {/* Zone center line — zone's own color */}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: 0,
          bottom: 0,
          width: '1px',
          background: isPending ? 'var(--rule)' : zoneColor,
          opacity: isPending ? 0.3 : 0.6,
          transform: 'translateX(-50%)',
        }}
      />
      {/* Current price dot */}
      {!isPending && (
        <div
          style={{
            position: 'absolute',
            left: `${dotLeftPct}%`,
            top: '50%',
            transform: 'translate(-50%, -50%)',
            width: '5px',
            height: '5px',
            borderRadius: '50%',
            background: dColor,
            flexShrink: 0,
            transition: 'left 300ms ease-out, background 200ms ease',
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Blinking cursor for empty state
// ---------------------------------------------------------------------------

function BlinkCursor() {
  return (
    <span
      style={{
        animation: 'blink-cursor 1.1s step-start infinite',
        color: 'var(--text-mute)',
      }}
    >
      _
      <style>{`
        @keyframes blink-cursor {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .blink-cursor { animation: none; }
        }
      `}</style>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Zone row component
// ---------------------------------------------------------------------------

interface ZoneRowItemProps {
  zone: ZoneRow;
}

function ZoneRowItem({ zone }: ZoneRowItemProps) {
  const [hovered, setHovered] = useState(false);
  const tooltip = ZONE_TOOLTIPS[zone.kind];
  const tc = tileColor(zone.kind);

  return (
    <div
      title={tooltip}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        height: '24px',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '0 4px',
        borderRadius: '2px',
        cursor: 'default',
        background: hovered ? 'var(--surface-1)' : 'transparent',
        transition: 'background 150ms ease',
        userSelect: 'none',
      }}
    >
      {/* Zone monogram tile (14×14) */}
      <div
        style={{
          width: '14px',
          height: '14px',
          background: zone.isPending ? 'var(--surface-2)' : tc,
          border: zone.isPending ? '1px solid var(--rule)' : 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          borderRadius: '1px',
        }}
      >
        <span
          style={{
            fontSize: '6.5px',
            fontWeight: 700,
            color: zone.isPending ? 'var(--text-mute)' : '#000000',
            fontFamily: 'var(--font-jetbrains-mono), monospace',
            lineHeight: 1,
            letterSpacing: '-0.03em',
          }}
        >
          {tileLabel(zone.kind)}
        </span>
      </div>

      {/* Price — 68px width, right-aligned, tabular */}
      <span
        className="text-xs tnum"
        style={{
          color: zone.isPending ? 'var(--text-mute)' : 'var(--text)',
          width: '68px',
          textAlign: 'right',
          flexShrink: 0,
          fontStyle: zone.isPending ? 'italic' : 'normal',
          letterSpacing: 0,
        }}
      >
        {zone.isPending
          ? '— pending —'
          : zone.price !== null
            ? zone.price.toFixed(2)
            : '—'
        }
      </span>

      {/* Mini proximity bar */}
      <MiniBar
        distanceTicks={zone.distanceTicks}
        kind={zone.kind}
        isPending={zone.isPending}
      />

      {/* Delta distance */}
      <span
        className="text-xs tnum"
        style={{
          color: zone.isPending ? 'var(--text-mute)' : deltaColor(zone.distanceTicks),
          width: '36px',
          textAlign: 'right',
          flexShrink: 0,
          letterSpacing: 0,
        }}
      >
        {zone.isPending ? '' : deltaLabel(zone.distanceTicks, zone.price)}
      </span>

      {/* Alert count badge */}
      <span
        className="text-xs tnum"
        style={{
          color: zone.isPending ? 'var(--text-mute)' : alertColor(zone.alertCount),
          width: '16px',
          textAlign: 'right',
          flexShrink: 0,
          letterSpacing: 0,
          marginLeft: 'auto',
          fontWeight: zone.alertCount >= 3 ? 600 : 400,
        }}
      >
        {zone.isPending ? '' : zone.alertCount > 0 ? zone.alertCount : ''}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ZoneList() {
  const lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  const bars           = useTradingStore((s) => s.bars);

  // Suppress unused warning — used to trigger re-render on new bars
  void lastBarVersion;

  const latestBar    = bars.size > 0 ? bars.latest : null;
  const currentPrice = latestBar?.close ?? 0;
  const pocPrice     = latestBar?.poc_price ?? 0;
  const barRange     = latestBar?.bar_range ?? 0;

  const TICK_SIZE = 0.25; // NQ tick

  function priceDist(zonePrice: number): number {
    if (!currentPrice || !zonePrice) return 0;
    return Math.round((zonePrice - currentPrice) / TICK_SIZE);
  }

  // Build zone rows
  // POC: always first if available
  // VAH/VAL: estimated from bar range (close ± range*0.3 as placeholder)
  // LVN/HVN: pending until Phase 5 zone_registry
  const hasBarData = pocPrice > 0;

  const vahEstimate = hasBarData ? latestBar!.close + barRange * 0.3 : 0;
  const valEstimate = hasBarData ? latestBar!.close - barRange * 0.3 : 0;

  const zones: ZoneRow[] = [
    {
      kind: 'POC',
      price: hasBarData ? pocPrice : null,
      alertCount: 0,
      distanceTicks: hasBarData ? priceDist(pocPrice) : 0,
      isPending: !hasBarData,
    },
    {
      kind: 'VAH',
      price: hasBarData ? vahEstimate : null,
      alertCount: 0,
      distanceTicks: hasBarData ? priceDist(vahEstimate) : 0,
      isPending: !hasBarData,
    },
    {
      kind: 'VAL',
      price: hasBarData ? valEstimate : null,
      alertCount: 0,
      distanceTicks: hasBarData ? priceDist(valEstimate) : 0,
      isPending: !hasBarData,
    },
    {
      kind: 'LVN',
      price: null,
      alertCount: 0,
      distanceTicks: 0,
      isPending: true, // TODO: wire zone_registry Phase 5+
    },
    {
      kind: 'HVN',
      price: null,
      alertCount: 0,
      distanceTicks: 0,
      isPending: true, // TODO: wire zone_registry Phase 5+
    },
  ];

  const noData = !hasBarData;

  return (
    <div
      style={{
        background: 'var(--surface-1)',
        padding: '10px 12px',
        height: '100%',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '5px',
          paddingLeft: '4px',
          paddingRight: '4px',
        }}
      >
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-dim)' }}
        >
          ZONES
        </span>
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-dim)' }}
        >
          ALERTS
        </span>
      </div>

      {/* Divider */}
      <div
        style={{
          borderBottom: '1px solid var(--rule)',
          marginBottom: '4px',
        }}
      />

      {/* Content */}
      {noData ? (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '2px',
          }}
        >
          <span className="text-xs label-tracked" style={{ color: 'var(--text-mute)' }}>
            NO ZONES
          </span>
          <BlinkCursor />
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '1px',
          }}
        >
          {zones.map((zone, i) => (
            <ZoneRowItem key={`${zone.kind}-${i}`} zone={zone} />
          ))}
        </div>
      )}
    </div>
  );
}
