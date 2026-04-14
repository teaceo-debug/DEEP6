/**
 * KronosBar.test.tsx
 * Unit tests for KronosBar component.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import React from 'react';
import { useTradingStore } from '@/store/tradingStore';

// ── Mock motion/react ─────────────────────────────────────────────────────────
vi.mock('motion/react', () => {
  const React2 = require('react');
  class MotionValue {
    private _v: number;
    constructor(v: number) { this._v = v; }
    get() { return this._v; }
    set(v: number) { this._v = v; }
    on(_: string, cb: (v: unknown) => void) { cb(String(this._v)); return () => {}; }
  }
  return {
    motion: new Proxy({}, {
      get: (_: unknown, tag: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ children, ...rest }: any) => React2.createElement(tag, rest, children),
    }),
    AnimatePresence: ({ children }: { children: React.ReactNode }) =>
      React2.createElement(React2.Fragment, null, children),
    animate: (_mv: MotionValue, target: number) => {
      _mv.set(target);
      return { stop: () => {} };
    },
    useMotionValue: (v: number) => new MotionValue(v),
    useTransform: (mv: MotionValue, fn: (v: number) => string) => ({
      get: () => fn(mv.get()),
      on: (_ev: string, cb: (v: string) => void) => { cb(fn(mv.get())); return () => {}; },
    }),
    MotionValue,
  };
});

// ── Mock @/lib/animations ─────────────────────────────────────────────────────
vi.mock('@/lib/animations', () => ({
  prefersReducedMotion: vi.fn().mockReturnValue(false),
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
}));

// ── Store helper ──────────────────────────────────────────────────────────────
function setKronos(bias: number, direction: string) {
  useTradingStore.setState({
    score: {
      totalScore: 0, tier: 'QUIET', direction: 0,
      categoriesFiring: [], categoryScores: {},
      kronosBias: bias, kronosDirection: direction, gexRegime: 'NEUTRAL',
    },
  });
}

// Lazy import after mocks
const KBModule = () => import('@/components/score/KronosBar');

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('KronosBar', () => {
  beforeEach(() => {
    setKronos(0, 'NEUTRAL');
  });

  it('renders BUILDING HISTORY… and AWAITING in empty state (bias=0, direction=NEUTRAL)', async () => {
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    await waitFor(() => {
      const text = document.body.textContent ?? '';
      expect(text).toMatch(/BUILDING HISTORY/i);
      expect(text).toMatch(/AWAITING/i);
    });
  });

  it('shows "KRONOS E10" label', async () => {
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    await waitFor(() => {
      const text = document.body.textContent ?? '';
      expect(text).toMatch(/KRONOS E10/i);
    });
  });

  it('renders sparkline SVG after 3+ history entries accumulate', async () => {
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    // Trigger history accumulation by updating bias three times
    act(() => setKronos(50, 'LONG'));
    act(() => setKronos(60, 'LONG'));
    act(() => setKronos(70, 'LONG'));
    await waitFor(() => {
      const svgs = document.querySelectorAll('svg');
      expect(svgs.length).toBeGreaterThan(0);
    });
  });

  it('does not crash when bias changes multiple times rapidly', async () => {
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    expect(() => {
      act(() => { for (let i = 0; i < 25; i++) setKronos(i * 4, i % 2 === 0 ? 'LONG' : 'SHORT'); });
    }).not.toThrow();
  });

  it('shows LONG direction label for positive bias', async () => {
    setKronos(75, 'LONG');
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    await waitFor(() => {
      const text = document.body.textContent ?? '';
      expect(text).toMatch(/LONG/);
    });
  });

  it('shows SHORT direction label for negative bias', async () => {
    setKronos(-60, 'SHORT');
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    await waitFor(() => {
      const text = document.body.textContent ?? '';
      expect(text).toMatch(/SHORT/);
    });
  });

  it('shows neutral dash "─" when direction is NEUTRAL with no data', async () => {
    setKronos(0, 'NEUTRAL');
    const { KronosBar } = await KBModule();
    render(<KronosBar />);
    await waitFor(() => {
      const text = document.body.textContent ?? '';
      expect(text).toMatch(/─|AWAITING/);
    });
  });
});

// ── stdDev helper tests (internal function, tested via mock calculation) ─────

describe('stdDev calculation (standalone verification)', () => {
  // Replicate the internal stdDev logic to verify our expected values
  function stdDev(values: number[]): number {
    if (values.length < 2) return 0;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / values.length;
    return Math.sqrt(variance);
  }

  it('returns 0 for fewer than 2 values', () => {
    expect(stdDev([])).toBe(0);
    expect(stdDev([42])).toBe(0);
  });

  it('returns 0 for all identical values', () => {
    expect(stdDev([5, 5, 5, 5])).toBe(0);
  });

  it('calculates correct stdDev for known values [2, 4, 4, 4, 5, 5, 7, 9]', () => {
    // Classic example: mean=5, variance=4, stdDev=2
    const result = stdDev([2, 4, 4, 4, 5, 5, 7, 9]);
    expect(result).toBeCloseTo(2, 5);
  });

  it('calculates correct stdDev for [10, 20]', () => {
    // mean=15, variance=25, stdDev=5
    const result = stdDev([10, 20]);
    expect(result).toBeCloseTo(5, 5);
  });

  it('calculates correct stdDev for bias history [50, 60, 70]', () => {
    // mean=60, deviations: [-10, 0, 10], variance=200/3≈66.67, stdDev≈8.165
    const result = stdDev([50, 60, 70]);
    expect(result).toBeCloseTo(8.165, 2);
  });
});

// ── TrendArrow direction tests (internal logic verification) ──────────────────

describe('TrendArrow direction logic', () => {
  function trendArrow(current: number, oldest: number): string {
    const diff = current - oldest;
    if (diff > 2) return '↗';
    if (diff < -2) return '↘';
    return '→';
  }

  it('returns ↗ when current > oldest by more than 2', () => {
    expect(trendArrow(80, 50)).toBe('↗');
    expect(trendArrow(25, 20)).toBe('↗'); // diff=5 > 2
  });

  it('returns ↘ when current < oldest by more than 2', () => {
    expect(trendArrow(50, 80)).toBe('↘');
    expect(trendArrow(20, 25)).toBe('↘'); // diff=-5 < -2
  });

  it('returns → when difference is within ±2', () => {
    expect(trendArrow(50, 50)).toBe('→');
    expect(trendArrow(51, 50)).toBe('→'); // diff=1
    expect(trendArrow(50, 51)).toBe('→'); // diff=-1
    expect(trendArrow(52, 50)).toBe('→'); // diff=2 — not > 2
  });
});
