'use client';

/**
 * KronosBar.tsx — Kronos E10 horizontal capsule (UI-SPEC v2 §4.5).
 *
 * Layout (top → bottom, ~140px total):
 *   [header row]          "KRONOS E10" label + pulsing dot
 *   [sparkline row 14px]  rolling 20-point bias sparkline (SVG) — or "BUILDING HISTORY..."
 *   [main row]            direction text | confidence % | trend arrow
 *   [gradient bar 8px]    magenta→direction-color spring-animated
 *   [direction strip 4px] 20-slot color history (LONG=green, SHORT=red, NEUTRAL=grey)
 *   [bias sub-bar 2px]    |bias|/100 magenta thin fill
 *
 * Additions vs prior revision:
 *   - Local history state: last 20 {ts, bias, direction} entries (component-only)
 *   - Sparkline: 80×14px SVG, magenta line + 10% fill area, dot at current point
 *   - Direction history strip: 80×4px, each slot colored by direction
 *   - σ stability indicator: std-dev of last 20 bias values (JetBrains Mono text-xs)
 *   - Trend arrow: ↗/↘/→ comparing current bias to 20-tick-ago bias
 *   - prefers-reduced-motion: all spring/animate transitions disabled
 *
 * Unchanged animations:
 *   - Direction text: slide-up / fade on change
 *   - Confidence number: digit-roll via useMotionValue + animate
 *   - Bar fill width: spring (stiffness 200, damping 25)
 *   - "Signal received" ping: 1px magenta underline sweeps left-to-right on update
 *   - Pulsing indicator dot: 2s opacity loop 0.5→1.0
 *
 * Color semantics:
 *   Direction: --ask (LONG), --bid (SHORT), --text-mute (NEUTRAL)
 *   Confidence + bias + sparkline: --magenta
 */

import { useRef, useEffect, useState, useMemo } from 'react';
import {
  animate,
  useMotionValue,
  useTransform,
  motion,
  AnimatePresence,
} from 'motion/react';
import { useTradingStore } from '@/store/tradingStore';
import { prefersReducedMotion, DURATION, EASING, SPRING } from '@/lib/animations';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HistoryEntry {
  ts: number;
  bias: number;
  direction: string;
}

const MAX_HISTORY = 20;

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

function stdDev(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
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
      duration: DURATION.slow / 1000 * 1.2, // 600ms digit roll — EASING.spring
      ease: EASING.spring as [number, number, number, number],
    });
    return () => controls.stop();
  }, [value, motionVal, reduced]);

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
// Animated sigma value (digit-roll)
// ---------------------------------------------------------------------------

interface AnimatedSigmaProps {
  value: number;
}

function AnimatedSigma({ value }: AnimatedSigmaProps) {
  const motionVal = useMotionValue(value);
  const reduced   = prefersReducedMotion();

  useEffect(() => {
    if (reduced) {
      motionVal.set(value);
      return;
    }
    const controls = animate(motionVal, value, {
      duration: DURATION.slow / 1000 * 1.2, // 600ms sigma roll — EASING.spring
      ease: EASING.spring as [number, number, number, number],
    });
    return () => controls.stop();
  }, [value, motionVal, reduced]);

  const display = useTransform(motionVal, (v) => `σ ${Math.round(v)}`);

  return (
    <motion.span
      style={{
        fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
        fontSize: '10px',
        color: 'var(--text-dim)',
        letterSpacing: '0.02em',
      }}
    >
      {display}
    </motion.span>
  );
}

// ---------------------------------------------------------------------------
// Ping sweep — thin 1px magenta line sweeps left-to-right on Kronos update
// ---------------------------------------------------------------------------

