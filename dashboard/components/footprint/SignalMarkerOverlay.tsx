'use client';
/**
 * SignalMarkerOverlay
 *
 * A sibling <canvas> element that draws signal markers above footprint bars:
 *   - Tier-colored vertical line (2px wide, 12px tall) from chart top toward bars
 *   - Hollow triangle (6×6) at the top of the line, pointing down
 *   - Multiple signals on the same bar are stacked with 3px horizontal offset
 *   - Fade-in animation on new markers (opacity 0→1 over 400ms)
 *   - Tooltip on hover showing tier + categories
 *
 * Sits as an absolute-positioned overlay, pointer-events: none so it doesn't
 * block chart interactions — except the canvas itself handles mousemove for
 * tooltip positioning.
 */

import { useEffect, useRef, useCallback } from 'react';
import type { IChartApi, UTCTimestamp } from 'lightweight-charts';
import { useTradingStore } from '@/store/tradingStore';
import type { SignalEvent } from '@/types/deep6';

// ── Tier color map (CSS custom properties resolved to hex for canvas) ─────────

const TIER_COLORS: Record<string, string> = {
  TYPE_A: 'var(--lime,   #a3e635)',
  TYPE_B: 'var(--amber,  #f59e0b)',
  TYPE_C: 'var(--cyan,   #06b6d4)',
};
const FALLBACK_COLOR = 'var(--text-mute, #555555)';

