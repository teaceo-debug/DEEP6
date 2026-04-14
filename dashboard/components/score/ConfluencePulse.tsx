'use client';

/**
 * ConfluencePulse.tsx — The dashboard's signature element (UI-SPEC v2 §4.1).
 *
 * A 320×320 SVG with three concentric rings:
 *   Outer ring (r=150): 44 individual signal arcs — real SVG bloom filters, arc breathing,
 *                        shockwave on ignite, white-hot TYPE_A flash
 *   Middle ring (r=130): 8 category sector arcs with radial gradient fill + crosshatch texture
 *   Inner core (r≤100):  3-layer ambient glow, spring digit-roll, level-up threshold flash,
 *                         pulsing tier badge, animated direction triangle
 *
 * TYPE_A flash sequence:
 *   Phase 1 (0-120ms):   all arcs → #ffffff, core glow 3×, background lime bloom
 *   Phase 2 (120-400ms): arcs settle to category color with scale pulse
 *   Phase 3 (400-1500ms): aftershock radial expansion 100→300px, 30% lime → 0%
 *   Optional: body.shake CSS class (respects prefers-reduced-motion)
 *
 * All animations respect prefers-reduced-motion via prefersReducedMotion().
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { motion, useMotionValue, useTransform, animate, AnimatePresence } from 'motion/react';
import { useTradingStore } from '@/store/tradingStore';
import {
  SIGNAL_BIT_CATEGORIES,
  CATEGORY_COLORS,
  CATEGORY_COLORS_HEX,
  CategoryKey,
  digitRollTransition,
  arcIgniteTransition,
  arcStagger,
  typeAFlashKeyframes,
  typeAFlashTransition,
  radialBloomKeyframes,
  radialBloomTransition,
  aftershockBloomKeyframes,
  aftershockBloomTransition,
  backgroundFlashKeyframes,
  backgroundFlashTransition,
  directionFlipTransition,
  levelUpKeyframes,
  levelUpTransition,
  tierBadgePulseKeyframes,
  tierBadgePulseTransition,
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
const ARC_SLOT_DEG = 360 / 44;          // ≈ 8.1818°
const ARC_GAP_DEG = 0.5;
const ARC_SWEEP_DEG = ARC_SLOT_DEG - ARC_GAP_DEG; // ≈ 7.6818°

// Middle ring: 8 category sectors (45° each)
const MIDDLE_RADIUS = 130;
const MIDDLE_STROKE_WIDTH = 10; // slightly wider for gradient visibility

// Clockwise order starting from 12 o'clock (UI-SPEC §4.1)
const CATEGORY_ORDER: CategoryKey[] = [
  'absorption', 'exhaustion', 'imbalance', 'delta',
  'auction', 'volume', 'trap', 'ml',
];

// Middle ring slow rotation speed: 0.05 rad/s = ~2.86°/s → full rotation in ~126s
const RING_ROTATION_DEG_PER_S = 0.05 * (180 / Math.PI); // ≈ 2.865°/s
const RING_FULL_ROT_DURATION = 360 / RING_ROTATION_DEG_PER_S; // ≈ 125.7s

// ---------------------------------------------------------------------------
// SVG arc math helpers
// ---------------------------------------------------------------------------

function degToRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

/**
 * Compute a point on the arc midpoint — used for shockwave origin.
 * Returns [x, y] at the arc's angular midpoint.
 */
function arcMidpoint(cx: number, cy: number, r: number, startDeg: number, endDeg: number): [number, number] {
  const midDeg = (startDeg + endDeg) / 2;
  const midRad = degToRad(midDeg - 90);
  const round = (n: number) => Math.round(n * 1000) / 1000;
  return [round(cx + r * Math.cos(midRad)), round(cy + r * Math.sin(midRad))];
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

  // Round to 3 decimals to avoid SSR/client float-precision hydration mismatches.
  const round = (n: number) => Math.round(n * 1000) / 1000;
  const x1 = round(cx + r * Math.cos(startRad));
  const y1 = round(cy + r * Math.sin(startRad));
  const x2 = round(cx + r * Math.cos(endRad));
  const y2 = round(cy + r * Math.sin(endRad));

  const sweepDeg = endDeg - startDeg;
  const largeArc = sweepDeg > 180 ? 1 : 0;

  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
}

