'use client';

/**
 * ConfluencePulse.tsx — The dashboard's signature element (UI-SPEC v2 §4.1).
 *
 * A 320×320 SVG with three concentric rings:
 *   Outer ring (r=150): 44 individual signal arcs (7.68° arc + 0.5° gap × 44)
 *   Middle ring (r=130): 8 category sector arcs, opacity = categoryScore/100
 *   Inner core (r≤100): digit-rolling confluence number + tier badge + direction glyph
 *
 * TYPE_A flash: white-hot 200ms → lime settle, radial bloom, optional screen-shake.
 * All animation respects prefers-reduced-motion.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { motion, useMotionValue, useTransform, animate } from 'motion/react';
import { useTradingStore } from '@/store/tradingStore';
import {
  SIGNAL_BIT_CATEGORIES,
  CATEGORY_COLORS,
  CategoryKey,
  digitRollTransition,
  arcIgniteTransition,
  arcStagger,
  typeAFlashKeyframes,
  typeAFlashTransition,
  radialBloomKeyframes,
  radialBloomTransition,
  prefersReducedMotion,
} from '@/lib/animations';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SVG_SIZE = 320;
const CENTER = SVG_SIZE / 2; // 160

// Outer ring: 44 arcs
const OUTER_RADIUS = 150;
const OUTER_STROKE_WIDTH = 8;
// Arc geometry: 360° / 44 = 8.18° per slot = 7.68° arc + 0.5° gap
const ARC_SLOT_DEG = 360 / 44;           // ≈ 8.1818°
const ARC_GAP_DEG = 0.5;
const ARC_SWEEP_DEG = ARC_SLOT_DEG - ARC_GAP_DEG; // ≈ 7.6818°

// Middle ring: 8 category sectors (45° each)
const MIDDLE_RADIUS = 130;
const MIDDLE_STROKE_WIDTH = 8;
const CATEGORY_SLOT_DEG = 45; // 360 / 8

// Clockwise order starting from 12 o'clock (UI-SPEC §4.1)
const CATEGORY_ORDER: CategoryKey[] = [
  'absorption', 'exhaustion', 'imbalance', 'delta',
  'auction', 'volume', 'trap', 'ml',
];

// ---------------------------------------------------------------------------
// SVG arc math helpers
// ---------------------------------------------------------------------------

function degToRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

/**
 * Compute SVG arc path for a stroke-based arc on a circle.
 * startDeg / endDeg are measured from 12 o'clock, clockwise.
 */
function arcPath(
  cx: number,
  cy: number,
  r: number,
  startDeg: number,
  endDeg: number,
): string {
  // Convert from "12 o'clock = 0, clockwise" to standard SVG angle (3 o'clock = 0)
  const startRad = degToRad(startDeg - 90);
  const endRad = degToRad(endDeg - 90);

  const x1 = cx + r * Math.cos(startRad);
  const y1 = cy + r * Math.sin(startRad);
  const x2 = cx + r * Math.cos(endRad);
  const y2 = cy + r * Math.sin(endRad);

  const sweepDeg = endDeg - startDeg;
  const largeArc = sweepDeg > 180 ? 1 : 0;

  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
}

// ---------------------------------------------------------------------------
// Arc geometry pre-computation (immutable — computed once)
// ---------------------------------------------------------------------------

interface ArcSpec {
  path: string;
  category: CategoryKey;
  index: number;
}

const OUTER_ARCS: ArcSpec[] = Array.from({ length: 44 }, (_, i) => {
  const startDeg = i * ARC_SLOT_DEG + ARC_GAP_DEG / 2;
  const endDeg = startDeg + ARC_SWEEP_DEG;
  return {
    path: arcPath(CENTER, CENTER, OUTER_RADIUS, startDeg, endDeg),
    category: SIGNAL_BIT_CATEGORIES[i],
    index: i,
  };
});

interface SectorSpec {
  path: string;
  category: CategoryKey;
  color: string;
  index: number;
}

const MIDDLE_SECTORS: SectorSpec[] = CATEGORY_ORDER.map((cat, i) => {
  const startDeg = i * CATEGORY_SLOT_DEG;
  const endDeg = startDeg + CATEGORY_SLOT_DEG - 0.5; // tiny gap between sectors
  return {
    path: arcPath(CENTER, CENTER, MIDDLE_RADIUS, startDeg, endDeg),
    category: cat,
    color: CATEGORY_COLORS[cat],
    index: i,
  };
});

