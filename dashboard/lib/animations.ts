/**
 * dashboard/lib/animations.ts
 * Shared Motion variants and helpers for DEEP6 Terminal Noir (UI-SPEC v2 §5).
 * All motion respects prefers-reduced-motion — use prefersReducedMotion() wrapper.
 */

// ---------------------------------------------------------------------------
// Unified animation tokens (UI-SPEC v2 §5 — animation vocabulary)
//
// Usage:
//   import { DURATION, EASING, SPRING } from '@/lib/animations';
//   transition={{ duration: DURATION.normal / 1000, ease: EASING.standard }}
//   transition={{ type: 'spring', ...SPRING.snap }}
// ---------------------------------------------------------------------------

/** Duration in milliseconds. Divide by 1000 for framer-motion `duration`. */
export const DURATION = {
  fast:     150,  // microinteractions: hover, click feedback
  normal:   250,  // state transitions: tier change, direction flip
  slow:     500,  // emphasis: digit roll, sparkline update
  entrance: 800,  // new element arrivals: signal row, bar append
  flash:    1200, // TYPE_A decay tail
} as const;

/**
 * Easing cubic-bezier tuples for framer-motion `ease` prop.
 * Also works as CSS `transition-timing-function` values via string form.
 */
export const EASING = {
  standard: [0.4, 0, 0.2, 1] as const,   // Material standard ease
  enter:    [0, 0, 0.2, 1] as const,     // Decelerate (elements entering)
  exit:     [0.4, 0, 1, 1] as const,     // Accelerate (elements leaving)
  spring:   [0.16, 1, 0.3, 1] as const,  // Slight overshoot (digit rolls)
  bounce:   [0.34, 1.56, 0.64, 1] as const, // Overshoot for celebration (threshold cross)
} as const;

/** Spring physics presets for framer-motion `type: 'spring'` transitions. */
export const SPRING = {
  soft: { stiffness: 120, damping: 22 },  // gentle settle (digit roll, bar fill)
  snap: { stiffness: 200, damping: 25 },  // crisp state transition (tier, direction)
  pop:  { stiffness: 300, damping: 20 },  // energetic appear (overlay pill, glyph flip)
} as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CategoryKey =
  | 'absorption'
  | 'exhaustion'
  | 'imbalance'
  | 'delta'
  | 'auction'
  | 'trap'
  | 'volume'
  | 'ml';

// ---------------------------------------------------------------------------
// Digit-roll transition — spring physics for satisfying settle (UI-SPEC §5)
// Maps to: DURATION.slow + EASING.spring (soft spring variant)
// ---------------------------------------------------------------------------

export const digitRollTransition = {
  type: 'spring' as const,
  stiffness: SPRING.soft.stiffness,  // 120
  damping: 18,
  mass: 1,
} as const;

// ---------------------------------------------------------------------------
// Arc ignite transition (UI-SPEC §5 — 200ms cubic-bezier)
// ---------------------------------------------------------------------------

export const arcIgniteTransition = {
  duration: DURATION.normal / 1000, // 0.25s — EASING.standard
  ease: EASING.standard as [number, number, number, number],
} as const;

/**
 * arcStagger — stagger delay in seconds for arc index i (15ms × i).
 */
export function arcStagger(i: number): number {
  return i * 0.015;
}

// ---------------------------------------------------------------------------
// TYPE_A flash keyframes (UI-SPEC §4.1 / §5)
// Phase 1 (0-120ms):   all arcs → #ffffff, core intensifies 3x
// Phase 2 (120-400ms): arcs settle to category color + slight scale
// Phase 3 (400-1500ms): aftershock radial expansion, secondary glow decay
// ---------------------------------------------------------------------------

/** Motion `animate` prop for the inner core <g> element. */
export const typeAFlashKeyframes: {
  scale: number[];
  filter: string[];
} = {
  scale: [1, 1.04, 1.0, 1],
  filter: [
    // Normal lime glow
    'drop-shadow(0 0 4px color-mix(in oklch, #a3ff00 80%, transparent)) drop-shadow(0 0 12px color-mix(in oklch, #a3ff00 40%, transparent))',
    // White-hot intensified (120ms mark) — 3× glow
    'drop-shadow(0 0 12px rgba(255,255,255,0.95)) drop-shadow(0 0 40px rgba(255,255,255,0.7)) drop-shadow(0 0 80px rgba(163,255,0,0.9))',
    // Bright lime settle (400ms mark)
    'drop-shadow(0 0 8px rgba(163,255,0,0.9)) drop-shadow(0 0 24px rgba(163,255,0,0.5)) drop-shadow(0 0 48px rgba(163,255,0,0.3))',
    // Final settled lime glow (1500ms mark)
    'drop-shadow(0 0 4px color-mix(in oklch, #a3ff00 80%, transparent)) drop-shadow(0 0 12px color-mix(in oklch, #a3ff00 40%, transparent))',
  ],
};

