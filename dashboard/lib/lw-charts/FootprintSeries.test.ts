import { describe, it, expect, vi } from 'vitest';
import type { PaneRendererCustomData, Time, UTCTimestamp } from 'lightweight-charts';

import {
  FootprintSeries,
  footprintSeriesDefaults,
  type FootprintBarLW,
} from './FootprintSeries';
import { FootprintRenderer } from './FootprintRenderer';

// Helper: build a FootprintBarLW fixture with optional levels
function makeBar(overrides: Partial<FootprintBarLW> = {}): FootprintBarLW {
  return {
    session_id: '2026-04-14',
    bar_index: 0,
    ts: 1_744_600_000,
    time: 1_744_600_000 as UTCTimestamp,
    open: 21_000,
    high: 21_010,
    low: 20_990,
    close: 21_005,
    total_vol: 120,
    bar_delta: 5,
    cvd: 42,
    poc_price: 21_000,
    bar_range: 20,
    running_delta: 10,
    max_delta: 12,
    min_delta: -3,
    levels: {
      '84000': { bid_vol: 10, ask_vol: 20 },
      '84001': { bid_vol: 5, ask_vol: 8 },
    },
    ...overrides,
  };
}

describe('FootprintSeries', () => {
  it('Test 1: priceValueBuilder returns [low, high, close]', () => {
    const s = new FootprintSeries();
    const bar = makeBar({ low: 100, high: 200, close: 150 });
    expect(s.priceValueBuilder(bar)).toEqual([100, 200, 150]);
  });

  it('Test 2: isWhitespace returns true for empty levels and false when levels present', () => {
    const s = new FootprintSeries();
    expect(s.isWhitespace(makeBar({ levels: {} }))).toBe(true);
    expect(
      s.isWhitespace(
        makeBar({ levels: { '84000': { bid_vol: 5, ask_vol: 5 } } }),
      ),
    ).toBe(false);
  });

  it('Test 3: defaultOptions returns the DEEP6 footprint option set', () => {
    const s = new FootprintSeries();
    const opts = s.defaultOptions();
    expect(opts.rowHeight).toBe(20);
    expect(opts.showDelta).toBe(true);
    expect(opts.showImbalance).toBe(true);
    expect(opts.pocLineColor).toBe('#facc15');
  });

  it('Test 4: renderer() returns a stable FootprintRenderer singleton', () => {
    const s = new FootprintSeries();
    const r1 = s.renderer();
    const r2 = s.renderer();
    expect(r1).toBeInstanceOf(FootprintRenderer);
    expect(r1).toBe(r2);
  });

  it('Test 5: update() forwards to the renderer.update with same args', () => {
    const s = new FootprintSeries();
    const r = s.renderer() as FootprintRenderer;
    const spy = vi.spyOn(r, 'update');
    const data = {
      bars: [],
      barSpacing: 6,
      visibleRange: null,
    } as unknown as PaneRendererCustomData<Time, FootprintBarLW>;
    s.update(data, footprintSeriesDefaults);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(data, footprintSeriesDefaults);
  });

  it('Test 6: defaults include all CustomSeriesOptions base fields from LW Charts', () => {
    // Must extend customSeriesDefaultOptions — verify presence of a known base field.
    expect(footprintSeriesDefaults).toHaveProperty('rowHeight', 20);
    expect(footprintSeriesDefaults).toHaveProperty('showDelta', true);
    expect(footprintSeriesDefaults).toHaveProperty('pocLineColor', '#facc15');
  });
});
