'use client';

/**
 * KronosBar.tsx — Kronos E10 horizontal capsule (UI-SPEC v2 §4.5).
 *
 * Layout:
 *   Title row:  "KRONOS E10" label + pulsing magenta dot
 *   Main row:   direction text (LONG/SHORT/─) | confidence % | (right-aligned)
 *   Bar row:    8px gradient bar — magenta→direction-color, remainder --rule
 *   Bias row:   2px thin fill = |bias|/100 in magenta
 *
 * Animations (motion/react):
 *   - Direction text: slide-up / fade on change
 *   - Confidence number: digit-roll via useMotionValue + animate
 *   - Bar fill width: spring (stiffness 200, damping 25)
 *   - "Signal received" ping: 1px magenta underline sweeps left-to-right on update
 *   - Pulsing indicator dot: 2s opacity loop 0.5→1.0
 *
 * Edge cases:
 *   - NEUTRAL direction: rendered as ─
 *   - No Kronos data (bias=0): entire bar fades to 30% opacity, shows "AWAITING"
 *
 * Color semantics:
 *   Direction: --ask (LONG), --bid (SHORT), --text-mute (NEUTRAL)
 *   Confidence + bias: --magenta
 */

import { useRef, useEffect, useState } from 'react';
import {
  animate,
  useMotionValue,
  useTransform,
  motion,
  AnimatePresence,
} from 'motion/react';
import { useTradingStore } from '@/store/tradingStore';
import { prefersReducedMotion } from '@/lib/animations';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function directionColor(dir: string): string {
  switch (dir) {
    case 'LONG':  return 'var(--ask)';
    case 'SHORT': return 'var(--bid)';
    default:      return 'var(--text-mute)';
  }
}

function directionLabel(dir: string): string {
  if (dir === 'NEUTRAL' || !dir) return '─';
  return dir;
}

// ---------------------------------------------------------------------------
// Animated confidence number (digit-roll)
// ---------------------------------------------------------------------------

interface AnimatedNumberProps {
  value: number;
  color: string;
}

function AnimatedNumber({ value, color }: AnimatedNumberProps) {
  const motionVal = useMotionValue(value);
  const reduced   = prefersReducedMotion();

  useEffect(() => {
    if (reduced) {
      motionVal.set(value);
      return;
    }
    const controls = animate(motionVal, value, {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1],
    });
    return () => controls.stop();
  }, [value, motionVal, reduced]);

  // Round for display
  const display = useTransform(motionVal, (v) => `${Math.round(v)}%`);

  return (
    <motion.span
      className="text-md tnum"
      style={{ color, letterSpacing: 0 }}
    >
      {display}
    </motion.span>
  );
}

// ---------------------------------------------------------------------------
// Ping sweep — thin 1px magenta line sweeps left-to-right on Kronos update
// ---------------------------------------------------------------------------

interface PingSweepProps {
  pingKey: number; // increment to trigger a new sweep
}

function PingSweep({ pingKey }: PingSweepProps) {
  const reduced = prefersReducedMotion();
  if (reduced || pingKey === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        key={pingKey}
        initial={{ scaleX: 0, transformOrigin: 'left center', opacity: 1 }}
        animate={{ scaleX: 1, opacity: [1, 1, 0] }}
        exit={{}}
        transition={{
          scaleX: { duration: 0.3, ease: 'easeOut' },
          opacity: { duration: 0.5, ease: 'easeOut', times: [0, 0.6, 1] },
        }}
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '1px',
          background: 'var(--magenta)',
          pointerEvents: 'none',
        }}
      />
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// Animated bar fill (spring)
// ---------------------------------------------------------------------------

interface AnimatedBarFillProps {
  pct: number;
  dirColor: string;
}

