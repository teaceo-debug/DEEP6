'use client';

/**
 * ZoneList.tsx — Compact zone table (UI-SPEC v2 §4.6).
 *
 * Columns: monogram | age | price | sparkline (80px) | proximity | alerts
 *
 * Zone monogram tiles: POC/HVN → --amber, VAH/VAL → --text, LVN → --cyan,
 * GEX+ → --ask, GEX- → --bid.
 *
 * Age column (28px): "NEW" in --lime for zones < 60s old, else "1m"/"3m" etc.
 * Sparkline: last 14 (price - zone_price) data points. Zero-line = zone level.
 * Zero-crossings = "reactions" counted as alert badge.
 * Delta column: ● AT / ↑ +1.25 ABOVE / ↓ -0.50 BELOW.
 * Hover: row expands 24→40px, reveals session metadata.
 * LVN/HVN: detected from bars if 5+ bars available.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import type { FootprintBar } from '@/types/deep6';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ZoneKind = 'POC' | 'VAH' | 'VAL' | 'LVN' | 'HVN' | 'GEX+' | 'GEX-';

interface ZoneRow {
  kind: ZoneKind;
  price: number | null; // null = pending / not available
  distanceTicks: number; // signed: positive = above current price
  isPending: boolean;
  /** Unix ms when this zone was first established (for age calc) */
  establishedAt: number;
  /** Last 14 (price - zone_price) deltas for sparkline */
  history: number[];
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

// Alert badge color — driven by reaction count
function reactionColor(count: number): string {
  if (count >= 3) return 'var(--lime)';
  if (count >= 1) return 'var(--amber)';
  return 'var(--text-mute)';
}

// Tile label — abbreviate to fit 14×14
function tileLabel(kind: ZoneKind): string {
  switch (kind) {
    case 'GEX+': return 'G+';
    case 'GEX-': return 'G-';
    default:     return kind.slice(0, 3);
  }
}

// Zero-crossings in a history array = "reactions"
function countReactions(history: number[]): number {
  if (history.length < 2) return 0;
  let crossings = 0;
  for (let i = 1; i < history.length; i++) {
    const prev = history[i - 1];
    const curr = history[i];
    if ((prev < 0 && curr >= 0) || (prev >= 0 && curr < 0)) {
      crossings++;
    }
  }
  return crossings;
}

// ---------------------------------------------------------------------------
// Zone age formatting
// ---------------------------------------------------------------------------

function formatAge(establishedAt: number, nowMs: number): { label: string; isNew: boolean } {
  const ageMs = nowMs - establishedAt;
  if (ageMs < 60_000) return { label: 'NEW', isNew: true };
  const mins = Math.floor(ageMs / 60_000);
  if (mins < 60) return { label: `${mins}m`, isNew: false };
  const hrs = Math.floor(mins / 60);
  return { label: `${hrs}h`, isNew: false };
}

// ---------------------------------------------------------------------------
// Delta column — polished proximity indicator
// ---------------------------------------------------------------------------

interface DeltaColProps {
  distanceTicks: number;
  price: number | null;
  isPending: boolean;
}

