'use client';
import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';
import { useTradingStore } from '@/store/tradingStore';
import {
  aggregateProfile,
  drawProfile,
  yToPrice,
  PROFILE_WIDTH_CSS,
} from '@/lib/lw-charts/VolumeProfileRenderer';
import type { ProfileData } from '@/lib/lw-charts/VolumeProfileRenderer';
import type { FootprintBar } from '@/types/deep6';

// NQ tick size: 0.25 points per tick
const TICK_SIZE = 0.25;

// Fade-in duration when the profile re-aggregates (ms)
const FADE_IN_MS = 200;

interface VolumeProfileProps {
  chartRef: React.RefObject<IChartApi | null>;
}

export function VolumeProfile({ chartRef }: VolumeProfileProps) {
  const canvasRef      = useRef<HTMLCanvasElement | null>(null);
  // Cache the last aggregated profile so we don't re-aggregate on every redraw
  const profileCache   = useRef<ProfileData | null>(null);
  const lastVersionRef = useRef<number>(-1);

  // Animation state
  const fadeStartRef = useRef<number | null>(null);   // timestamp fade began
  const fadeAlphaRef = useRef<number>(1);             // current alpha (0–1)

  // Last known visible range (for click handler)
  const visRangeRef = useRef<{ from: number; to: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let rafId: number | null = null;

    // ── Helpers ────────────────────────────────────────────────────────────────

    /** Sync canvas bitmap size to its CSS size with DPR correction. */
    function syncDpr(
      el: HTMLCanvasElement,
      ctx: CanvasRenderingContext2D,
    ): { w: number; h: number } {
      const rect     = el.getBoundingClientRect();
      const dpr      = window.devicePixelRatio || 1;
      const w        = rect.width;
      const h        = rect.height;
      const bitmapW  = Math.round(w * dpr);
      const bitmapH  = Math.round(h * dpr);
      if (el.width !== bitmapW || el.height !== bitmapH) {
        el.width  = bitmapW;
        el.height = bitmapH;
        ctx.scale(dpr, dpr);
      }
      return { w, h };
    }

    /** Get or recompute the aggregated profile. Returns true if re-aggregated. */
    function getProfile(
      bars: FootprintBar[],
      version: number,
    ): { profile: ProfileData; fresh: boolean } {
      if (profileCache.current && version === lastVersionRef.current) {
        return { profile: profileCache.current, fresh: false };
      }
      const p = aggregateProfile(bars);
      profileCache.current   = p;
      lastVersionRef.current = version;
      return { profile: p, fresh: true };
    }

    // ── Redraw ─────────────────────────────────────────────────────────────────

    const redraw = (timestamp: number) => {
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
      visRangeRef.current = visibleRange;

      const state   = useTradingStore.getState();
      const bars    = state.bars.toArray();
      const version = state.lastBarVersion;

      if (bars.length === 0) {
        ctx.clearRect(0, 0, w, h);
        return;
      }

      const { profile, fresh } = getProfile(bars, version);

      // Kick off fade if fresh aggregation
      if (fresh) {
        fadeStartRef.current = timestamp;
        fadeAlphaRef.current = 0;
      }

      // Advance fade
      if (fadeStartRef.current !== null) {
        const elapsed = timestamp - fadeStartRef.current;
        fadeAlphaRef.current = Math.min(1, elapsed / FADE_IN_MS);
        if (fadeAlphaRef.current >= 1) {
          fadeStartRef.current = null;
        }
      }

      drawProfile({
        ctx,
        profile,
        priceMin:  visibleRange.from,
        priceMax:  visibleRange.to,
        canvasW:   w,
        canvasH:   h,
        tickSize:  TICK_SIZE,
        fadeAlpha: fadeAlphaRef.current,
      });

      // Continue animation loop until fade completes
      if (fadeStartRef.current !== null) {
        rafId = requestAnimationFrame(redraw);
      } else {
        rafId = null;
      }
    };

    const scheduleRedraw = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(redraw);
    };

    // ── Click handler (interaction stub) ──────────────────────────────────────

    const handleClick = (e: MouseEvent) => {
      const vr = visRangeRef.current;
      if (!vr || !canvas) return;

      const rect   = canvas.getBoundingClientRect();
      const clickY = e.clientY - rect.top;
      const price  = yToPrice(clickY, vr.from, vr.to, rect.height, TICK_SIZE);
      if (price !== null) {
        // Stub: log to console. Wire up to parent via onRowClick prop in future.
        console.log('[VolumeProfile] row click →', price);
      }
    };

    // ── Subscriptions ──────────────────────────────────────────────────────────

    let unsubTime: (() => void) | null = null;
    const chart = chartRef.current;
    if (chart) {
      chart.timeScale().subscribeVisibleTimeRangeChange(scheduleRedraw);
      unsubTime = () => chart.timeScale().unsubscribeVisibleTimeRangeChange(scheduleRedraw);

      // LW Charts doesn't expose priceScale subscription directly; use
      // crosshair move as a proxy for any visible range update.
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

    // Click interaction (pointer-events must be 'auto' for this to fire)
    canvas.addEventListener('click', handleClick);

    // Initial draw
    scheduleRedraw();

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      unsubTime?.();
      if (chart) chart.unsubscribeCrosshairMove(scheduleRedraw);
      unsubStore();
      ro.disconnect();
      canvas.removeEventListener('click', handleClick);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <canvas
      ref={canvasRef}
      style={{
        position:      'absolute',
        top:           0,
        left:          0,
        width:         `${PROFILE_WIDTH_CSS}px`,
        height:        '100%',
        pointerEvents: 'auto',   // needed for click interaction
        cursor:        'crosshair',
        zIndex:        10,
      }}
      aria-hidden="true"
    />
  );
}
