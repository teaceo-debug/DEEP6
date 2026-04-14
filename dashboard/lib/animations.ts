/**
 * dashboard/lib/animations.ts
 * Shared Motion variants and helpers for DEEP6 Terminal Noir (UI-SPEC v2 §5).
 * All motion respects prefers-reduced-motion — use reducedMotion() wrapper.
 */

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
// Digit-roll transition (UI-SPEC §5 — 600ms ease-out)
// ---------------------------------------------------------------------------

export const digitRollTransition = {
  duration: 0.6,
  ease: [0.16, 1, 0.3, 1] as [number, number, number, number],
} as const;

// ---------------------------------------------------------------------------
// Arc ignite transition (UI-SPEC §5 — 200ms cubic-bezier)
// ---------------------------------------------------------------------------

export const arcIgniteTransition = {
  duration: 0.2,
  ease: [0.4, 0, 0.2, 1] as [number, number, number, number],
} as const;

/**
 * arcStagger — stagger delay in seconds for arc index i (15ms × i).
 */
export function arcStagger(i: number): number {
  return i * 0.015;
}

// ---------------------------------------------------------------------------
// TYPE_A flash keyframes (UI-SPEC §4.1 / §5)
// Total: 200ms white-hot flash + 1200ms decay = 1400ms
// ---------------------------------------------------------------------------

/** Motion `animate` prop for the inner core <g> element. */
export const typeAFlashKeyframes: {
  scale: number[];
  filter: string[];
} = {
  scale: [1, 1.08, 1],
  filter: [
    // Normal state
    'drop-shadow(0 0 4px color-mix(in oklch, #a3ff00 80%, transparent)) drop-shadow(0 0 12px color-mix(in oklch, #a3ff00 40%, transparent))',
    // White-hot intensified (200ms mark)
    'drop-shadow(0 0 8px rgba(255,255,255,0.9)) drop-shadow(0 0 32px rgba(255,255,255,0.6)) drop-shadow(0 0 64px rgba(163,255,0,0.8))',
    // Settled lime glow (1400ms mark)
    'drop-shadow(0 0 4px color-mix(in oklch, #a3ff00 80%, transparent)) drop-shadow(0 0 12px color-mix(in oklch, #a3ff00 40%, transparent))',
  ],
};

export const typeAFlashTransition = {
  duration: 1.4,
  ease: 'easeOut' as const,
  times: [0, 0.143, 1], // 0ms / 200ms / 1400ms mapped to [0, 1]
};

// ---------------------------------------------------------------------------
// Radial bloom keyframes (UI-SPEC §4.1 TYPE_A flash step 3)
// Expands from r=90 to r=200, opacity 0.3 → 0, over 1200ms
// ---------------------------------------------------------------------------

/** Motion `animate` prop for the bloom <circle>. */
export const radialBloomKeyframes: {
  r: number[];
  opacity: number[];
} = {
  r: [90, 200],
  opacity: [0.3, 0],
};

export const radialBloomTransition = {
  duration: 1.2,
  ease: 'easeOut' as const,
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
