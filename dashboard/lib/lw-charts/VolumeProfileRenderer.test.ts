/**
 * VolumeProfileRenderer.test.ts
 * Unit tests for aggregateProfile() in VolumeProfileRenderer.ts
 */

import { describe, it, expect } from 'vitest';
import { aggregateProfile } from './VolumeProfileRenderer';

// Helper: build a bar with given levels map
function makeBar(levels: Record<string, { bid_vol: number; ask_vol: number }>) {
  return { levels };
}

describe('VolumeProfileRenderer — aggregateProfile', () => {
  it('returns empty profile for empty bars array', () => {
    const result = aggregateProfile([]);
    expect(result.levels).toHaveLength(0);
    expect(result.maxTotal).toBe(0);
    expect(result.pocPrice).toBe(0);
    expect(result.cumBid).toBe(0);
    expect(result.cumAsk).toBe(0);
  });

  it('correctly sums volumes across all bars at the same tick', () => {
    const bars = [
      makeBar({ '84000': { bid_vol: 10, ask_vol: 20 } }),
      makeBar({ '84000': { bid_vol: 5,  ask_vol: 8  } }),
    ];
    const result = aggregateProfile(bars);
    expect(result.levels).toHaveLength(1);
    const lv = result.levels[0];
    expect(lv.bidVol).toBe(15);
    expect(lv.askVol).toBe(28);
    expect(lv.total).toBe(43);
    // Price: 84000 * 0.25 = 21000
    expect(lv.price).toBeCloseTo(21000);
  });

  it('correctly sums volumes across multiple different price levels', () => {
    const bars = [
      makeBar({
        '84000': { bid_vol: 10, ask_vol: 20 },
        '84001': { bid_vol: 2,  ask_vol: 3  },
      }),
      makeBar({
        '84000': { bid_vol: 5,  ask_vol: 5  },
        '84002': { bid_vol: 8,  ask_vol: 7  },
      }),
    ];
    const result = aggregateProfile(bars);
    expect(result.levels).toHaveLength(3);
    // Sorted ascending by price
    expect(result.levels[0].price).toBeLessThan(result.levels[1].price);
    expect(result.levels[1].price).toBeLessThan(result.levels[2].price);
  });

  it('identifies POC as the price level with highest total volume', () => {
    const bars = [
      makeBar({
        '84000': { bid_vol: 5,  ask_vol: 5  },  // total 10
        '84001': { bid_vol: 30, ask_vol: 70 },  // total 100 — highest
        '84002': { bid_vol: 3,  ask_vol: 2  },  // total 5
      }),
    ];
    const result = aggregateProfile(bars);
    // 84001 * 0.25 = 21000.25
    expect(result.pocPrice).toBeCloseTo(84001 * 0.25);
    expect(result.maxTotal).toBe(100);
  });

  it('computes cumulative bid and ask totals correctly', () => {
    const bars = [
      makeBar({
        '84000': { bid_vol: 10, ask_vol: 20 },
        '84001': { bid_vol: 5,  ask_vol: 15 },
      }),
    ];
    const result = aggregateProfile(bars);
    expect(result.cumBid).toBe(15);
    expect(result.cumAsk).toBe(35);
  });

  it('correctly converts tick integer keys to prices (tick * 0.25)', () => {
    const bars = [
      makeBar({ '4': { bid_vol: 1, ask_vol: 1 } }),  // price = 1.0
      makeBar({ '8': { bid_vol: 1, ask_vol: 1 } }),  // price = 2.0
    ];
    const result = aggregateProfile(bars);
    const prices = result.levels.map((l) => l.price);
    expect(prices).toContain(1.0);
    expect(prices).toContain(2.0);
  });

  it('aggregation of 500-bar ring-buffer-like input completes in < 10ms', () => {
    // Build 500 bars each with 10 price levels
    const bars = Array.from({ length: 500 }, (_, barIdx) =>
      makeBar(
        Object.fromEntries(
          Array.from({ length: 10 }, (_, i) => [
            String(84000 + i),
            { bid_vol: barIdx % 50 + 1, ask_vol: (barIdx + i) % 30 + 1 },
          ]),
        ),
      ),
    );

    const start = performance.now();
    const result = aggregateProfile(bars);
    const elapsed = performance.now() - start;

    expect(elapsed).toBeLessThan(10);
    expect(result.levels.length).toBeGreaterThan(0);
  });

  it('handles bars with empty levels gracefully', () => {
    const bars = [makeBar({}), makeBar({ '84000': { bid_vol: 5, ask_vol: 5 } }), makeBar({})];
    const result = aggregateProfile(bars);
    expect(result.levels).toHaveLength(1);
    expect(result.cumBid).toBe(5);
    expect(result.cumAsk).toBe(5);
  });

  it('maxTotal equals the highest single-level total, not the sum of all', () => {
    const bars = [
      makeBar({
        '1': { bid_vol: 100, ask_vol: 200 }, // total 300
        '2': { bid_vol: 50,  ask_vol: 50  }, // total 100
      }),
    ];
    const result = aggregateProfile(bars);
    expect(result.maxTotal).toBe(300);
  });
});
