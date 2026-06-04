'use client';
/**
 * DOMLadder.tsx — DOM bid/ask ladder component for DEEP6 dashboard.
 *
 * Renders a vertical price ladder with bid volumes on the left, price in the
 * center, and ask volumes on the right. Uses fixture data from DOMSnapshot
 * contract — does NOT import or embed detector logic.
 *
 * Input: DOMLadderState from WebSocket or fixture.
 * Schema: { bids: [{price, volume}], asks: [{price, volume}], version: int }
 */
import { useMemo } from 'react';
import type { DOMLadderState, DOMLadderLevel } from '@/types/deep6';

// ── Helpers ──────────────────────────────────────────────────────────────────

interface MergedRow {
  price: number;
  bidVolume: number;
  askVolume: number;
}

function mergeLevels(bids: DOMLadderLevel[], asks: DOMLadderLevel[]): MergedRow[] {
  const priceMap = new Map<number, MergedRow>();

  for (const b of bids) {
    const existing = priceMap.get(b.price);
    if (existing) {
      existing.bidVolume = b.volume;
    } else {
      priceMap.set(b.price, { price: b.price, bidVolume: b.volume, askVolume: 0 });
    }
  }

  for (const a of asks) {
    const existing = priceMap.get(a.price);
    if (existing) {
      existing.askVolume = a.volume;
    } else {
      priceMap.set(a.price, { price: a.price, bidVolume: 0, askVolume: a.volume });
    }
  }

  // Sort descending by price (highest at top)
  return Array.from(priceMap.values()).sort((a, b) => b.price - a.price);
}

function volumeBarWidth(volume: number, maxVolume: number): string {
  if (maxVolume <= 0) return '0%';
  return `${Math.min(100, (volume / maxVolume) * 100)}%`;
}

// ── Component ────────────────────────────────────────────────────────────────

export interface DOMLadderProps {
  state: DOMLadderState;
  /** Maximum number of rows to display (default: 20). */
  maxRows?: number;
}

export function DOMLadder({ state, maxRows = 20 }: DOMLadderProps) {
  const rows = useMemo(() => {
    const merged = mergeLevels(state.bids, state.asks);
    // Center on the spread midpoint: take maxRows/2 from each side
    const half = Math.floor(maxRows / 2);
    const firstAskIdx = merged.findIndex((r) => r.askVolume > 0 && r.bidVolume === 0);
    if (firstAskIdx === -1) return merged.slice(0, maxRows);
    const start = Math.max(0, firstAskIdx - half);
    return merged.slice(start, start + maxRows);
  }, [state.bids, state.asks, maxRows]);

  const maxVolume = useMemo(
    () => Math.max(1, ...rows.map((r) => Math.max(r.bidVolume, r.askVolume))),
    [rows],
  );

  return (
    <div
      className="dom-ladder"
      role="table"
      aria-label="DOM Ladder"
      style={{
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: '11px',
        lineHeight: '18px',
        width: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        role="row"
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 80px 1fr',
          borderBottom: '1px solid var(--border-mute, #333)',
          padding: '2px 4px',
          color: 'var(--text-mute, #888)',
          fontSize: '10px',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        <span style={{ textAlign: 'right' }}>Bid</span>
        <span style={{ textAlign: 'center' }}>Price</span>
        <span style={{ textAlign: 'left' }}>Ask</span>
      </div>

      {/* Rows */}
      {rows.map((row) => (
        <div
          key={row.price}
          role="row"
          data-testid={`ladder-row-${row.price}`}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 80px 1fr',
            padding: '1px 4px',
            borderBottom: '1px solid var(--border-subtle, #222)',
            position: 'relative',
          }}
        >
          {/* Bid cell */}
          <div style={{ position: 'relative', textAlign: 'right' }}>
            <div
              data-testid={`bid-bar-${row.price}`}
              style={{
                position: 'absolute',
                right: 0,
                top: 0,
                bottom: 0,
                width: volumeBarWidth(row.bidVolume, maxVolume),
                background: 'rgba(38, 166, 154, 0.2)',
              }}
            />
            <span style={{ position: 'relative', color: row.bidVolume > 0 ? '#26a69a' : 'transparent' }}>
              {row.bidVolume > 0 ? row.bidVolume : ''}
            </span>
          </div>

          {/* Price cell */}
          <div style={{ textAlign: 'center', color: 'var(--text-primary, #ddd)', fontWeight: 500 }}>
            {row.price.toFixed(2)}
          </div>

          {/* Ask cell */}
          <div style={{ position: 'relative', textAlign: 'left' }}>
            <div
              data-testid={`ask-bar-${row.price}`}
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: volumeBarWidth(row.askVolume, maxVolume),
                background: 'rgba(239, 83, 80, 0.2)',
              }}
            />
            <span style={{ position: 'relative', color: row.askVolume > 0 ? '#ef5350' : 'transparent' }}>
              {row.askVolume > 0 ? row.askVolume : ''}
            </span>
          </div>
        </div>
      ))}

      {/* Footer: version */}
      <div
        style={{
          padding: '2px 4px',
          color: 'var(--text-mute, #555)',
          fontSize: '9px',
          textAlign: 'right',
        }}
      >
        v{state.version}
      </div>
    </div>
  );
}

export default DOMLadder;
