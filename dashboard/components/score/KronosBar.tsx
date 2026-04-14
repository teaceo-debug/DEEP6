'use client';

/**
 * KronosBar.tsx — Kronos E10 horizontal capsule (UI-SPEC v2 §4.5).
 *
 * Layout (88px tall container):
 *   Row 1: "KRONOS E10" label
 *   Row 2: direction | confidence % | gradient progress bar
 *   Row 3: thin bias fill bar (|bias|/100)
 *
 * Color semantics:
 *   Direction: --ask (LONG), --bid (SHORT), --text-mute (NEUTRAL)
 *   Confidence + bias: --magenta (Kronos always speaks magenta)
 *   Bar gradient: --magenta → direction-color
 */

import { useTradingStore } from '@/store/tradingStore';
import { prefersReducedMotion } from '@/lib/animations';

function directionColor(dir: string): string {
  switch (dir) {
    case 'LONG':  return 'var(--ask)';
    case 'SHORT': return 'var(--bid)';
    default:      return 'var(--text-mute)';
  }
}

export function KronosBar() {
  const kronosBias      = useTradingStore((s) => s.score.kronosBias);
  const kronosDirection = useTradingStore((s) => s.score.kronosDirection);

  // Store does not expose kronosConfidence separately; derive from |kronosBias|
  // (bias is -100..100; confidence = |bias| as a 0-100 measure of conviction)
  // TODO: wire kronosConfidence when backend exposes it separately
  const confidence = Math.max(0, Math.min(100, Math.abs(kronosBias ?? 0)));
  const biasAbs    = confidence; // same value — |bias|/100 fill

  const direction  = kronosDirection || 'NEUTRAL';
  const dirColor   = directionColor(direction);

  const reduced    = prefersReducedMotion();
  const transitionStyle = reduced ? undefined : { transition: 'width 200ms ease-out' };

  return (
    <div
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--rule)',
        padding: '12px 16px',
        height: '88px',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
      }}
    >
      {/* Row 1: label */}
      <div
        className="text-xs label-tracked"
        style={{ color: 'var(--text-dim)' }}
      >
        KRONOS E10
      </div>

      {/* Row 2: direction + confidence + gradient bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        {/* Direction label */}
        <span
          className="text-md"
          style={{ color: dirColor, minWidth: '52px' }}
        >
          {direction}
        </span>

        {/* Confidence percentage */}
        <span
          className="text-md tnum"
          style={{ color: 'var(--magenta)', minWidth: '40px' }}
        >
          {Math.round(confidence)}%
        </span>

        {/* Gradient progress bar */}
        <div
          style={{
            flex: 1,
            height: '8px',
            background: 'var(--surface-2)',
            borderRadius: '2px',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${confidence}%`,
              background: `linear-gradient(to right, var(--magenta), ${dirColor})`,
              borderRadius: '2px',
              ...transitionStyle,
            }}
          />
        </div>
      </div>

      {/* Row 3: thin bias bar (3px, magenta, |bias|/100 fill) */}
      <div
        style={{
          height: '3px',
          background: 'var(--surface-2)',
          borderRadius: '1px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${biasAbs}%`,
            background: 'var(--magenta)',
            borderRadius: '1px',
            ...transitionStyle,
          }}
        />
      </div>
    </div>
  );
}
