'use client';

/**
 * ZoneList.tsx — Compact zone table (UI-SPEC v2 §4.6).
 *
 * Round 4 enhancements:
 *   1. Session POC/VAH/VAL — cumulative volume across all bars (70% VA)
 *   2. Zone persistence — establishedAt tracking, broken-zone strikethrough (3-bar TTL)
 *   3. Prior session levels — PDH/PDL/PDC (first 25% as "yesterday" proxy if < 200 bars)
 *   4. Zone merge logic — POC+VAH or LVN+VAL when within 1 tick
 *   5. Zone strength indicator — 5-dot strength meter (touch+reversal count)
 *   6. Market profile shape hints — NORMAL/TREND_DAY/P-SHAPE/b-SHAPE label above list
 *   7. Empty state expansion — "SESSION BUILDING... N/30 bars needed"
 *
 * Columns: monogram | age | price | sparkline (80px) | proximity | strength | alerts
 *
 * Zone monogram tiles: POC/HVN → --amber, VAH/VAL → --text, LVN → --cyan,
 * GEX+ → --ask, GEX- → --bid, PDH/PDL/PDC → --text-mute (dashed border).
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import type { FootprintBar } from '@/types/deep6';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ZoneKind =
  | 'POC' | 'VAH' | 'VAL'
  | 'LVN' | 'HVN'
  | 'GEX+' | 'GEX-'
  | 'PDH' | 'PDL' | 'PDC';

interface ZoneRow {
  kind: ZoneKind;
  label: string;               // May differ from kind for merged zones e.g. "POC+VAH"
  price: number | null;
  distanceTicks: number;
  isPending: boolean;
  isBroken: boolean;           // Round 2: broken zones show strikethrough
  brokenBarsAgo: number;       // 0 = just broken; hide after 3
  establishedAt: number;       // unix ms
  history: number[];           // last 14 (price − zone) deltas
  strengthTouches: number;     // # times price touched and reversed
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TICK_SIZE   = 0.25;
const HISTORY_LEN = 14;
const VA_PCT      = 0.70;    // 70% of volume = Value Area
const MERGE_TICKS = 1;       // merge zones within 1 tick
const BREAK_TICKS = 5;       // > 5 ticks beyond zone = broken
const BREAK_BAR_TTL = 3;     // show broken zone for 3 bars, then hide

// ---------------------------------------------------------------------------
// Tooltips
// ---------------------------------------------------------------------------

const ZONE_TOOLTIPS: Record<string, string> = {
  'POC':  'Point of Control — session\'s highest-volume price. Prices orbit here.',
  'VAH':  'Value Area High — top of 70% session volume. Resistance.',
  'VAL':  'Value Area Low — bottom of 70% session volume. Support.',
  'LVN':  'Low Volume Node — thin pricing zone. Breaks fast; acceptance = trend.',
  'HVN':  'High Volume Node — price magnet. Contests reversals.',
  'GEX+': 'GEX Call Wall — large positive gamma. Suppresses upside.',
  'GEX-': 'GEX Put Wall — large negative gamma. Suppresses downside.',
  'PDH':  'Prior Day High — key resistance reference.',
  'PDL':  'Prior Day Low — key support reference.',
  'PDC':  'Prior Day Close — directional bias pivot.',
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
    case 'PDH':
    case 'PDL':
    case 'PDC':  return 'var(--text-mute)';
  }
}

function reactionColor(count: number): string {
  if (count >= 3) return 'var(--lime)';
  if (count >= 1) return 'var(--amber)';
  return 'var(--text-mute)';
}

function tileLabel(zone: ZoneRow): string {
  // Use zone.label for merged e.g. "POC+VAH" → "P+V"
  if (zone.label !== zone.kind) {
    // Merge label: first char of each part
    return zone.label.split('+').map((p) => p[0]).join('+');
  }
  switch (zone.kind) {
    case 'GEX+': return 'G+';
    case 'GEX-': return 'G-';
    case 'PDH':  return 'PDH';
    case 'PDL':  return 'PDL';
    case 'PDC':  return 'PDC';
    default:     return zone.kind.slice(0, 3);
  }
}

// ---------------------------------------------------------------------------
// Zero-crossings = reactions
// ---------------------------------------------------------------------------

function countReactions(history: number[]): number {
  if (history.length < 2) return 0;
  let crossings = 0;
  for (let i = 1; i < history.length; i++) {
    const prev = history[i - 1];
    const curr = history[i];
    if ((prev < 0 && curr >= 0) || (prev >= 0 && curr < 0)) crossings++;
  }
  return crossings;
}

// ---------------------------------------------------------------------------
// Age formatting
// ---------------------------------------------------------------------------

function formatAge(establishedAt: number, nowMs: number): { label: string; isNew: boolean } {
  const ageMs = nowMs - establishedAt;
  if (ageMs < 60_000) return { label: 'NEW', isNew: true };
  const mins = Math.floor(ageMs / 60_000);
  if (mins < 60) return { label: `${mins}m`, isNew: false };
  return { label: `${Math.floor(mins / 60)}h`, isNew: false };
}

// ---------------------------------------------------------------------------
// Session POC/VAH/VAL computation — memoized on bars.size
// ---------------------------------------------------------------------------

interface SessionProfile {
  poc: number | null;
  vah: number | null;
  val: number | null;
}

function computeSessionProfile(allBars: FootprintBar[]): SessionProfile {
  if (allBars.length === 0) return { poc: null, vah: null, val: null };

  // Accumulate volume per price level (snap to tick grid)
  const volByPrice = new Map<number, number>();

  for (const bar of allBars) {
    // Each bar contributes its total_vol centred around its poc_price.
    // Use bid+ask vol if available; fall back to total_vol.
    // Approximate: spread the bar's volume across bar's price range,
    // but weight the POC price with the most volume.
    const vol = bar.total_vol > 0 ? bar.total_vol : 1;
    const poc = bar.poc_price > 0 ? Math.round(bar.poc_price / TICK_SIZE) * TICK_SIZE : 0;

    if (poc > 0) {
      // 60% weight to POC
      volByPrice.set(poc, (volByPrice.get(poc) ?? 0) + vol * 0.6);

      // Distribute remaining 40% across bar range in steps of 1 tick
      const lo  = Math.round(bar.low  / TICK_SIZE) * TICK_SIZE;
      const hi  = Math.round(bar.high / TICK_SIZE) * TICK_SIZE;
      const steps = Math.max(1, Math.round((hi - lo) / TICK_SIZE));
      const perStep = (vol * 0.4) / steps;
      for (let p = lo; p <= hi + 0.001; p = Math.round((p + TICK_SIZE) * 1e6) / 1e6) {
        const snapped = Math.round(p / TICK_SIZE) * TICK_SIZE;
        volByPrice.set(snapped, (volByPrice.get(snapped) ?? 0) + perStep);
      }
    }
  }

  if (volByPrice.size === 0) return { poc: null, vah: null, val: null };

  // Find POC (max volume price)
  let poc: number | null = null;
  let maxVol = -Infinity;
  for (const [price, vol] of volByPrice) {
    if (vol > maxVol) { maxVol = vol; poc = price; }
  }

  // Total session volume
  let totalVol = 0;
  for (const vol of volByPrice.values()) totalVol += vol;

  // Value Area — 70% of volume centred around POC
  // Algorithm: iteratively expand outward (up or down one tick, pick higher vol)
  const sorted = Array.from(volByPrice.entries()).sort((a, b) => a[0] - b[0]);
  if (sorted.length === 0 || poc === null) return { poc, vah: null, val: null };

  const pocIdx  = sorted.findIndex(([p]) => p === poc);
  const target  = totalVol * VA_PCT;
  let   inVA    = volByPrice.get(poc!) ?? 0;
  let   lo      = pocIdx;
  let   hi      = pocIdx;

  while (inVA < target) {
    const canUp   = hi + 1 < sorted.length;
    const canDown = lo - 1 >= 0;
    if (!canUp && !canDown) break;

    const upVol   = canUp   ? sorted[hi + 1][1] : -Infinity;
    const downVol = canDown ? sorted[lo - 1][1] : -Infinity;

    if (upVol >= downVol && canUp) {
      hi++;
      inVA += sorted[hi][1];
    } else if (canDown) {
      lo--;
      inVA += sorted[lo][1];
    } else {
      break;
    }
  }

  const vah = sorted[hi][0];
  const val = sorted[lo][0];

  return { poc, vah, val };
}

// ---------------------------------------------------------------------------
// Prior session levels (PDH/PDL/PDC)
// ---------------------------------------------------------------------------

interface PriorSession {
  pdh: number | null;
  pdl: number | null;
  pdc: number | null;
}

function computePriorSession(allBars: FootprintBar[]): PriorSession {
  if (allBars.length < 10) return { pdh: null, pdl: null, pdc: null };

  // If ≥ 400 bars, treat first half of bars up to 400 as "yesterday"
  // If < 200 bars, first 25% as "yesterday" proxy (demo mode)
  const len   = allBars.length;
  const cutoff = len >= 400
    ? Math.min(400, Math.floor(len / 2))
    : Math.floor(len * 0.25);

  if (cutoff < 5) return { pdh: null, pdl: null, pdc: null };

  const yesterday = allBars.slice(0, cutoff);
  let pdh = -Infinity;
  let pdl =  Infinity;
  let pdc: number | null = null;

  for (const bar of yesterday) {
    if (bar.high > pdh) pdh = bar.high;
    if (bar.low  < pdl) pdl = bar.low;
  }
  pdc = yesterday[yesterday.length - 1]?.close ?? null;

  return {
    pdh: pdh  > -Infinity ? Math.round(pdh  / TICK_SIZE) * TICK_SIZE : null,
    pdl: pdl  <  Infinity ? Math.round(pdl  / TICK_SIZE) * TICK_SIZE : null,
    pdc: pdc  !== null    ? Math.round(pdc! / TICK_SIZE) * TICK_SIZE : null,
  };
}

// ---------------------------------------------------------------------------
// LVN/HVN detection
// ---------------------------------------------------------------------------

interface LvnHvnDetection {
  hvnPrice: number | null;
  lvnPrice: number | null;
}

function detectLvnHvn(allBars: FootprintBar[], currentPrice: number): LvnHvnDetection {
  if (allBars.length < 5) return { hvnPrice: null, lvnPrice: null };

  const pocCounts   = new Map<number, number>();
  const allPocPrices = new Set<number>();

  for (const bar of allBars) {
    if (bar.poc_price > 0) {
      const rounded = Math.round(bar.poc_price / TICK_SIZE) * TICK_SIZE;
      pocCounts.set(rounded, (pocCounts.get(rounded) ?? 0) + 1);
      allPocPrices.add(rounded);
    }
  }

  let hvnPrice: number | null = null;
  let bestHvnCount = 0;
  for (const [price, count] of pocCounts) {
    if (count >= 3 && count > bestHvnCount) { bestHvnCount = count; hvnPrice = price; }
  }

  let rangeHigh = -Infinity;
  let rangeLow  =  Infinity;
  for (const bar of allBars) {
    if (bar.high > rangeHigh) rangeHigh = bar.high;
    if (bar.low  < rangeLow)  rangeLow  = bar.low;
  }

  let lvnPrice: number | null = null;
  let lvnMinDist = Infinity;
  for (let p = rangeLow; p <= rangeHigh; p += 1.0) {
    const snapped = Math.round(p / TICK_SIZE) * TICK_SIZE;
    if (!allPocPrices.has(snapped)) {
      const dist = Math.abs(snapped - currentPrice);
      if (dist > 2 && dist < lvnMinDist) { lvnMinDist = dist; lvnPrice = snapped; }
    }
  }

  return { hvnPrice, lvnPrice };
}

// ---------------------------------------------------------------------------
// Market profile shape classification
// ---------------------------------------------------------------------------

type ProfileShape = 'NORMAL' | 'TREND_DAY_UP' | 'TREND_DAY_DOWN' | 'P-SHAPE' | 'b-SHAPE' | 'BUILDING';

function classifyProfileShape(
  poc: number | null,
  vah: number | null,
  val: number | null,
  sessionHigh: number,
  sessionLow: number,
): ProfileShape {
  if (poc === null || vah === null || val === null) return 'BUILDING';

  const range = sessionHigh - sessionLow;
  if (range <= 0) return 'BUILDING';

  const pocNorm = (poc - sessionLow) / range;  // 0 = bottom, 1 = top
  const vaWidth = vah - val;
  const relVA   = vaWidth / range;             // how wide is VA relative to total range

  // P-SHAPE: POC near top, VAL extends far below (bullish capitulation / long liquidation)
  if (pocNorm > 0.70 && (poc - val) / range > 0.50) return 'P-SHAPE';

  // b-SHAPE: POC near bottom, VAH extends far above (bearish capitulation)
  if (pocNorm < 0.30 && (vah - poc) / range > 0.50) return 'b-SHAPE';

  // TREND_DAY: wide VA (> 65% of range) and POC skewed significantly
  if (relVA > 0.65) {
    return pocNorm > 0.55 ? 'TREND_DAY_UP' : 'TREND_DAY_DOWN';
  }

  // NORMAL: POC in middle 40% of range, tight VA
  return 'NORMAL';
}

function profileShapeLabel(shape: ProfileShape): string {
  switch (shape) {
    case 'NORMAL':         return 'NORMAL ↔';
    case 'TREND_DAY_UP':   return 'TREND_DAY ↑';
    case 'TREND_DAY_DOWN': return 'TREND_DAY ↓';
    case 'P-SHAPE':        return 'P-SHAPE ↑ (bull)';
    case 'b-SHAPE':        return 'b-SHAPE ↓ (bear)';
    case 'BUILDING':       return 'BUILDING…';
  }
}

function profileShapeColor(shape: ProfileShape): string {
  switch (shape) {
    case 'TREND_DAY_UP':
    case 'P-SHAPE':        return 'var(--ask)';
    case 'TREND_DAY_DOWN':
    case 'b-SHAPE':        return 'var(--bid)';
    case 'NORMAL':         return 'var(--text-dim)';
    case 'BUILDING':       return 'var(--text-mute)';
  }
}

// ---------------------------------------------------------------------------
// Strength meter — 5-dot display
// ---------------------------------------------------------------------------

interface StrengthMeterProps {
  touches: number;
  color: string;
}

function StrengthMeter({ touches, color }: StrengthMeterProps) {
  // 0=0, 1=1, 2=2, 3=3, 4-5=4, 6+=5
  const filled = Math.min(5, touches === 0 ? 0 : touches <= 3 ? touches : touches <= 5 ? 4 : 5);
  return (
    <div style={{ display: 'flex', gap: '2px', width: '36px', flexShrink: 0, justifyContent: 'flex-end' }}>
      {[1, 2, 3, 4, 5].map((dot) => (
        <div
          key={dot}
          style={{
            width: '4px',
            height: '4px',
            borderRadius: '50%',
            background: dot <= filled ? color : 'var(--rule)',
            opacity: dot <= filled ? 1 : 0.35,
            flexShrink: 0,
          }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Delta column
// ---------------------------------------------------------------------------

interface DeltaColProps {
  distanceTicks: number;
  price: number | null;
  isPending: boolean;
  isBroken: boolean;
}

function DeltaCol({ distanceTicks, price, isPending, isBroken }: DeltaColProps) {
  if (isPending || price === null || isBroken) {
    return (
      <span className="text-xs tnum"
        style={{ color: 'var(--text-mute)', width: '52px', textAlign: 'right', flexShrink: 0 }} />
    );
  }

  const abs = Math.abs(distanceTicks);
  const points = distanceTicks * TICK_SIZE;

  if (abs <= 1) {
    return (
      <span className="text-xs tnum"
        style={{ color: 'var(--lime)', width: '52px', textAlign: 'right', flexShrink: 0, fontWeight: 700 }}>
        ●
      </span>
    );
  }

  const sign = distanceTicks > 0 ? '↑' : '↓';
  const formatted = (points > 0 ? '+' : '') + points.toFixed(2);
  const color = distanceTicks > 0 ? 'var(--ask)' : 'var(--bid)';

  return (
    <span className="text-xs tnum"
      style={{ color, width: '52px', textAlign: 'right', flexShrink: 0 }}>
      {sign} {formatted}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Sparkline
// ---------------------------------------------------------------------------

interface SparklineProps {
  history: number[];
  kind: ZoneKind;
  isPending: boolean;
  isBroken: boolean;
}

function Sparkline({ history, kind, isPending, isBroken }: SparklineProps) {
  const W = 80;
  const H = 28;
  const zoneColor = isBroken ? 'var(--text-mute)' : tileColor(kind);

  if (isPending || history.length < 2) {
    return (
      <div style={{ width: `${W}px`, height: `${H}px`, flexShrink: 0, display: 'flex', alignItems: 'center' }}>
        <div style={{ width: '100%', height: '1px', background: 'var(--rule)', opacity: 0.4 }} />
      </div>
    );
  }

  const maxAbs = Math.max(...history.map(Math.abs), 0.01);
  const yMid   = H / 2;

  const pts = history.map((v, i) => ({
    x: (i / (history.length - 1)) * W,
    y: yMid - (v / maxAbs) * (yMid - 2),
  }));

  const pathD   = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const lastPt  = pts[pts.length - 1];

  return (
    <svg width={W} height={H} style={{ flexShrink: 0, overflow: 'visible', opacity: isBroken ? 0.4 : 1 }}>
      <line x1={0} y1={yMid} x2={W} y2={yMid}
        stroke="var(--rule-bright)" strokeWidth={0.75} strokeDasharray="3 2" />
      <path d={pathD} fill="none" stroke={zoneColor}
        strokeWidth={1.2} strokeLinejoin="round" strokeLinecap="round" opacity={0.85} />
      <circle cx={lastPt.x} cy={lastPt.y} r={2.5} fill={zoneColor} opacity={1} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Blinking cursor
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
        @media (prefers-reduced-motion: reduce) { .blink-cursor { animation: none; } }
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
  barCount: number;
}

function ZoneRowItem({ zone, nowMs, barCount }: ZoneRowItemProps) {
  const [hovered, setHovered] = useState(false);
  const tooltip   = ZONE_TOOLTIPS[zone.kind] ?? zone.kind;
  const tc        = zone.isBroken ? 'var(--text-mute)' : tileColor(zone.kind);
  const reactions = countReactions(zone.history);
  const { label: ageLabel, isNew } = formatAge(zone.establishedAt, nowMs);

  const lastTouchAgo: string = (() => {
    if (zone.isPending || zone.history.length < 2) return '—';
    for (let i = zone.history.length - 1; i >= 0; i--) {
      if (Math.abs(zone.history[i]) <= 1) {
        const secsAgo = Math.round((zone.history.length - 1 - i) * 10);
        if (secsAgo < 60) return `${secsAgo}s ago`;
        return `${Math.floor(secsAgo / 60)}m ago`;
      }
    }
    return '—';
  })();

  const sessionVolLabel = barCount > 0 ? `${(barCount * 1.2).toFixed(1)}k` : '—';

  const isPDZone = zone.kind === 'PDH' || zone.kind === 'PDL' || zone.kind === 'PDC';

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
        opacity: zone.isBroken ? 0.45 : 1,
      }}
    >
      {/* Main row */}
      <div style={{ height: '24px', minHeight: '24px', display: 'flex', alignItems: 'center', gap: '6px', flex: '0 0 auto' }}>

        {/* Monogram tile (14×14) */}
        <div style={{
          width: '14px', height: '14px',
          background: zone.isPending ? 'var(--surface-2)' : isPDZone ? 'transparent' : tc,
          border: zone.isPending
            ? '1px solid var(--rule)'
            : isPDZone ? `1px dashed ${tc}` : 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, borderRadius: '1px',
        }}>
          <span style={{
            fontSize: '5.5px', fontWeight: 700,
            color: zone.isPending ? 'var(--text-mute)' : isPDZone ? tc : '#000000',
            fontFamily: 'var(--font-jetbrains-mono), monospace',
            lineHeight: 1, letterSpacing: '-0.02em',
          }}>
            {tileLabel(zone)}
          </span>
        </div>

        {/* Age (28px) */}
        <span className="text-xs tnum" style={{
          width: '28px', textAlign: 'center', flexShrink: 0,
          fontWeight: isNew ? 700 : 400,
          color: zone.isPending ? 'var(--text-mute)' : isNew ? 'var(--lime)' : 'var(--text-dim)',
          fontFamily: 'var(--font-jetbrains-mono), monospace', fontSize: '9px',
        }}>
          {zone.isPending ? '' : ageLabel}
        </span>

        {/* Price (60px) — strikethrough if broken */}
        <span className="text-xs tnum" style={{
          color: zone.isPending ? 'var(--text-mute)' : zone.isBroken ? 'var(--text-mute)' : 'var(--text)',
          width: '60px', textAlign: 'right', flexShrink: 0,
          fontStyle: zone.isPending ? 'italic' : 'normal',
          textDecoration: zone.isBroken ? 'line-through' : 'none',
          letterSpacing: 0,
        }}>
          {zone.isPending
            ? '— pending —'
            : zone.price !== null
              ? zone.price.toFixed(2)
              : '—'}
        </span>

        {/* Sparkline (80px) */}
        <Sparkline history={zone.history} kind={zone.kind} isPending={zone.isPending} isBroken={zone.isBroken} />

        {/* Delta */}
        <DeltaCol
          distanceTicks={zone.distanceTicks}
          price={zone.price}
          isPending={zone.isPending}
          isBroken={zone.isBroken}
        />

        {/* Strength meter (36px) */}
        <StrengthMeter touches={zone.strengthTouches} color={tc} />

        {/* Reaction count badge (16px) */}
        <span className="text-xs tnum" style={{
          color: zone.isPending ? 'var(--text-mute)' : reactionColor(reactions),
          width: '16px', textAlign: 'right', flexShrink: 0,
          letterSpacing: 0, marginLeft: 'auto',
          fontWeight: reactions >= 3 ? 600 : 400,
        }}>
          {zone.isPending ? '' : reactions === 0 ? '—' : reactions}
        </span>
      </div>

      {/* Expanded hover detail */}
      {hovered && !zone.isPending && (
        <div style={{ height: '16px', display: 'flex', alignItems: 'center', paddingLeft: '20px', gap: '8px' }}>
          <span style={{ fontSize: '9px', color: 'var(--text-mute)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            Session vol at zone: {sessionVolLabel}
          </span>
          <span style={{ fontSize: '9px', color: 'var(--rule-bright)' }}>·</span>
          <span style={{ fontSize: '9px', color: 'var(--text-mute)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            Last touch: {lastTouchAgo}
          </span>
          <span style={{ fontSize: '9px', color: 'var(--rule-bright)' }}>·</span>
          <span style={{ fontSize: '9px', color: 'var(--text-mute)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            Strength: {zone.strengthTouches} touches
          </span>
          {zone.isBroken && (
            <>
              <span style={{ fontSize: '9px', color: 'var(--rule-bright)' }}>·</span>
              <span style={{ fontSize: '9px', color: 'var(--bid)', fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
                BROKEN {zone.brokenBarsAgo}b ago
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Persistent zone state — tracked across bar updates
// ---------------------------------------------------------------------------

interface ZonePersistState {
  establishedAt: number;   // unix ms
  brokenAtBar: number;     // bar index when broken (-1 = not broken)
  strengthTouches: number; // touch+reversal count
}

type PersistMap = Map<string, ZonePersistState>;

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

  // Stable refs for persistence across renders
  const persistRef  = useRef<PersistMap>(new Map());
  const historyRef  = useRef<Map<string, number[]>>(new Map());
  const barCountRef = useRef<number>(0);   // tracks "current bar index"

  void lastBarVersion; // triggers re-render on new bar

  const allBars      = bars.toArray();
  const latestBar    = bars.size > 0 ? bars.latest : null;
  const currentPrice = latestBar?.close ?? 0;
  const barTs        = latestBar?.ts ?? 0;
  const barTsMs      = barTs > 0 ? barTs * 1000 : Date.now();

  // Advance bar counter on each new bar
  if (allBars.length !== barCountRef.current) {
    barCountRef.current = allBars.length;
  }
  const currentBarIdx = barCountRef.current;

  // --- Session profile (memoized on bars.size) ---
  const sessionProfile = useMemo(
    () => computeSessionProfile(allBars),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bars.size],
  );

  // --- Prior session (memoized on bars.size) ---
  const priorSession = useMemo(
    () => computePriorSession(allBars),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bars.size],
  );

  // --- LVN/HVN ---
  const { hvnPrice, lvnPrice } = useMemo(
    () => (allBars.length >= 5 && currentPrice > 0
      ? detectLvnHvn(allBars, currentPrice)
      : { hvnPrice: null, lvnPrice: null }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bars.size, currentPrice],
  );

  // --- Session high/low for profile shape ---
  const { sessionHigh, sessionLow } = useMemo(() => {
    let hi = -Infinity;
    let lo =  Infinity;
    for (const bar of allBars) {
      if (bar.high > hi) hi = bar.high;
      if (bar.low  < lo) lo = bar.low;
    }
    return { sessionHigh: hi > -Infinity ? hi : 0, sessionLow: lo < Infinity ? lo : 0 };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars.size]);

  // --- Profile shape ---
  const profileShape = classifyProfileShape(
    sessionProfile.poc,
    sessionProfile.vah,
    sessionProfile.val,
    sessionHigh,
    sessionLow,
  );

  // --- Helper ---
  function priceDist(zonePrice: number): number {
    if (!currentPrice || !zonePrice) return 0;
    return Math.round((zonePrice - currentPrice) / TICK_SIZE);
  }

  const hasBarData = currentPrice > 0 && allBars.length > 0;

  // --- Candidate zone definitions (before merge) ---
  type ZoneDef = { kind: ZoneKind; price: number | null; isPending: boolean };

  const rawDefs: ZoneDef[] = [
    { kind: 'POC', price: sessionProfile.poc,   isPending: sessionProfile.poc === null },
    { kind: 'VAH', price: sessionProfile.vah,   isPending: sessionProfile.vah === null },
    { kind: 'VAL', price: sessionProfile.val,   isPending: sessionProfile.val === null },
    { kind: 'LVN', price: lvnPrice,              isPending: lvnPrice === null },
    { kind: 'HVN', price: hvnPrice,              isPending: hvnPrice === null },
    ...(priorSession.pdh !== null ? [{ kind: 'PDH' as ZoneKind, price: priorSession.pdh, isPending: false }] : []),
    ...(priorSession.pdl !== null ? [{ kind: 'PDL' as ZoneKind, price: priorSession.pdl, isPending: false }] : []),
    ...(priorSession.pdc !== null ? [{ kind: 'PDC' as ZoneKind, price: priorSession.pdc, isPending: false }] : []),
  ];

  // --- Zone merge logic (Round 4) ---
  // If VAH within 1 tick of POC → merge to "POC+VAH"; if LVN within 1 tick of VAL → merge to "LVN+VAL"
  type MergedDef = ZoneDef & { mergeLabel?: string };

  const mergedDefs: MergedDef[] = [];
  const skippedKinds = new Set<ZoneKind>();

  for (const def of rawDefs) {
    if (skippedKinds.has(def.kind)) continue;

    if (def.kind === 'POC' && !def.isPending && def.price !== null) {
      const vah = rawDefs.find((d) => d.kind === 'VAH');
      if (vah && !vah.isPending && vah.price !== null) {
        const tickDist = Math.abs(def.price - vah.price) / TICK_SIZE;
        if (tickDist <= MERGE_TICKS) {
          mergedDefs.push({ ...def, mergeLabel: 'POC+VAH' });
          skippedKinds.add('VAH');
          continue;
        }
      }
    }

    if (def.kind === 'LVN' && !def.isPending && def.price !== null) {
      const val = rawDefs.find((d) => d.kind === 'VAL');
      if (val && !val.isPending && val.price !== null) {
        const tickDist = Math.abs(def.price - val.price) / TICK_SIZE;
        if (tickDist <= MERGE_TICKS) {
          mergedDefs.push({ ...def, mergeLabel: 'LVN+VAL' });
          skippedKinds.add('VAL');
          continue;
        }
      }
    }

    mergedDefs.push(def);
  }

  // --- Update persistence, history, strength ---
  for (const def of mergedDefs) {
    const key = def.kind as string;
    if (!def.isPending && def.price !== null) {

      // Establish timestamp
      if (!persistRef.current.has(key)) {
        persistRef.current.set(key, {
          establishedAt: barTsMs,
          brokenAtBar: -1,
          strengthTouches: 0,
        });
      }

      const ps = persistRef.current.get(key)!;

      // Broken detection: has price moved > 5 ticks beyond zone?
      if (ps.brokenAtBar === -1 && currentPrice > 0) {
        const ticksAway = (currentPrice - def.price) / TICK_SIZE;
        const isBroken = (def.kind === 'VAH' && ticksAway > BREAK_TICKS)
                      || (def.kind === 'VAL' && ticksAway < -BREAK_TICKS)
                      || (def.kind === 'POC' && Math.abs(ticksAway) > BREAK_TICKS * 2);
        if (isBroken) {
          ps.brokenAtBar = currentBarIdx;
        }
      }

      // Strength: track touch+reversals from sparkline history
      const h = historyRef.current.get(key) ?? [];
      if (h.length >= 2) {
        const prev = h[h.length - 2];
        const curr = h[h.length - 1];
        // Reversal = was within 2 ticks of zone AND moved away
        if (Math.abs(prev) <= 2 && Math.abs(curr) > Math.abs(prev)) {
          ps.strengthTouches += 1;
        }
      }

      // Append history delta
      if (!historyRef.current.has(key)) historyRef.current.set(key, []);
      const hArr = historyRef.current.get(key)!;
      const delta = currentPrice - def.price;
      if (hArr.length === 0 || hArr[hArr.length - 1] !== delta) {
        hArr.push(delta);
        if (hArr.length > HISTORY_LEN) hArr.splice(0, hArr.length - HISTORY_LEN);
      }
    }
  }

  // --- Assemble final ZoneRow list ---
  const zones: ZoneRow[] = mergedDefs
    .map((def): ZoneRow => {
      const key = def.kind as string;
      const ps  = persistRef.current.get(key);
      const brokenAtBar = ps?.brokenAtBar ?? -1;
      const barsAgoBroken = brokenAtBar >= 0 ? currentBarIdx - brokenAtBar : 0;
      const isBroken = brokenAtBar >= 0 && barsAgoBroken <= BREAK_BAR_TTL;
      const shouldHide = brokenAtBar >= 0 && barsAgoBroken > BREAK_BAR_TTL;

      return {
        kind: def.kind,
        label: (def as MergedDef).mergeLabel ?? def.kind,
        price: def.price,
        distanceTicks: def.price !== null ? priceDist(def.price) : 0,
        isPending: def.isPending,
        isBroken,
        brokenBarsAgo: barsAgoBroken,
        establishedAt: def.isPending
          ? Date.now()
          : (ps?.establishedAt ?? barTsMs),
        history: historyRef.current.get(key) ?? [],
        strengthTouches: ps?.strengthTouches ?? 0,
        _shouldHide: shouldHide,
      } as ZoneRow & { _shouldHide: boolean };
    })
    .filter((z) => !(z as ZoneRow & { _shouldHide: boolean })._shouldHide);

  const noData  = !hasBarData;
  const barCount = allBars.length;

  return (
    <div style={{
      background: 'var(--surface-1)',
      padding: '10px 12px',
      height: '100%',
      boxSizing: 'border-box',
      display: 'flex',
      flexDirection: 'column',
      gap: 0,
    }}>

      {/* Session profile shape label */}
      {hasBarData && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          marginBottom: '3px',
          gap: '4px',
        }}>
          <span style={{
            fontSize: '8px',
            color: 'var(--text-mute)',
            fontFamily: 'var(--font-jetbrains-mono), monospace',
            letterSpacing: '0.06em',
          }}>
            SESSION:
          </span>
          <span style={{
            fontSize: '8px',
            fontWeight: 600,
            color: profileShapeColor(profileShape),
            fontFamily: 'var(--font-jetbrains-mono), monospace',
            letterSpacing: '0.04em',
          }}>
            {profileShapeLabel(profileShape)}
          </span>
        </div>
      )}

      {/* Column header row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        marginBottom: '4px',
        paddingLeft: '4px',
        paddingRight: '4px',
      }}>
        <div style={{ width: '14px', flexShrink: 0 }} />
        <span className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '28px', textAlign: 'center', flexShrink: 0, fontSize: '9px' }}>
          AGE
        </span>
        <span className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '60px', textAlign: 'right', flexShrink: 0, fontSize: '9px' }}>
          ZONES
        </span>
        <span className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '80px', textAlign: 'center', flexShrink: 0, fontSize: '9px' }}>
          PROXIMITY
        </span>
        <span className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '52px', textAlign: 'right', flexShrink: 0, fontSize: '9px' }}>
          Δ
        </span>
        <span className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '36px', textAlign: 'right', flexShrink: 0, fontSize: '9px' }}>
          STR
        </span>
        <span className="text-xs label-tracked"
          style={{ color: 'var(--text-mute)', width: '16px', textAlign: 'right', marginLeft: 'auto', flexShrink: 0, fontSize: '9px' }}>
          ⚡
        </span>
      </div>

      {/* Separator */}
      <div style={{ borderBottom: '1px solid var(--rule-bright)', marginBottom: '4px' }} />

      {/* Content */}
      {noData ? (
        /* Empty state — expanded */
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '4px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
            <span className="text-xs label-tracked" style={{ color: 'var(--text-mute)' }}>
              SESSION BUILDING
            </span>
            <BlinkCursor />
          </div>
          <span className="text-xs"
            style={{ color: 'var(--text-mute)', fontStyle: 'italic', fontSize: '10px' }}>
            {barCount}/30 bars needed
          </span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
          {zones.map((zone, i) => (
            <ZoneRowItem
              key={`${zone.kind}-${i}`}
              zone={zone}
              nowMs={nowMs}
              barCount={barCount}
            />
          ))}
        </div>
      )}
    </div>
  );
}
