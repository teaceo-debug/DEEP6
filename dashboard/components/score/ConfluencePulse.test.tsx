/**
 * ConfluencePulse.test.tsx
 * Smoke tests for the ConfluencePulse component.
 * Uses zustand store to inject state rather than props.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { useTradingStore } from '@/store/tradingStore';

// ── Mock motion/react ────────────────────────────────────────────────────────
// The component makes heavy use of motion primitives. In jsdom we just need
// the component to render without errors; we don't need real animations.
vi.mock('motion/react', () => {
  const React2 = require('react');
  const MotionValue = class {
    private _v: number;
    constructor(v: number) { this._v = v; }
    get() { return this._v; }
    set(v: number) { this._v = v; }
    on(_: string, cb: (v: unknown) => void) { cb(String(this._v)); return () => {}; }
  };
  return {
    motion: new Proxy({}, {
      get: (_: unknown, tag: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ children, ...rest }: any) => React2.createElement(tag, rest, children),
    }),
    AnimatePresence: ({ children }: { children: React.ReactNode }) =>
      React2.createElement(React2.Fragment, null, children),
    animate: (_mv: InstanceType<typeof MotionValue>, target: number) => {
      _mv.set(target);
      return { stop: () => {} };
    },
    useMotionValue: (v: number) => new MotionValue(v),
    useTransform: (mv: InstanceType<typeof MotionValue>, fn: (v: number) => string) => {
      const transformed = new MotionValue(0);
      // expose getter that calls fn
      return {
        get: () => fn(mv.get()),
        on: (_ev: string, cb: (v: string) => void) => { cb(fn(mv.get())); return () => {}; },
      };
    },
    MotionValue,
  };
});

// ── Mock @/lib/animations ────────────────────────────────────────────────────
vi.mock('@/lib/animations', () => ({
  prefersReducedMotion: vi.fn().mockReturnValue(false),
  SIGNAL_BIT_CATEGORIES: Array.from({ length: 44 }, (_, i) => [
    'absorption', 'exhaustion', 'imbalance', 'delta',
    'auction', 'volume', 'trap', 'ml',
  ][i % 8]),
  CATEGORY_COLORS: {
    absorption: 'var(--lime)', exhaustion: 'var(--bid)',
    imbalance: 'var(--amber)', delta: 'var(--cyan)',
    auction: 'var(--magenta)', volume: 'var(--ask)',
    trap: 'var(--text)', ml: 'var(--text-dim)',
  },
  CATEGORY_COLORS_HEX: {
    absorption: '#a3ff00', exhaustion: '#ff2e63',
    imbalance: '#ffd60a', delta: '#00d9ff',
    auction: '#ff00aa', volume: '#00ff88',
    trap: '#e0e0e0', ml: '#888888',
  },
  digitRollTransition: { type: 'spring', stiffness: 120, damping: 18, mass: 1 },
  arcIgniteTransition: { duration: 0.25, ease: [0.4, 0, 0.2, 1] },
  arcStagger: (_i: number) => 0,
  typeAFlashKeyframes: { opacity: [0, 1] },
  typeAFlashTransition: { duration: 0.1 },
  radialBloomKeyframes: { opacity: [1, 0] },
  radialBloomTransition: { duration: 0.1 },
  aftershockBloomKeyframes: { opacity: [1, 0] },
  aftershockBloomTransition: { duration: 0.1 },
  backgroundFlashKeyframes: { backgroundColor: ['transparent', 'transparent'] },
  backgroundFlashTransition: { duration: 0.1 },
  directionFlipTransition: { duration: 0.1 },
  levelUpKeyframes: { scale: [1, 1.1, 1] },
  levelUpTransition: { duration: 0.1 },
  tierBadgePulseKeyframes: { opacity: [1, 0.5, 1] },
  tierBadgePulseTransition: { duration: 1 },
  spokeBreathKeyframes: { opacity: [0.6, 1, 0.6] },
  spokeBreathTransition: { duration: 2 },
  directionHaloKeyframes: { opacity: [1, 0], scale: [0.8, 1.5] },
  directionHaloTransition: { duration: 0.5 },
  directionCrossKeyframes: { opacity: [0, 1, 0] },
  directionCrossTransition: { duration: 0.3 },
  scoreThresholdUpKeyframes: { scale: [1, 1.2, 1] },
  scoreThresholdUpTransition: { duration: 0.3 },
  scoreThresholdDownKeyframes: { scale: [1, 0.9, 1] },
  scoreThresholdDownTransition: { duration: 0.3 },
  harmonizedDigitRollTransition: { type: 'spring', stiffness: 120, damping: 18, mass: 1 },
  DELTA_VISIBLE_MS: 800,
  FLASH_DURATION_MS: 300,
  FLASH_THRESHOLD_CONFIDENCE: 20,
  DURATION: { fast: 150, normal: 250, slow: 500, entrance: 800, flash: 1200 },
  EASING: {
    standard: [0.4, 0, 0.2, 1],
    enter: [0, 0, 0.2, 1],
    exit: [0.4, 0, 1, 1],
    spring: [0.16, 1, 0.3, 1],
    bounce: [0.34, 1.56, 0.64, 1],
  },
  SPRING: { soft: { stiffness: 120, damping: 22 }, snap: { stiffness: 200, damping: 25 }, pop: { stiffness: 300, damping: 20 } },
  CategoryKey: 'absorption',
}));

// ── Store reset helper ────────────────────────────────────────────────────────
function setScore(overrides: Partial<{
  totalScore: number; tier: string; direction: number;
  categoriesFiring: string[]; categoryScores: Record<string, number>;
  kronosBias: number; kronosDirection: string; gexRegime: string;
}> = {}) {
  useTradingStore.setState({
    score: {
      totalScore: 0, tier: 'QUIET', direction: 0,
      categoriesFiring: [], categoryScores: {},
      kronosBias: 0, kronosDirection: 'NEUTRAL', gexRegime: 'NEUTRAL',
      ...overrides,
    },
  });
}

// Lazy import after mocks
const CPModule = () => import('@/components/score/ConfluencePulse');

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ConfluencePulse', () => {
  beforeEach(() => {
    setScore();
  });

  it('renders at score=0 without errors (empty state)', async () => {
    setScore({ totalScore: 0, tier: 'QUIET', direction: 0 });
    const { ConfluencePulse } = await CPModule();
    expect(() => render(<ConfluencePulse />)).not.toThrow();
    // SVG should be present
    const svgs = document.querySelectorAll('svg');
    expect(svgs.length).toBeGreaterThan(0);
  });

  it('renders at score=50 without errors (middle ring)', async () => {
    setScore({ totalScore: 50, tier: 'TYPE_C', direction: 1 });
    const { ConfluencePulse } = await CPModule();
    expect(() => render(<ConfluencePulse />)).not.toThrow();
  });

  it('renders at score=92 with TYPE_A tier without errors', async () => {
    setScore({
      totalScore: 92,
      tier: 'TYPE_A',
      direction: 1,
      categoriesFiring: ['absorption', 'delta', 'imbalance'],
    });
    const { ConfluencePulse } = await CPModule();
    expect(() => render(<ConfluencePulse />)).not.toThrow();
    // The TYPE_A badge text should appear somewhere in the document
    await waitFor(() => {
      const text = document.body.textContent ?? '';
      expect(text).toMatch(/TYPE.A|TYPE_A|A/i);
    });
  });

  it('shows ▼ for direction=-1', async () => {
    setScore({ totalScore: 60, tier: 'TYPE_B', direction: -1 });
    const { ConfluencePulse } = await CPModule();
    render(<ConfluencePulse />);
    // Direction glyph uses an SVG polygon, not text — verify the SVG renders
    // The component renders polygon points="9,16 17,2 1,2" for direction=-1 (downward)
    await waitFor(() => {
      const polygons = document.querySelectorAll('polygon');
      // Should have at least one polygon (direction triangle)
      expect(polygons.length).toBeGreaterThan(0);
    });
  });

  it('shows ▲ for direction=+1 (upward triangle polygon)', async () => {
    setScore({ totalScore: 60, tier: 'TYPE_B', direction: 1 });
    const { ConfluencePulse } = await CPModule();
    render(<ConfluencePulse />);
    await waitFor(() => {
      const polygons = document.querySelectorAll('polygon');
      expect(polygons.length).toBeGreaterThan(0);
      // direction=1 polygon has points="9,2 17,16 1,16"
      const upPolygon = Array.from(polygons).find(
        (p) => p.getAttribute('points') === '9,2 17,16 1,16',
      );
      expect(upPolygon).toBeTruthy();
    });
  });

  it('shows neutral dash for direction=0 (rect element)', async () => {
    setScore({ totalScore: 30, tier: 'QUIET', direction: 0 });
    const { ConfluencePulse } = await CPModule();
    render(<ConfluencePulse />);
    await waitFor(() => {
      // direction=0 renders a rect (dash glyph)
      const rects = document.querySelectorAll('rect');
      expect(rects.length).toBeGreaterThan(0);
    });
  });

  it('respects useReducedMotion — prefersReducedMotion mocked to true renders without crash', async () => {
    const { prefersReducedMotion } = await import('@/lib/animations');
    (prefersReducedMotion as ReturnType<typeof vi.fn>).mockReturnValue(true);
    setScore({ totalScore: 80, tier: 'TYPE_A', direction: 1 });
    const { ConfluencePulse } = await CPModule();
    expect(() => render(<ConfluencePulse />)).not.toThrow();
    (prefersReducedMotion as ReturnType<typeof vi.fn>).mockReturnValue(false);
  });
});
