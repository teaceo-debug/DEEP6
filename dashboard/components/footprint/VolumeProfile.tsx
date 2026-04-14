'use client';
import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';
import { useTradingStore } from '@/store/tradingStore';
import { aggregateProfile, drawProfile } from '@/lib/lw-charts/VolumeProfileRenderer';
import type { ProfileData } from '@/lib/lw-charts/VolumeProfileRenderer';
import type { FootprintBar } from '@/types/deep6';

// NQ tick size: 0.25 points per tick
const TICK_SIZE = 0.25;
// CSS width of the profile canvas
const PROFILE_WIDTH = 60;

interface VolumeProfileProps {
  chartRef: React.RefObject<IChartApi | null>;
}

export function VolumeProfile({ chartRef }: VolumeProfileProps) {
  const canvasRef     = useRef<HTMLCanvasElement | null>(null);
  // Cache the last aggregated profile so we don't re-aggregate on every redraw
  const profileCache  = useRef<ProfileData | null>(null);
  const lastVersionRef = useRef<number>(-1);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let rafId: number | null = null;

    // ── Helpers ────────────────────────────────────────────────────────────────

    /** Sync canvas bitmap size to its CSS size with DPR correction. */
    function syncDpr(el: HTMLCanvasElement, ctx: CanvasRenderingContext2D): { w: number; h: number } {
      const rect = el.getBoundingClientRect();
      const dpr  = window.devicePixelRatio || 1;
      const w    = rect.width;
      const h    = rect.height;
      const bitmapW = Math.round(w * dpr);
      const bitmapH = Math.round(h * dpr);
      if (el.width !== bitmapW || el.height !== bitmapH) {
        el.width  = bitmapW;
        el.height = bitmapH;
        ctx.scale(dpr, dpr);
      }
      return { w, h };
    }

    /** Get or recompute the aggregated profile. */
    function getProfile(bars: FootprintBar[], version: number): ProfileData {
      if (profileCache.current && version === lastVersionRef.current) {
        return profileCache.current;
      }
      const p = aggregateProfile(bars);
      profileCache.current  = p;
      lastVersionRef.current = version;
      return p;
    }

    // ── Redraw ─────────────────────────────────────────────────────────────────

    const redraw = () => {
      const chart = chartRef.current;
      if (!chart || !canvas) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const { w, h } = syncDpr(canvas, ctx);
      if (w <= 0 || h <= 0) return;

      // Get visible price range from LW Charts price scale
      const visibleRange = chart.priceScale('right').getVisibleRange();
      if (!visibleRange) {
        ctx.clearRect(0, 0, w, h);
        return;
      }

      const state   = useTradingStore.getState();
      const bars    = state.bars.toArray();
      const version = state.lastBarVersion;

      if (bars.length === 0) {
        ctx.clearRect(0, 0, w, h);
        return;
      }

      const profile = getProfile(bars, version);

      drawProfile({
        ctx,
        profile,
        priceMin:  visibleRange.from,
        priceMax:  visibleRange.to,
        canvasW:   w,
        canvasH:   h,
        tickSize:  TICK_SIZE,
      });
    };

    const scheduleRedraw = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        redraw();
      });
    };

    // ── Subscriptions ──────────────────────────────────────────────────────────

    // Redraw on price scale pan/zoom
    let unsubTime: (() => void) | null = null;
    const chart = chartRef.current;
    if (chart) {
      chart.timeScale().subscribeVisibleTimeRangeChange(scheduleRedraw);
      unsubTime = () => chart.timeScale().unsubscribeVisibleTimeRangeChange(scheduleRedraw);

      // Also subscribe to price scale changes (vertical scroll / zoom)
      // LW Charts doesn't expose priceScale subscription directly; we use
      // a crosshair move subscription as a proxy for any visible range update.
      chart.subscribeCrosshairMove(scheduleRedraw);
    }

    // Redraw when bar data changes (new bars → new aggregation)
    const unsubStore = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      scheduleRedraw,
    );

    // ResizeObserver for container resize
    const ro = new ResizeObserver(scheduleRedraw);
    ro.observe(canvas.parentElement ?? canvas);

    // Initial draw
    scheduleRedraw();

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      unsubTime?.();
      if (chart) chart.unsubscribeCrosshairMove(scheduleRedraw);
      unsubStore();
      ro.disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <canvas
      ref={canvasRef}
      style={{
        position:       'absolute',
        top:            0,
        left:           0,
        width:          `${PROFILE_WIDTH}px`,
        height:         '100%',
        pointerEvents:  'none',
        zIndex:         10,
      }}
      aria-hidden="true"
    />
  );
}
