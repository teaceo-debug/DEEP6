/**
 * digit-roll.test.tsx
 * Unit tests for useDigitRoll, DigitRoll, useDeltaIndicator, useFlashHint.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, renderHook, waitFor } from '@testing-library/react';
import React from 'react';

// Mock motion/react — synchronous animate so no async animation needed
vi.mock('motion/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('motion/react')>();
  return {
    ...actual,
    animate: (_mv: { get: () => number; set: (v: number) => void }, target: number) => {
      _mv.set(target);
      return { stop: () => {} };
    },
    motion: {
      ...actual.motion,
      span: (props: React.HTMLAttributes<HTMLSpanElement> & { children?: React.ReactNode }) =>
        React.createElement('span', props),
    },
    AnimatePresence: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
  };
});

// Mock @/lib/animations constants used by digit-roll
vi.mock('@/lib/animations', () => ({
  harmonizedDigitRollTransition: { type: 'spring', stiffness: 120, damping: 18, mass: 1 },
  prefersReducedMotion: () => false,
  DELTA_VISIBLE_MS: 800,
  FLASH_DURATION_MS: 300,
  DURATION: { fast: 150, normal: 250, slow: 500, entrance: 800, flash: 1200 },
}));

import { sanitizeNumber, useDigitRoll, DigitRoll, useDeltaIndicator, useFlashHint } from '@/lib/digit-roll';

// ---------------------------------------------------------------------------
// sanitizeNumber — pure function, no async needed
// ---------------------------------------------------------------------------

describe('sanitizeNumber', () => {
  it('returns the value unchanged for finite numbers', () => {
    expect(sanitizeNumber(42)).toEqual({ safe: 42, invalid: false });
    expect(sanitizeNumber(-7.5)).toEqual({ safe: -7.5, invalid: false });
    expect(sanitizeNumber(0)).toEqual({ safe: 0, invalid: false });
  });

  it('returns safe=0 and invalid=true for NaN', () => {
    expect(sanitizeNumber(NaN)).toEqual({ safe: 0, invalid: true });
  });

  it('returns safe=0 and invalid=true for Infinity', () => {
    expect(sanitizeNumber(Infinity)).toEqual({ safe: 0, invalid: true });
    expect(sanitizeNumber(-Infinity)).toEqual({ safe: 0, invalid: true });
  });
});

// ---------------------------------------------------------------------------
// useDigitRoll hook — animate is mocked synchronous, so mv settles immediately
// ---------------------------------------------------------------------------

describe('useDigitRoll', () => {
  it('eventually produces the correct string for a given integer', async () => {
    const { result } = renderHook(() => useDigitRoll(42));
    await waitFor(() => {
      expect(result.current.get()).toBe('42');
    });
  });

  it('formats to the requested precision', async () => {
    const { result } = renderHook(() => useDigitRoll(42.1, 2));
    await waitFor(() => {
      expect(result.current.get()).toBe('42.10');
    });
  });
});

// ---------------------------------------------------------------------------
// DigitRoll component
// ---------------------------------------------------------------------------

describe('DigitRoll component', () => {
  it('renders the value as formatted text', async () => {
    render(<DigitRoll value={42.1} precision={2} />);
    await waitFor(() => {
      expect(screen.getByText('42.10')).toBeTruthy();
    });
  });

  it('renders "—" for NaN input', () => {
    render(<DigitRoll value={NaN} />);
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('renders "—" for Infinity input', () => {
    render(<DigitRoll value={Infinity} />);
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('renders prefix visible when provided', async () => {
    render(<DigitRoll value={5} prefix="σ " suffix="%" />);
    await waitFor(() => {
      // prefix appears in the DOM as part of the rendered span
      const el = document.body.querySelector('span');
      expect(el?.textContent).toMatch(/σ/);
    });
  });

  it('renders integer 0 as "0"', async () => {
    render(<DigitRoll value={0} />);
    await waitFor(() => {
      expect(screen.getByText('0')).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// useDeltaIndicator — uses real timers to avoid waitFor / fake-timer conflict
// ---------------------------------------------------------------------------

describe('useDeltaIndicator', () => {
  // Use real timers — useDeltaIndicator uses setTimeout(fn, 800).
  // We flush via vi.runAllTimers() inside act() for timer-dependent tests.
  beforeEach(() => { vi.useRealTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('is not visible on initial mount', () => {
    const { result } = renderHook(() => useDeltaIndicator(10));
    expect(result.current.visible).toBe(false);
  });

  it('shows ▲ after an upward value change', async () => {
    const { result, rerender } = renderHook(({ v }) => useDeltaIndicator(v), {
      initialProps: { v: 10 },
    });
    act(() => { rerender({ v: 20 }); });
    await waitFor(() => {
      expect(result.current.visible).toBe(true);
      expect(result.current.arrow).toBe('▲');
      expect(result.current.color).toBe('var(--ask)');
    });
  });

  it('shows ▼ after a downward value change', async () => {
    const { result, rerender } = renderHook(({ v }) => useDeltaIndicator(v), {
      initialProps: { v: 20 },
    });
    act(() => { rerender({ v: 10 }); });
    await waitFor(() => {
      expect(result.current.visible).toBe(true);
      expect(result.current.arrow).toBe('▼');
      expect(result.current.color).toBe('var(--bid)');
    });
  });

  it('hides indicator after 800ms (real timers)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { result, rerender } = renderHook(({ v }) => useDeltaIndicator(v), {
      initialProps: { v: 10 },
    });
    act(() => { rerender({ v: 20 }); });
    expect(result.current.visible).toBe(true);
    act(() => { vi.advanceTimersByTime(800); });
    expect(result.current.visible).toBe(false);
    vi.useRealTimers();
  });
});

// ---------------------------------------------------------------------------
// useFlashHint — same real-timer strategy
// ---------------------------------------------------------------------------

describe('useFlashHint', () => {
  beforeEach(() => { vi.useRealTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('does not flash when change is below threshold', async () => {
    const { result, rerender } = renderHook(({ v }) => useFlashHint(v, 20), {
      initialProps: { v: 50 },
    });
    act(() => { rerender({ v: 55 }); }); // delta = 5 < threshold 20
    expect(result.current.flashing).toBe(false);
  });

  it('flashes when absolute change meets or exceeds threshold', async () => {
    const { result, rerender } = renderHook(({ v }) => useFlashHint(v, 20), {
      initialProps: { v: 50 },
    });
    act(() => { rerender({ v: 75 }); }); // delta = 25 >= 20
    expect(result.current.flashing).toBe(true);
    expect(result.current.direction).toBe('up');
  });

  it('reports direction "down" when value decreases past threshold', async () => {
    const { result, rerender } = renderHook(({ v }) => useFlashHint(v, 20), {
      initialProps: { v: 80 },
    });
    act(() => { rerender({ v: 50 }); }); // delta = -30, abs = 30 >= 20
    expect(result.current.flashing).toBe(true);
    expect(result.current.direction).toBe('down');
  });

  it('stops flashing after FLASH_DURATION_MS (300ms)', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { result, rerender } = renderHook(({ v }) => useFlashHint(v, 20), {
      initialProps: { v: 50 },
    });
    act(() => { rerender({ v: 80 }); });
    expect(result.current.flashing).toBe(true);
    act(() => { vi.advanceTimersByTime(300); });
    expect(result.current.flashing).toBe(false);
    vi.useRealTimers();
  });
});