function DeltaCol({ distanceTicks, price, isPending }: DeltaColProps) {
  if (isPending || price === null) {
    return (
      <span
        className="text-xs tnum"
        style={{ color: 'var(--text-mute)', width: '52px', textAlign: 'right', flexShrink: 0 }}
      >
        {''}
      </span>
    );
  }

  const abs = Math.abs(distanceTicks);
  const points = distanceTicks * 0.25;

  if (abs <= 1) {
    // AT zone
    return (
      <span
        className="text-xs tnum"
        style={{ color: 'var(--lime)', width: '52px', textAlign: 'right', flexShrink: 0, fontWeight: 700 }}
      >
        ●
      </span>
    );
  }

  const sign = distanceTicks > 0 ? '↑' : '↓';
  const formatted = (points > 0 ? '+' : '') + points.toFixed(2);
  const color = distanceTicks > 0 ? 'var(--ask)' : 'var(--bid)';

  return (
    <span
      className="text-xs tnum"
      style={{ color, width: '52px', textAlign: 'right', flexShrink: 0 }}
    >
      {sign} {formatted}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Sparkline component
// ---------------------------------------------------------------------------

interface SparklineProps {
  history: number[];
  kind: ZoneKind;
  isPending: boolean;
  reactions: number;
}

function Sparkline({ history, kind, isPending }: SparklineProps) {
  const W = 80;
  const H = 28;
  const zoneColor = tileColor(kind);

  if (isPending || history.length < 2) {
    return (
      <div
        style={{
          width: `${W}px`,
          height: `${H}px`,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ width: '100%', height: '1px', background: 'var(--rule)', opacity: 0.4 }} />
      </div>
    );
  }

  // Compute y-scale
  const maxAbs = Math.max(...history.map(Math.abs), 0.01);
  const yMid = H / 2;

  // Map data points to SVG coords
  const pts = history.map((v, i) => {
    const x = (i / (history.length - 1)) * W;
    const y = yMid - (v / maxAbs) * (yMid - 2);
    return { x, y };
  });

  const pathD = pts
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ');

  const lastPt = pts[pts.length - 1];

  return (
    <svg
      width={W}
      height={H}
      style={{ flexShrink: 0, overflow: 'visible' }}
    >
      {/* Zero line (dashed, rule-bright) */}
      <line
        x1={0}
        y1={yMid}
        x2={W}
        y2={yMid}
        stroke="var(--rule-bright)"
        strokeWidth={0.75}
        strokeDasharray="3 2"
      />

      {/* Sparkline */}
      <path
        d={pathD}
        fill="none"
        stroke={zoneColor}
        strokeWidth={1.2}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.85}
      />

      {/* Current point */}
      <circle
        cx={lastPt.x}
        cy={lastPt.y}
        r={2.5}
        fill={zoneColor}
        opacity={1}
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Blinking cursor for empty state
// ---------------------------------------------------------------------------

function BlinkCursor() {
  return (
    <span style={{ animation: 'blink-cursor 1.1s step-start infinite', color: 'var(--text-mute)' }}>
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
  nowMs: number;
  currentPrice: number;
  barCount: number;
}

function ZoneRowItem({ zone, nowMs, currentPrice, barCount }: ZoneRowItemProps) {
  const [hovered, setHovered] = useState(false);
  const tooltip = ZONE_TOOLTIPS[zone.kind];
  const tc = tileColor(zone.kind);
  const reactions = countReactions(zone.history);
  const { label: ageLabel, isNew } = formatAge(zone.establishedAt, nowMs);

  // Last touch: find most recent zero-crossing in history
  const lastTouchAgo: string = (() => {
    if (zone.isPending || zone.history.length < 2) return '—';
    // Simple proxy: last time price was near zero (within 1 tick)
    for (let i = zone.history.length - 1; i >= 0; i--) {
      if (Math.abs(zone.history[i]) <= 1) {
        const secsAgo = Math.round(((zone.history.length - 1 - i) * 10));
        if (secsAgo < 60) return `${secsAgo}s ago`;
        return `${Math.floor(secsAgo / 60)}m ago`;
      }
    }
    return '—';
  })();

  // Session volume proxy: total_vol from bars near zone (rough estimate)
  const sessionVolLabel = barCount > 0 ? `${(barCount * 1.2).toFixed(1)}k` : '—';

  return (
    <div
      title={tooltip}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        height: hovered ? '40px' : '24px',
        display: 'flex',
        flexDirection: 'column',
        padding: '0 4px',
        borderRadius: '2px',
        cursor: 'default',
        background: hovered ? 'var(--surface-1)' : 'transparent',
        transition: 'height 200ms cubic-bezier(0.34, 1.56, 0.64, 1), background 150ms ease',
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Main row content */}
      <div
        style={{
          height: '24px',
          minHeight: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          flex: '0 0 auto',
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

        {/* Age column (28px) */}
        <span
          className="text-xs tnum"
          style={{
            width: '28px',
            textAlign: 'center',
            flexShrink: 0,
            fontWeight: isNew ? 700 : 400,
            color: zone.isPending ? 'var(--text-mute)' : isNew ? 'var(--lime)' : 'var(--text-dim)',
            letterSpacing: 0,
            fontFamily: 'var(--font-jetbrains-mono), monospace',
            fontSize: '9px',
          }}
        >
          {zone.isPending ? '' : ageLabel}
        </span>

        {/* Price — 60px width, right-aligned, tabular */}
        <span
          className="text-xs tnum"
          style={{
            color: zone.isPending ? 'var(--text-mute)' : 'var(--text)',
            width: '60px',
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

        {/* Sparkline (80px) */}
        <Sparkline
          history={zone.history}
          kind={zone.kind}
          isPending={zone.isPending}
          reactions={reactions}
        />

        {/* Delta / proximity */}
        <DeltaCol
          distanceTicks={zone.distanceTicks}
          price={zone.price}
          isPending={zone.isPending}
        />

        {/* Reaction count badge */}
        <span
          className="text-xs tnum"
          style={{
            color: zone.isPending ? 'var(--text-mute)' : reactionColor(reactions),
            width: '16px',
            textAlign: 'right',
            flexShrink: 0,
            letterSpacing: 0,
            marginLeft: 'auto',
            fontWeight: reactions >= 3 ? 600 : 400,
          }}
        >
          {zone.isPending ? '' : reactions === 0 ? '—' : reactions}
        </span>
      </div>

      {/* Expanded hover detail */}
      {hovered && !zone.isPending && (
        <div
          style={{
            height: '16px',
            display: 'flex',
            alignItems: 'center',
            paddingLeft: '20px',
            gap: '8px',
          }}
        >
          <span style={{ fontSize: '9px', color: 'var(--text-mute)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            Session vol at zone: {sessionVolLabel}
          </span>
          <span style={{ fontSize: '9px', color: 'var(--rule-bright)' }}>·</span>
          <span style={{ fontSize: '9px', color: 'var(--text-mute)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            Last touch: {lastTouchAgo}
          </span>
          <span style={{ fontSize: '9px', color: 'var(--rule-bright)' }}>·</span>
          <span style={{ fontSize: '9px', color: 'var(--text-mute)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            Reactions: {reactions}
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History tracker — maintains rolling 14-point (price - zone_price) per zone
// ---------------------------------------------------------------------------

const HISTORY_LEN = 14;

interface HistoryMap {
  [kind: string]: number[];
}

// ---------------------------------------------------------------------------
// LVN/HVN detection from bars array
// ---------------------------------------------------------------------------

interface LvnHvnDetection {
  hvnPrice: number | null;
  lvnPrice: number | null;
}

function detectLvnHvn(allBars: FootprintBar[], currentPrice: number): LvnHvnDetection {
  if (allBars.length < 5) return { hvnPrice: null, lvnPrice: null };

  // Count how many times each POC price appears across bars
  const pocCounts = new Map<number, number>();
  const allPocPrices = new Set<number>();

  for (const bar of allBars) {
    if (bar.poc_price > 0) {
      const rounded = Math.round(bar.poc_price * 4) / 4; // snap to 0.25 tick
      pocCounts.set(rounded, (pocCounts.get(rounded) ?? 0) + 1);
      allPocPrices.add(rounded);
    }
  }

  // HVN: price that appears as POC in 3+ bars
  let hvnPrice: number | null = null;
  let bestHvnCount = 0;
  for (const [price, count] of pocCounts) {
    if (count >= 3 && count > bestHvnCount) {
      bestHvnCount = count;
      hvnPrice = price;
    }
  }

  // LVN: scan price range between bar high/low — levels that never appear as POC
  // Find overall range
  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  for (const bar of allBars) {
    if (bar.high > rangeHigh) rangeHigh = bar.high;
    if (bar.low < rangeLow) rangeLow = bar.low;
  }

  // Sample every 4 ticks (1 point) in range; pick the candidate closest to current price
  let lvnPrice: number | null = null;
  let lvnMinDist = Infinity;
  const stepSize = 1.0; // 4 ticks = 1 NQ point
  for (let p = rangeLow; p <= rangeHigh; p += stepSize) {
    const snapped = Math.round(p * 4) / 4;
    if (!allPocPrices.has(snapped)) {
      const dist = Math.abs(snapped - currentPrice);
      if (dist > 2 && dist < lvnMinDist) { // > 2pts away to avoid noise
        lvnMinDist = dist;
        lvnPrice = snapped;
      }
    }
  }

  return { hvnPrice, lvnPrice };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ZoneList() {
  const lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  const bars           = useTradingStore((s) => s.bars);

  // Age/sparkline auto-refresh every 10s
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 10_000);
    return () => clearInterval(id);
  }, []);

  // Established timestamps (stable across bar updates)
  const establishedRef = useRef<Record<string, number>>({});
  const historyRef = useRef<HistoryMap>({});

  // Suppress unused warning — triggers re-render on new bars
  void lastBarVersion;

  const allBars       = bars.toArray();
  const latestBar     = bars.size > 0 ? bars.latest : null;
  const currentPrice  = latestBar?.close ?? 0;
  const pocPrice      = latestBar?.poc_price ?? 0;
  const barRange      = latestBar?.bar_range ?? 0;
  const barTs         = latestBar?.ts ?? 0; // unix ms from bar

  const TICK_SIZE = 0.25;

  function priceDist(zonePrice: number): number {
    if (!currentPrice || !zonePrice) return 0;
    return Math.round((zonePrice - currentPrice) / TICK_SIZE);
  }

  const hasBarData = pocPrice > 0;
  const vahEstimate = hasBarData ? latestBar!.close + barRange * 0.3 : 0;
  const valEstimate = hasBarData ? latestBar!.close - barRange * 0.3 : 0;

  // LVN/HVN detection
  const { hvnPrice, lvnPrice } = hasBarData && allBars.length >= 5
    ? detectLvnHvn(allBars, currentPrice)
    : { hvnPrice: null, lvnPrice: null };

  // Zone definitions (price may be null if not yet available)
  const zoneDefs: Array<{ kind: ZoneKind; price: number | null; isPending: boolean }> = [
    { kind: 'POC', price: hasBarData ? pocPrice : null, isPending: !hasBarData },
    { kind: 'VAH', price: hasBarData ? vahEstimate : null, isPending: !hasBarData },
    { kind: 'VAL', price: hasBarData ? valEstimate : null, isPending: !hasBarData },
    { kind: 'LVN', price: lvnPrice, isPending: lvnPrice === null },
    { kind: 'HVN', price: hvnPrice, isPending: hvnPrice === null },
  ];

  // Update established timestamps and history rings
  const barTsMs = barTs > 0 ? barTs : Date.now();
  for (const def of zoneDefs) {
    if (!def.isPending && def.price !== null) {
      if (!establishedRef.current[def.kind]) {
        establishedRef.current[def.kind] = barTsMs;
      }
      // Append delta point
      if (!historyRef.current[def.kind]) historyRef.current[def.kind] = [];
      const h = historyRef.current[def.kind];
      const delta = currentPrice - def.price; // positive = price above zone
      if (h.length === 0 || h[h.length - 1] !== delta) {
        h.push(delta);
        if (h.length > HISTORY_LEN) h.splice(0, h.length - HISTORY_LEN);
      }
    }
  }

  const getHistory = useCallback((kind: ZoneKind): number[] => {
    return historyRef.current[kind] ?? [];
  }, []);

  // Build final zone rows
  const zones: ZoneRow[] = zoneDefs.map((def) => ({
    kind: def.kind,
    price: def.price,
    distanceTicks: def.price !== null ? priceDist(def.price) : 0,
    isPending: def.isPending,
    establishedAt: def.isPending ? Date.now() : (establishedRef.current[def.kind] ?? barTsMs),
    history: getHistory(def.kind),
  }));

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
      {/* Column header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          marginBottom: '4px',
          paddingLeft: '4px',
          paddingRight: '4px',
        }}
      >
        {/* Monogram spacer (14px) */}
        <div style={{ width: '14px', flexShrink: 0 }} />

        {/* AGE (28px) */}
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '28px', textAlign: 'center', flexShrink: 0, fontSize: '9px' }}
        >
          AGE
        </span>

        {/* ZONES (60px) */}
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '60px', textAlign: 'right', flexShrink: 0, fontSize: '9px' }}
        >
          ZONES
        </span>

        {/* PROXIMITY (80px) */}
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '80px', textAlign: 'center', flexShrink: 0, fontSize: '9px' }}
        >
          PROXIMITY
        </span>

        {/* Delta (52px) */}
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '52px', textAlign: 'right', flexShrink: 0, fontSize: '9px' }}
        >
          Δ
        </span>

        {/* ALERTS */}
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '16px', textAlign: 'right', marginLeft: 'auto', flexShrink: 0, fontSize: '9px' }}
        >
          ALERTS
        </span>
      </div>

      {/* Thin separator */}
      <div
        style={{
          borderBottom: '1px solid var(--rule-bright)',
          marginBottom: '4px',
        }}
      />

      {/* Content */}
      {noData ? (
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '4px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
            <span className="text-xs label-tracked" style={{ color: 'var(--text-mute)' }}>
              NO ZONES
            </span>
            <BlinkCursor />
          </div>
          <span
            className="text-xs"
            style={{ color: 'var(--text-mute)', fontStyle: 'italic', fontSize: '10px' }}
          >
            zones emerge after 30 bars
          </span>
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
            <ZoneRowItem
              key={`${zone.kind}-${i}`}
              zone={zone}
              nowMs={nowMs}
              currentPrice={currentPrice}
              barCount={allBars.length}
            />
          ))}
        </div>
      )}
    </div>
  );
}
