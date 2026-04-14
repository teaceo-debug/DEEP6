'use client';

/**
 * ZoneList.tsx — Compact zone table (UI-SPEC v2 §4.6).
 *
 * Shows up to 4 most relevant zones ordered by proximity to current price.
 * Zone monogram tiles: POC/HVN → --amber, VAH/VAL → --text, LVN → --cyan.
 * Mini-bar (80px): ● dot positioned at (distanceTicks + 5) / 10 of the width.
 *
 * NOTE: The tradingStore does not yet expose a dedicated zones array with
 * VAH/VAL/LVN/HVN and alert counts. We derive a POC zone from the latest
 * bar's poc_price and current close. Remaining zone types will be wired when
 * the backend exposes zone_registry data (future plan).
 * TODO: wire backend zone_registry when Phase 5+ data flow is established.
 */

import { useTradingStore } from '@/store/tradingStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ZoneKind = 'POC' | 'VAH' | 'VAL' | 'LVN' | 'HVN';

interface ZoneRow {
  kind: ZoneKind;
  price: number;
  alertCount: number;
  distanceTicks: number; // negative = below current, positive = above
}

// ---------------------------------------------------------------------------
// Zone tile color helper
// ---------------------------------------------------------------------------

function tileColor(kind: ZoneKind): string {
  switch (kind) {
    case 'POC':
    case 'HVN': return 'var(--amber)';
    case 'VAH':
    case 'VAL': return 'var(--text)';
    case 'LVN': return 'var(--cyan)';
  }
}

function tileTextColor(kind: ZoneKind): string {
  // All tiles get black text on colored background for readability
  switch (kind) {
    case 'POC':
    case 'HVN': return '#000000';
    case 'VAH':
    case 'VAL': return '#000000';
    case 'LVN': return '#000000';
  }
}

// ---------------------------------------------------------------------------
// Mini-bar component (80px wide)
// ● positioned at (distanceTicks + 5) / 10 clamped [0,1]
// ---------------------------------------------------------------------------

function MiniBar({ distanceTicks, kind }: { distanceTicks: number; kind: ZoneKind }) {
  const position = Math.max(0, Math.min(1, (distanceTicks + 5) / 10));
  const dotLeftPct = position * 100;
  const zoneColor = tileColor(kind);

  return (
    <div
      style={{
        width: '80px',
        height: '12px',
        background: 'var(--surface-2)',
        borderRadius: '1px',
        position: 'relative',
        flexShrink: 0,
      }}
    >
      {/* Zone center line */}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: 0,
          bottom: 0,
          width: '1px',
          background: zoneColor,
          opacity: 0.4,
        }}
      />
      {/* Current price dot */}
      <div
        style={{
          position: 'absolute',
          left: `${dotLeftPct}%`,
          top: '50%',
          transform: 'translate(-50%, -50%)',
          width: '5px',
          height: '5px',
          borderRadius: '50%',
          background: 'var(--text)',
          flexShrink: 0,
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ZoneList() {
  // Read latest bar for POC price and current close
  const lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  const bars           = useTradingStore((s) => s.bars);

  // Suppress unused warning for lastBarVersion — it's used to trigger re-render
  void lastBarVersion;

  const latestBar = bars.size > 0 ? bars.latest : null;
  const currentPrice = latestBar?.close ?? 0;
  const pocPrice     = latestBar?.poc_price ?? 0;

  // NQ tick size = 0.25 (1 tick = $5)
  const TICK_SIZE = 0.25;

  function priceDist(zonePrice: number): number {
    if (!currentPrice || !zonePrice) return 0;
    return Math.round((zonePrice - currentPrice) / TICK_SIZE);
  }

  // Build zone rows from available bar data
  // TODO: replace with live zone_registry data from backend (Phase 5+)
  const zones: ZoneRow[] = [];

  if (pocPrice > 0) {
    zones.push({
      kind: 'POC',
      price: pocPrice,
      alertCount: 0, // TODO: wire alert count from backend
      distanceTicks: priceDist(pocPrice),
    });
  }

  // Sort by proximity (nearest first) — with only POC we have 0-1 rows
  zones.sort((a, b) => Math.abs(a.distanceTicks) - Math.abs(b.distanceTicks));

  const displayZones = zones.slice(0, 4);

  return (
    <div
      style={{
        background: 'var(--surface-1)',
        padding: '12px 16px',
        height: '100%',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: '0',
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: '6px',
        }}
      >
        <span className="text-xs label-tracked" style={{ color: 'var(--text-dim)' }}>
          ZONES
        </span>
        <span className="text-xs label-tracked" style={{ color: 'var(--text-dim)' }}>
          ALERTS
        </span>
      </div>

      {/* Divider */}
      <div
        style={{
          borderBottom: '1px solid var(--rule)',
          marginBottom: '6px',
        }}
      />

      {/* Zone rows */}
      {displayZones.length === 0 ? (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span className="text-xs" style={{ color: 'var(--text-mute)' }}>
            NO ZONES
          </span>
        </div>
      ) : (
        displayZones.map((zone, i) => (
          <div
            key={`${zone.kind}-${zone.price}-${i}`}
            style={{
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            {/* Zone monogram tile (14×14) */}
            <div
              style={{
                width: '14px',
                height: '14px',
                background: tileColor(zone.kind),
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                borderRadius: '1px',
              }}
            >
              <span
                style={{
                  fontSize: '7px',
                  fontWeight: 600,
                  color: tileTextColor(zone.kind),
                  fontFamily: 'var(--font-jetbrains-mono), monospace',
                  lineHeight: 1,
                  letterSpacing: '-0.02em',
                }}
              >
                {zone.kind.slice(0, 3)}
              </span>
            </div>

            {/* Price */}
            <span
              className="text-sm tnum"
              style={{ color: 'var(--text)', minWidth: '56px' }}
            >
              {zone.price.toFixed(2)}
            </span>

            {/* Mini-bar */}
            <MiniBar distanceTicks={zone.distanceTicks} kind={zone.kind} />

            {/* Alert count */}
            <span
              className="text-xs tnum"
              style={{
                color: zone.alertCount > 0 ? 'var(--text)' : 'var(--text-mute)',
                marginLeft: 'auto',
                minWidth: '16px',
                textAlign: 'right',
              }}
            >
              {zone.alertCount > 0 ? zone.alertCount : ''}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
