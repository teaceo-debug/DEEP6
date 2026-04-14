/**
 * replayClient.ts — fetch wrappers for the Phase 9 replay API endpoints.
 *
 * Endpoints:
 *   GET /api/replay/sessions
 *   GET /api/replay/{session}?start=N&end=M
 *   GET /api/replay/{session}/{bar_index}
 *
 * Per D-13 (11-CONTEXT.md): replay reads from Phase 9 EventStore via FastAPI.
 */
import type { FootprintBar, SignalEvent } from '@/types/deep6';

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export interface SessionMeta {
  session_id: string;
  bar_count: number;
  first_ts: number;
  last_ts: number;
}

/**
 * fetchSessions — list all recorded sessions from EventStore.
 * Returns [] when no bars have been stored yet.
 */
export async function fetchSessions(): Promise<SessionMeta[]> {
  const r = await fetch(`${BASE}/api/replay/sessions`);
  if (!r.ok) throw new Error(`sessions ${r.status}`);
  return r.json();
}

/**
 * fetchSessionRange — prefetch a contiguous range of bars for a session.
 * Used by useReplayController to preload all bars on session activation.
 *
 * Returns SESSION_NOT_FOUND error when session does not exist (404).
 */
export async function fetchSessionRange(
  sessionId: string,
  start: number,
  end: number,
): Promise<{ session_id: string; total_bars: number; bars: FootprintBar[] }> {
  const r = await fetch(
    `${BASE}/api/replay/${encodeURIComponent(sessionId)}?start=${start}&end=${end}`,
  );
  if (r.status === 404) throw new Error('SESSION_NOT_FOUND');
  if (!r.ok) throw new Error(`range ${r.status}`);
  return r.json();
}

/**
 * fetchReplayBar — fetch one bar plus all signals fired up to that bar's timestamp.
 * Used by useReplayController for signal projection on each bar advance.
 *
 * Returns BAR_NOT_FOUND when bar_index is out of range or session absent.
 */
export async function fetchReplayBar(
  sessionId: string,
  barIndex: number,
): Promise<{ bar: FootprintBar; signals_up_to: SignalEvent[] }> {
  const r = await fetch(
    `${BASE}/api/replay/${encodeURIComponent(sessionId)}/${barIndex}`,
  );
  if (r.status === 404) throw new Error('BAR_NOT_FOUND');
  if (!r.ok) throw new Error(`bar ${r.status}`);
  return r.json();
}
