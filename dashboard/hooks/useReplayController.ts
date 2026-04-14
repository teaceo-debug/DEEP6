/**
 * useReplayController.ts — Replay loop driver.
 *
 * Mounts in app/page.tsx. Three duties:
 *
 * 1. URL → mode sync: if `?session=` present on mount, activate replay mode.
 * 2. Session load: when mode flips to 'replay', fetch all bars via fetchSessionRange
 *    and cache them locally. Projects bars[0..barIdx] into tradingStore on each advance.
 * 3. Auto-advance loop: when playing=true, schedule next advanceBar() tick based on speed.
 *    1x→1000ms, 2x→500ms, 5x→200ms, auto→requestAnimationFrame.
 *
 * Per D-13 (11-CONTEXT.md): replay reads from EventStore via FastAPI.
 * Per D-14: replay controls are UI-side; backend is stateless.
 */
'use client';
import { useEffect, useRef } from 'react';
import { useReplayStore } from '@/store/replayStore';
import { useTradingStore, BAR_CAPACITY, SIGNAL_CAPACITY } from '@/store/tradingStore';
import { RingBuffer } from '@/store/ringBuffer';
import { fetchSessionRange, fetchReplayBar } from '@/lib/replayClient';
import type { FootprintBar, SignalEvent } from '@/types/deep6';

const DELAY_BY_SPEED: Record<string, number> = {
  '1x': 1000,
  '2x': 500,
  '5x': 200,
};

export function useReplayController() {
  const mode = useReplayStore((s) => s.mode);
  const sessionId = useReplayStore((s) => s.sessionId);
  const barIdx = useReplayStore((s) => s.currentBarIndex);
  const playing = useReplayStore((s) => s.playing);
  const speed = useReplayStore((s) => s.speed);

  // Cached bar array for the loaded session — avoids re-fetching on every advance.
  const barsCacheRef = useRef<FootprintBar[]>([]);

  // ── 1. URL → mode sync (runs once on mount) ────────────────────────────────
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const session = new URLSearchParams(window.location.search).get('session');
    if (session) {
      useReplayStore.getState().setMode('replay', session);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── 2. Session load (runs when mode/sessionId changes) ────────────────────
  useEffect(() => {
    if (mode !== 'replay' || !sessionId) return;
    let cancelled = false;

    (async () => {
      try {
        const data = await fetchSessionRange(sessionId, 0, 10000);
        if (cancelled) return;
        barsCacheRef.current = data.bars;
        useReplayStore.getState().setTotalBars(data.total_bars);
      } catch (e) {
        if (cancelled) return;
        const msg =
          e instanceof Error && e.message === 'SESSION_NOT_FOUND'
            ? 'Session not found. Select a date from history.'
            : 'Failed to load session.';
        useReplayStore.getState().setError(msg);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mode, sessionId]);

  // ── 3a. Bar projection (runs when barIdx changes in replay mode) ──────────
  useEffect(() => {
    if (mode !== 'replay') return;
    const cache = barsCacheRef.current;
    if (cache.length === 0) return;

    const slice = cache.slice(0, barIdx + 1);
    const ring = new RingBuffer<FootprintBar>(BAR_CAPACITY);
    for (const b of slice.slice(-BAR_CAPACITY)) ring.push(b);
    useTradingStore.setState((s) => ({
      bars: ring,
      lastBarVersion: s.lastBarVersion + 1,
    }));
  }, [barIdx, mode]);

  // ── 3b. Signal projection (fetch signals_up_to on barIdx change) ──────────
  useEffect(() => {
    if (mode !== 'replay' || !sessionId) return;
    let cancelled = false;

    (async () => {
      try {
        const { signals_up_to } = await fetchReplayBar(sessionId, barIdx);
        if (cancelled) return;
        const ring = new RingBuffer<SignalEvent>(SIGNAL_CAPACITY);
        for (const sig of signals_up_to.slice(-SIGNAL_CAPACITY)) ring.push(sig);
        useTradingStore.setState((s) => ({
          signals: ring,
          lastSignalVersion: s.lastSignalVersion + 1,
        }));
      } catch {
        // Swallow — error already displayed by session load handler
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [barIdx, mode, sessionId]);

  // ── 4. Auto-advance playback loop ─────────────────────────────────────────
  useEffect(() => {
    if (mode !== 'replay' || !playing) return;

    if (speed === 'auto') {
      let rafId = 0;
      const tick = () => {
        useReplayStore.getState().advanceBar();
        rafId = requestAnimationFrame(tick);
      };
      rafId = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(rafId);
    }

    const delay = DELAY_BY_SPEED[speed] ?? 1000;
    const id = setInterval(() => {
      useReplayStore.getState().advanceBar();
    }, delay);
    return () => clearInterval(id);
  }, [mode, playing, speed]);
}
