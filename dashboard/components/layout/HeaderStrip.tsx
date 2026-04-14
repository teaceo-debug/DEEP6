'use client';
import { useTradingStore } from '@/store/tradingStore';

export function HeaderStrip() {
  const status = useTradingStore((s) => s.status);
  const score = useTradingStore((s) => s.score);
  // Read latest bar close from bars ring buffer via a stable selector
  // We subscribe to lastBarVersion to re-render when a new bar arrives
  const lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  // lastBarVersion is consumed to trigger re-render; actual price comes from getState
  void lastBarVersion;
  const latestBar = useTradingStore.getState().bars.toArray()[0] ?? null;

  const dotColor = status.connected
    ? 'bg-ask'
    : 'bg-bid';

  const e10Color =
    score.kronosDirection === 'LONG'
      ? 'text-ask'
      : score.kronosDirection === 'SHORT'
      ? 'text-bid'
      : 'text-muted';

  const gexColor =
    score.gexRegime === 'POS_GAMMA'
      ? 'text-ask'
      : score.gexRegime === 'NEG_GAMMA'
      ? 'text-bid'
      : 'text-muted';

  return (
    <header className="h-10 bg-bg-surface border-b border-border-subtle flex items-center px-4 gap-3 text-[13px] shrink-0">
      <span className="font-semibold text-fg-strong">DEEP6</span>
      <span className="font-semibold text-fg">NQ</span>
      <span className="font-mono font-semibold text-fg-strong">
        {latestBar ? latestBar.close.toFixed(2) : '—'}
      </span>
      <span className="text-muted">|</span>
      <span className="text-muted">E10</span>
      <span className={`font-semibold ${e10Color}`}>
        {score.kronosDirection}
        {score.kronosBias ? ` ${Math.round(score.kronosBias)}%` : ''}
      </span>
      <span className="text-muted">|</span>
      <span className="text-muted">GEX</span>
      <span className={`font-semibold ${gexColor}`}>{score.gexRegime || '—'}</span>
      <span
        className={`ml-auto w-2 h-2 rounded-full ${dotColor}`}
        aria-label={status.connected ? 'connected' : 'disconnected'}
        title={status.connected ? 'Connected' : 'Connection lost. Reconnecting...'}
      />
    </header>
  );
}
