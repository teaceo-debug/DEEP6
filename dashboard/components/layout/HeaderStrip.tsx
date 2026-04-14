'use client';

import { useEffect, useRef, useState } from 'react';
import { useTradingStore } from '@/store/tradingStore';

/**
 * HeaderStrip — 44px terminal header per UI-SPEC §4.7
 *
 * Layout: DEEP6 ▸ NQ ▸ price delta │ E10 │ GEX │ clock │ B:/S: stats ● connection
 *
 * Improvements over v1:
 *  - ▸ separators at 80% size, --text-mute, baseline aligned
 *  - Pipe │ replaced with 1px --rule vertical lines, 18px tall
 *  - Section pills with hover border
 *  - Connection dot 10px, 2px border glow when connected
 *  - Connection dot states: connected (--ask, pulse-breathe), connecting (--amber, fast flash),
 *    disconnected (--bid, no animation), stale (--amber, slow breathe)
 *  - Session stats block: B: bars count, S: signals count, updated every 2s
 *  - Clock: HH:MM:SS ET in New York time
 */
export function HeaderStrip() {
  // Store selectors — READ ONLY, never mutate
  const score = useTradingStore((s) => s.score);
  const status = useTradingStore((s) => s.status);
  const lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  void lastBarVersion; // trigger re-render on new bar

  // Price + direction tracking
  const priceRef = useRef<number | null>(null);
  const [price, setPrice] = useState<number | null>(null);
  const [priceDelta, setPriceDelta] = useState<number>(0);
  const [priceFlash, setPriceFlash] = useState<'ask' | 'bid' | null>(null);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Session stats — updated every 2s to avoid re-render thrash
  const [barCount, setBarCount] = useState(0);
  const [signalCount, setSignalCount] = useState(0);

  // Update price from latest bar
  useEffect(() => {
    const latestBar = useTradingStore.getState().bars.latest;
    if (!latestBar) return;
    const newPrice = latestBar.close;
    const prev = priceRef.current;
    priceRef.current = newPrice;
    setPrice(newPrice);
    if (prev !== null && prev !== newPrice) {
      const delta = newPrice - prev;
      setPriceDelta(delta);
      const dir = delta > 0 ? 'ask' : 'bid';
      setPriceFlash(dir);
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      flashTimerRef.current = setTimeout(() => setPriceFlash(null), 300);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastBarVersion]);

  // Clock — ET (America/New_York)
  const [clock, setClock] = useState('--:--:-- ET');
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
      setClock(`${et} ET`);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  // Session stats — poll every 2s
  useEffect(() => {
    function sample() {
      const state = useTradingStore.getState();
      setBarCount(state.bars.size);
      setSignalCount(state.signals.size);
    }
    sample();
    const id = setInterval(sample, 2000);
    return () => clearInterval(id);
  }, []);

  // Price color
  const priceColor =
    priceFlash === 'ask'
      ? 'var(--ask)'
      : priceFlash === 'bid'
      ? 'var(--bid)'
      : 'var(--text)';

  // Delta display
  const deltaIsPositive = priceDelta >= 0;
  const deltaSymbol = deltaIsPositive ? '▲' : '▼';
  const deltaColor = deltaIsPositive ? 'var(--ask)' : 'var(--bid)';

  // E10 direction color
  const e10Color =
    score.kronosDirection === 'LONG'
      ? 'var(--ask)'
      : score.kronosDirection === 'SHORT'
      ? 'var(--bid)'
      : 'var(--text-mute)';

  // GEX regime color
  const gexColor =
    score.gexRegime === 'POS_GAMMA'
      ? 'var(--ask)'
      : score.gexRegime === 'NEG_GAMMA'
      ? 'var(--bid)'
      : 'var(--text-mute)';

  // Connection dot state
  let dotColor: string;
  let dotClass: string;
  let dotGlow: string;
  const dotTooltip = status.connected
    ? `connected: true / last-tick: ${status.lastTs > 0 ? ((Date.now() / 1000 - status.lastTs).toFixed(1) + 's ago') : 'n/a'} / pnl: ${status.pnl >= 0 ? '+' : ''}$${status.pnl.toFixed(2)}`
    : status.feedStale
    ? 'Feed stale — reconnecting…'
    : 'Disconnected';

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

  // Thin vertical rule separator
  const PipeSep = () => (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width: '1px',
        height: '18px',
        background: 'var(--rule)',
        flexShrink: 0,
        margin: '0 12px',
        alignSelf: 'center',
      }}
    />
  );

  // Section pill — subtle hover border top+bottom
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
      {/* Inline keyframes — avoids touching globals.css */}
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
        @media (prefers-reduced-motion: reduce) {
          .dot-breathe-connected,
          .dot-breathe-stale {
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
        {/* DEEP6 ▸ NQ ▸ price delta */}
        <span className="text-md label-tracked" style={{ color: 'var(--text)' }}>
          DEEP6
        </span>

        {/* ▸ — smaller, muted, baseline aligned */}
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

        {/* Price — flash color, then settle */}
        <span
          className={`text-md tnum${priceFlash ? ` flash-${priceFlash}` : ''}`}
          style={{
            color: priceColor,
            transition: priceFlash ? undefined : 'color 150ms ease-out',
            marginRight: '6px',
          }}
        >
          {price !== null
            ? price.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })
            : '—'}
        </span>

        {/* Delta — static direction color, never flashing */}
        {price !== null && priceDelta !== 0 ? (
          <span className="text-sm tnum" style={{ color: deltaColor }}>
            {deltaSymbol}{deltaIsPositive ? '+' : ''}
            {priceDelta.toFixed(2)}
          </span>
        ) : (
          <span style={{ minWidth: 52 }} />
        )}

        <PipeSep />

        {/* E10 section */}
        <SectionPill>
          <span className="text-xs label-tracked" style={{ color: 'var(--text-dim)' }}>
            E10
          </span>
          <span className="text-sm tnum" style={{ color: 'var(--magenta)' }}>
            {score.kronosBias ? `${Math.round(score.kronosBias)}%` : '—'}
          </span>
          <span className="text-sm label-tracked" style={{ color: e10Color }}>
            {score.kronosDirection || 'NEUTRAL'}
          </span>
        </SectionPill>

        <PipeSep />

        {/* GEX section */}
        <SectionPill>
          <span className="text-xs label-tracked" style={{ color: 'var(--text-dim)' }}>
            GEX
          </span>
          <span className="text-sm label-tracked" style={{ color: gexColor }}>
            {score.gexRegime || 'NEUTRAL'}
          </span>
        </SectionPill>

        <PipeSep />

        {/* Clock section */}
        <SectionPill>
          <span className="text-xs tnum" style={{ color: 'var(--text-dim)' }}>
            {clock}
          </span>
        </SectionPill>

        {/* Right side — pushed to far right */}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <PipeSep />

          {/* Session stats B:/S: */}
          <span
            className="text-xs tnum"
            style={{
              color: 'var(--text-dim)',
              display: 'flex',
              gap: 10,
              letterSpacing: 0,
            }}
          >
            <span>
              B:{' '}
              <span style={{ color: 'var(--text-mute)' }}>{barCount}</span>
            </span>
            <span>
              S:{' '}
              <span style={{ color: 'var(--text-mute)' }}>{signalCount}</span>
            </span>
          </span>

          <PipeSep />

          {/* Connection dot — 10px, glow when connected */}
          <span
            className={dotClass}
            aria-label={
              status.connected
                ? 'connected'
                : status.feedStale
                ? 'feed stale'
                : 'disconnected'
            }
            title={dotTooltip}
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: dotColor,
              display: 'inline-block',
              flexShrink: 0,
              boxShadow: dotGlow,
            }}
          />
        </span>
      </header>
    </>
  );
}
