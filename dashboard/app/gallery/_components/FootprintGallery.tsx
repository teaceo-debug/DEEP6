import Link from 'next/link';
import type { CSSProperties } from 'react';

type VariantId = 'minimal' | 'zone-first' | 'signal-first' | 'analytica' | 'hybrid';

type Cell = {
  bid: number;
  ask: number;
  poc?: boolean;
  askImbalance?: boolean;
  bidImbalance?: boolean;
  absorption?: boolean;
  trigger?: boolean;
};

type PriceRow = {
  price: number;
  note?: string;
  band?: 'resistance' | 'value' | 'support';
  cells: Cell[];
};

type Variant = {
  id: VariantId;
  rank: string;
  name: string;
  tagline: string;
  thesis: string;
  bestFor: string;
  strengths: string[];
  risks: string[];
  callout: string;
  accent: string;
  zoneOpacity: number;
  neutralText: string;
  chrome: string;
  surface: string;
  panel: string;
  signalMode: 'muted' | 'balanced' | 'loud';
  contextMode: 'compact' | 'detailed';
  densityMode: 'airy' | 'dense';
  rowBandsStrong?: boolean;
};

const BAR_LABELS = ['09:33', '09:34', '09:35', '09:36'];
const BAR_STATES = ['Context', 'Setup', 'Armed', 'Trigger'];
const BAR_DELTAS = [-82, 36, 128, 244];
const DECISION_STEPS = [
  'Location: responsive absorption shelf below VWAP',
  'Evidence: stacked bid absorption + ask imbalance ladder',
  'Trigger: accept above 19,487.50 with follow-through delta',
  'Fail: lose 19,486.75 on heavy sell response',
];

const PRICE_ROWS: PriceRow[] = [
  {
    price: 19488.5,
    band: 'resistance',
    note: 'Overhead reaction band',
    cells: [
      { bid: 102, ask: 28, bidImbalance: true },
      { bid: 88, ask: 41 },
      { bid: 75, ask: 68 },
      { bid: 60, ask: 92, askImbalance: true },
    ],
  },
  {
    price: 19488.25,
    band: 'resistance',
    cells: [
      { bid: 118, ask: 36, bidImbalance: true },
      { bid: 95, ask: 48 },
      { bid: 74, ask: 86 },
      { bid: 52, ask: 108, askImbalance: true },
    ],
  },
  {
    price: 19488,
    note: 'Control / POC',
    cells: [
      { bid: 140, ask: 62, poc: true },
      { bid: 116, ask: 82, poc: true },
      { bid: 94, ask: 124, poc: true },
      { bid: 84, ask: 146, poc: true },
    ],
  },
  {
    price: 19487.75,
    band: 'value',
    cells: [
      { bid: 92, ask: 74 },
      { bid: 84, ask: 98 },
      { bid: 66, ask: 132, askImbalance: true },
      { bid: 58, ask: 154, askImbalance: true },
    ],
  },
  {
    price: 19487.5,
    band: 'value',
    note: 'Acceptance trigger',
    cells: [
      { bid: 84, ask: 66 },
      { bid: 74, ask: 112, absorption: true },
      { bid: 52, ask: 162, askImbalance: true },
      { bid: 46, ask: 188, askImbalance: true, trigger: true },
    ],
  },
  {
    price: 19487.25,
    band: 'support',
    note: 'Absorption shelf',
    cells: [
      { bid: 126, ask: 58, absorption: true },
      { bid: 148, ask: 72, absorption: true },
      { bid: 164, ask: 88, absorption: true },
      { bid: 118, ask: 94, absorption: true },
    ],
  },
  {
    price: 19487,
    band: 'support',
    cells: [
      { bid: 132, ask: 54, absorption: true },
      { bid: 156, ask: 70, absorption: true },
      { bid: 148, ask: 76, absorption: true },
      { bid: 112, ask: 82 },
    ],
  },
  {
    price: 19486.75,
    note: 'Risk line / fail below',
    cells: [
      { bid: 98, ask: 42, bidImbalance: true },
      { bid: 114, ask: 50 },
      { bid: 106, ask: 52 },
      { bid: 94, ask: 48 },
    ],
  },
];

