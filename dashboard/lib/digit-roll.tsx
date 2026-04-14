'use client';

/**
 * dashboard/lib/digit-roll.tsx
 * Shared digit-roll primitives for DEEP6 Terminal Noir.
 *
 * Exports:
 *   useDigitRoll(target, precision?) → MotionValue<string>
 *     Low-level hook. Returns a spring-animated MotionValue whose string value
 *     matches the formatted number. Safe to call inside any 'use client' component.
 *
 *   DigitRoll — React component
 *     Renders the animated number with optional prefix, suffix, className.
 *     Suitable for numbers that don't need per-digit span breakdown (σ, small %).
 *
 *   useDeltaIndicator(value) → { arrow, amount, color, visible }
 *     Tracks changes to `value`. For 800ms after each change, returns a visible
 *     delta arrow (▲/▼), the delta amount, and a --ask/--bid color.
 *     Use for numbers that update ≥ 1×/sec (price, confidence, σ).
 *
 *   useFlashHint(value, threshold) → { flashing, direction }
 *     Fires when |newValue - prevValue| / prevValue > threshold/100.
 *     Returns flashing=true + direction for FLASH_DURATION_MS (300ms), then resets.
 *     Use for significant-change background flash.
 *
 * Spring spec: harmonizedDigitRollTransition from animations.ts
 * (stiffness 120, damping 18, mass 1 — matches SPRING.soft + 500ms budget)
 */

import { useEffect, useRef, useState } from 'react';
import { animate, useMotionValue, useTransform, motion, MotionValue } from 'motion/react';
import {
  harmonizedDigitRollTransition,
  prefersReducedMotion,
  DELTA_VISIBLE_MS,
  FLASH_DURATION_MS,
  DURATION,
} from '@/lib/animations';

// ---------------------------------------------------------------------------
// useDigitRoll — core hook
// ---------------------------------------------------------------------------

/**
 * Sanitize a number for display: clamp NaN/Infinity to a safe finite value (0).
 * Returns the sanitized number and a flag indicating if the value was invalid.
 *
 * @internal
 */
export function sanitizeNumber(v: number): { safe: number; invalid: boolean } {
  if (!Number.isFinite(v)) return { safe: 0, invalid: true };
  return { safe: v, invalid: false };
}

/**
 * Returns a MotionValue<string> that spring-animates from the previous value
 * to `target`. The string is formatted to `precision` decimal places.
 * If `target` is NaN or Infinity, the MotionValue holds `"—"` and does not animate.
 *
 * @param target     The numeric value to animate toward.
 * @param precision  Decimal places in the output string (default 0).
 */
export function useDigitRoll(target: number, precision = 0): MotionValue<string> {
  const { safe, invalid } = sanitizeNumber(target);
  const mv = useMotionValue(safe);
  const reduced = prefersReducedMotion();

  // displayText is a derived MotionValue so it stays reactive with no React state
  const displayText = useTransform(mv, (v) => v.toFixed(precision));

  useEffect(() => {
    if (invalid) {
      // Hold current position — do not animate toward NaN/Infinity
      return;
    }
    if (reduced) {
      mv.set(safe);
      return;
    }
    const ctrl = animate(mv, safe, harmonizedDigitRollTransition);
    return () => ctrl.stop();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safe, invalid, mv, reduced]);

  return displayText;
}

// ---------------------------------------------------------------------------
// DigitRoll component
// ---------------------------------------------------------------------------

export interface DigitRollProps {
  /** The number to display and animate. */
  value: number;
  /** Decimal places (default 0). */
  precision?: number;
  /** Optional prefix rendered before the animated number (e.g. "+"). */
  prefix?: string;
  /** Optional suffix rendered after the animated number (e.g. "%"). */
  suffix?: string;
  /** CSS class name applied to the wrapping <motion.span>. */
  className?: string;
  /** Inline styles applied to the wrapping <motion.span>. */
  style?: React.CSSProperties;
}

/**
 * Drop-in animated number display.
 * Smaller numbers (σ, confidence %) use this whole-value roll.
 * Per-digit span rendering is reserved for large score numbers (≥36px) in
 * ConfluencePulse which handles its own ScoreDigits sub-component.
 */
