'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { HelpCircle } from 'lucide-react';
import { useTradingStore } from '@/store/tradingStore';
import { KeyboardHelp } from '@/components/common/KeyboardHelp';
import { DigitRoll, DeltaIndicator, useDeltaIndicator } from '@/lib/digit-roll';

/**
 * HeaderStrip — 44px terminal header per UI-SPEC §4.7
 *
 * Layout: DEEP6 ▸ NQ ▸ price delta [sparkline] │ E10 │ GEX │ clock │ [signals-per-min] B:/S: stats ● connection
 *
 * v2 enhancements:
 *  - Price sparkline: 60×18px SVG showing last 30 close prices inline after delta
 *  - Signals-per-minute: 10-bar mini chart (last 10 minutes) right side
 *  - Session stats: tabular-nums right-aligned, hover tooltip
 *  - Clock: HH:MM:SS.● ET with 1Hz pulsing fractional-second dot
 *  - Price flash: up tick = --ask, down tick = --bid, settle in 300ms via useRef guard
 *  - Connection dot: hover tooltip with connected/last-tick/pnl
 *  - E10/GEX labels: 0.08em letter-spacing, 11px, --text-mute
 *  - PipeSep: 16px tall, vertically centered
 *
 * v3 enhancements (digit-roll harmonization):
 *  - Price uses shared DigitRoll (spring-animated, tabular-nums) + DeltaIndicator (▲▼ 800ms)
 */

// ─── Price Sparkline ──────────────────────────────────────────────────────────

interface SparklineProps {
  prices: number[];
}

function PriceSparkline({ prices }: SparklineProps) {
  if (prices.length < 5) return null;

  const W = 60;
  const H = 18;
  const DOT_R = 1.5;

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  const scaleY = (v: number) => H - DOT_R - ((v - min) / range) * (H - DOT_R * 2);
  const scaleX = (i: number) => (i / (prices.length - 1)) * (W - DOT_R * 2) + DOT_R;

  const points = prices.map((p, i) => `${scaleX(i).toFixed(2)},${scaleY(p).toFixed(2)}`).join(' ');

  const first = prices[0];
  const last = prices[prices.length - 1];
  const diff = last - first;
  const lineColor =
    diff > 0 ? 'var(--ask)' : diff < 0 ? 'var(--bid)' : 'var(--text-mute)';

  const dotX = scaleX(prices.length - 1);
  const dotY = scaleY(last);

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, marginLeft: 5 }}
      aria-hidden
    >
      <polyline
        points={points}
        fill="none"
        stroke={lineColor}
        strokeWidth="1"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={dotX} cy={dotY} r={DOT_R} fill={lineColor} />
    </svg>
  );
}

// ─── Signals-per-Minute Bar Chart ─────────────────────────────────────────────

interface SignalBin {
  typeA: number;
  typeB: number;
  typeC: number;
  total: number;
}

interface SpmChartProps {
  bins: SignalBin[];
}