export const VARIANTS: Variant[] = [
  {
    id: 'minimal',
    rank: 'V1',
    name: 'Institutional Minimal',
    tagline: 'Quiet tape, loud location.',
    thesis: 'The footprint stays mostly grayscale so your eye goes to price location, POC, and only the true decision rows.',
    bestFor: 'disciplined intraday discretionary execution',
    strengths: ['Fast cognitive scan', 'Low eye fatigue', 'POC and trigger pop instantly'],
    risks: ['Least dramatic for training newer traders'],
    callout: 'Closest to a prop-desk read: no noise, just the rows that matter.',
    accent: '#9fe870',
    zoneOpacity: 0.18,
    neutralText: '#c9ced8',
    chrome: '#8891a7',
    surface: '#090b10',
    panel: '#0f131a',
    signalMode: 'muted',
    contextMode: 'compact',
    densityMode: 'airy',
  },
  {
    id: 'zone-first',
    rank: 'V2',
    name: 'Zone-First Pro',
    tagline: 'Map before microstructure.',
    thesis: 'Horizontal reaction bands carry the layout, so you know where price is responding before reading any footprint numbers.',
    bestFor: 'traders who anchor to support, resistance, and reaction shelves',
    strengths: ['Best level orientation', 'Strongest support/resistance memory', 'Excellent session context'],
    risks: ['Slightly less emphasis on raw delta intensity'],
    callout: 'If your trades start with where, this is the cleanest version.',
    accent: '#00d9ff',
    zoneOpacity: 0.34,
    neutralText: '#d7dee8',
    chrome: '#7fa4bb',
    surface: '#061018',
    panel: '#0b1821',
    signalMode: 'balanced',
    contextMode: 'detailed',
    densityMode: 'airy',
    rowBandsStrong: true,
  },
  {
    id: 'signal-first',
    rank: 'V3',
    name: 'Signal-First Scalper',
    tagline: 'Setup. Armed. Triggered.',
    thesis: 'The chart compresses the read path into a state machine, making it painfully obvious when a setup becomes tradeable.',
    bestFor: 'fast execution during active RTH rotation',
    strengths: ['Strongest trade-state clarity', 'Best for avoiding late entries', 'Most explicit trigger framing'],
    risks: ['Can feel aggressive if you prefer subtle visuals'],
    callout: 'This is the best version for fast yes/no decision-making.',
    accent: '#ffd60a',
    zoneOpacity: 0.22,
    neutralText: '#f1f5f9',
    chrome: '#facc15',
    surface: '#120b05',
    panel: '#1a1108',
    signalMode: 'loud',
    contextMode: 'compact',
    densityMode: 'dense',
  },
  {
    id: 'analytica',
    rank: 'V4',
    name: 'Analytica-Inspired Dense',
    tagline: 'High-density, restrained teal/orange grammar.',
    thesis: 'This leans closest to the public Futures Analytica feel: dark base, teal/orange event accents, and dense but structured information.',
    bestFor: 'traders who want maximum information per square inch',
    strengths: ['Most Futures Analytica-inspired', 'Strong event hierarchy', 'Professional market-ops feel'],
    risks: ['Denser than the other four concepts'],
    callout: 'The strongest candidate if you want “professional platform” energy.',
    accent: '#ff8a36',
    zoneOpacity: 0.26,
    neutralText: '#d8e4ec',
    chrome: '#9ccad6',
    surface: '#071218',
    panel: '#0b171d',
    signalMode: 'balanced',
    contextMode: 'detailed',
    densityMode: 'dense',
  },
  {
    id: 'hybrid',
    rank: 'V5',
    name: 'Executive Hybrid',
    tagline: 'Best-balanced candidate.',
    thesis: 'This combines restrained cells, clear zones, and a compact decision rail so you get context and trigger clarity without clutter.',
    bestFor: 'the likely production candidate if one design must satisfy everything',
    strengths: ['Best balance of clarity + detail', 'Readable all day', 'Easiest bridge to production'],
    risks: ['Not as specialized as the extremes'],
    callout: 'If we had to ship one after today, this is the safest starting point.',
    accent: '#5eead4',
    zoneOpacity: 0.26,
    neutralText: '#e5eef5',
    chrome: '#9cc8bf',
    surface: '#081011',
    panel: '#10191a',
    signalMode: 'balanced',
    contextMode: 'detailed',
    densityMode: 'airy',
  },
];