interface PingSweepProps {
  pingKey: number;
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
          scaleX: { duration: DURATION.normal / 1000, ease: 'easeOut' },       // 250ms ping sweep
          opacity: { duration: DURATION.slow / 1000, ease: 'easeOut', times: [0, 0.6, 1] }, // 500ms fade
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
      ...SPRING.snap, // stiffness:200, damping:25 — bar fill spring
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
          transition={{ duration: DURATION.normal / 1000, ease: EASING.spring as [number, number, number, number] }}
        >
          {label}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sparkline — 80×14px SVG line + area chart of last 20 bias values
// ---------------------------------------------------------------------------

interface SparklineProps {
  history: HistoryEntry[];
}

function Sparkline({ history }: SparklineProps) {
  const W = 80;
  const H = 14;

  const biasValues = history.map((h) => h.bias);
  const minV = Math.min(...biasValues);
  const maxV = Math.max(...biasValues);
  const range = maxV - minV || 1; // avoid division by zero when all same

  const points = biasValues.map((v, i) => {
    const x = (i / (biasValues.length - 1)) * W;
    const y = H - ((v - minV) / range) * H;
    return { x, y };
  });

  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(' ');

  // Area path: line path + close down to baseline
  const areaPath =
    linePath +
    ` L${points[points.length - 1].x.toFixed(1)},${H} L0,${H} Z`;

  const last = points[points.length - 1];

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'block', overflow: 'visible' }}
    >
      {/* Area fill */}
      <path
        d={areaPath}
        fill="rgba(255,0,170,0.10)"
        stroke="none"
      />
      {/* Line */}
      <path
        d={linePath}
        fill="none"
        stroke="var(--magenta)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Current point dot */}
      {last && (
        <circle
          cx={last.x.toFixed(1)}
          cy={last.y.toFixed(1)}
          r="3"
          fill="var(--magenta)"
        />
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Direction history strip — 80×4px row of 20 colored slots
// ---------------------------------------------------------------------------

interface DirectionStripProps {
  history: HistoryEntry[];
}

function DirectionStrip({ history }: DirectionStripProps) {
  const W = 80;
  const H = 4;
  const slotW = W / MAX_HISTORY;

  // Pad with empty slots on the left when history is short
  const padded: (HistoryEntry | null)[] = [
    ...Array(MAX_HISTORY - history.length).fill(null),
    ...history,
  ];

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'block' }}
    >
      {padded.map((entry, i) => {
        let fill = 'var(--text-mute)';
        if (entry) {
          if (entry.direction === 'LONG')  fill = 'var(--ask)';
          else if (entry.direction === 'SHORT') fill = 'var(--bid)';
        } else {
          fill = 'var(--surface-2)';
        }
        return (
          <rect
            key={i}
            x={(i * slotW).toFixed(1)}
            y="0"
            width={(slotW - 0.5).toFixed(1)}
            height={H}
            fill={fill}
            rx="0.5"
          />
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Trend arrow — compare current bias to oldest in history window
// ---------------------------------------------------------------------------

interface TrendArrowProps {
  current: number;
  oldest: number | null;
}

function TrendArrow({ current, oldest }: TrendArrowProps) {
  if (oldest === null) return null;

  const diff = current - oldest;
  let arrow: string;
  let color: string;

  if (diff > 2) {
    arrow = '↗';
    color = 'var(--ask)';
  } else if (diff < -2) {
    arrow = '↘';
    color = 'var(--bid)';
  } else {
    arrow = '→';
    color = 'var(--text-mute)';
  }

  return (
    <span style={{ color, fontSize: '11px', lineHeight: 1 }}>
      {arrow}
    </span>
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

  // ---------------------------------------------------------------------------
  // Local history (component-level only, not persisted to store)
  // ---------------------------------------------------------------------------
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    // Only push when bias or direction actually changes (skip initial zero/NEUTRAL)
    if (kronosBias !== prevBiasRef.current) {
      prevBiasRef.current = kronosBias;
      pingKeyRef.current += 1;
      setPingKey(pingKeyRef.current);

      setHistory((prev) => {
        const next = [
          ...prev,
          { ts: Date.now(), bias: kronosBias ?? 0, direction },
        ];
        return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
      });
    }
  }, [kronosBias, direction]);

  // ---------------------------------------------------------------------------
  // Derived stats
  // ---------------------------------------------------------------------------
  const sigma = useMemo(() => {
    if (history.length < 2) return 0;
    return stdDev(history.map((h) => h.bias));
  }, [history]);

  const oldestBias = history.length === MAX_HISTORY ? history[0].bias : null;

  // Bias warning — bias > confidence (same value here, but structure left for wiring)
  const biasExceedsConfidence = biasAbs > confidence;

  const hasEnoughHistory = history.length >= 3;

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
        minHeight: '140px',
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
            duration: DURATION.slow / 1000 * 4, // 2000ms — pulsing dot breathe loop
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

      {/* Sparkline row — 80×14px or "BUILDING HISTORY..." placeholder */}
      <div style={{ height: '14px', display: 'flex', alignItems: 'center' }}>
        {hasEnoughHistory ? (
          <Sparkline history={history} />
        ) : (
          <span
            className="text-xs label-tracked"
            style={{ color: 'var(--text-mute)', fontSize: '9px', letterSpacing: '0.06em' }}
          >
            BUILDING HISTORY...
          </span>
        )}
      </div>

      {/* Main row: direction | confidence + σ | trend arrow */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <DirectionText direction={direction} color={dirColor} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {/* σ stability indicator */}
          {history.length >= 2 && (
            <AnimatedSigma value={sigma} />
          )}

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

          {/* Trend arrow */}
          <TrendArrow current={kronosBias ?? 0} oldest={oldestBias} />
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

      {/* Direction history strip (4px, 20 slots) */}
      <div style={{ height: '4px' }}>
        <DirectionStrip history={history} />
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
            : { type: 'spring', ...SPRING.snap } // stiffness:200, damping:25
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