// ---------------------------------------------------------------------------
// Tier color helper
// ---------------------------------------------------------------------------

function tierColor(tier: string): string {
  switch (tier) {
    case 'TYPE_A': return 'var(--lime)';
    case 'TYPE_B': return 'var(--amber)';
    case 'TYPE_C': return 'var(--cyan)';
    default:       return 'var(--text-mute)';
  }
}

// ---------------------------------------------------------------------------
// Score color helper (UI-SPEC §4.1)
// ---------------------------------------------------------------------------

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--lime)';
  if (score >= 50) return 'var(--amber)';
  return 'var(--text-mute)';
}

// ---------------------------------------------------------------------------
// Direction glyph component
// ---------------------------------------------------------------------------

function DirectionGlyph({ direction }: { direction: number }) {
  if (direction === 1) {
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <polygon points="9,2 17,16 1,16" fill="var(--ask)" />
      </svg>
    );
  }
  if (direction === -1) {
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <polygon points="9,16 17,2 1,2" fill="var(--bid)" />
      </svg>
    );
  }
  return (
    <svg width="18" height="4" viewBox="0 0 18 4" fill="none">
      <rect x="0" y="1" width="18" height="2" rx="1" fill="var(--text-mute)" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConfluencePulse() {
  // -- Store reads ---------------------------------------------------------
  const totalScore     = useTradingStore((s) => s.score.totalScore);
  const tier           = useTradingStore((s) => s.score.tier);
  const direction      = useTradingStore((s) => s.score.direction);
  const categoriesFiring = useTradingStore((s) => s.score.categoriesFiring);
  const categoryScores = useTradingStore((s) => s.score.categoryScores);

  // Clamp score to [0, 100] per T-11.2-04
  const score = Math.max(0, Math.min(100, totalScore ?? 0));

  // Derive a Set for O(1) lookup of firing categories
  const firingSet = new Set(
    (categoriesFiring ?? []).map((c) => c.toLowerCase()),
  );

  // Derive per-category scores (clamp to [0,100] per T-11.2-05)
  function getCatScore(cat: CategoryKey): number {
    const raw = categoryScores?.[cat] ?? 0;
    return Math.max(0, Math.min(100, raw));
  }

  // -- Digit-roll via MotionValue ------------------------------------------
  const mv = useMotionValue(score);
  const displayText = useTransform(mv, (v) => String(Math.round(v)));

  const reduced = prefersReducedMotion();

  useEffect(() => {
    if (reduced) {
      mv.set(score);
      return;
    }
    const ctrl = animate(mv, score, digitRollTransition);
    return () => ctrl.stop();
  }, [score, mv, reduced]);

  // -- TYPE_A flash state --------------------------------------------------
  const [flashActive, setFlashActive] = useState(false);
  const [bloomActive, setBloomActive] = useState(false);
  const lastTierRef = useRef<string>(tier);
  const lastScoreRef = useRef<number>(score);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const triggerFlash = useCallback(() => {
    if (reduced) return;
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    setFlashActive(true);
    setBloomActive(true);
    // Remove bloom after 1200ms
    setTimeout(() => setBloomActive(false), 1200);
    // Remove flash marker after 1400ms
    flashTimerRef.current = setTimeout(() => setFlashActive(false), 1400);

    // Screen shake — dispatch custom event; CSS handles the animation
    if (!reduced && typeof document !== 'undefined') {
      document.body.classList.remove('shake');
      // Force reflow so re-adding the class triggers the animation again
      void document.body.offsetWidth;
      document.body.classList.add('shake');
      setTimeout(() => document.body.classList.remove('shake'), 120);
    }
  }, [reduced]);

  useEffect(() => {
    const wasTypeA = lastTierRef.current === 'TYPE_A';
    const isTypeA  = tier === 'TYPE_A';
    const crossedThreshold = lastScoreRef.current < 80 && score >= 80;

    if ((!wasTypeA && isTypeA) || crossedThreshold) {
      triggerFlash();
    }

    lastTierRef.current  = tier;
    lastScoreRef.current = score;
  }, [tier, score, triggerFlash]);

  useEffect(() => {
    return () => {
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    };
  }, []);

  // -- Render --------------------------------------------------------------
  const color = scoreColor(score);
  const showGlow = score >= 80;

  return (
    <div
      style={{
        width: '320px',
        height: '320px',
        position: 'relative',
        flexShrink: 0,
      }}
    >
      <svg
        width={SVG_SIZE}
        height={SVG_SIZE}
        viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
        style={{ overflow: 'visible' }}
      >
        {/* ── Radial bloom (TYPE_A) ──────────────────────────────────── */}
        {bloomActive && !reduced && (
          <motion.circle
            cx={CENTER}
            cy={CENTER}
            r={90}
            fill="none"
            stroke="var(--lime)"
            strokeWidth={0}
            fillOpacity={0.3}
            style={{ fill: 'var(--lime)' }}
            animate={radialBloomKeyframes}
            transition={radialBloomTransition}
            initial={{ r: 90, opacity: 0.3 }}
          />
        )}

        {/* ── Outer ring: 44 signal arcs ────────────────────────────── */}
        {OUTER_ARCS.map((arc) => {
          const isFired = firingSet.has(arc.category);
          const strokeColor = flashActive && !reduced
            ? '#ffffff'
            : isFired
              ? CATEGORY_COLORS[arc.category]
              : 'var(--rule)';

          return (
            <motion.path
              key={arc.index}
              d={arc.path}
              fill="none"
              stroke={strokeColor}
              strokeWidth={OUTER_STROKE_WIDTH}
              strokeLinecap="round"
              animate={{ stroke: strokeColor }}
              transition={
                reduced
                  ? { duration: 0 }
                  : {
                      ...arcIgniteTransition,
                      delay: arcStagger(arc.index),
                    }
              }
            />
          );
        })}

        {/* ── Middle ring: 8 category sectors ──────────────────────── */}
        {MIDDLE_SECTORS.map((sector) => {
          const catScore = getCatScore(sector.category);
          const opacity = catScore / 100;

          return (
            <motion.path
              key={sector.index}
              d={sector.path}
              fill="none"
              stroke={sector.color}
              strokeWidth={MIDDLE_STROKE_WIDTH}
              strokeLinecap="butt"
              animate={{ opacity }}
              transition={reduced ? { duration: 0 } : { duration: 0.3 }}
              style={{ opacity }}
            />
          );
        })}

        {/* ── Inner core via foreignObject ─────────────────────────── */}
        <motion.g
          animate={
            flashActive && !reduced
              ? {
                  scale: typeAFlashKeyframes.scale,
                  filter: typeAFlashKeyframes.filter,
                }
              : {
                  scale: 1,
                  filter: showGlow
                    ? 'drop-shadow(0 0 4px color-mix(in oklch, var(--lime) 80%, transparent)) drop-shadow(0 0 12px color-mix(in oklch, var(--lime) 40%, transparent))'
                    : 'none',
                }
          }
          transition={
            flashActive && !reduced
              ? typeAFlashTransition
              : { duration: 0.3 }
          }
          style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
        >
          {/* Background circle for inner core */}
          <circle
            cx={CENTER}
            cy={CENTER}
            r={100}
            fill="var(--void)"
          />

          {/* foreignObject for text content — allows CSS classes */}
          <foreignObject
            x={CENTER - 100}
            y={CENTER - 100}
            width={200}
            height={200}
          >
            <div
              style={{
                width: '200px',
                height: '200px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
              }}
            >
              {/* Score number — digit-roll */}
              <motion.div
                className={`text-display tnum${showGlow ? ' glow-lime' : ''}`}
                style={{ color }}
              >
                {displayText}
              </motion.div>

              {/* Tier badge — bordered rectangle, no fill */}
              <div
                style={{
                  border: `1px solid ${tierColor(tier)}`,
                  color: tierColor(tier),
                  padding: '4px 8px',
                  fontSize: '16px',
                  fontWeight: 600,
                  lineHeight: 1.2,
                  letterSpacing: '0.08em',
                  fontFamily: 'var(--font-jetbrains-mono), monospace',
                }}
              >
                {tier || 'QUIET'}
              </div>

              {/* Direction glyph */}
              <DirectionGlyph direction={direction ?? 0} />
            </div>
          </foreignObject>
        </motion.g>
      </svg>
    </div>
  );
}