// ---------------------------------------------------------------------------
// Arc geometry pre-computation (immutable — computed once)
// ---------------------------------------------------------------------------

interface ArcSpec {
  path: string;
  midpoint: [number, number];
  category: CategoryKey;
  index: number;
}

const OUTER_ARCS: ArcSpec[] = Array.from({ length: 44 }, (_, i) => {
  const startDeg = i * ARC_SLOT_DEG + ARC_GAP_DEG / 2;
  const endDeg = startDeg + ARC_SWEEP_DEG;
  return {
    path: arcPath(CENTER, CENTER, OUTER_RADIUS, startDeg, endDeg),
    midpoint: arcMidpoint(CENTER, CENTER, OUTER_RADIUS, startDeg, endDeg),
    category: SIGNAL_BIT_CATEGORIES[i],
    index: i,
  };
});

interface SectorSpec {
  path: string;
  category: CategoryKey;
  color: string;
  hexColor: string;
  index: number;
  midAngleDeg: number;
}

const MIDDLE_SECTORS: SectorSpec[] = CATEGORY_ORDER.map((cat, i) => {
  const startDeg = i * 45;
  const endDeg = startDeg + 45 - 0.5; // tiny gap between sectors
  return {
    path: arcPath(CENTER, CENTER, MIDDLE_RADIUS, startDeg, endDeg),
    category: cat,
    color: CATEGORY_COLORS[cat],
    hexColor: CATEGORY_COLORS_HEX[cat],
    index: i,
    midAngleDeg: startDeg + 22.25,
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

function tierColorHex(tier: string): string {
  switch (tier) {
    case 'TYPE_A': return '#a3ff00';
    case 'TYPE_B': return '#ffd60a';
    case 'TYPE_C': return '#00d9ff';
    default:       return '#4a4a4a';
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
// Shockwave element — radial ring expanding from an arc's midpoint
// ---------------------------------------------------------------------------

interface ShockwaveProps {
  id: number;
  cx: number;
  cy: number;
  color: string;
  onDone: (id: number) => void;
}

function Shockwave({ id, cx, cy, color, onDone }: ShockwaveProps) {
  return (
    <motion.circle
      cx={cx}
      cy={cy}
      r={4}
      fill="none"
      stroke={color}
      strokeWidth={1.5}
      initial={{ r: 4, opacity: 0.8, strokeWidth: 1.5 }}
      animate={{ r: 18, opacity: 0, strokeWidth: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      onAnimationComplete={() => onDone(id)}
      style={{ pointerEvents: 'none' }}
    />
  );
}

// ---------------------------------------------------------------------------
// Animated Direction Glyph — flips/scales between states
// ---------------------------------------------------------------------------

function DirectionGlyph({ direction, reduced }: { direction: number; reduced: boolean }) {
  const key = direction === 1 ? 'up' : direction === -1 ? 'down' : 'neutral';

  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={key}
        initial={reduced ? false : { scale: 0.4, opacity: 0, rotate: direction === 1 ? -30 : 30 }}
        animate={{ scale: 1, opacity: 1, rotate: 0 }}
        exit={reduced ? undefined : { scale: 0.4, opacity: 0 }}
        transition={reduced ? { duration: 0 } : directionFlipTransition}
        style={{ display: 'inline-flex', alignItems: 'center' }}
      >
        {direction === 1 && (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <polygon points="9,2 17,16 1,16" fill="var(--ask)" />
          </svg>
        )}
        {direction === -1 && (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <polygon points="9,16 17,2 1,2" fill="var(--bid)" />
          </svg>
        )}
        {direction === 0 && (
          <svg width="18" height="4" viewBox="0 0 18 4" fill="none">
            <rect x="0" y="1" width="18" height="2" rx="1" fill="var(--text-mute)" />
          </svg>
        )}
      </motion.span>
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// Unique filter/gradient ID generator (stable per render)
// ---------------------------------------------------------------------------

const FILTER_ID_ARC_GLOW = 'cp-arc-glow';
const FILTER_ID_ARC_GLOW_WHITE = 'cp-arc-glow-white';
const FILTER_ID_CORE_GLOW = 'cp-core-glow';
const GRADIENT_ID_PREFIX = 'cp-sector-grad-';
const PATTERN_ID_CROSSHATCH = 'cp-crosshatch';

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConfluencePulse() {
  // -- Store reads ---------------------------------------------------------
  const totalScore       = useTradingStore((s) => s.score.totalScore);
  const tier             = useTradingStore((s) => s.score.tier);
  const direction        = useTradingStore((s) => s.score.direction);
  const categoriesFiring = useTradingStore((s) => s.score.categoriesFiring);
  const categoryScores   = useTradingStore((s) => s.score.categoryScores);
  const connected        = useTradingStore((s) => s.status.connected);

  // Clamp score to [0, 100] per T-11.2-04
  const score = Math.max(0, Math.min(100, totalScore ?? 0));

  const reduced = prefersReducedMotion();

  // Derive a Set for O(1) lookup of firing categories
  const firingSet = useMemo(
    () => new Set((categoriesFiring ?? []).map((c) => c.toLowerCase())),
    [categoriesFiring],
  );

  // Derive per-category scores (clamp to [0,100] per T-11.2-05)
  const getCatScore = useCallback((cat: CategoryKey): number => {
    const raw = categoryScores?.[cat] ?? 0;
    return Math.max(0, Math.min(100, raw));
  }, [categoryScores]);

  // -- Digit-roll via MotionValue with spring transition -------------------
  const mv = useMotionValue(score);
  const displayText = useTransform(mv, (v) => String(Math.round(v)));

  useEffect(() => {
    if (reduced) {
      mv.set(score);
      return;
    }
    const ctrl = animate(mv, score, digitRollTransition);
    return () => ctrl.stop();
  }, [score, mv, reduced]);

  // -- Breathing phase for ignited arcs (staggered per arc) ---------------
  // Each arc has its own phase offset so they feel organic, not in sync
  const breathingPhaseRef = useRef<number[]>(
    Array.from({ length: 44 }, (_, i) => i * (2500 / 44)),
  );

  // -- Arc ignition shockwaves --------------------------------------------
  interface ShockwaveEntry {
    id: number;
    cx: number;
    cy: number;
    color: string;
  }
  const [shockwaves, setShockwaves] = useState<ShockwaveEntry[]>([]);
  const shockwaveIdRef = useRef(0);
  const prevFiringRef = useRef<Set<string>>(new Set());

  const removeShockwave = useCallback((id: number) => {
    setShockwaves((prev) => prev.filter((s) => s.id !== id));
  }, []);

  // -- TYPE_A flash state --------------------------------------------------
  const [flashPhase, setFlashPhase] = useState<'idle' | 'white' | 'settle' | 'aftershock'>('idle');
  const [bloomActive, setBloomActive] = useState(false);
  const [aftershockActive, setAftershockActive] = useState(false);
  const [bgFlashActive, setBgFlashActive] = useState(false);
  const lastTierRef = useRef<string>(tier);
  const lastScoreRef = useRef<number>(score);
  const flashTimerRefs = useRef<ReturnType<typeof setTimeout>[]>([]);

  // -- Level-up animation state (crosses 50 or 80) -------------------------
  const [levelUpActive, setLevelUpActive] = useState(false);
  const lastThresholdRef = useRef<number>(score >= 80 ? 2 : score >= 50 ? 1 : 0);

  const clearFlashTimers = useCallback(() => {
    flashTimerRefs.current.forEach((t) => clearTimeout(t));
    flashTimerRefs.current = [];
  }, []);

  const triggerFlash = useCallback(() => {
    if (reduced) return;
    clearFlashTimers();

    // Phase 1 (0-120ms): white-hot
    setFlashPhase('white');
    setBgFlashActive(true);
    setBloomActive(true);

    // Phase 2 (120ms): settle to category colors
    const t1 = setTimeout(() => {
      setFlashPhase('settle');
    }, 120);

    // Phase 3 (400ms): aftershock
    const t2 = setTimeout(() => {
      setFlashPhase('aftershock');
      setAftershockActive(true);
    }, 400);

    // End of bloom (1200ms)
    const t3 = setTimeout(() => {
      setBloomActive(false);
      setBgFlashActive(false);
    }, 1200);

    // End of aftershock (1500ms)
    const t4 = setTimeout(() => {
      setAftershockActive(false);
      setFlashPhase('idle');
    }, 1500);

    flashTimerRefs.current = [t1, t2, t3, t4];

    // Screen shake — CSS handles the animation
    if (typeof document !== 'undefined') {
      document.body.classList.remove('shake');
      void document.body.offsetWidth; // force reflow
      document.body.classList.add('shake');
      setTimeout(() => document.body.classList.remove('shake'), 120);
    }
  }, [reduced, clearFlashTimers]);

  // Watch for tier → TYPE_A and score threshold crossings
  useEffect(() => {
    const wasTypeA = lastTierRef.current === 'TYPE_A';
    const isTypeA = tier === 'TYPE_A';
    const crossedHigh = lastScoreRef.current < 80 && score >= 80;

    if ((!wasTypeA && isTypeA) || crossedHigh) {
      triggerFlash();
    }

    // Level-up for crossing 50 and 80
    const prevThreshold = lastThresholdRef.current;
    const newThreshold = score >= 80 ? 2 : score >= 50 ? 1 : 0;
    if (newThreshold > prevThreshold && !reduced) {
      setLevelUpActive(true);
      setTimeout(() => setLevelUpActive(false), 300);
    }
    lastThresholdRef.current = newThreshold;

    lastTierRef.current = tier;
    lastScoreRef.current = score;
  }, [tier, score, triggerFlash, reduced]);

  // Watch for newly-fired arcs and spawn shockwaves
  useEffect(() => {
    if (reduced) return;
    const newlyFired: string[] = [];
    firingSet.forEach((cat) => {
      if (!prevFiringRef.current.has(cat)) newlyFired.push(cat);
    });

    if (newlyFired.length > 0) {
      // Find one representative arc per newly-fired category
      const newWaves: ShockwaveEntry[] = [];
      const seenCats = new Set<string>();
      OUTER_ARCS.forEach((arc) => {
        if (newlyFired.includes(arc.category) && !seenCats.has(arc.category)) {
          seenCats.add(arc.category);
          newWaves.push({
            id: ++shockwaveIdRef.current,
            cx: arc.midpoint[0],
            cy: arc.midpoint[1],
            color: CATEGORY_COLORS_HEX[arc.category],
          });
        }
      });
      if (newWaves.length > 0) {
        setShockwaves((prev) => [...prev, ...newWaves]);
      }
    }

    prevFiringRef.current = new Set(firingSet);
  }, [firingSet, reduced]);

  useEffect(() => {
    return () => {
      clearFlashTimers();
    };
  }, [clearFlashTimers]);

  // -- Render helpers -------------------------------------------------------
  const color = scoreColor(score);
  const showGlow = score >= 80;
  const isFlashWhite = flashPhase === 'white' && !reduced;
  const isFlashSettle = flashPhase === 'settle' && !reduced;
  const isLoading = score === 0 && !firingSet.size;

  // Desaturate when disconnected
  const containerFilter = !connected && !reduced ? 'saturate(0.2) brightness(0.7)' : 'none';

  // Normal core glow (3 layers: tight/medium/wide)
  const coreGlowFilter = showGlow
    ? 'drop-shadow(0 0 2px rgba(163,255,0,0.9)) drop-shadow(0 0 6px rgba(163,255,0,0.5)) drop-shadow(0 0 18px rgba(163,255,0,0.2))'
    : 'none';

  return (
    <div
      style={{
        width: '320px',
        height: '320px',
        position: 'relative',
        flexShrink: 0,
        filter: containerFilter,
        transition: reduced ? undefined : 'filter 0.6s ease-out',
      }}
    >
      <svg
        width={SVG_SIZE}
        height={SVG_SIZE}
        viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
        style={{ overflow: 'visible' }}
      >
        {/* ── SVG Defs: filters, gradients, patterns ───────────────── */}
        <defs>
          {/* Arc glow filter — feGaussianBlur bloom for ignited arcs */}
          <filter id={FILTER_ID_ARC_GLOW} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Arc glow filter — white-hot version for TYPE_A flash */}
          <filter id={FILTER_ID_ARC_GLOW_WHITE} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Core glow filter — ambient bloom behind the number */}
          <filter id={FILTER_ID_CORE_GLOW} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" result="blur1" />
            <feGaussianBlur stdDeviation="12" result="blur2" in="SourceGraphic" />
            <feMerge>
              <feMergeNode in="blur2" />
              <feMergeNode in="blur1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Per-category radial gradients for middle ring sectors */}
          {MIDDLE_SECTORS.map((sector) => {
            const gradId = `${GRADIENT_ID_PREFIX}${sector.index}`;
            // Gradient runs along the stroke of the arc.
            // We approximate as a linearGradient from center outward at the sector's mid-angle.
            const midRad = degToRad(sector.midAngleDeg - 90);
            const round3 = (n: number) => Math.round(n * 1000) / 1000;
            // Gradient axis from inner edge to outer edge through sector midpoint
            const innerR = MIDDLE_RADIUS - MIDDLE_STROKE_WIDTH / 2;
            const outerR = MIDDLE_RADIUS + MIDDLE_STROKE_WIDTH / 2;
            const x1p = round3(50 + (innerR / SVG_SIZE) * 100 * Math.cos(midRad));
            const y1p = round3(50 + (innerR / SVG_SIZE) * 100 * Math.sin(midRad));
            const x2p = round3(50 + (outerR / SVG_SIZE) * 100 * Math.cos(midRad));
            const y2p = round3(50 + (outerR / SVG_SIZE) * 100 * Math.sin(midRad));
            return (
              <linearGradient
                key={gradId}
                id={gradId}
                gradientUnits="objectBoundingBox"
                x1={`${x1p}%`}
                y1={`${y1p}%`}
                x2={`${x2p}%`}
                y2={`${y2p}%`}
              >
                <stop offset="0%" stopColor={sector.hexColor} stopOpacity="0.6" />
                <stop offset="50%" stopColor={sector.hexColor} stopOpacity="1" />
                <stop offset="100%" stopColor={sector.hexColor} stopOpacity="0.3" />
              </linearGradient>
            );
          })}

          {/* Crosshatch pattern for middle ring texture overlay */}
          <pattern
            id={PATTERN_ID_CROSSHATCH}
            x="0"
            y="0"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
          >
            <line x1="0" y1="4" x2="4" y2="0" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
            <line x1="-1" y1="1" x2="1" y2="-1" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
            <line x1="3" y1="5" x2="5" y2="3" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
          </pattern>
        </defs>

        {/* ── Background lime flash during TYPE_A (radial glow) ──────── */}
        {bgFlashActive && !reduced && (
          <motion.circle
            cx={CENTER}
            cy={CENTER}
            r={SVG_SIZE * 0.3}
            fill="var(--lime)"
            fillOpacity={0}
            animate={backgroundFlashKeyframes}
            transition={backgroundFlashTransition}
            initial={{ opacity: 0, scale: 0.6 }}
            style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
          />
        )}

        {/* ── Primary radial bloom (TYPE_A) ──────────────────────────── */}
        {bloomActive && !reduced && (
          <motion.circle
            cx={CENTER}
            cy={CENTER}
            r={90}
            fill="var(--lime)"
            fillOpacity={0.3}
            stroke="none"
            animate={radialBloomKeyframes}
            transition={radialBloomTransition}
            initial={{ r: 90, opacity: 0.3 }}
          />
        )}

        {/* ── Aftershock bloom (TYPE_A phase 3) ──────────────────────── */}
        {aftershockActive && !reduced && (
          <motion.circle
            cx={CENTER}
            cy={CENTER}
            r={100}
            fill="none"
            stroke="var(--lime)"
            strokeWidth={1}
            animate={aftershockBloomKeyframes}
            transition={aftershockBloomTransition}
            initial={{ r: 100, opacity: 0.3 }}
          />
        )}

        {/* ── Scanning arc (zero/loading state) ──────────────────────── */}
        {isLoading && !reduced && (
          <motion.path
            d={arcPath(CENTER, CENTER, OUTER_RADIUS, 0, ARC_SWEEP_DEG)}
            fill="none"
            stroke="var(--lime)"
            strokeWidth={OUTER_STROKE_WIDTH}
            strokeLinecap="round"
            strokeOpacity={0.1}
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 4, ease: 'linear' }}
            style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
          />
        )}

        {/* ── Outer ring: 44 signal arcs ────────────────────────────── */}
        {OUTER_ARCS.map((arc) => {
          const isFired = firingSet.has(arc.category);
          const strokeColor = isFlashWhite
            ? '#ffffff'
            : isFired
              ? CATEGORY_COLORS[arc.category]
              : 'var(--rule)';

          const filterAttr = isFlashWhite
            ? `url(#${FILTER_ID_ARC_GLOW_WHITE})`
            : isFired
              ? `url(#${FILTER_ID_ARC_GLOW})`
              : undefined;

          return (
            <motion.path
              key={arc.index}
              d={arc.path}
              fill="none"
              stroke={strokeColor}
              strokeWidth={OUTER_STROKE_WIDTH}
              strokeLinecap="round"
              filter={filterAttr}
              animate={
                reduced
                  ? { stroke: strokeColor }
                  : {
                      stroke: strokeColor,
                      // Breathing pulse on ignited arcs: opacity 0.85 ↔ 1.0
                      opacity: isFired && !isFlashWhite
                        ? [0.85, 1.0, 0.85]
                        : isFlashWhite
                          ? [1, 1]
                          : 1,
                    }
              }
              transition={
                reduced
                  ? { duration: 0 }
                  : isFired && !isFlashWhite
                    ? {
                        stroke: { ...arcIgniteTransition, delay: arcStagger(arc.index) },
                        opacity: {
                          duration: 2.5,
                          ease: 'easeInOut',
                          repeat: Infinity,
                          delay: (breathingPhaseRef.current[arc.index] / 1000),
                        },
                      }
                    : {
                        stroke: { ...arcIgniteTransition, delay: arcStagger(arc.index) },
                        opacity: { duration: 0.2 },
                      }
              }
            />
          );
        })}

        {/* ── Shockwaves on arc ignition ─────────────────────────────── */}
        {shockwaves.map((sw) => (
          <Shockwave
            key={sw.id}
            id={sw.id}
            cx={sw.cx}
            cy={sw.cy}
            color={sw.color}
            onDone={removeShockwave}
          />
        ))}

        {/* ── Middle ring: 8 category sectors with gradient + texture ── */}
        <motion.g
          animate={reduced ? undefined : { rotate: 360 }}
          transition={reduced ? undefined : {
            repeat: Infinity,
            duration: RING_FULL_ROT_DURATION,
            ease: 'linear',
          }}
          style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
        >
          {MIDDLE_SECTORS.map((sector) => {
            const catScore = getCatScore(sector.category);
            const opacity = catScore / 100;

            return (
              <g key={sector.index}>
                {/* Gradient-filled arc stroke */}
                <motion.path
                  d={sector.path}
                  fill="none"
                  stroke={`url(#${GRADIENT_ID_PREFIX}${sector.index})`}
                  strokeWidth={MIDDLE_STROKE_WIDTH}
                  strokeLinecap="butt"
                  animate={{ opacity }}
                  transition={reduced ? { duration: 0 } : { duration: 0.4 }}
                  style={{ opacity }}
                />
                {/* Crosshatch texture overlay at same opacity */}
                <motion.path
                  d={sector.path}
                  fill="none"
                  stroke={`url(#${PATTERN_ID_CROSSHATCH})`}
                  strokeWidth={MIDDLE_STROKE_WIDTH}
                  strokeLinecap="butt"
                  animate={{ opacity }}
                  transition={reduced ? { duration: 0 } : { duration: 0.4 }}
                  style={{ opacity }}
                />
              </g>
            );
          })}
        </motion.g>

        {/* ── Inner core via foreignObject ─────────────────────────── */}
        <motion.g
          animate={
            isFlashWhite || isFlashSettle
              ? {
                  scale: typeAFlashKeyframes.scale,
                  filter: typeAFlashKeyframes.filter,
                }
              : levelUpActive && !reduced
                ? {
                    scale: levelUpKeyframes.scale,
                    filter: coreGlowFilter !== 'none' ? coreGlowFilter : undefined,
                  }
                : {
                    scale: 1,
                    filter: coreGlowFilter,
                  }
          }
          transition={
            (isFlashWhite || isFlashSettle) && !reduced
              ? typeAFlashTransition
              : levelUpActive && !reduced
                ? levelUpTransition
                : { duration: 0.3 }
          }
          style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
        >
          {/* Ambient glow ring behind core (only when score >= 80) */}
          {showGlow && (
            <circle
              cx={CENTER}
              cy={CENTER}
              r={102}
              fill="none"
              stroke="rgba(163,255,0,0.08)"
              strokeWidth={6}
              filter={`url(#${FILTER_ID_CORE_GLOW})`}
            />
          )}

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
              {/* Score number — digit-roll with dominant sizing */}
              <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <motion.div
                  className={`tnum${showGlow ? ' glow-lime' : ''}`}
                  style={{
                    color,
                    fontSize: '68px',
                    lineHeight: 1.0,
                    fontWeight: 700,
                    letterSpacing: '-0.05em',
                    fontFamily: 'var(--font-jetbrains-mono), monospace',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {displayText}
                </motion.div>

                {/* Thin underline — visible only when score > 0 */}
                {score > 0 && (
                  <div
                    style={{
                      width: '100%',
                      height: '1px',
                      background: 'var(--rule-bright)',
                      marginTop: '2px',
                    }}
                  />
                )}
              </div>

              {/* Tier badge — bordered rectangle with optional pulse */}
              <motion.div
                animate={
                  tier === 'TYPE_A' && !reduced
                    ? tierBadgePulseKeyframes
                    : { opacity: 1 }
                }
                transition={
                  tier === 'TYPE_A' && !reduced
                    ? tierBadgePulseTransition
                    : { duration: 0 }
                }
                style={{
                  border: `1px solid ${tierColor(tier)}`,
                  boxShadow: tier === 'TYPE_A' || tier === 'TYPE_B' || tier === 'TYPE_C'
                    ? `0 0 6px ${tierColorHex(tier)}40, inset 0 0 4px ${tierColorHex(tier)}15`
                    : 'none',
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
              </motion.div>

              {/* Direction glyph — animated flip */}
              <DirectionGlyph direction={direction ?? 0} reduced={reduced} />
            </div>
          </foreignObject>
        </motion.g>
      </svg>
    </div>
  );
}
