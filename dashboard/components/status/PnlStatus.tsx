/**
 * PnlStatus.tsx — APP-06 lite: P&L running total + circuit breaker state.
 *
 * Per D-05 (11-CONTEXT.md): minimal status widget — live P&L running total +
 * circuit breaker state. No historical performance view, no drawdown chart.
 *
 * Rendered at the bottom of ScoreWidget.
 *
 * Data source: tradingStore.status (populated by LiveStatusMessage via WebSocket).
 */
'use client';
import { useTradingStore } from '@/store/tradingStore';

export function PnlStatus() {
  const status = useTradingStore((s) => s.status);
  const { pnl, circuitBreakerActive } = status;

  const pnlColor =
    pnl > 0 ? 'var(--ask)' : pnl < 0 ? 'var(--bid)' : 'var(--muted)';

  return (
    <div
      className="mt-4 pt-3"
      style={{ borderTop: '1px solid var(--border-subtle)' }}
    >
      {/* P&L row */}
      <div className="flex items-center justify-between text-[13px]">
        <span style={{ color: 'var(--muted)' }}>P&amp;L</span>
        <span
          className="font-mono font-semibold"
          style={{ color: pnlColor }}
        >
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </span>
      </div>

      {/* Circuit breaker row */}
      <div className="flex items-center justify-between text-[13px] mt-1">
        <span style={{ color: 'var(--muted)' }}>Circuit Breaker</span>
        <span
          className="w-2 h-2 rounded-full"
          style={{
            background: circuitBreakerActive ? 'var(--bid)' : 'var(--ask)',
          }}
          aria-label={circuitBreakerActive ? 'active' : 'inactive'}
        />
      </div>
    </div>
  );
}