export function getVariantById(id: string): Variant | undefined {
  return VARIANTS.find((variant) => variant.id === id);
}

function alpha(hex: string, opacity: number): string {
  const safe = hex.replace('#', '');
  if (safe.length !== 6) return hex;
  const r = parseInt(safe.slice(0, 2), 16);
  const g = parseInt(safe.slice(2, 4), 16);
  const b = parseInt(safe.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

function formatPrice(price: number): string {
  return price.toFixed(2);
}

function formatSigned(value: number): string {
  return `${value > 0 ? '+' : ''}${value}`;
}

function bandColor(band: PriceRow['band'], variant: Variant): string {
  if (!band) return 'transparent';
  if (variant.id === 'zone-first') {
    if (band === 'resistance') return alpha('#ff8a36', 0.18 + variant.zoneOpacity * 0.2);
    if (band === 'value') return alpha('#00d9ff', 0.12 + variant.zoneOpacity * 0.2);
    return alpha('#4ade80', 0.14 + variant.zoneOpacity * 0.2);
  }
  if (band === 'resistance') return alpha('#ff8a36', variant.zoneOpacity * 0.65);
  if (band === 'value') return alpha(variant.accent, variant.zoneOpacity * 0.55);
  return alpha('#22c55e', variant.zoneOpacity * 0.6);
}

function cellBackground(cell: Cell, variant: Variant): string {
  if (cell.trigger) return 'linear-gradient(135deg, rgba(163,255,0,0.32), rgba(0,217,255,0.18))';
  if (cell.poc) return alpha('#ffd60a', variant.id === 'minimal' ? 0.24 : 0.3);
  if (cell.absorption) return alpha(variant.id === 'analytica' ? '#00d9ff' : '#5eead4', variant.id === 'signal-first' ? 0.24 : 0.18);
  if (cell.askImbalance) return alpha(variant.id === 'analytica' ? '#00d9ff' : '#4ade80', variant.id === 'signal-first' ? 0.3 : 0.2);
  if (cell.bidImbalance) return alpha(variant.id === 'analytica' ? '#ff8a36' : '#fb7185', variant.id === 'signal-first' ? 0.28 : 0.18);
  if (variant.id === 'analytica') return 'rgba(148, 163, 184, 0.05)';
  if (variant.id === 'signal-first') return 'rgba(255,255,255,0.04)';
  return 'rgba(255,255,255,0.03)';
}

function cellBorder(cell: Cell, variant: Variant): string {
  if (cell.trigger) return alpha('#a3ff00', 0.95);
  if (cell.poc) return alpha('#ffd60a', 0.9);
  if (cell.askImbalance) return alpha(variant.id === 'analytica' ? '#00d9ff' : '#4ade80', 0.8);
  if (cell.bidImbalance) return alpha(variant.id === 'analytica' ? '#ff8a36' : '#fb7185', 0.72);
  if (cell.absorption) return alpha('#5eead4', 0.6);
  return 'rgba(255,255,255,0.06)';
}

function textColor(cell: Cell, variant: Variant): string {
  if (cell.trigger || cell.poc) return '#081018';
  if (cell.askImbalance) return variant.id === 'analytica' ? '#c6fbff' : '#d9ffe6';
  if (cell.bidImbalance) return variant.id === 'analytica' ? '#ffe1cf' : '#ffd8e1';
  if (cell.absorption) return '#d7fffb';
  return variant.neutralText;
}

function pillStyle(active: boolean, color: string, loud: boolean): CSSProperties {
  return {
    padding: loud ? '6px 8px' : '4px 8px',
    borderRadius: 999,
    border: `1px solid ${active ? alpha(color, 0.95) : 'rgba(255,255,255,0.08)'}`,
    background: active ? alpha(color, loud ? 0.24 : 0.14) : 'rgba(255,255,255,0.02)',
    color: active ? '#f8fafc' : '#8e9baa',
    fontSize: loud ? 10 : 9,
    textTransform: 'uppercase',
    letterSpacing: '0.12em',
    fontWeight: 700,
    textAlign: 'center',
  };
}

function variantDecisionTone(variant: Variant): { label: string; color: string } {
  switch (variant.id) {
    case 'minimal':
      return { label: 'Wait for acceptance above 19,487.50', color: '#9fe870' };
    case 'zone-first':
      return { label: 'Long bias while support shelf holds', color: '#00d9ff' };
    case 'signal-first':
      return { label: 'TRIGGER LONG on hold above 19,487.50', color: '#ffd60a' };
    case 'analytica':
      return { label: 'Responsive buy ladder active', color: '#ff8a36' };
    default:
      return { label: 'Balanced long thesis, shelf still valid', color: '#5eead4' };
  }
}

function PriceRowLabel({ row }: { row: PriceRow }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        paddingRight: 10,
        borderRight: '1px solid rgba(255,255,255,0.08)',
        color: row.note ? '#f8fafc' : '#93a4b8',
        fontSize: 12,
        fontWeight: row.note ? 700 : 500,
        letterSpacing: row.note ? '0.04em' : '0.02em',
      }}
    >
      {formatPrice(row.price)}
    </div>
  );
}

