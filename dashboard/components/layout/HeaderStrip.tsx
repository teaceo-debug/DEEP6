'use client';

import { useEffect, useRef, useState } from 'react';
import { useTradingStore } from '@/store/tradingStore';

/**
 * HeaderStrip — 44px terminal header per UI-SPEC §4.7
 *
 * Layout: DEEP6 ▸ NQ ▸ price delta │ E10 │ GEX │ clock ● connection
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
      // Flash direction
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
  const deltaAbs = Math.abs(priceDelta);
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

  // Connection dot
  let dotColor: string;
  let dotClass: string;
  if (status.connected) {
    dotColor = 'var(--ask)';
    dotClass = 'animate-pulse-dot';
  } else if (status.feedStale) {
    dotColor = 'var(--amber)';
    dotClass = 'animate-flash-amber';
  } else {
    dotColor = 'var(--bid)';
    dotClass = '';
  }

  return (
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
      }}
    >
      {/* DEEP6 */}
      <span
        className="text-md label-tracked"
        style={{ color: 'var(--text)', marginRight: '8px' }}
      >
        DEEP6
      </span>

      {/* ▸ separator */}
      <span className="text-sm" style={{ color: 'var(--text-mute)', marginRight: '8px' }}>
        ▸
      </span>

      {/* NQ */}
      <span
        className="text-md label-tracked"
        style={{ color: 'var(--text)', marginRight: '8px' }}
      >
        NQ
      </span>

      {/* ▸ separator */}
      <span className="text-sm" style={{ color: 'var(--text-mute)', marginRight: '8px' }}>
        ▸
      </span>

      {/* Price */}
      <span
        className={`text-md tnum${priceFlash ? ` flash-${priceFlash}` : ''}`}
        style={{ color: priceColor, marginRight: '6px', transition: priceFlash ? undefined : 'color 150ms ease-out' }}
      >
        {price !== null ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
      </span>

      {/* Delta */}
      {price !== null && priceDelta !== 0 && (
        <span
          className="text-sm tnum"
          style={{ color: deltaColor, marginRight: '12px' }}
        >
          {deltaSymbol}{deltaIsPositive ? '+' : ''}{priceDelta.toFixed(2)}
        </span>
      )}
      {(price === null || priceDelta === 0) && (
        <span style={{ marginRight: '12px' }} />
      )}

      {/* │ pipe */}
      <span
        style={{
          color: 'var(--rule-bright)',
          margin: '0 12px',
          userSelect: 'none',
        }}
      >
        │
      </span>

      {/* E10 */}
      <span
        className="text-xs label-tracked"
        style={{ color: 'var(--text-dim)', marginRight: '6px' }}
      >
        E10
      </span>
      <span
        className="text-sm tnum"
        style={{ color: 'var(--magenta)', marginRight: '4px' }}
      >
        {score.kronosBias ? `${Math.round(score.kronosBias)}%` : '—'}
      </span>
      <span
        className="text-sm label-tracked"
        style={{ color: e10Color }}
      >
        {score.kronosDirection || 'NEUTRAL'}
      </span>

      {/* │ pipe */}
      <span
        style={{
          color: 'var(--rule-bright)',
          margin: '0 12px',
          userSelect: 'none',
        }}
      >
        │
      </span>

      {/* GEX */}
      <span
        className="text-xs label-tracked"
        style={{ color: 'var(--text-dim)', marginRight: '6px' }}
      >
        GEX
      </span>
      <span
        className="text-sm label-tracked"
        style={{ color: gexColor }}
      >
        {score.gexRegime || 'NEUTRAL'}
      </span>

      {/* │ pipe */}
      <span
        style={{
          color: 'var(--rule-bright)',
          margin: '0 12px',
          userSelect: 'none',
        }}
      >
        │
      </span>

      {/* Clock */}
      <span
        className="text-xs tnum"
        style={{ color: 'var(--text-dim)' }}
      >
        {clock}
      </span>

      {/* Connection dot — far right */}
      <span
        className={dotClass}
        aria-label={status.connected ? 'connected' : status.feedStale ? 'reconnecting' : 'disconnected'}
        title={
          status.connected
            ? 'Connected'
            : status.feedStale
            ? 'Feed stale — reconnecting…'
            : 'Disconnected'
        }
        style={{
          marginLeft: 'auto',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: dotColor,
          display: 'inline-block',
          flexShrink: 0,
        }}
      />
    </header>
  );
}