/** Resolve a CSS custom-property string to a computed color value. */
function resolveColor(cssValue: string): string {
  // Extract the fallback from var(--foo, fallback) if running on server or
  // if the custom property is not defined; otherwise getComputedStyle will
  // return the live value.
  if (typeof document === 'undefined') {
    const fallbackMatch = cssValue.match(/,\s*([^)]+)\s*\)/);
    return fallbackMatch ? fallbackMatch[1].trim() : '#888888';
  }
  const el = document.documentElement;
  const computed = getComputedStyle(el);
  // Extract --property-name from the var() string
  const propMatch = cssValue.match(/var\((--[\w-]+)/);
  if (propMatch) {
    const val = computed.getPropertyValue(propMatch[1]).trim();
    if (val) return val;
  }
  // Fall through to the hard-coded fallback colour inside the var()
  const fallbackMatch = cssValue.match(/,\s*(#[\da-fA-F]{3,8}|[\w]+)\s*\)/);
  return fallbackMatch ? fallbackMatch[1].trim() : '#888888';
}

function tierColor(tier: string): string {
  return resolveColor(TIER_COLORS[tier] ?? FALLBACK_COLOR);
}

// ── Marker geometry constants ────────────────────────────────────────────────

const LINE_WIDTH      = 2;   // px
const LINE_HEIGHT     = 12;  // px, from chart top downward
const TRIANGLE_SIZE   = 6;   // px, equilateral-ish pointing down
const TRIANGLE_STROKE = 1.5; // px
const TOP_OFFSET      = 6;   // px from chart top to triangle apex
const STACK_OFFSET    = 9;   // px horizontal stagger between signals on same bar
const FADE_DURATION   = 400; // ms

// ── Types ─────────────────────────────────────────────────────────────────────

interface Marker {
  signal:  SignalEvent;
  /** CSS-pixel X at the center of the bar column */
  barX:    number;
  /** Stacked X offset when multiple signals share a bar (0, ±STACK_OFFSET, …) */
  stackX:  number;
  /** Timestamp when this marker became visible (for fade-in) */
  spawnMs: number;
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  marker: Marker | null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export interface SignalMarkerOverlayProps {
  chartRef: React.RefObject<IChartApi | null>;
  /** Called when user clicks a marker (future: wire to SignalContext drawer) */
  onMarkerClick?: (signalId: number) => void;
}

export function SignalMarkerOverlay({ chartRef, onMarkerClick }: SignalMarkerOverlayProps) {
  const canvasRef  = useRef<HTMLCanvasElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);

  // Persistent state across redraws — no React re-renders needed
  const markersRef        = useRef<Marker[]>([]);
  const lastSignalCount   = useRef<number>(0);
  const rafId             = useRef<number | null>(null);
  const animationActive   = useRef<boolean>(false);
  const tooltipState      = useRef<TooltipState>({ visible: false, x: 0, y: 0, marker: null });

  // ── Canvas helpers ──────────────────────────────────────────────────────────

  /** Sync canvas bitmap to CSS size with DPR correction. Returns CSS dimensions. */
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

  // ── Bar X-coordinate resolution ─────────────────────────────────────────────

  /**
   * Given a timestamp, return the CSS-pixel X center of that bar column using
   * the LightweightCharts time scale coordinate API.
   * Returns null if the bar is not in the current visible range.
   */
  function barXFromTs(chart: IChartApi, ts: number): number | null {
    // LW Charts timeToCoordinate expects a UTCTimestamp (seconds)
    const x = chart.timeScale().timeToCoordinate(ts as UTCTimestamp);
    return x ?? null;
  }

  // ── Marker building ──────────────────────────────────────────────────────────

  /**
   * Re-derive all markers from the current signal ring buffer + visible bars.
   * Only rebuilds markers whose count changed; preserves spawnMs for existing ones.
   */
  const rebuildMarkers = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const signals = useTradingStore.getState().signals.toArray();

    if (signals.length === lastSignalCount.current && markersRef.current.length > 0) {
      // Nothing new — update barX positions only (for pan/zoom)
      markersRef.current = markersRef.current.map((m) => {
        const newX = barXFromTs(chart, m.signal.ts);
        return newX !== null ? { ...m, barX: newX } : m;
      });
      return;
    }

    lastSignalCount.current = signals.length;

    // Build a map: barTs → list of signals
    // We approximate bar boundaries by using bar.ts for the signal's bar.
    const bars = useTradingStore.getState().bars.toArray();

    const barForSignal = (sig: SignalEvent): number | null => {
      // Find bar where bar.ts <= sig.ts < bar.ts + bar_duration
      // Since we don't know bar_duration directly, find the bar whose ts is
      // closest to sig.ts from below (most recent bar start <= sig.ts).
      let bestTs: number | null = null;
      for (const bar of bars) {
        if (bar.ts <= sig.ts) {
          bestTs = bar.ts;
        }
      }
      return bestTs;
    };

    // Group signals by their bar timestamp
    const grouped = new Map<number, SignalEvent[]>();
    for (const sig of signals) {
      const barTs = barForSignal(sig);
      if (barTs === null) continue;
      const list = grouped.get(barTs) ?? [];
      list.push(sig);
      grouped.set(barTs, list);
    }

    // Build markers with stacking offsets
    const now = performance.now();
    const prevMarkers = new Map(markersRef.current.map((m) => [m.signal.ts, m]));

    const newMarkers: Marker[] = [];
    for (const [barTs, sigs] of grouped) {
      const x = barXFromTs(chart, barTs);
      if (x === null) continue;

      const count = sigs.length;
      // Centre the stack: if 3 signals, offsets = -STACK_OFFSET, 0, +STACK_OFFSET
      sigs.forEach((sig, i) => {
        const stackX = (i - Math.floor(count / 2)) * STACK_OFFSET;
        const existing = prevMarkers.get(sig.ts);
        newMarkers.push({
          signal:  sig,
          barX:    x,
          stackX,
          spawnMs: existing?.spawnMs ?? now,
        });
      });
    }

    markersRef.current = newMarkers;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Draw ─────────────────────────────────────────────────────────────────────

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { w, h } = syncDpr(canvas, ctx);
    ctx.clearRect(0, 0, w, h);

    const now = performance.now();
    let needsNextFrame = false;

    for (const marker of markersRef.current) {
      const elapsed = now - marker.spawnMs;
      const opacity = Math.min(1, elapsed / FADE_DURATION);
      if (opacity < 1) needsNextFrame = true;

      const cx = marker.barX + marker.stackX;
      const color = tierColor(marker.signal.tier);

      ctx.globalAlpha = opacity;

      // Vertical line: from TOP_OFFSET down by LINE_HEIGHT
      const lineTop    = TOP_OFFSET + TRIANGLE_SIZE; // line starts below the triangle
      const lineBottom = lineTop + LINE_HEIGHT;
      ctx.strokeStyle = color;
      ctx.lineWidth   = LINE_WIDTH;
      ctx.beginPath();
      ctx.moveTo(cx, lineTop);
      ctx.lineTo(cx, lineBottom);
      ctx.stroke();

      // Hollow triangle pointing DOWN, apex at TOP_OFFSET
      // Vertices: left-top, right-top, apex-bottom (pointing down)
      const triTop   = TOP_OFFSET;              // top edge of the triangle
      const triBot   = TOP_OFFSET + TRIANGLE_SIZE; // apex pointing down
      const triLeft  = cx - TRIANGLE_SIZE / 2;
      const triRight = cx + TRIANGLE_SIZE / 2;

      ctx.strokeStyle = color;
      ctx.lineWidth   = TRIANGLE_STROKE;
      ctx.beginPath();
      ctx.moveTo(triLeft,  triTop);   // top-left
      ctx.lineTo(triRight, triTop);   // top-right
      ctx.lineTo(cx,       triBot);   // apex (center, pointing down)
      ctx.closePath();
      ctx.stroke();

      ctx.globalAlpha = 1;
    }

    // Schedule next frame only while fading
    if (needsNextFrame) {
      rafId.current = requestAnimationFrame(() => {
        rafId.current = null;
        draw();
      });
      animationActive.current = true;
    } else {
      animationActive.current = false;
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleRedraw = useCallback(() => {
    if (rafId.current !== null) return;
    rafId.current = requestAnimationFrame(() => {
      rafId.current = null;
      rebuildMarkers();
      draw();
    });
  }, [rebuildMarkers, draw]);

  // ── Tooltip ─────────────────────────────────────────────────────────────────

  const updateTooltip = useCallback((canvasX: number, canvasY: number) => {
    const HIT_RADIUS = 10; // px
    let closest: Marker | null = null;
    let closestDist = Infinity;

    for (const m of markersRef.current) {
      const mx = m.barX + m.stackX;
      const my = TOP_OFFSET + TRIANGLE_SIZE / 2; // triangle center Y
      const dist = Math.hypot(canvasX - mx, canvasY - my);
      if (dist < HIT_RADIUS && dist < closestDist) {
        closest = m;
        closestDist = dist;
      }
    }

    const tooltip = tooltipRef.current;
    if (!tooltip) return;

    if (closest) {
      const sig = closest.signal;
      const cats = sig.categories_firing.length > 0
        ? sig.categories_firing.slice(0, 3).join(', ')
        : '—';
      const dirLabel = sig.direction === 1 ? 'LONG' : sig.direction === -1 ? 'SHORT' : 'FLAT';
      tooltip.innerHTML = `
        <span class="font-semibold" style="color:${tierColor(sig.tier)}">${sig.tier}</span>
        <span class="text-text-dim ml-1">${dirLabel}</span>
        <span class="text-text-mute ml-2 text-xs">${cats}</span>
      `;
      tooltip.style.left    = `${canvasX + 10}px`;
      tooltip.style.top     = `${canvasY - 8}px`;
      tooltip.style.display = 'block';
      tooltipState.current  = { visible: true, x: canvasX, y: canvasY, marker: closest };
    } else {
      tooltip.style.display = 'none';
      tooltipState.current  = { visible: false, x: 0, y: 0, marker: null };
    }
  }, []);

  // ── Click handler ────────────────────────────────────────────────────────────

  const handleCanvasClick = useCallback((e: MouseEvent) => {
    if (!onMarkerClick) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const canvasX = e.clientX - rect.left;
    const canvasY = e.clientY - rect.top;
    const HIT_RADIUS = 10;

    for (const m of markersRef.current) {
      const mx = m.barX + m.stackX;
      const my = TOP_OFFSET + TRIANGLE_SIZE / 2;
      if (Math.hypot(canvasX - mx, canvasY - my) < HIT_RADIUS) {
        // Use ts as a stable signal identifier until backend assigns IDs
        onMarkerClick(m.signal.ts);
        // eslint-disable-next-line no-console
        console.log('[SignalMarkerOverlay] marker clicked:', m.signal);
        return;
      }
    }
  }, [onMarkerClick]);

  // ── Mouse move on canvas (tooltip) ──────────────────────────────────────────

  const handleMouseMove = useCallback((e: MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    updateTooltip(e.clientX - rect.left, e.clientY - rect.top);
  }, [updateTooltip]);

  const handleMouseLeave = useCallback(() => {
    const tooltip = tooltipRef.current;
    if (tooltip) tooltip.style.display = 'none';
    tooltipState.current = { visible: false, x: 0, y: 0, marker: null };
  }, []);

  // ── Effect: subscribe to store + chart + resize ──────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Canvas needs pointer-events enabled for hover / click
    canvas.style.pointerEvents = 'none'; // will be overridden below for mouse tracking
    // We allow mousemove/click on the canvas but not chart-blocking
    canvas.style.pointerEvents = 'auto';

    canvas.addEventListener('mousemove',  handleMouseMove);
    canvas.addEventListener('mouseleave', handleMouseLeave);
    canvas.addEventListener('click',      handleCanvasClick);

    // Subscribe to new signals
    const unsubSignal = useTradingStore.subscribe(
      (s) => s.lastSignalVersion,
      scheduleRedraw,
    );

    // Subscribe to bar version (bar positions change on new bars, and we need
    // to re-map signal timestamps → bar X coords)
    const unsubBar = useTradingStore.subscribe(
      (s) => s.lastBarVersion,
      scheduleRedraw,
    );

    // Subscribe to pan/zoom
    let unsubTime: (() => void) | null = null;
    const chart = chartRef.current;
    if (chart) {
      chart.timeScale().subscribeVisibleTimeRangeChange(scheduleRedraw);
      unsubTime = () => chart.timeScale().unsubscribeVisibleTimeRangeChange(scheduleRedraw);
    }

    // ResizeObserver
    const ro = new ResizeObserver(scheduleRedraw);
    ro.observe(canvas.parentElement ?? canvas);

    // Initial draw
    scheduleRedraw();

    return () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current);
      canvas.removeEventListener('mousemove',  handleMouseMove);
      canvas.removeEventListener('mouseleave', handleMouseLeave);
      canvas.removeEventListener('click',      handleCanvasClick);
      unsubSignal();
      unsubBar();
      unsubTime?.();
      ro.disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      {/* Marker canvas — pointer-events: auto so hover works, but sits on top
          of the chart without blocking it for most interactions */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0"
        style={{ pointerEvents: 'none', zIndex: 10 }}
        aria-hidden="true"
      />
      {/* Floating tooltip */}
      <div
        ref={tooltipRef}
        className="absolute z-20 hidden whitespace-nowrap rounded bg-bg-elevated border border-border-subtle px-2 py-1 text-xs text-text-base shadow-lg"
        style={{ pointerEvents: 'none' }}
        aria-hidden="true"
      />
    </>
  );
}
