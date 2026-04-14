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

// ── Helper ────────────────────────────────────────────────────────────────────

function toLWData(bars: FootprintBar[]): FootprintBarLW[] {
  // RingBuffer.toArray() is insertion order (oldest→newest) — LW Charts needs
  // ascending time, which matches. No reverse.
  return bars.map((b) => ({
    ...b,
    time: b.ts as UTCTimestamp,
  }));
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
        background: { type: ColorType.Solid, color: '#0a0a0f' },
        textColor: '#6b7280',
      },
      grid: {
        horzLines: { color: '#1e1e2e' },
        vertLines: { color: '#1e1e2e' },
      },
      crosshair: { mode: 1 /* Magnet */ },
      rightPriceScale: { borderColor: '#1e1e2e' },
      timeScale: {
        borderColor: '#1e1e2e',
        timeVisible: true,
        secondsVisible: false,
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
    // the user has not manually panned away.
    const unsub = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      () => {
        const arr = useTradingStore.getState().bars.toArray();
        series.setData(toLWData(arr));
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
    <div className="relative flex-1 min-w-[600px] bg-bg-base border-r border-border-subtle">
      <div ref={hostRef} className="absolute inset-0" />
      <ZoneOverlay chartRef={chartRef} />
      <ReturnToLivePill />
    </div>
  );
}
