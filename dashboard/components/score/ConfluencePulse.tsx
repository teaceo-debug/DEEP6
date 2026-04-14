'use client';

/**
 * ConfluencePulse.tsx — The dashboard's signature element (UI-SPEC v2 §4.1).
 *
 * A 320×320 SVG with three concentric rings:
 *   Outer ring (r=150): 44 individual signal arcs — always visible at 15% opacity
 *                        in category color; ignited = 100% with bloom.
 *                        Scanner arc when score<10 && no categories firing.
 *                        Stagger-ignite left-to-right 20ms/arc per category.
 *   Middle ring (r=130): 8 category sector arcs, gradient + crosshatch.
 *                        opacity = 0.25 + (catScore/100)*0.6 (min 25%, max 85%).
 *   Inner core (r≤100):  3-layer ambient glow, spring digit-roll, score threshold
 *                        flash (50/80 boundary), pulsing tier badge, direction triangle
 *                        with halo on change + cross-flash on polarity reversal.
 *   Connection spokes:   TYPE_A only — 8 radial lines from r=60 to r=150,
 *                        one at midpoint of each category sector, bloom filter.
 *   Ambient glow halo:   TYPE_A only — radial gradient outside outer ring to r=200.
 *   Score underline:     grows with score (20% width at 40, 100% at 100).
 *
 * TYPE_A flash sequence (unchanged):
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
  spokeBreathKeyframes,
  spokeBreathTransition,
  directionHaloKeyframes,
  directionHaloTransition,
  directionCrossKeyframes,
  directionCrossTransition,
  scoreThresholdUpKeyframes,
  scoreThresholdUpTransition,
  scoreThresholdDownKeyframes,
  scoreThresholdDownTransition,
  prefersReducedMotion,
  DURATION,
  EASING,
} from '@/lib/animations';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SVG_SIZE = 320;
const CENTER = SVG_SIZE / 2; // 160

// Outer ring: 44 arcs
const OUTER_RADIUS = 150;
const OUTER_STROKE_WIDTH = 8;
const ARC_SLOT_DEG = 360 / 44;
const ARC_GAP_DEG = 0.5;
const ARC_SWEEP_DEG = ARC_SLOT_DEG - ARC_GAP_DEG;

// Middle ring: 8 category sectors (45° each)
const MIDDLE_RADIUS = 130;
const MIDDLE_STROKE_WIDTH = 10;

// Connection spokes: inner/outer radii
// SPOKE_OUTER_R is 144 (not 150) to keep stroke + glow filter inside outer ring.
// At r=150 with strokeWidth=1.5 + feGaussianBlur stdDeviation=3, the glow bleeds ~9px
// beyond r=150 — visually manifests as a rogue cyan arc outside the outer ring.
// 144 + 4 (half of outer stroke-width 8) + 3 (blur clearance) = 151 — safe by design.
const SPOKE_INNER_R = 60;
const SPOKE_OUTER_R = 144;

// Ambient glow halo outer radius (behind outer ring)
const AMBIENT_GLOW_R = 200;

// Clockwise order starting from 12 o'clock (UI-SPEC §4.1)
const CATEGORY_ORDER: CategoryKey[] = [
  'absorption', 'exhaustion', 'imbalance', 'delta',
  'auction', 'volume', 'trap', 'ml',
];

// Middle ring slow rotation speed
const RING_ROTATION_DEG_PER_S = 0.05 * (180 / Math.PI);
const RING_FULL_ROT_DURATION = 360 / RING_ROTATION_DEG_PER_S;

// ---------------------------------------------------------------------------
// SVG arc math helpers
// ---------------------------------------------------------------------------

function degToRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function arcMidpoint(cx: number, cy: number, r: number, startDeg: number, endDeg: number): [number, number] {
  const midDeg = (startDeg + endDeg) / 2;
  const midRad = degToRad(midDeg - 90);
  const round = (n: number) => Math.round(n * 1000) / 1000;
  return [round(cx + r * Math.cos(midRad)), round(cy + r * Math.sin(midRad))];
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const startRad = degToRad(startDeg - 90);
  const endRad = degToRad(endDeg - 90);
  const round = (n: number) => Math.round(n * 1000) / 1000;
  const x1 = round(cx + r * Math.cos(startRad));
  const y1 = round(cy + r * Math.sin(startRad));
  const x2 = round(cx + r * Math.cos(endRad));
  const y2 = round(cy + r * Math.sin(endRad));
  const sweepDeg = endDeg - startDeg;
  const largeArc = sweepDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
}

// Radial line from innerR to outerR at given angle (degrees from 12-o'clock cw)
function spokeLine(cx: number, cy: number, angleDeg: number, innerR: number, outerR: number): string {
  const rad = degToRad(angleDeg - 90);
  const round = (n: number) => Math.round(n * 1000) / 1000;
  const x1 = round(cx + innerR * Math.cos(rad));
  const y1 = round(cy + innerR * Math.sin(rad));
  const x2 = round(cx + outerR * Math.cos(rad));
  const y2 = round(cy + outerR * Math.sin(rad));
  return `M ${x1} ${y1} L ${x2} ${y2}`;
}

// ---------------------------------------------------------------------------
// Arc geometry pre-computation (immutable)
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
  const endDeg = startDeg + 45 - 0.5;
  return {
    path: arcPath(CENTER, CENTER, MIDDLE_RADIUS, startDeg, endDeg),
    category: cat,
    color: CATEGORY_COLORS[cat],
    hexColor: CATEGORY_COLORS_HEX[cat],
    index: i,
    midAngleDeg: startDeg + 22.25,
  };
});

// Pre-compute spoke paths (one per sector midpoint)
const SPOKE_PATHS: { path: string; category: CategoryKey; hexColor: string }[] =
  MIDDLE_SECTORS.map((sector) => ({
    path: spokeLine(CENTER, CENTER, sector.midAngleDeg, SPOKE_INNER_R, SPOKE_OUTER_R),
    category: sector.category,
    hexColor: sector.hexColor,
  }));

// ---------------------------------------------------------------------------
// Tier color helpers
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
// Shockwave element
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
      transition={{ duration: DURATION.normal / 1000, ease: 'easeOut' }} // 250ms shockwave expand
      onAnimationComplete={() => onDone(id)}
      style={{ pointerEvents: 'none' }}
    />
  );
}

// ---------------------------------------------------------------------------
// Animated Direction Glyph — with halo on change + cross-flash on polarity flip
// ---------------------------------------------------------------------------

function DirectionGlyph({ direction, reduced }: { direction: number; reduced: boolean }) {
  const prevDirRef = useRef<number>(direction);
  const [showHalo, setShowHalo] = useState(false);
  const [showCross, setShowCross] = useState(false);
  const haloTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const crossTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (reduced) {
      prevDirRef.current = direction;
      return;
    }
    const prev = prevDirRef.current;
    const changed = prev !== direction;
    // Polarity flip: LONG↔SHORT (crossing zero means prev and curr are opposite nonzero)
    const polarityFlip = (prev === 1 && direction === -1) || (prev === -1 && direction === 1);
    // Direction becoming non-neutral from neutral (or neutral to non-neutral)
    const activated = prev === 0 && direction !== 0;

    if (changed) {
      if (polarityFlip) {
        // Show cross-flash first, then halo
        setShowCross(true);
        if (crossTimerRef.current) clearTimeout(crossTimerRef.current);
        crossTimerRef.current = setTimeout(() => setShowCross(false), 300);
      }
      if (activated || polarityFlip) {
        setShowHalo(true);
        if (haloTimerRef.current) clearTimeout(haloTimerRef.current);
        haloTimerRef.current = setTimeout(() => setShowHalo(false), 500);
      }
    }
    prevDirRef.current = direction;
  }, [direction, reduced]);

  useEffect(() => {
    return () => {
      if (haloTimerRef.current) clearTimeout(haloTimerRef.current);
      if (crossTimerRef.current) clearTimeout(crossTimerRef.current);
    };
  }, []);

  const key = direction === 1 ? 'up' : direction === -1 ? 'down' : 'neutral';
  const glowColor = direction === 1 ? 'var(--ask)' : direction === -1 ? 'var(--bid)' : 'var(--text-mute)';
  const glowColorHex = direction === 1 ? '#00d9ff' : direction === -1 ? '#ff2e63' : '#4a4a4a';

  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      {/* Cross-flash on polarity reversal */}
      <AnimatePresence>
        {showCross && !reduced && (
          <motion.div
            key="cross-flash"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={directionCrossKeyframes as Record<string, number[]>}
            transition={directionCrossTransition}
            exit={{ opacity: 0 }}
            style={{
              position: 'absolute',
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              background: `radial-gradient(circle, ${glowColorHex}60 0%, transparent 70%)`,
              pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

      {/* Halo glow on direction activation */}
      <AnimatePresence>
        {showHalo && !reduced && (
          <motion.div
            key="direction-halo"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={directionHaloKeyframes as Record<string, number[]>}
            transition={directionHaloTransition}
            exit={{ opacity: 0 }}
            style={{
              position: 'absolute',
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              border: `2px solid ${glowColor}`,
              boxShadow: `0 0 8px ${glowColorHex}80`,
              pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter/gradient IDs (stable)
// ---------------------------------------------------------------------------

const FILTER_ID_ARC_GLOW = 'cp-arc-glow';
const FILTER_ID_ARC_GLOW_WHITE = 'cp-arc-glow-white';
const FILTER_ID_CORE_GLOW = 'cp-core-glow';
const FILTER_ID_SPOKE_GLOW = 'cp-spoke-glow';
const FILTER_ID_AMBIENT_GLOW = 'cp-ambient-glow';
const GRADIENT_ID_PREFIX = 'cp-sector-grad-';
const PATTERN_ID_CROSSHATCH = 'cp-crosshatch';
const GRADIENT_ID_AMBIENT = 'cp-ambient-radial';

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

  const score = Math.max(0, Math.min(100, totalScore ?? 0));
  const reduced = prefersReducedMotion();

  const firingSet = useMemo(
    () => new Set((categoriesFiring ?? []).map((c) => c.toLowerCase())),
    [categoriesFiring],
  );

  const getCatScore = useCallback((cat: CategoryKey): number => {
    const raw = categoryScores?.[cat] ?? 0;
    return Math.max(0, Math.min(100, raw));
  }, [categoryScores]);

  // -- Digit-roll -----------------------------------------------------------
  const mv = useMotionValue(score);
  const displayText = useTransform(mv, (v) => String(Math.round(v)));

  useEffect(() => {
    if (reduced) { mv.set(score); return; }
    const ctrl = animate(mv, score, digitRollTransition);
    return () => ctrl.stop();
  }, [score, mv, reduced]);

  // -- Breathing phase offsets (stable) ------------------------------------
  const breathingPhaseRef = useRef<number[]>(
    Array.from({ length: 44 }, (_, i) => i * (2500 / 44)),
  );

  // -- Shockwaves ----------------------------------------------------------
  interface ShockwaveEntry { id: number; cx: number; cy: number; color: string; }
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

  // -- Score threshold flash (80/50 boundary crossing) --------------------
  type ThresholdFlash = 'none' | 'up-80' | 'down-80' | 'up-50' | 'down-50';
  const [thresholdFlash, setThresholdFlash] = useState<ThresholdFlash>('none');
  const thresholdFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevScoreThresholdRef = useRef<number>(score);

  // -- Level-up animation --------------------------------------------------
  const [levelUpActive, setLevelUpActive] = useState(false);
  const lastThresholdRef = useRef<number>(score >= 80 ? 2 : score >= 50 ? 1 : 0);

  // -- TYPE_A ambient glow / spokes visibility ----------------------------
  const [spokesVisible, setSpokesVisible] = useState(tier === 'TYPE_A');
  const [ambientGlowVisible, setAmbientGlowVisible] = useState(tier === 'TYPE_A');
  const spokesTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearFlashTimers = useCallback(() => {
    flashTimerRefs.current.forEach((t) => clearTimeout(t));
    flashTimerRefs.current = [];
  }, []);

  const triggerFlash = useCallback(() => {
    if (reduced) return;
    clearFlashTimers();
    setFlashPhase('white');
    setBgFlashActive(true);
    setBloomActive(true);
    const t1 = setTimeout(() => setFlashPhase('settle'), 120);
    const t2 = setTimeout(() => { setFlashPhase('aftershock'); setAftershockActive(true); }, 400);
    const t3 = setTimeout(() => { setBloomActive(false); setBgFlashActive(false); }, 1200);
    const t4 = setTimeout(() => { setAftershockActive(false); setFlashPhase('idle'); }, 1500);
    flashTimerRefs.current = [t1, t2, t3, t4];
    if (typeof document !== 'undefined') {
      document.body.classList.remove('shake');
      void document.body.offsetWidth;
      document.body.classList.add('shake');
      setTimeout(() => document.body.classList.remove('shake'), 120);
    }
  }, [reduced, clearFlashTimers]);

  // Watch tier + score thresholds
  useEffect(() => {
    const wasTypeA = lastTierRef.current === 'TYPE_A';
    const isTypeA = tier === 'TYPE_A';
    const crossedHigh = lastScoreRef.current < 80 && score >= 80;

    if ((!wasTypeA && isTypeA) || crossedHigh) triggerFlash();

    // Level-up crossing
    const prevThreshold = lastThresholdRef.current;
    const newThreshold = score >= 80 ? 2 : score >= 50 ? 1 : 0;
    if (newThreshold > prevThreshold && !reduced) {
      setLevelUpActive(true);
      setTimeout(() => setLevelUpActive(false), 300);
    }
    lastThresholdRef.current = newThreshold;

    // Score threshold color flash (crossing 80 or 50)
    const prev = prevScoreThresholdRef.current;
    if (!reduced) {
      if (prev < 80 && score >= 80) {
        setThresholdFlash('up-80');
        if (thresholdFlashTimerRef.current) clearTimeout(thresholdFlashTimerRef.current);
        thresholdFlashTimerRef.current = setTimeout(() => setThresholdFlash('none'), 350);
      } else if (prev >= 80 && score < 80) {
        setThresholdFlash('down-80');
        if (thresholdFlashTimerRef.current) clearTimeout(thresholdFlashTimerRef.current);
        thresholdFlashTimerRef.current = setTimeout(() => setThresholdFlash('none'), 450);
      } else if (prev < 50 && score >= 50) {
        setThresholdFlash('up-50');
        if (thresholdFlashTimerRef.current) clearTimeout(thresholdFlashTimerRef.current);
        thresholdFlashTimerRef.current = setTimeout(() => setThresholdFlash('none'), 350);
      } else if (prev >= 50 && score < 50) {
        setThresholdFlash('down-50');
        if (thresholdFlashTimerRef.current) clearTimeout(thresholdFlashTimerRef.current);
        thresholdFlashTimerRef.current = setTimeout(() => setThresholdFlash('none'), 450);
      }
    }
    prevScoreThresholdRef.current = score;

    // TYPE_A spokes + ambient glow
    if (isTypeA && !spokesVisible) {
      if (spokesTimerRef.current) clearTimeout(spokesTimerRef.current);
      setSpokesVisible(true);
      setAmbientGlowVisible(true);
    } else if (!isTypeA && spokesVisible) {
      // Keep rendered during fade-out (400ms)
      if (spokesTimerRef.current) clearTimeout(spokesTimerRef.current);
      spokesTimerRef.current = setTimeout(() => {
        setSpokesVisible(false);
        setAmbientGlowVisible(false);
      }, 500);
    }

    lastTierRef.current = tier;
    lastScoreRef.current = score;
  }, [tier, score, triggerFlash, reduced, spokesVisible]);

  // Shockwaves on new category fires
  useEffect(() => {
    if (reduced) return;
    const newlyFired: string[] = [];
    firingSet.forEach((cat) => { if (!prevFiringRef.current.has(cat)) newlyFired.push(cat); });
    if (newlyFired.length > 0) {
      const newWaves: ShockwaveEntry[] = [];
      const seenCats = new Set<string>();
      OUTER_ARCS.forEach((arc) => {
        if (newlyFired.includes(arc.category) && !seenCats.has(arc.category)) {
          seenCats.add(arc.category);
          newWaves.push({ id: ++shockwaveIdRef.current, cx: arc.midpoint[0], cy: arc.midpoint[1], color: CATEGORY_COLORS_HEX[arc.category] });
        }
      });
      if (newWaves.length > 0) setShockwaves((prev) => [...prev, ...newWaves]);
    }
    prevFiringRef.current = new Set(firingSet);
  }, [firingSet, reduced]);

  useEffect(() => () => { clearFlashTimers(); }, [clearFlashTimers]);

  useEffect(() => () => {
    if (thresholdFlashTimerRef.current) clearTimeout(thresholdFlashTimerRef.current);
    if (spokesTimerRef.current) clearTimeout(spokesTimerRef.current);
  }, []);

  // -- Render helpers -------------------------------------------------------
  const color = scoreColor(score);
  const showGlow = score >= 80;
  const isFlashWhite = flashPhase === 'white' && !reduced;
  const isFlashSettle = flashPhase === 'settle' && !reduced;
  // Scanner: only when score<10 AND zero categories firing
  const showScanner = score < 10 && firingSet.size === 0 && !reduced;
  const isTypeA = tier === 'TYPE_A';

  const containerFilter = !connected && !reduced ? 'saturate(0.2) brightness(0.7)' : 'none';

  const coreGlowFilter = showGlow
    ? 'drop-shadow(0 0 2px rgba(163,255,0,0.9)) drop-shadow(0 0 6px rgba(163,255,0,0.5)) drop-shadow(0 0 18px rgba(163,255,0,0.2))'
    : 'none';

  // Score number color with threshold flash override
  const scoreNumberColor: string = (() => {
    if (thresholdFlash !== 'none') {
      // Will be handled via motion animate; return base
    }
    return color;
  })();

  // Underline width: at score=0 → 0%, score=40 → 20%, score=100 → 100%
  // Linear from 0 to 100: width% = score%
  // But spec: score=40 → 20%, score=100 → 100%
  // So: width% = (score / 100) * 100 → that's just score%, but at 40 should be 20%
  // Formula: width = (score / 100) * 100 * 0.5 when score < 80, else full
  // Spec says: 20% at 40, 100% at 100 → that's linear: width = (score/100) * 100 → no
  // 20/40 = 0.5, 100/100 = 1.0 → slope = (1.0 - 0.5) / (100 - 40) = 0.5/60 per point from 40
  // Simpler: at score x, width = x * (x/100) makes it grow faster at high scores
  // Actually: 20% at 40 → 0.5 ratio; 100% at 100 → 1.0 ratio → linear width% = score * 0.5 + (score/100)*(score/100)*50
  // Simplest that satisfies: width_frac = (score / 100)^(1/1.2) ≈ power curve
  // Just use: width_frac = Math.pow(score / 100, 0.75) * 100  → at 40: 0.4^0.75 * 100 = ~55% — too high
  // Direct linear: width_percent = 20 + (score - 40) * (80/60) when score >= 40, else score * 0.5
  // At score=40: 20%; at score=100: 20 + 60*(80/60) = 20+80=100% ✓
  // At score=0: 0%; at score=10: 5%
  const underlineWidthPercent = score <= 0 ? 0
    : score < 40 ? score * 0.5
    : 20 + (score - 40) * (80 / 60);
  const clampedUnderline = Math.max(0, Math.min(100, underlineWidthPercent));

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
          {/* Arc glow filter */}
          <filter id={FILTER_ID_ARC_GLOW} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Arc glow filter — white-hot TYPE_A flash */}
          <filter id={FILTER_ID_ARC_GLOW_WHITE} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Core glow filter */}
          <filter id={FILTER_ID_CORE_GLOW} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" result="blur1" />
            <feGaussianBlur stdDeviation="12" result="blur2" in="SourceGraphic" />
            <feMerge>
              <feMergeNode in="blur2" />
              <feMergeNode in="blur1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Spoke glow filter */}
          <filter id={FILTER_ID_SPOKE_GLOW} x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Ambient glow filter (outside outer ring) */}
          <filter id={FILTER_ID_AMBIENT_GLOW} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="20" />
          </filter>

          {/* Ambient radial gradient (TYPE_A background glow) */}
          <radialGradient id={GRADIENT_ID_AMBIENT} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#a3ff00" stopOpacity="0.12" />
            <stop offset="60%" stopColor="#a3ff00" stopOpacity="0.04" />
            <stop offset="100%" stopColor="#a3ff00" stopOpacity="0" />
          </radialGradient>

          {/* Per-category radial gradients for middle ring sectors */}
          {MIDDLE_SECTORS.map((sector) => {
            const gradId = `${GRADIENT_ID_PREFIX}${sector.index}`;
            const midRad = degToRad(sector.midAngleDeg - 90);
            const round3 = (n: number) => Math.round(n * 1000) / 1000;
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

          {/* Crosshatch pattern */}
          <pattern id={PATTERN_ID_CROSSHATCH} x="0" y="0" width="4" height="4" patternUnits="userSpaceOnUse">
            <line x1="0" y1="4" x2="4" y2="0" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
            <line x1="-1" y1="1" x2="1" y2="-1" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
            <line x1="3" y1="5" x2="5" y2="3" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
          </pattern>
        </defs>

        {/* ── Ambient background glow (TYPE_A only, outside outer ring) ── */}
        {ambientGlowVisible && !reduced && (
          <motion.circle
            cx={CENTER}
            cy={CENTER}
            r={AMBIENT_GLOW_R}
            fill={`url(#${GRADIENT_ID_AMBIENT})`}
            stroke="none"
            initial={{ opacity: 0 }}
            animate={{ opacity: isTypeA ? 1 : 0 }}
            transition={{ duration: DURATION.normal / 1000 * 1.6, ease: 'easeInOut' }} // 400ms ambient glow fade
            style={{ pointerEvents: 'none' }}
          />
        )}

        {/* ── Background lime flash during TYPE_A ──────────────────────── */}
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

        {/* ── Scanner arc (score<10 and no categories firing) ────────── */}
        {showScanner && (
          <motion.path
            d={arcPath(CENTER, CENTER, OUTER_RADIUS, 0, ARC_SWEEP_DEG)}
            fill="none"
            stroke="var(--lime)"
            strokeWidth={OUTER_STROKE_WIDTH}
            strokeLinecap="round"
            strokeOpacity={0.4}
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: DURATION.slow / 1000 * 8, ease: 'linear' }} // 4s scanner rotation
            style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
          />
        )}

        {/* ── Outer ring: 44 signal arcs — always visible ───────────── */}
        {OUTER_ARCS.map((arc) => {
          const isFired = firingSet.has(arc.category);
          const hexColor = CATEGORY_COLORS_HEX[arc.category];

          // Unlit: category color at 15% opacity. Ignited: full color + bloom.
          const strokeColor = isFlashWhite
            ? '#ffffff'
            : CATEGORY_COLORS[arc.category]; // always category color; opacity controls visibility

          const strokeOpacity = isFlashWhite
            ? 1
            : isFired
              ? undefined  // controlled by animate breathing
              : 0.15;

          const filterAttr = isFlashWhite
            ? `url(#${FILTER_ID_ARC_GLOW_WHITE})`
            : isFired
              ? `url(#${FILTER_ID_ARC_GLOW})`
              : undefined;

          // Stagger delay for ignition: 20ms per arc within same category
          // Find position of this arc among arcs of its category
          const categoryArcIndex = OUTER_ARCS.filter(a => a.category === arc.category).findIndex(a => a.index === arc.index);
          const igniteDelay = isFired ? categoryArcIndex * 0.02 : 0;

          return (
            <motion.path
              key={arc.index}
              d={arc.path}
              fill="none"
              stroke={strokeColor}
              strokeWidth={OUTER_STROKE_WIDTH}
              strokeLinecap="round"
              filter={filterAttr}
              strokeOpacity={strokeOpacity}
              animate={
                reduced
                  ? { strokeOpacity: isFired ? 1 : 0.15 }
                  : isFired && !isFlashWhite
                    ? {
                        // Breathing: opacity 0.85 ↔ 1.0
                        strokeOpacity: [0.85, 1.0, 0.85],
                      }
                    : isFlashWhite
                      ? { strokeOpacity: 1 }
                      : { strokeOpacity: 0.15 }
              }
              transition={
                reduced
                  ? { duration: 0 }
                  : isFired && !isFlashWhite
                    ? {
                        strokeOpacity: {
                          duration: DURATION.slow / 1000 * 5, // 2500ms arc breathing loop
                          ease: 'easeInOut',
                          repeat: Infinity,
                          delay: igniteDelay + (breathingPhaseRef.current[arc.index] / 1000),
                        },
                      }
                    : {
                        strokeOpacity: {
                          ...arcIgniteTransition,
                          delay: igniteDelay,
                        },
                      }
              }
            />
          );
        })}

        {/* ── Shockwaves on arc ignition ─────────────────────────────── */}
        {shockwaves.map((sw) => (
          <Shockwave key={sw.id} id={sw.id} cx={sw.cx} cy={sw.cy} color={sw.color} onDone={removeShockwave} />
        ))}

        {/* ── Middle ring: 8 category sectors with gradient + texture ── */}
        <motion.g
          animate={reduced ? undefined : { rotate: 360 }}
          transition={reduced ? undefined : { repeat: Infinity, duration: RING_FULL_ROT_DURATION, ease: 'linear' }}
          style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
        >
          {MIDDLE_SECTORS.map((sector) => {
            const catScore = getCatScore(sector.category);
            // Boosted opacity: 0.25 + (catScore/100)*0.6 → min 25%, max 85%
            const opacity = 0.25 + (catScore / 100) * 0.6;

            return (
              <g key={sector.index}>
                <motion.path
                  d={sector.path}
                  fill="none"
                  stroke={`url(#${GRADIENT_ID_PREFIX}${sector.index})`}
                  strokeWidth={MIDDLE_STROKE_WIDTH}
                  strokeLinecap="butt"
                  animate={{ opacity }}
                  transition={reduced ? { duration: 0 } : { duration: DURATION.normal / 1000 * 1.6 }} // 400ms sector opacity
                  style={{ opacity }}
                />
                <motion.path
                  d={sector.path}
                  fill="none"
                  stroke={`url(#${PATTERN_ID_CROSSHATCH})`}
                  strokeWidth={MIDDLE_STROKE_WIDTH}
                  strokeLinecap="butt"
                  animate={{ opacity }}
                  transition={reduced ? { duration: 0 } : { duration: DURATION.normal / 1000 * 1.6 }} // 400ms sector opacity
                  style={{ opacity }}
                />
              </g>
            );
          })}
        </motion.g>

        {/* ── Connection spokes (TYPE_A only) ────────────────────────── */}
        {/* spokesVisible stays true for 500ms after tier drops so spokes can
            fade out — but we only attach the glow filter when isTypeA is true
            to prevent the feGaussianBlur halo from bleeding outside the outer
            ring during the fade. AnimatePresence removes the g from the DOM
            after the exit animation completes. */}
        <AnimatePresence>
          {spokesVisible && !reduced && (
            <motion.g
              key="connection-spokes"
              initial={{ opacity: 0 }}
              animate={{ opacity: isTypeA ? 1 : 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: DURATION.normal / 1000 * 1.6, ease: 'easeOut' }} // 400ms spokes group fade
              style={{ pointerEvents: 'none' }}
            >
              {SPOKE_PATHS.map((spoke, i) => (
                <motion.path
                  key={`spoke-${i}`}
                  d={spoke.path}
                  fill="none"
                  stroke={spoke.hexColor}
                  strokeWidth={1.5}
                  strokeLinecap="round"
                  // Only apply glow filter when actively TYPE_A — the blur
                  // bleeds outward and can create a rogue arc outside r=150
                  filter={isTypeA ? `url(#${FILTER_ID_SPOKE_GLOW})` : undefined}
                  initial={{ opacity: 0, strokeWidth: 1.5 }}
                  animate={
                    isTypeA
                      ? (spokeBreathKeyframes as Record<string, number[]>)
                      : { opacity: 0, strokeWidth: 1.5 }
                  }
                  transition={
                    isTypeA
                      ? { ...spokeBreathTransition, delay: i * 0.05 }
                      : { duration: DURATION.normal / 1000 * 1.6, ease: 'easeOut' } // 400ms spoke fade-out
                  }
                />
              ))}
            </motion.g>
          )}
        </AnimatePresence>

        {/* ── Inner core via foreignObject ─────────────────────────── */}
        <motion.g
          animate={
            isFlashWhite || isFlashSettle
              ? { scale: typeAFlashKeyframes.scale, filter: typeAFlashKeyframes.filter }
              : levelUpActive && !reduced
                ? { scale: levelUpKeyframes.scale, filter: coreGlowFilter !== 'none' ? coreGlowFilter : undefined }
                : { scale: 1, filter: coreGlowFilter }
          }
          transition={
            (isFlashWhite || isFlashSettle) && !reduced
              ? typeAFlashTransition
              : levelUpActive && !reduced
                ? levelUpTransition
                : { duration: DURATION.normal / 1000 * 1.2 } // 300ms core filter settle
          }
          style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
        >
          {/* Ambient glow ring behind core */}
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
          <circle cx={CENTER} cy={CENTER} r={100} fill="var(--void)" />

          {/* foreignObject for text content */}
          <foreignObject x={CENTER - 100} y={CENTER - 100} width={200} height={200}>
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
              {/* Score number with threshold-cross color flash */}
              <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <motion.div
                  className={`tnum${showGlow ? ' glow-lime' : ''}`}
                  animate={
                    thresholdFlash === 'up-80' || thresholdFlash === 'up-50'
                      ? (scoreThresholdUpKeyframes as Record<string, string[] | number[]>)
                      : thresholdFlash === 'down-80' || thresholdFlash === 'down-50'
                        ? (scoreThresholdDownKeyframes as Record<string, string[] | number[]>)
                        : { color: scoreNumberColor, scale: 1 }
                  }
                  transition={
                    thresholdFlash === 'up-80' || thresholdFlash === 'up-50'
                      ? scoreThresholdUpTransition
                      : thresholdFlash === 'down-80' || thresholdFlash === 'down-50'
                        ? scoreThresholdDownTransition
                        : { duration: DURATION.fast / 1000 } // 150ms score color settle
                  }
                  style={{
                    color: scoreNumberColor,
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

                {/* Score underline — grows with score */}
                {score > 0 && (
                  <motion.div
                    style={{
                      height: '1px',
                      background: 'var(--rule-bright)',
                      marginTop: '2px',
                      originX: 0.5,
                    }}
                    animate={{ width: `${clampedUnderline}%` }}
                    transition={reduced ? { duration: 0 } : { duration: DURATION.fast / 1000, ease: 'easeOut' }} // 150ms underline grow
                    initial={{ width: '0%' }}
                  />
                )}
              </div>

              {/* Tier badge */}
              <motion.div
                animate={tier === 'TYPE_A' && !reduced ? tierBadgePulseKeyframes : { opacity: 1 }}
                transition={tier === 'TYPE_A' && !reduced ? tierBadgePulseTransition : { duration: 0 }}
                style={{
                  border: `1px solid ${tierColor(tier)}`,
                  boxShadow: tier === 'TYPE_A' || tier === 'TYPE_B' || tier === 'TYPE_C'
                    ? `0 0 6px ${tierColorHex(tier)}40, inset 0 0 4px ${tierColorHex(tier)}15`
                    : 'none',
                  // TYPE_A gets a faint lime background tint
                  background: tier === 'TYPE_A' ? 'rgba(163,255,0,0.08)' : 'transparent',
                  color: tierColor(tier),
                  padding: '2px 4px',
                  fontSize: '16px',
                  fontWeight: 600,
                  lineHeight: 1.2,
                  letterSpacing: '0.08em',
                  fontFamily: 'var(--font-jetbrains-mono), monospace',
                  display: 'inline-block',
                  whiteSpace: 'nowrap',
                }}
              >
                {tier || 'QUIET'}
              </motion.div>

              {/* Direction glyph */}
              <DirectionGlyph direction={direction ?? 0} reduced={reduced} />
            </div>
          </foreignObject>
        </motion.g>
      </svg>
    </div>
  );
}