export const typeAFlashTransition = {
  duration: 1.5,
  ease: 'easeOut' as const,
  times: [0, 0.08, 0.267, 1], // 0ms / 120ms / 400ms / 1500ms
};

// ---------------------------------------------------------------------------
// Radial bloom keyframes (UI-SPEC §4.1 TYPE_A flash — primary bloom)
// Expands from r=90 to r=200, opacity 0.3 → 0, over 1200ms
// ---------------------------------------------------------------------------

export const radialBloomKeyframes: {
  r: number[];
  opacity: number[];
} = {
  r: [90, 200],
  opacity: [0.3, 0],
};

export const radialBloomTransition = {
  duration: DURATION.flash / 1000, // 1.2s → flash token (close enough; TYPE_A decay tail)
  ease: 'easeOut' as const,
};

// ---------------------------------------------------------------------------
// Aftershock bloom (phase 3 of TYPE_A) — 400ms delay, 1100ms duration
// Slower, wider, dimmer — a secondary echo after the main flash settles
// ---------------------------------------------------------------------------

export const aftershockBloomKeyframes: {
  r: number[];
  opacity: number[];
} = {
  r: [100, 300],
  opacity: [0.3, 0],
};

export const aftershockBloomTransition = {
  duration: 1.1,
  ease: 'easeOut' as const,
  delay: 0.4,
};

// ---------------------------------------------------------------------------
// Background flash keyframes (the lime ambient glow behind the pulse)
// ---------------------------------------------------------------------------

export const backgroundFlashKeyframes: {
  opacity: number[];
  scale: number[];
} = {
  opacity: [0, 0.22, 0],
  scale: [0.6, 1, 1.4],
};

export const backgroundFlashTransition = {
  duration: 1.4,
  ease: 'easeOut' as const,
  times: [0, 0.1, 1],
};

// ---------------------------------------------------------------------------
// Arc flash — white hot 120ms, then transition for arcs during TYPE_A
// ---------------------------------------------------------------------------

export const arcFlashTransition = {
  duration: 0.12, // intentional: white-hot phase is 120ms fixed (not a token)
  ease: EASING.standard as [number, number, number, number],
};

export const arcSettleTransition = {
  duration: DURATION.normal / 1000, // 0.25s — state transition after flash
  ease: EASING.standard as [number, number, number, number],
  delay: 0.12,
};

// ---------------------------------------------------------------------------
// Direction glyph flip transition — 200ms with spring for tactile feel
// ---------------------------------------------------------------------------

export const directionFlipTransition = {
  type: 'spring' as const,
  ...SPRING.pop,  // stiffness:300, damping:20 — energetic glyph flip
  mass: 0.8,
};

// ---------------------------------------------------------------------------
// Threshold cross ("level up") — scale 1→1.04→1, 250ms ease-out-back
// ---------------------------------------------------------------------------

export const levelUpKeyframes = {
  scale: [1, 1.04, 1],
};

export const levelUpTransition = {
  duration: DURATION.normal / 1000, // 0.25s — EASING.bounce (ease-out-back)
  ease: EASING.bounce as [number, number, number, number],
};

// ---------------------------------------------------------------------------
// Scanning arc (loading/zero state) — single arc rotating around ring
// 1 revolution per 4 seconds
// ---------------------------------------------------------------------------

export const scanTransition = {
  repeat: Infinity,
  duration: 4,
  ease: 'linear' as const,
};

// ---------------------------------------------------------------------------
// Tier badge pulse border — only for TYPE_A active
// ---------------------------------------------------------------------------

export const tierBadgePulseKeyframes = {
  opacity: [1, 0.4, 1],
};

export const tierBadgePulseTransition = {
  duration: 1.8,
  ease: 'easeInOut' as const,
  repeat: Infinity,
};

// ---------------------------------------------------------------------------
// reducedMotion — returns a zero-duration / no-op variant when user prefers
// reduced motion. Intended for "use client" contexts.
// ---------------------------------------------------------------------------