function SpmChart({ bins }: SpmChartProps) {
  const BAR_W = 2;
  const BAR_GAP = 1;
  const MAX_H = 12;
  const W = bins.length * (BAR_W + BAR_GAP) - BAR_GAP;
  const H = MAX_H;

  const maxTotal = Math.max(1, ...bins.map((b) => b.total));

  const hasAny = bins.some((b) => b.total > 0);

  if (!hasAny) {
    // Flat 1px lime line at bottom
    return (
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 }}
        aria-hidden
      >
        <line x1={0} y1={H - 0.5} x2={W} y2={H - 0.5} stroke="var(--lime, #84cc16)" strokeWidth="1" />
      </svg>
    );
  }

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 }}
      aria-hidden
    >
      {bins.map((bin, i) => {
        const x = i * (BAR_W + BAR_GAP);
        const barH = Math.max(1, (bin.total / maxTotal) * MAX_H);

        // Stacked: TYPE_A (lime) bottom, TYPE_B (amber) middle, TYPE_C (cyan) top
        const tA = bin.typeA / Math.max(1, bin.total);
        const tB = bin.typeB / Math.max(1, bin.total);
        const tC = bin.typeC / Math.max(1, bin.total);

        const hA = barH * tA;
        const hB = barH * tB;
        const hC = barH * tC;

        return (
          <g key={i}>
            {hA > 0 && (
              <rect
                x={x} y={H - hA}
                width={BAR_W} height={hA}
                fill="var(--lime, #84cc16)"
              />
            )}
            {hB > 0 && (
              <rect
                x={x} y={H - hA - hB}
                width={BAR_W} height={hB}
                fill="var(--amber, #f59e0b)"
              />
            )}
            {hC > 0 && (
              <rect
                x={x} y={H - hA - hB - hC}
                width={BAR_W} height={hC}
                fill="var(--cyan, #06b6d4)"
              />
            )}
            {bin.total === 0 && (
              <line
                x1={x} y1={H - 0.5} x2={x + BAR_W} y2={H - 0.5}
                stroke="var(--lime, #84cc16)" strokeWidth="1"
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ─── Connection Dot Tooltip ───────────────────────────────────────────────────

interface DotTooltipProps {
  connected: boolean;
  lastTickAgo: string;
  pnl: number;
  visible: boolean;
}

function DotTooltip({ connected, lastTickAgo, pnl, visible }: DotTooltipProps) {
  if (!visible) return null;
  const pnlStr = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
  return (
    <span
      style={{
        position: 'absolute',
        top: '36px',
        right: '16px',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: '11px',
        color: 'var(--text)',
        background: 'var(--surface-2)',
        padding: '4px 6px',
        borderRadius: '3px',
        border: '1px solid var(--rule)',
        whiteSpace: 'nowrap',
        pointerEvents: 'none',
        zIndex: 100,
        lineHeight: 1.4,
      }}
    >
      connected: {connected ? 'true' : 'false'} • last tick: {lastTickAgo} • pnl: {pnlStr}
    </span>
  );
}

// ─── Session Stats Tooltip ────────────────────────────────────────────────────

interface StatsTipProps {
  barCount: number;
  signalCount: number;
  sessionAge: string;
  visible: boolean;
}

function StatsTip({ barCount, signalCount, sessionAge, visible }: StatsTipProps) {
  if (!visible) return null;
  return (
    <span
      style={{
        position: 'absolute',
        top: '36px',
        right: '40px',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: '11px',
        color: 'var(--text)',
        background: 'var(--surface-2)',
        padding: '4px 6px',
        borderRadius: '3px',
        border: '1px solid var(--rule)',
        whiteSpace: 'nowrap',
        pointerEvents: 'none',
        zIndex: 100,
        lineHeight: 1.4,
      }}
    >
      {barCount} bars received • {signalCount} signals fired • session started {sessionAge}
    </span>
  );
}

// ─── PriceDisplay — animated digit-roll with delta indicator ─────────────────

interface PriceDisplayProps {
  price: number | null;
  priceColor: string;
  priceFlash: 'ask' | 'bid' | null;
}

/**
 * Renders the NQ price with spring-animated digit-roll (harmonized with Kronos/Pulse)
 * plus a brief ▲▼ delta arrow for 800ms after each price change.
 * Falls back to "—" when no price data yet.
 */
function PriceDisplay({ price, priceColor, priceFlash }: PriceDisplayProps) {
  const safePrice = price ?? 0;
  const delta = useDeltaIndicator(safePrice, 2);

  if (price === null) {
    return (
      <span className="text-md tnum" style={{ color: 'var(--text-mute)', marginRight: '6px' }}>
        —
      </span>
    );
  }

  return (
    <span
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        marginRight: '6px',
        paddingRight: delta.visible ? '44px' : undefined,
      }}
    >
      <DigitRoll
        value={safePrice}
        precision={2}
        className="text-md tnum"
        style={{
          color: priceColor,
          transition: priceFlash ? undefined : 'color 150ms ease-out',
        }}
      />
      <AnimatePresence>
        {delta.visible && (
          <DeltaIndicator key="price-delta" delta={delta} precision={2} fontSize={10} />
        )}
      </AnimatePresence>
    </span>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function HeaderStrip() {
  // Store selectors — READ ONLY, never mutate
  const score = useTradingStore((s) => s.score);
  const status = useTradingStore((s) => s.status);
  const lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  const lastSignalVersion = useTradingStore((s) => s.lastSignalVersion);
  void lastBarVersion;
  void lastSignalVersion;

  // ── Price + direction tracking ──
  const priceRef = useRef<number | null>(null);
  const [price, setPrice] = useState<number | null>(null);
  const [priceDelta, setPriceDelta] = useState<number>(0);
  const [priceFlash, setPriceFlash] = useState<'ask' | 'bid' | null>(null);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Sparkline prices (last 30 close prices) ──
  const [sparkPrices, setSparkPrices] = useState<number[]>([]);

  // ── Signals-per-minute bins ──
  const [spmBins, setSpmBins] = useState<SignalBin[]>(() =>
    Array.from({ length: 10 }, () => ({ typeA: 0, typeB: 0, typeC: 0, total: 0 }))
  );

  // ── Session stats ──
  const [barCount, setBarCount] = useState(0);
  const [signalCount, setSignalCount] = useState(0);
  const sessionStartRef = useRef<number>(Date.now());

  // ── Clock ──
  const [clockBase, setClockBase] = useState('--:--:-- ET');
  const [dotVisible, setDotVisible] = useState(false);

  // ── Tooltip state ──
  const [dotHovered, setDotHovered] = useState(false);
  const [statsHovered, setStatsHovered] = useState(false);
  const [sparkHovered, setSparkHovered] = useState(false);
  const [clockHovered, setClockHovered] = useState(false);
  const [spmHovered, setSpmHovered] = useState(false);

  // ── Keyboard help modal ──
  const [helpOpen, setHelpOpen] = useState(false);

  // Global `?` key opens/closes help modal
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === '?') {
        e.preventDefault();
        setHelpOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setHelpOpen(false);
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  // ── Update price + sparkline from latest bar ──
  useEffect(() => {
    const state = useTradingStore.getState();
    const latestBar = state.bars.latest;
    if (!latestBar) return;

    const newPrice = latestBar.close;
    // Guard: ignore NaN/Infinity prices — keep last known good price
    if (!Number.isFinite(newPrice)) return;

    const prev = priceRef.current;

    // Only flash if price actually changed (guards against remount)
    if (prev !== null && prev !== newPrice) {
      const delta = newPrice - prev;
      setPriceDelta(delta);
      const dir = delta > 0 ? 'ask' : 'bid';
      setPriceFlash(dir);
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      flashTimerRef.current = setTimeout(() => setPriceFlash(null), 300);
    }
    priceRef.current = newPrice;
    setPrice(newPrice);

    // Extract last 30 close prices — filter out non-finite values for sparkline
    const allBars = state.bars.toArray();
    const last30 = allBars.slice(-30).map((b) => b.close).filter(Number.isFinite);
    setSparkPrices(last30);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastBarVersion]);

  // ── Clock — ET (America/New_York) with pulsing dot ──
  useEffect(() => {
    function tick() {
      const now = new Date();
      const et = now.toLocaleTimeString('en-US', {
        timeZone: 'America/New_York',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
      setClockBase(`${et} ET`);
      // Pulse: dot visible for first 300ms of each second
      const ms = now.getMilliseconds();
      setDotVisible(ms < 300);
    }
    tick();
    // Tick every 100ms to catch the pulse window reliably
    const id = setInterval(tick, 100);
    return () => clearInterval(id);
  }, []);

  // ── Session stats + SPM bins — poll every 2s ──
  useEffect(() => {
    function sample() {
      const state = useTradingStore.getState();
      setBarCount(state.bars.size);
      setSignalCount(state.signals.size);

      // Compute signals-per-minute over last 10 minutes
      const nowSec = Date.now() / 1000;
      const bins: SignalBin[] = Array.from({ length: 10 }, () => ({
        typeA: 0, typeB: 0, typeC: 0, total: 0,
      }));

      const allSignals = state.signals.toArray();
      for (const sig of allSignals) {
        // Clamp future timestamps (clock skew) to 0 age before binning
        const ageMin = Math.max(0, nowSec - sig.ts) / 60;
        const binIdx = Math.floor(ageMin); // 0 = current minute, 9 = 9 min ago
        if (binIdx >= 0 && binIdx < 10) {
          bins[9 - binIdx].total++;
          if (sig.tier === 'TYPE_A') bins[9 - binIdx].typeA++;
          else if (sig.tier === 'TYPE_B') bins[9 - binIdx].typeB++;
          else if (sig.tier === 'TYPE_C') bins[9 - binIdx].typeC++;
        }
      }
      setSpmBins(bins);
    }
    sample();
    const id = setInterval(sample, 2000);
    return () => clearInterval(id);
  }, []);

  // ── Derived values ──

  // Price color — flash overrides, settles to --text
  const priceColor =
    priceFlash === 'ask'
      ? 'var(--ask)'
      : priceFlash === 'bid'
      ? 'var(--bid)'
      : 'var(--text)';

  const deltaIsPositive = priceDelta >= 0;
  const deltaSymbol = deltaIsPositive ? '▲' : '▼';
  const deltaColor = deltaIsPositive ? 'var(--ask)' : 'var(--bid)';

  const e10Color =
    score.kronosDirection === 'LONG'
      ? 'var(--ask)'
      : score.kronosDirection === 'SHORT'
      ? 'var(--bid)'
      : 'var(--text-mute)';

  const gexColor =
    score.gexRegime === 'POS_GAMMA'
      ? 'var(--ask)'
      : score.gexRegime === 'NEG_GAMMA'
      ? 'var(--bid)'
      : 'var(--text-mute)';

  // Connection dot
  let dotColor: string;
  let dotClass: string;
  let dotGlow: string;

  if (status.connected && !status.feedStale) {
    dotColor = 'var(--ask)';
    dotClass = 'dot-breathe-connected';
    dotGlow = '0 0 0 2px color-mix(in srgb, var(--ask) 30%, transparent)';
  } else if (status.feedStale) {
    dotColor = 'var(--amber)';
    dotClass = 'dot-breathe-stale';
    dotGlow = 'none';
  } else {
    dotColor = 'var(--bid)';
    dotClass = '';
    dotGlow = 'none';
  }

  // Last tick age for tooltip — clamp to 0 so future timestamps (clock skew) never show negative
  const lastTickAgo =
    status.lastTs > 0
      ? Math.max(0, Date.now() / 1000 - status.lastTs).toFixed(1) + 's ago'
      : 'n/a';

  // Session age
  const sessionAgeSec = Math.floor((Date.now() - sessionStartRef.current) / 1000);
  const sessionAgeStr =
    sessionAgeSec < 60
      ? `${sessionAgeSec}s ago`
      : `${Math.floor(sessionAgeSec / 60)}m ago`;

  // ── Sub-components (inline to avoid prop-drilling) ──

  const PipeSep = () => (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width: '1px',
        height: '16px',
        background: 'var(--rule)',
        flexShrink: 0,
        margin: '0 12px',
        alignSelf: 'center',
      }}
    />
  );

  const SectionPill = ({ children }: { children: React.ReactNode }) => {
    const [hovered, setHovered] = useState(false);
    return (
      <span
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '2px 6px',
          borderTop: hovered ? '1px solid var(--rule)' : '1px solid transparent',
          borderBottom: hovered ? '1px solid var(--rule)' : '1px solid transparent',
          borderRadius: 2,
          transition: 'border-color 120ms ease',
        }}
      >
        {children}
      </span>
    );
  };

  return (
    <>
      {/* Inline keyframes */}
      <style>{`
        @keyframes dot-breathe-connected {
          0%, 100% { opacity: 0.7; transform: scale(1.0); }
          50%       { opacity: 1.0; transform: scale(1.08); }
        }
        .dot-breathe-connected {
          animation: dot-breathe-connected 2s ease-in-out infinite;
        }
        @keyframes dot-breathe-stale {
          0%, 100% { opacity: 0.5; }
          50%       { opacity: 1.0; }
        }
        .dot-breathe-stale {
          animation: dot-breathe-stale 2s ease-in-out infinite;
        }
        @keyframes clock-dot-pulse {
          0%   { opacity: 1.0; }
          60%  { opacity: 0.15; }
          100% { opacity: 0.15; }
        }
        .clock-dot-pulse {
          animation: clock-dot-pulse 1s steps(1, end) infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .dot-breathe-connected,
          .dot-breathe-stale,
          .clock-dot-pulse {
            animation: none;
          }
        }
      `}</style>

      <header
        style={{
          height: '44px',
          background: 'var(--surface-1)',
          borderBottom: '1px solid var(--rule)',
          display: 'flex',
          alignItems: 'center',
          paddingLeft: '16px',
          paddingRight: '16px',
          gap: '0',
          flexShrink: 0,
          position: 'relative',
        }}
      >
        {/* DEEP6 ▸ NQ ▸ price delta [sparkline] */}
        <span className="text-md label-tracked" style={{ color: 'var(--text)' }}>
          DEEP6
        </span>

        <span
          style={{
            fontSize: '80%',
            color: 'var(--text-mute)',
            margin: '0 6px',
            lineHeight: 1,
            alignSelf: 'baseline',
            marginTop: 2,
          }}
        >
          ▸
        </span>

        <span className="text-md label-tracked" style={{ color: 'var(--text)' }}>
          NQ
        </span>

        <span
          style={{
            fontSize: '80%',
            color: 'var(--text-mute)',
            margin: '0 6px',
            lineHeight: 1,
            alignSelf: 'baseline',
            marginTop: 2,
          }}
        >
          ▸
        </span>

        {/* Price — spring digit-roll + ▲▼ delta indicator (800ms) */}
        <PriceDisplay price={price} priceColor={priceColor} priceFlash={priceFlash} />

        {/* Bar-to-bar delta — cumulative tick direction indicator */}
        {price !== null && priceDelta !== 0 ? (
          <span className="text-sm tnum" style={{ color: deltaColor }}>
            {deltaSymbol}{deltaIsPositive ? '+' : ''}
            {priceDelta.toFixed(2)}
          </span>
        ) : (
          <span style={{ minWidth: 52 }} />
        )}

        {/* Sparkline — inline after delta */}
        <span
          onMouseEnter={() => setSparkHovered(true)}
          onMouseLeave={() => setSparkHovered(false)}
          style={{ position: 'relative', display: 'inline-flex' }}
          title="Last 30 close prices."
        >
          <PriceSparkline prices={sparkPrices} />
          {sparkHovered && sparkPrices.length >= 5 && (
            <span style={{
              position: 'absolute',
              top: '100%',
              left: '50%',
              transform: 'translateX(-50%)',
              marginTop: 6,
              padding: '4px 8px',
              background: 'var(--surface-2)',
              border: '1px solid var(--rule-bright)',
              color: 'var(--text)',
              fontSize: 11,
              fontFamily: 'JetBrains Mono, monospace',
              whiteSpace: 'nowrap',
              zIndex: 100,
              pointerEvents: 'none',
            }}>
              Last 30 close prices.
            </span>
          )}
        </span>

        <PipeSep />

        {/* E10 section */}
        <SectionPill>
          <span
            style={{
              fontSize: '11px',
              letterSpacing: '0.08em',
              color: 'var(--text-mute)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            E10
          </span>
          <span
            style={{
              fontSize: '13px',
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
              color: 'var(--magenta)',
            }}
          >
            {score.kronosBias ? `${Math.round(score.kronosBias)}%` : '—'}
          </span>
          <span
            style={{
              fontSize: '13px',
              fontWeight: 600,
              letterSpacing: '0.04em',
              color: e10Color,
            }}
          >
            {score.kronosDirection || 'NEUTRAL'}
          </span>
        </SectionPill>

        <PipeSep />

        {/* GEX section */}
        <SectionPill>
          <span
            style={{
              fontSize: '11px',
              letterSpacing: '0.08em',
              color: 'var(--text-mute)',
            }}
          >
            GEX
          </span>
          <span
            style={{
              fontSize: '13px',
              fontWeight: 600,
              letterSpacing: '0.04em',
              color: gexColor,
            }}
          >
            {score.gexRegime || 'NEUTRAL'}
          </span>
        </SectionPill>

        <PipeSep />

        {/* Clock — HH:MM:SS.● ET, dot pulses 1Hz */}
        <span
          onMouseEnter={() => setClockHovered(true)}
          onMouseLeave={() => setClockHovered(false)}
          style={{ position: 'relative', display: 'inline-flex' }}
        >
          <SectionPill>
            <span
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '13px',
                fontVariantNumeric: 'tabular-nums',
                color: 'var(--text-dim)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              {clockBase.replace(' ET', '')}
              <span
                style={{
                  display: 'inline-block',
                  width: '4px',
                  height: '4px',
                  borderRadius: '50%',
                  background: 'var(--text-mute)',
                  opacity: dotVisible ? 1 : 0.15,
                  transition: 'opacity 80ms ease',
                  marginLeft: 1,
                  marginRight: 2,
                  flexShrink: 0,
                  alignSelf: 'center',
                }}
              />
              <span style={{ color: 'var(--text-dim)', fontSize: '11px', letterSpacing: '0.04em' }}>ET</span>
            </span>
          </SectionPill>
          {clockHovered && (
            <span style={{
              position: 'absolute',
              top: '100%',
              left: '50%',
              transform: 'translateX(-50%)',
              marginTop: 6,
              padding: '4px 8px',
              background: 'var(--surface-2)',
              border: '1px solid var(--rule-bright)',
              color: 'var(--text)',
              fontSize: 11,
              fontFamily: 'JetBrains Mono, monospace',
              whiteSpace: 'nowrap',
              zIndex: 100,
              pointerEvents: 'none',
            }}>
              New York market time.
            </span>
          )}
        </span>

        {/* Right side */}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <PipeSep />

          {/* Signals-per-minute chart */}
          <span
            onMouseEnter={() => setSpmHovered(true)}
            onMouseLeave={() => setSpmHovered(false)}
            style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
          >
            <SpmChart bins={spmBins} />
            {spmHovered && (
              <span style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: 6,
                padding: '4px 8px',
                background: 'var(--surface-2)',
                border: '1px solid var(--rule-bright)',
                color: 'var(--text)',
                fontSize: 11,
                fontFamily: 'JetBrains Mono, monospace',
                whiteSpace: 'nowrap',
                zIndex: 100,
                pointerEvents: 'none',
              }}>
                Signal arrivals per minute, last 10 min.
              </span>
            )}
          </span>

          <PipeSep />

          {/* Session stats B:/S: — tabular nums, right-aligned 3-digit */}
          <span
            className="text-xs tnum"
            onMouseEnter={() => setStatsHovered(true)}
            onMouseLeave={() => setStatsHovered(false)}
            style={{
              color: 'var(--text-dim)',
              display: 'inline-flex',
              gap: 10,
              letterSpacing: 0,
              cursor: 'default',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            <span>
              {'B:'}
              <span
                style={{
                  color: 'var(--text-mute)',
                  display: 'inline-block',
                  minWidth: '3ch',
                  textAlign: 'right',
                  paddingLeft: 3,
                }}
              >
                {barCount}
              </span>
            </span>
            <span>
              {'S:'}
              <span
                style={{
                  color: 'var(--text-mute)',
                  display: 'inline-block',
                  minWidth: '3ch',
                  textAlign: 'right',
                  paddingLeft: 3,
                }}
              >
                {signalCount}
              </span>
            </span>
          </span>

          <PipeSep />

          {/* Keyboard help button */}
          <button
            aria-label="Keyboard shortcuts (?)"
            onClick={() => setHelpOpen(true)}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-mute)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 24,
              height: 24,
              borderRadius: 4,
              flexShrink: 0,
              padding: 0,
              transition: 'color 150ms ease',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-mute)'; }}
          >
            <HelpCircle style={{ width: 14, height: 14, strokeWidth: 1.5 }} />
          </button>

          <PipeSep />

          {/* Connection dot */}
          <span
            className={dotClass}
            aria-label={
              status.connected
                ? 'connected'
                : status.feedStale
                ? 'feed stale'
                : 'disconnected'
            }
            onMouseEnter={() => setDotHovered(true)}
            onMouseLeave={() => setDotHovered(false)}
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: dotColor,
              display: 'inline-block',
              flexShrink: 0,
              boxShadow: dotGlow,
              cursor: 'default',
            }}
          />
        </span>

        {/* Dot tooltip */}
        <DotTooltip
          connected={status.connected}
          lastTickAgo={lastTickAgo}
          pnl={status.pnl}
          visible={dotHovered}
        />

        {/* Stats tooltip */}
        <StatsTip
          barCount={barCount}
          signalCount={signalCount}
          sessionAge={sessionAgeStr}
          visible={statsHovered}
        />
      </header>

      {/* Keyboard help modal */}
      <KeyboardHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
