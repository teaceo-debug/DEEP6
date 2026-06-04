'use client';
/**
 * useDepthRadar.ts — polling hooks for DepthRadar REST endpoints.
 *
 * Fetches from:
 *   GET /api/depthradar/walls     — active walls (polled every 2s)
 *   GET /api/depthradar/episodes  — episode history
 *   GET /api/depthradar/touches   — touch outcomes
 *   GET /api/depthradar/metrics   — aggregated stats
 *
 * Falls back to empty state when backend is unreachable (demo mode compatible).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  DepthRadarWall,
  DepthRadarEpisode,
  DepthRadarTouch,
  DepthRadarMetrics,
} from '@/types/deep6';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8765';
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Polling intervals (ms)
const WALLS_POLL_MS = 2000;
const EPISODES_POLL_MS = 10000;
const TOUCHES_POLL_MS = 10000;
const METRICS_POLL_MS = 15000;

// ── Generic fetcher with error swallowing ────────────────────────────────────

async function fetchJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

// ── usePolledFetch — generic polling primitive ───────────────────────────────

function usePolledFetch<T>(
  path: string,
  intervalMs: number,
  enabled: boolean,
): { data: T | null; loading: boolean; error: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const mountedRef = useRef(true);

  const doFetch = useCallback(async () => {
    const result = await fetchJSON<T>(path);
    if (!mountedRef.current) return;
    if (result !== null) {
      setData(result);
      setError(false);
    } else {
      setError(true);
    }
    setLoading(false);
  }, [path]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) {
      setLoading(false);
      return;
    }

    doFetch();
    const id = setInterval(doFetch, intervalMs);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [doFetch, intervalMs, enabled]);

  return { data, loading, error };
}

// ── Exported hooks ───────────────────────────────────────────────────────────

export function useDepthRadarWalls() {
  return usePolledFetch<DepthRadarWall[]>(
    '/api/depthradar/walls',
    WALLS_POLL_MS,
    !DEMO_MODE,
  );
}

export function useDepthRadarEpisodes(limit = 50) {
  return usePolledFetch<DepthRadarEpisode[]>(
    `/api/depthradar/episodes?limit=${limit}`,
    EPISODES_POLL_MS,
    !DEMO_MODE,
  );
}

export function useDepthRadarTouches(limit = 100) {
  return usePolledFetch<DepthRadarTouch[]>(
    `/api/depthradar/touches?limit=${limit}`,
    TOUCHES_POLL_MS,
    !DEMO_MODE,
  );
}

export function useDepthRadarMetrics() {
  return usePolledFetch<DepthRadarMetrics>(
    '/api/depthradar/metrics',
    METRICS_POLL_MS,
    !DEMO_MODE,
  );
}
