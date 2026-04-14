'use client';
import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';
import { useTradingStore } from '@/store/tradingStore';
import { drawZones } from '@/lib/lw-charts/zoneDrawer';
import type { ZoneRef } from '@/types/deep6';

// ── Zone derivation ───────────────────────────────────────────────────────────
// Wave 2 stub: extract zones from the latest bar's __zones field if present.
// Real zone computation is backend-side (Wave 3+). If no zones, draw nothing.
function deriveZonesFromLatestBar(): ZoneRef[] {
  const latest = useTradingStore.getState().bars.latest;
  if (!latest) return [];
  // Backend may inject __zones into the bar payload
  const zones = (latest as typeof latest & { __zones?: ZoneRef[] }).__zones;
  return Array.isArray(zones) ? zones : [];
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ZoneOverlayProps {
  chartRef: React.RefObject<IChartApi | null>;
}

export function ZoneOverlay({ chartRef }: ZoneOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let rafId: number | null = null;

    const redraw = () => {
      const chart = chartRef.current;
      if (!chart || !canvas) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Sync canvas dimensions to its CSS size
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = rect.width;
      const h = rect.height;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width  = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        ctx.scale(dpr, dpr);
      }

      ctx.clearRect(0, 0, w, h);

      const zones = deriveZonesFromLatestBar();
      if (zones.length === 0) return;

      // Get visible price range via IPriceScaleApi.getVisibleRange()
      // which returns IRange<number> = { from: number, to: number }
      // where `from` = min price and `to` = max price (price scale bottom→top).
      const visiblePriceRange = chart.priceScale('right').getVisibleRange();
      if (!visiblePriceRange) return;

      // getVisibleRange() returns { from: minPrice, to: maxPrice }
      const priceMin = visiblePriceRange.from;
      const priceMax = visiblePriceRange.to;
      const priceRange = priceMax - priceMin;
      if (priceRange <= 0) return;

      const paneHeight = h;

      const priceToCoordinate = (price: number): number | null => {
        // CSS pixels: Y=0 at top (high price), Y=height at bottom (low price)
        const ratio = (priceMax - price) / priceRange;
        return ratio * paneHeight;
      };

      drawZones(ctx, zones, priceToCoordinate, w);
    };

    const scheduleRedraw = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        redraw();
      });
    };

    // Redraw on scroll/zoom
    let unsubTime: (() => void) | null = null;
    const chart = chartRef.current;
    if (chart) {
      chart.timeScale().subscribeVisibleTimeRangeChange(scheduleRedraw);
      unsubTime = () => chart.timeScale().unsubscribeVisibleTimeRangeChange(scheduleRedraw);
    }

    // Redraw when store bar data changes (new zones may arrive)
    const unsubStore = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      scheduleRedraw,
    );

    // ResizeObserver to handle container resize
    const ro = new ResizeObserver(scheduleRedraw);
    ro.observe(canvas.parentElement ?? canvas);

    // Initial draw
    scheduleRedraw();

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      unsubTime?.();
      unsubStore();
      ro.disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none"
      aria-hidden="true"
    />
  );
}