function AnimatedBarFill({ pct, dirColor }: AnimatedBarFillProps) {
  const reduced   = prefersReducedMotion();
  const motionPct = useMotionValue(pct);
  const widthStr  = useTransform(motionPct, (v) => `${v}%`);

  useEffect(() => {
    if (reduced) {
      motionPct.set(pct);
      return;
    }
    const controls = animate(motionPct, pct, {
      type: 'spring',
      stiffness: 200,
      damping: 25,
    });
    return () => controls.stop();
  }, [pct, motionPct, reduced]);

  return (
    <motion.div
      style={{
        height: '100%',
        width: widthStr,
        background: `linear-gradient(to right, var(--magenta), ${dirColor})`,
        borderRadius: '2px',
        boxShadow: `inset 0 1px 3px rgba(0,0,0,0.5)`,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Direction text with slide-up change animation
// ---------------------------------------------------------------------------

interface DirectionTextProps {
  direction: string;
  color: string;
}

function DirectionText({ direction, color }: DirectionTextProps) {
  const reduced = prefersReducedMotion();
  const label   = directionLabel(direction);

  return (
    <div
      style={{
        position: 'relative',
        overflow: 'hidden',
        height: '20px',
        minWidth: '52px',
        display: 'flex',
        alignItems: 'center',
      }}
    >
      <AnimatePresence mode="popLayout">
        <motion.span
          key={label}
          className="text-md"
          style={{ color, fontWeight: 600, lineHeight: 1 }}
          initial={reduced ? undefined : { y: 12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={reduced ? undefined : { y: -12, opacity: 0 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        >
          {label}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function KronosBar() {
  const kronosBias      = useTradingStore((s) => s.score.kronosBias);
  const kronosDirection = useTradingStore((s) => s.score.kronosDirection);

  const direction  = kronosDirection || 'NEUTRAL';
  const dirColor   = directionColor(direction);

  // Confidence = |kronosBias| (0–100 scale)
  const confidence = Math.max(0, Math.min(100, Math.abs(kronosBias ?? 0)));
  const biasAbs    = confidence;

  // "No data" state — bias is 0 and direction is NEUTRAL
  const noData = confidence === 0 && direction === 'NEUTRAL';

  // Ping key — increments when Kronos data changes to trigger sweep animation
  const pingKeyRef  = useRef(0);
  const prevBiasRef = useRef(kronosBias);
  const [pingKey, setPingKey] = useState(0);

  useEffect(() => {
    if (kronosBias !== prevBiasRef.current) {
      prevBiasRef.current = kronosBias;
      pingKeyRef.current += 1;
      setPingKey(pingKeyRef.current);
    }
  }, [kronosBias]);

  // Bias warning — bias > confidence (same value here, but structure left for wiring)
  const biasExceedsConfidence = biasAbs > confidence;

  return (
    <div
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--rule)',
        padding: '10px 14px',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: '5px',
        opacity: noData ? 0.3 : 1,
        transition: 'opacity 400ms ease',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Ping sweep — "signal received" cosmetic */}
      <PingSweep pingKey={pingKey} />

      {/* Title row: label + pulsing dot */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span
          className="text-xs label-tracked"
          style={{ color: 'var(--text-dim)' }}
        >
          KRONOS E10
        </span>
        <motion.div
          animate={{ opacity: [0.5, 1.0, 0.5] }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          style={{
            width: '5px',
            height: '5px',
            borderRadius: '50%',
            background: 'var(--magenta)',
            flexShrink: 0,
          }}
        />
      </div>

      {/* Main row: direction | confidence */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <DirectionText direction={direction} color={dirColor} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {biasExceedsConfidence && !noData && (
            <span style={{ color: 'var(--amber)', fontSize: '11px' }}>⚠</span>
          )}
          {noData ? (
            <span
              className="text-xs label-tracked"
              style={{ color: 'var(--magenta)', opacity: 0.7 }}
            >
              AWAITING
            </span>
          ) : (
            <AnimatedNumber value={confidence} color="var(--magenta)" />
          )}
        </div>
      </div>

      {/* Gradient confidence bar (8px) */}
      <div
        style={{
          height: '8px',
          background: 'var(--rule)',
          borderRadius: '2px',
          overflow: 'hidden',
          boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.6)',
        }}
      >
        <AnimatedBarFill pct={confidence} dirColor={dirColor} />
      </div>

      {/* Bias sub-bar (2px, magenta) */}
      <div
        style={{
          height: '2px',
          background: 'var(--surface-2)',
          borderRadius: '1px',
          overflow: 'hidden',
        }}
      >
        <motion.div
          animate={{ width: `${biasAbs}%` }}
          transition={prefersReducedMotion()
            ? { duration: 0 }
            : { type: 'spring', stiffness: 200, damping: 25 }
          }
          style={{
            height: '100%',
            background: 'var(--magenta)',
            borderRadius: '1px',
          }}
        />
      </div>
    </div>
  );
}