/**
 * Returns true if the user has requested reduced motion.
 * Safe to call in browser only (returns false on server / during SSR).
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * reducedMotion — wraps a variant object, overriding `transition.duration`
 * to 0 and removing filter/scale animations when reduced motion is active.
 */
export function reducedMotion<T extends object>(variant: T): T {
  if (!prefersReducedMotion()) return variant;
  return {
    ...variant,
    transition: { duration: 0 },
  };
}

// ---------------------------------------------------------------------------
// SIGNAL_BIT_CATEGORIES — canonical 44-bit → category mapping
// Source: deep6/signals/flags.py
//
//   ABS  (Absorption):  bits  0-3   (4 signals: ABS-01..04)
//   EXH  (Exhaustion):  bits  4-11  (8 signals: EXH-01..08)
//   IMB  (Imbalance):   bits 12-20  (9 signals: IMB-01..09)
//   DELT (Delta):       bits 21-31  (11 signals: DELT-01..11)
//   AUCT (Auction):     bits 32-36  (5 signals: AUCT-01..05)
//   TRAP (Trap):        bits 37-41  (5 signals: TRAP-01..05)
//   VOLP (Volume):      bits 42-43  (2 signals: VOLP-01..02)
//
// Total: 4 + 8 + 9 + 11 + 5 + 5 + 2 = 44
// ---------------------------------------------------------------------------

export const SIGNAL_BIT_CATEGORIES: ReadonlyArray<CategoryKey> = Object.freeze([
  // bits 0-3 — Absorption (ABS-01..04)
  'absorption', 'absorption', 'absorption', 'absorption',
  // bits 4-11 — Exhaustion (EXH-01..08)
  'exhaustion', 'exhaustion', 'exhaustion', 'exhaustion',
  'exhaustion', 'exhaustion', 'exhaustion', 'exhaustion',
  // bits 12-20 — Imbalance (IMB-01..09)
  'imbalance', 'imbalance', 'imbalance', 'imbalance', 'imbalance',
  'imbalance', 'imbalance', 'imbalance', 'imbalance',
  // bits 21-31 — Delta (DELT-01..11)
  'delta', 'delta', 'delta', 'delta', 'delta', 'delta',
  'delta', 'delta', 'delta', 'delta', 'delta',
  // bits 32-36 — Auction (AUCT-01..05)
  'auction', 'auction', 'auction', 'auction', 'auction',
  // bits 37-41 — Trapped Traders (TRAP-01..05)
  'trap', 'trap', 'trap', 'trap', 'trap',
  // bits 42-43 — Volume Patterns (VOLP-01..02)
  'volume', 'volume',
]) as ReadonlyArray<CategoryKey>;

// ---------------------------------------------------------------------------
// signalRowArrival — clip-path + bg-flash + glow for TYPE_A signal row
// UI-SPEC §4.3 / §5: 320ms reveal, 800ms flash, 1200ms glow
// ---------------------------------------------------------------------------

/** Initial state for a newly-arrived TYPE_A row (pre-animation). */
export const signalRowArrivalInitial = {
  clipPath: 'inset(0 100% 0 0)',
  backgroundColor: 'rgba(163,255,0,0)',
  filter: 'drop-shadow(0 0 0px rgba(163,255,0,0))',
} as const;

/** animate prop — drives all three phases. */
export const signalRowArrivalAnimate = {
  clipPath: 'inset(0 0% 0 0)',
  backgroundColor: ['rgba(163,255,0,0.2)', 'rgba(163,255,0,0)'],
  filter: [
    'drop-shadow(0 0 8px rgba(163,255,0,0.5))',
    'drop-shadow(0 0 0px rgba(163,255,0,0))',
  ],
} as const;

export const signalRowArrivalTransition = {
  clipPath: { duration: DURATION.entrance / 1000 * 0.4, ease: EASING.spring as [number, number, number, number] }, // ~320ms entrance spring
  backgroundColor: { duration: DURATION.slow / 1000 * 1.6, ease: 'easeOut' as const }, // ~800ms
  filter: { duration: DURATION.flash / 1000, ease: 'easeOut' as const }, // 1200ms flash decay
} as const;

// ---------------------------------------------------------------------------
// Score threshold cross flash — visible color flicker when crossing 50 or 80
// 79→80: flash amber → lime over 200ms (upgrade)
// 80→79: flash lime → amber over 300ms (slower decline)
// ---------------------------------------------------------------------------

