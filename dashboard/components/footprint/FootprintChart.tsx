'use client';
import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';
import type { FootprintBar } from '@/types/deep6';
import { FootprintSeries, footprintSeriesDefaults, type FootprintBarLW } from '@/lib/lw-charts/FootprintSeries';
import { ZoneOverlay } from './ZoneOverlay';
import { ReturnToLivePill } from '@/components/replay/ReturnToLivePill';

// ── Helpers ───────────────────────────────────────────────────────────────────

function toLWData(bars: FootprintBar[]): FootprintBarLW[] {
  // RingBuffer.toArray() is insertion order (oldest→newest) — LW Charts needs
  // ascending time, which matches. No reverse.
  return bars.map((b) => ({
    ...b,
    time: b.ts as UTCTimestamp,
  }));
}

/**
 * Compute an appropriate barSpacing (media pixels per bar) based on how many
 * bars are visible.  Footprint cells must be readable — at ≤5 bars we want
 * wide columns (~110px) so bid/ask wings and volume numbers are clear; at 30+
 * bars we compress to ~40px and rely on color intensity alone.
 *
 * Range: [40, 120] px — hard limits that keep cells legible.
 */
function computeBarSpacing(visibleBarCount: number): number {
  if (visibleBarCount <= 0) return 80;
  // Linear interpolation: 5 bars → 110px, 30 bars → 40px
  const MIN_BARS = 5;
  const MAX_BARS = 30;
  const MAX_SPACING = 110;
  const MIN_SPACING = 40;
  const clamped = Math.max(MIN_BARS, Math.min(MAX_BARS, visibleBarCount));
  const t = (clamped - MIN_BARS) / (MAX_BARS - MIN_BARS);  // 0..1
  return Math.round(MAX_SPACING + t * (MIN_SPACING - MAX_SPACING));
}

// ── Component ─────────────────────────────────────────────────────────────────

export function FootprintChart() {
  const hostRef   = useRef<HTMLDivElement | null>(null);
  const chartRef  = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Custom'> | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;

    const chart = createChart(hostRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#000000' }, // --void (UI-SPEC v2 §0)
        textColor: '#8a8a8a', // --text-dim
      },
      grid: {
        horzLines: { color: '#1f1f1f' }, // --rule
        vertLines: { color: '#1f1f1f' }, // --rule
      },
      crosshair: { mode: 1 /* Magnet */ },
      rightPriceScale: { borderColor: '#1f1f1f' }, // --rule
      timeScale: {
        borderColor: '#1f1f1f', // --rule
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 80, // initial value; recalculated dynamically below
        rightOffset: 2, // minimal pad at right edge
      },
      autoSize: true,
    });

    chartRef.current = chart;

    // Register footprint custom series
    const series = chart.addCustomSeries(
      new FootprintSeries(),
      footprintSeriesDefaults,
    );
    seriesRef.current = series;

    // Initial data load
    const initBars = useTradingStore.getState().bars.toArray();
    if (initBars.length) {
      series.setData(toLWData(initBars));
      chart.timeScale().scrollToRealTime();
    }

    // Pan detection: when the visible time range changes and the right edge no
    // longer reaches the newest bar, mark userHasPanned = true so the
    // ReturnToLivePill appears. Wave 2 called scrollToRealTime() unconditionally;
    // this guard respects the user's manual scroll position.
    chart.timeScale().subscribeVisibleTimeRangeChange(() => {
      const range = chart.timeScale().getVisibleRange();
      if (!range) return;
      const bars = useTradingStore.getState().bars.toArray();
      if (bars.length === 0) return;
      const newestTs = bars[bars.length - 1].ts;
      // If the visible right edge is more than 2 bars behind the newest bar,
      // the user has manually panned away.
      const rightEdge = range.to as number;
      if (rightEdge < newestTs - 2) {
        useReplayStore.getState().setPanned(true);
      }
    });

    // Subscribe to ReturnToLivePill reset: when userHasPanned flips to false,
    // scroll back to real-time.
    let prevPanned = useReplayStore.getState().userHasPanned;
    const unsubPan = useReplayStore.subscribe((s) => {
      const panned = s.userHasPanned;
      if (prevPanned && !panned) {
        chart.timeScale().scrollToRealTime();
      }
      prevPanned = panned;
    });

    // Subscribe to lastBarVersion WITHOUT triggering React re-renders.
    // On each new bar, update the series data and scroll to latest ONLY when
    // the user has not manually panned away.  Also recompute barSpacing so
    // columns stay readable regardless of how many bars are on screen.
    const unsub = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      () => {
        const arr = useTradingStore.getState().bars.toArray();
        series.setData(toLWData(arr));

        // Dynamic barSpacing: measure how many bars are currently visible and
        // pick a width that keeps bid/ask wings and numbers legible.
        const logicalRange = chart.timeScale().getVisibleLogicalRange();
        if (logicalRange) {
          const visibleCount = Math.max(1, Math.round(logicalRange.to - logicalRange.from));
          const spacing = computeBarSpacing(visibleCount);
          chart.timeScale().applyOptions({ barSpacing: spacing });
        }

        if (!useReplayStore.getState().userHasPanned) {
          chart.timeScale().scrollToRealTime();
        }
      },
    );

    return () => {
      unsub();
      unsubPan();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  return (
    <div className="relative flex-1 min-w-0 overflow-hidden bg-bg-base border-r border-border-subtle">
      <div ref={hostRef} className="absolute inset-0" />
      <ZoneOverlay chartRef={chartRef} />
      <ReturnToLivePill />
    </div>
  );
}