export function DigitRoll({
  value,
  precision = 0,
  prefix,
  suffix,
  className,
  style,
}: DigitRollProps) {
  const { invalid } = sanitizeNumber(value);
  const displayText = useDigitRoll(value, precision);
  const [snap, setSnap] = useState<string>(() => displayText.get());

  useEffect(() => {
    setSnap(displayText.get());
    const unsub = displayText.on('change', (v) => setSnap(v));
    return unsub;
  }, [displayText]);

  // Show placeholder for non-finite numbers
  if (invalid) {
    return (
      <span
        className={className}
        style={{
          fontVariantNumeric: 'tabular-nums',
          display: 'inline-block',
          ...style,
        }}
      >
        {prefix}{'—'}{suffix}
      </span>
    );
  }

  return (
    <span
      className={className}
      style={{
        fontVariantNumeric: 'tabular-nums',
        display: 'inline-block',
        ...style,
      }}
    >
      {prefix}
      {snap}
      {suffix}
    </span>
  );
}

// ---------------------------------------------------------------------------
// useDeltaIndicator — brief ▲/▼ arrow visible for 800ms after change
// ---------------------------------------------------------------------------

export interface DeltaState {
  /** True when the delta indicator should be rendered. */
  visible: boolean;
  /** '▲' or '▼' */
  arrow: string;
  /** Absolute magnitude of the change (to displayed precision). */
  amount: number;
  /** CSS color token — 'var(--ask)' for up, 'var(--bid)' for down. */
  color: string;
}

/**
 * Tracks numeric changes and exposes a brief delta indicator state.
 * Only fires for actual value changes (not on mount).
 *
 * @param value       The live numeric value.
 * @param precision   Decimal places for the amount display (default 0).
 */
export function useDeltaIndicator(value: number, precision = 0): DeltaState {
  const prevRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [state, setState] = useState<DeltaState>({
    visible: false,
    arrow: '▲',
    amount: 0,
    color: 'var(--ask)',
  });

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;

    // Skip mount (no previous value yet)
    if (prev === null) return;
    // Skip no-change ticks
    if (value === prev) return;

    const delta = value - prev;
    const isUp = delta > 0;

    setState({
      visible: true,
      arrow: isUp ? '▲' : '▼',
      amount: Math.abs(parseFloat(delta.toFixed(precision))),
      color: isUp ? 'var(--ask)' : 'var(--bid)',
    });

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setState((s) => ({ ...s, visible: false }));
    }, DELTA_VISIBLE_MS);
  }, [value, precision]);

  // Cleanup on unmount
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return state;
}

// ---------------------------------------------------------------------------
// useFlashHint — background flash for significant changes
// ---------------------------------------------------------------------------

export interface FlashHintState {
  /** True for FLASH_DURATION_MS (300ms) after a significant change. */
  flashing: boolean;
  /** 'up' or 'down' — determines green vs red flash colour. */
  direction: 'up' | 'down';
}

/**
 * Fires when |newValue - prevValue| >= threshold (absolute units, not %).
 * Returns flashing=true + direction for 300ms, then resets.
 *
 * @param value      The live numeric value.
 * @param threshold  Absolute change magnitude required to trigger the flash.
 */
export function useFlashHint(value: number, threshold: number): FlashHintState {
  const prevRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [state, setState] = useState<FlashHintState>({ flashing: false, direction: 'up' });

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;

    if (prev === null) return;

    const delta = value - prev;
    if (Math.abs(delta) < threshold) return;

    setState({ flashing: true, direction: delta > 0 ? 'up' : 'down' });

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setState((s) => ({ ...s, flashing: false }));
    }, FLASH_DURATION_MS);
  }, [value, threshold]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return state;
}

// ---------------------------------------------------------------------------
// DeltaIndicator — inline ▲▼ badge shown right of the number
// ---------------------------------------------------------------------------

export interface DeltaIndicatorProps {
  delta: DeltaState;
  precision?: number;
  /** Font size in pixels (default 10). */
  fontSize?: number;
}

/**
 * Renders the ▲/▼ delta arrow with amount.
 * Position is `position: absolute, right` — parent must have `position: relative`.
 */
export function DeltaIndicator({ delta, precision = 0, fontSize = 10 }: DeltaIndicatorProps) {
  if (!delta.visible) return null;

  return (
    <motion.span
      initial={{ opacity: 0, x: 4 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 4 }}
      transition={{ duration: DURATION.fast / 1000, ease: 'easeOut' }}
      style={{
        position: 'absolute',
        right: 0,
        top: '50%',
        transform: 'translateY(-50%)',
        color: delta.color,
        fontSize,
        fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
        fontVariantNumeric: 'tabular-nums',
        whiteSpace: 'nowrap',
        pointerEvents: 'none',
        lineHeight: 1,
      }}
    >
      {delta.arrow}{delta.amount.toFixed(precision)}
    </motion.span>
  );
}