function FootprintCell({ cell, variant }: { cell: Cell; variant: Variant }) {
  return (
    <div
      style={{
        minHeight: variant.densityMode === 'dense' ? 38 : 42,
        borderRadius: 10,
        border: `1px solid ${cellBorder(cell, variant)}`,
        background: cellBackground(cell, variant),
        color: textColor(cell, variant),
        padding: variant.densityMode === 'dense' ? '5px 6px' : '7px 8px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        boxShadow: cell.trigger ? `0 0 0 1px ${alpha('#a3ff00', 0.24)}, 0 12px 30px rgba(163,255,0,0.10)` : 'none',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: variant.densityMode === 'dense' ? 11 : 12, fontWeight: 700 }}>
        <span>{cell.bid}</span>
        <span>{cell.ask}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 9, color: cell.trigger || cell.poc ? '#081018' : '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        <span>{cell.bidImbalance ? 'BID' : cell.absorption ? 'ABS' : ' '}</span>
        <span>{cell.askImbalance ? 'ASK' : cell.trigger ? 'GO' : cell.poc ? 'POC' : ' '}</span>
      </div>
    </div>
  );
}

export function FootprintPreview({ variant, expanded = false }: { variant: Variant; expanded?: boolean }) {
  const tone = variantDecisionTone(variant);
  const loud = variant.signalMode === 'loud';

  return (
    <div
      style={{
        borderRadius: expanded ? 28 : 22,
        border: `1px solid ${alpha(variant.accent, 0.28)}`,
        background: `linear-gradient(180deg, ${alpha(variant.surface, 0.98)}, ${alpha(variant.panel, 0.98)})`,
        overflow: 'hidden',
        boxShadow: `0 24px 60px ${alpha('#000000', 0.42)}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: expanded ? '18px 22px' : '14px 16px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          background: 'rgba(255,255,255,0.02)',
        }}
      >
        <div>
          <div style={{ fontSize: expanded ? 12 : 11, color: variant.chrome, textTransform: 'uppercase', letterSpacing: '0.16em', fontWeight: 700 }}>
            NQ · RTH · responsive buy setup
          </div>
          <div style={{ marginTop: 6, fontSize: expanded ? 24 : 18, color: '#f8fafc', fontWeight: 700 }}>
            19,487.50 trigger shelf
          </div>
        </div>
        <div
          style={{
            padding: expanded ? '10px 14px' : '8px 10px',
            borderRadius: 12,
            border: `1px solid ${alpha(tone.color, 0.72)}`,
            background: alpha(tone.color, 0.14),
            color: '#f8fafc',
            fontSize: expanded ? 12 : 10,
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            fontWeight: 800,
            maxWidth: expanded ? 320 : 220,
            textAlign: 'right',
          }}
        >
          {tone.label}
        </div>
      </div>

      <div style={{ padding: expanded ? 22 : variant.densityMode === 'dense' ? 14 : 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: expanded ? '108px repeat(4, minmax(0, 1fr)) 240px' : '86px repeat(4, minmax(0, 1fr)) 176px', gap: expanded ? 14 : 10, alignItems: 'stretch' }}>
          <div />
          {BAR_LABELS.map((label, index) => (
            <div key={label} style={{ display: 'grid', gap: 6 }}>
              <div style={{ fontSize: expanded ? 11 : 10, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.14em', fontWeight: 700 }}>
                {label}
              </div>
              <div style={pillStyle(true, index === 3 ? tone.color : variant.accent, loud && index >= 1)}>{BAR_STATES[index]}</div>
            </div>
          ))}
          <div style={{ fontSize: expanded ? 11 : 10, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.14em', fontWeight: 700 }}>Decision rail</div>

          {PRICE_ROWS.map((row) => (
            <div key={`${variant.id}-${row.price}`} style={{ display: 'contents' }}>
              <PriceRowLabel row={row} />
              {row.cells.map((cell, index) => {
                const rowBand = variant.rowBandsStrong ? bandColor(row.band, variant) : alpha(bandColor(row.band, variant), 0.7);
                return (
                  <div
                    key={`${variant.id}-${row.price}-${index}`}
                    style={{
                      padding: expanded ? 6 : 4,
                      borderRadius: 12,
                      background: row.band ? rowBand : 'transparent',
                      outline: row.note && index === 3 ? `1px solid ${alpha(variant.accent, 0.34)}` : 'none',
                    }}
                  >
                    <FootprintCell cell={cell} variant={variant} />
                  </div>
                );
              })}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  borderRadius: 14,
                  padding: expanded ? '0 16px' : '0 12px',
                  background: row.note ? alpha(variant.accent, 0.12) : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${row.note ? alpha(variant.accent, 0.34) : 'rgba(255,255,255,0.05)'}`,
                  color: row.note ? '#f8fafc' : '#7c8ea2',
                  fontSize: expanded ? 12 : row.note ? 11 : 10,
                  lineHeight: 1.4,
                  fontWeight: row.note ? 700 : 500,
                }}
              >
                {row.note ?? ' '}
              </div>
            </div>
          ))}

          <div style={{ fontSize: expanded ? 11 : 10, color: '#7c8ea2', textTransform: 'uppercase', letterSpacing: '0.14em', fontWeight: 700 }}>Delta</div>
          {BAR_DELTAS.map((delta, index) => (
            <div
              key={`${variant.id}-delta-${index}`}
              style={{
                padding: expanded ? '14px 16px' : '10px 12px',
                borderRadius: 12,
                border: `1px solid ${alpha(delta > 0 ? '#4ade80' : '#fb7185', 0.26)}`,
                background: alpha(delta > 0 ? '#4ade80' : '#fb7185', 0.1),
                color: delta > 0 ? '#d9ffe6' : '#ffd9df',
                fontSize: expanded ? 14 : 12,
                fontWeight: 800,
                textAlign: 'center',
              }}
            >
              {formatSigned(delta)}
            </div>
          ))}
          <div
            style={{
              borderRadius: 14,
              padding: expanded ? '14px 16px' : '12px 14px',
              background: 'rgba(255,255,255,0.025)',
              border: `1px solid ${alpha(variant.accent, 0.18)}`,
              display: 'grid',
              gap: 8,
            }}
          >
            {DECISION_STEPS.slice(0, variant.contextMode === 'detailed' ? 4 : 2).map((item) => (
              <div key={`${variant.id}-${item}`} style={{ fontSize: expanded ? 12 : 10, color: '#d6e0ea', lineHeight: 1.45 }}>
                {item}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionHeading({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ fontSize: 12, color: '#8ea1b4', letterSpacing: '0.24em', textTransform: 'uppercase', fontWeight: 700 }}>{eyebrow}</div>
      <div style={{ fontSize: 40, lineHeight: 1.02, fontWeight: 800, letterSpacing: '-0.04em', color: '#f8fafc', maxWidth: 780 }}>{title}</div>
      <div style={{ maxWidth: 920, fontSize: 16, lineHeight: 1.65, color: '#c4d0db' }}>{copy}</div>
    </div>
  );
}

function BulletList({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ fontSize: 11, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.18em', fontWeight: 700 }}>{title}</div>
      <div style={{ display: 'grid', gap: 8 }}>
        {items.map((item) => (
          <div key={item} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', color: '#dbe5ef', fontSize: 14, lineHeight: 1.5 }}>
            <span style={{ color: '#5eead4' }}>•</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function VariantCard({ variant }: { variant: Variant }) {
  return (
    <section
      id={variant.id}
      style={{
        borderRadius: 28,
        border: `1px solid ${alpha(variant.accent, 0.2)}`,
        background: `linear-gradient(180deg, ${alpha(variant.surface, 0.9)}, rgba(5,8,12,0.96))`,
        padding: 24,
        display: 'grid',
        gap: 22,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ padding: '7px 10px', borderRadius: 999, fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', fontWeight: 800, color: '#081018', background: variant.accent }}>
              {variant.rank}
            </span>
            <span style={{ fontSize: 11, color: '#8ea1b4', letterSpacing: '0.18em', textTransform: 'uppercase', fontWeight: 700 }}>{variant.tagline}</span>
          </div>
          <div style={{ fontSize: 30, lineHeight: 1.05, color: '#f8fafc', fontWeight: 800, letterSpacing: '-0.03em' }}>{variant.name}</div>
          <div style={{ fontSize: 15, lineHeight: 1.6, color: '#c4d0db', maxWidth: 880 }}>{variant.thesis}</div>
        </div>
        <div style={{ minWidth: 220, borderRadius: 18, padding: '14px 16px', border: `1px solid ${alpha(variant.accent, 0.22)}`, background: alpha(variant.accent, 0.08), display: 'grid', gap: 8 }}>
          <div style={{ fontSize: 11, color: '#8ea1b4', letterSpacing: '0.16em', textTransform: 'uppercase', fontWeight: 700 }}>Best for</div>
          <div style={{ fontSize: 15, color: '#f8fafc', lineHeight: 1.5, fontWeight: 700 }}>{variant.bestFor}</div>
          <div style={{ fontSize: 13, color: '#d0dbe6', lineHeight: 1.55 }}>{variant.callout}</div>
          <Link href={`/gallery/${variant.id}`} style={{ marginTop: 8, padding: '10px 12px', borderRadius: 12, border: `1px solid ${alpha(variant.accent, 0.3)}`, background: alpha(variant.accent, 0.12), color: '#f8fafc', textDecoration: 'none', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', fontWeight: 800, textAlign: 'center' }}>
            Open full render
          </Link>
        </div>
      </div>

      <FootprintPreview variant={variant} />

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 18 }}>
        <BulletList title="Why this version works" items={variant.strengths} />
        <BulletList title="Watch-outs" items={variant.risks} />
      </div>
    </section>
  );
}

export function GalleryOverviewPage() {
  return (
    <main style={{ minHeight: '100vh', background: 'radial-gradient(circle at top, rgba(0,217,255,0.06), transparent 22%), #020406', color: '#f8fafc' }}>
      <div style={{ maxWidth: 1480, margin: '0 auto', padding: '36px 24px 80px', display: 'grid', gap: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {['Future Analytica public design study', 'Five DEEP6 variants', 'Localhost review board'].map((item) => (
              <span key={item} style={{ padding: '8px 12px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)', color: '#c6d3df', fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700 }}>
                {item}
              </span>
            ))}
          </div>
          <Link href="/" style={{ padding: '10px 14px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.08)', color: '#f8fafc', textDecoration: 'none', fontSize: 12, letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 700, background: 'rgba(255,255,255,0.03)' }}>
            Back to dashboard
          </Link>
        </div>

        <SectionHeading
          eyebrow="Footprint design lab"
          title="Five professional footprint chart directions for DEEP6"
          copy="I turned the Futures Analytica public design research into five DEEP6 concept directions that all solve the same trading problem in different ways: make location, aggression, absorption, and trigger timing readable during live market hours without forcing you to decode visual noise. Each card below uses the same market scenario, so you are comparing visual grammar, not different trade setups."
        />

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
          {[
            'Dark low-glare base with selective accents only',
            'Horizontal reaction bands carry location memory',
            'Signal hierarchy: setup → armed → trigger',
            'Neutral numbers fade; decision rows stay bright',
            'Designed for fast intraday yes/no trade decisions',
          ].map((item) => (
            <div key={item} style={{ borderRadius: 18, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)', padding: '14px 16px', color: '#d1dde8', fontSize: 14, lineHeight: 1.5 }}>
              {item}
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gap: 24 }}>
          {VARIANTS.map((variant) => (
            <VariantCard key={variant.id} variant={variant} />
          ))}
        </div>
      </div>
    </main>
  );
}

export function VariantFullPage({ variant }: { variant: Variant }) {
  return (
    <main style={{ minHeight: '100vh', background: 'radial-gradient(circle at top, rgba(0,217,255,0.06), transparent 24%), #020406', color: '#f8fafc' }}>
      <div style={{ maxWidth: 1680, margin: '0 auto', padding: '28px 20px 56px', display: 'grid', gap: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ padding: '8px 12px', borderRadius: 999, background: variant.accent, color: '#081018', fontWeight: 800, letterSpacing: '0.16em', textTransform: 'uppercase', fontSize: 11 }}>{variant.rank}</span>
            <span style={{ color: '#c8d5df', fontSize: 14 }}>{variant.name}</span>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link href="/gallery" style={{ padding: '10px 14px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.08)', color: '#f8fafc', textDecoration: 'none', fontSize: 12, letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 700, background: 'rgba(255,255,255,0.03)' }}>
              Back to all versions
            </Link>
            <Link href="/" style={{ padding: '10px 14px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.08)', color: '#f8fafc', textDecoration: 'none', fontSize: 12, letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 700, background: 'rgba(255,255,255,0.03)' }}>
              Dashboard
            </Link>
          </div>
        </div>

        <section style={{ borderRadius: 28, border: `1px solid ${alpha(variant.accent, 0.24)}`, background: `linear-gradient(180deg, ${alpha(variant.surface, 0.86)}, rgba(3,5,8,0.98))`, padding: 24, display: 'grid', gap: 18 }}>
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 12, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.22em', fontWeight: 700 }}>Full local render</div>
            <div style={{ fontSize: 42, lineHeight: 1.02, fontWeight: 800, letterSpacing: '-0.04em', color: '#f8fafc' }}>{variant.name}</div>
            <div style={{ maxWidth: 1100, fontSize: 16, lineHeight: 1.65, color: '#c5d2dd' }}>{variant.thesis}</div>
          </div>

          <FootprintPreview variant={variant} expanded />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
            <div style={{ borderRadius: 18, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', padding: '16px 18px', display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 11, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.16em', fontWeight: 700 }}>Best for</div>
              <div style={{ fontSize: 15, color: '#f8fafc', lineHeight: 1.5, fontWeight: 700 }}>{variant.bestFor}</div>
            </div>
            <div style={{ borderRadius: 18, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', padding: '16px 18px', display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 11, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.16em', fontWeight: 700 }}>Strengths</div>
              {variant.strengths.map((item) => (
                <div key={item} style={{ fontSize: 14, color: '#dbe5ef', lineHeight: 1.45 }}>• {item}</div>
              ))}
            </div>
            <div style={{ borderRadius: 18, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', padding: '16px 18px', display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 11, color: '#8ea1b4', textTransform: 'uppercase', letterSpacing: '0.16em', fontWeight: 700 }}>Trade note</div>
              <div style={{ fontSize: 14, color: '#dbe5ef', lineHeight: 1.55 }}>{variant.callout}</div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