export const scoreThresholdUpKeyframes: { color: string[]; scale: number[] } = {
  color: ['#ffd60a', '#ffd60a', '#a3ff00'],
  scale: [1, 1.06, 1],
};

export const scoreThresholdUpTransition = {
  duration: DURATION.normal / 1000, // 0.25s — threshold cross upgrade flash
  ease: 'easeOut' as const,
  times: [0, 0.15, 1],
};

export const scoreThresholdDownKeyframes: { color: string[]; scale: number[] } = {
  color: ['#a3ff00', '#a3ff00', '#ffd60a'],
  scale: [1, 1.02, 1],
};

export const scoreThresholdDownTransition = {
  duration: DURATION.normal / 1000 * 1.2, // 0.3s — slightly slower decline
  ease: 'easeOut' as const,
  times: [0, 0.1, 1],
};

// ---------------------------------------------------------------------------
// Connection spoke pulse — TYPE_A radial spokes breathe 2s repeat
// ---------------------------------------------------------------------------

export const spokeBreathKeyframes: { opacity: number[]; strokeWidth: number[] } = {
  opacity: [0.4, 0.6, 0.4],  // max 0.6 — spokes are structural, not focal
  strokeWidth: [1.5, 2.0, 1.5],
};

export const spokeBreathTransition = {
  duration: 2,
  ease: 'easeInOut' as const,
  repeat: Infinity,
};

// ---------------------------------------------------------------------------
// Direction glyph halo — 2px glow that dissipates 400ms after direction change
// ---------------------------------------------------------------------------

export const directionHaloKeyframes: { opacity: number[]; scale: number[] } = {
  opacity: [0, 0.8, 0],
  scale: [0.8, 1.2, 1.4],
};

export const directionHaloTransition = {
  duration: DURATION.normal / 1000 * 1.6, // 0.4s — direction halo dissipation
  ease: 'easeOut' as const,
};

// ---------------------------------------------------------------------------
// Direction cross-flash — brief white cross when crossing zero (LONG↔SHORT)
// ---------------------------------------------------------------------------

export const directionCrossKeyframes: { opacity: number[]; scale: number[] } = {
  opacity: [0, 1, 0],
  scale: [0.6, 1, 1.5],
};

export const directionCrossTransition = {
  duration: DURATION.normal / 1000, // 0.25s — cross-flash on polarity flip
  ease: 'easeOut' as const,
};

// Verify at module load (development guard)
if (process.env.NODE_ENV !== 'production') {
  if (SIGNAL_BIT_CATEGORIES.length !== 44) {
    throw new Error(
      `[animations.ts] SIGNAL_BIT_CATEGORIES must have 44 entries; got ${SIGNAL_BIT_CATEGORIES.length}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Category color mapping (UI-SPEC §4.1 / plan interfaces)
// Uses CSS custom property names — resolved at render time.
// ---------------------------------------------------------------------------

export const CATEGORY_COLORS: Readonly<Record<CategoryKey, string>> = Object.freeze({
  absorption: 'var(--lime)',
  exhaustion:  'var(--lime)',
  imbalance:   'var(--cyan)',
  delta:       'var(--amber)',
  auction:     'var(--cyan)',
  volume:      'var(--amber)',
  trap:        'var(--bid)',
  ml:          'var(--magenta)',
});

// Hex values for use in SVG gradients/filters (CSS vars don't resolve in SVG defs)
export const CATEGORY_COLORS_HEX: Readonly<Record<CategoryKey, string>> = Object.freeze({
  absorption: '#a3ff00',
  exhaustion:  '#a3ff00',
  imbalance:   '#00d9ff',
  delta:       '#ffd60a',
  auction:     '#00d9ff',
  volume:      '#ffd60a',
  trap:        '#ff2e63',
  ml:          '#ff00aa',
});

// ---------------------------------------------------------------------------
// Category arc sizes (number of arcs per category — must sum to 44)
// ---------------------------------------------------------------------------
export const CATEGORY_ARC_COUNTS: Readonly<Record<CategoryKey, number>> = Object.freeze({
  absorption: 4,
  exhaustion: 8,
  imbalance:  9,
  delta:      11,
  auction:    5,
  trap:       5,
  volume:     2,
  ml:         0, // ML (E10) is not a bit-signal; handled via Kronos separately
});
