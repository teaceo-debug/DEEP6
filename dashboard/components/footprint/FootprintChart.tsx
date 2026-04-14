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
import type { FootprintBar } from '@/types/deep6';
import { FootprintSeries, footprintSeriesDefaults, type FootprintBarLW } from '@/lib/lw-charts/FootprintSeries';
import { ZoneOverlay } from './ZoneOverlay';

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

    // Subscribe to lastBarVersion WITHOUT triggering React re-renders.
    // On each new bar, update the series data and scroll to latest.
    const unsub = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      () => {
        const arr = useTradingStore.getState().bars.toArray();
        series.setData(toLWData(arr));
        chart.timeScale().scrollToRealTime();
      },
    );

    return () => {
      unsub();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  return (
    <div className="relative flex-1 min-w-[600px] bg-bg-base border-r border-border-subtle">
      <div ref={hostRef} className="absolute inset-0" />
      <ZoneOverlay chartRef={chartRef} />
    </div>
  );
}
