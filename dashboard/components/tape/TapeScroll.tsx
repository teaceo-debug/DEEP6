'use client';
/**
 * TapeScroll.tsx — per UI-SPEC v2 §4.4 (11.3-r8 upgrade)
 *
 * Upgrades from 11.3 baseline:
 * - Stats summary line: "N prints · $X.XM notional · XX% ASK" (visible when >5 prints)
 * - Hover expand passes runningVolumeAtPrice + directionBias to TapeRow
 * - Floating "↓ NEW (N)" pill preserved
 * - Empty state: // no prints yet_ with blinking cursor
 */
import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import { TapeRow } from './TapeRow';
import type { TapeMarker } from './TapeRow';
import type { TapeEntry } from '@/types/deep6';

// Map backend marker strings (uppercase) to TapeRow marker type (lowercase)
function toMarker(m: TapeEntry['marker']): TapeMarker {
  if (m === 'SWEEP')   return 'sweep';
  if (m === 'ICEBERG') return 'iceberg';
  if (m === 'KRONOS')  return 'kronos';
  return null;
}

// ── Blinking cursor ───────────────────────────────────────────────────────────

function BlinkingCursor() {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const id = setInterval(() => setVisible((v) => !v), 500);
    return () => clearInterval(id);
  }, []);
  return (
    <span
      style={{
        color: 'var(--text-mute)',
        opacity: visible ? 1 : 0,
        transition: 'opacity 60ms',
        userSelect: 'none',
      }}
    >
      _
    </span>
  );
}

// ── Stats summary ─────────────────────────────────────────────────────────────

interface TapeStats {
  count: number;
  notionalM: string;
  askPct: number;
}

function computeStats(tape: TapeEntry[]): TapeStats {
  const count = tape.length;
  // NQ point value: $20 per point. Approximate notional = price * size * $20
  let totalNotional = 0;
  let askCount = 0;
  for (const e of tape) {
    totalNotional += e.price * e.size * 20;
    if (e.side === 'ASK') askCount++;
  }
  const notionalM = (totalNotional / 1_000_000).toFixed(1);
  const askPct = count > 0 ? Math.round((askCount / count) * 100) : 0;
  return { count, notionalM, askPct };
}

function TapeStatsSummary({ tape }: { tape: TapeEntry[] }) {
  const stats = useMemo(() => computeStats(tape), [tape]);
  if (tape.length <= 5) return null;

  const askPctColor = stats.askPct >= 60
    ? 'var(--ask)'
    : stats.askPct <= 40
      ? 'var(--bid)'
      : 'var(--text-dim)';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 8px',
        borderBottom: '1px solid var(--rule)',
        flexShrink: 0,
        fontSize: 10,
        color: 'var(--text-dim)',
        fontVariantNumeric: 'tabular-nums',
        letterSpacing: '0.02em',
      }}
    >
      <span>{stats.count} prints</span>
      <span style={{ color: 'var(--rule-bright)' }}>·</span>
      <span>${stats.notionalM}M notional</span>
      <span style={{ color: 'var(--rule-bright)' }}>·</span>
      <span style={{ color: askPctColor, fontWeight: 600 }}>
        {stats.askPct}% ASK
      </span>
    </div>
  );
}

// ── Running volume at price + direction bias ──────────────────────────────────

function buildVolumeMap(tape: TapeEntry[]): Map<number, { total: number; askVol: number }> {
  const now = Date.now() / 1000;
  const cutoff = now - 30;
  const map = new Map<number, { total: number; askVol: number }>();
  for (const e of tape) {
    if (e.ts < cutoff) continue;
    const existing = map.get(e.price) ?? { total: 0, askVol: 0 };
    existing.total += e.size;
    if (e.side === 'ASK') existing.askVol += e.size;
    map.set(e.price, existing);
  }
  return map;
}

// ── Component ─────────────────────────────────────────────────────────────────

const SCROLL_THRESHOLD = 8; // px — if scrollTop > this, user has scrolled up

export function TapeScroll() {
  // Subscribe to lastTapeVersion so this component re-renders on every new tape entry
  const _lastTapeVersion = useTradingStore((s) => s.lastTapeVersion);
  void _lastTapeVersion;

  const tape: TapeEntry[] = useTradingStore.getState().tape.toArray();
  // newest first
  const displayTape = useMemo(() => [...tape].reverse(), [tape]);

  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const prevLengthRef = useRef(displayTape.length);

  // Precompute per-price volume map for hover detail
  const volumeMap = useMemo(() => buildVolumeMap(tape), [tape]);

  // Track scroll position
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const scrolledUp = el.scrollTop > SCROLL_THRESHOLD;
    setUserScrolled(scrolledUp);
    if (!scrolledUp) setNewCount(0);
  }, []);

  // Auto-scroll or count new rows
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const added = displayTape.length - prevLengthRef.current;
    prevLengthRef.current = displayTape.length;

    if (added > 0) {
      if (!userScrolled) {
        el.scrollTop = 0;
      } else {
        setNewCount((c) => c + added);
      }
    }
  }, [displayTape.length, userScrolled]);

  const scrollToTop = useCallback(() => {
    const el = containerRef.current;
    if (el) el.scrollTo({ top: 0, behavior: 'smooth' });
    setUserScrolled(false);
    setNewCount(0);
  }, []);

  // ── Empty state ─────────────────────────────────────────────────────────────

  if (displayTape.length === 0) {
    return (
      <div
        style={{
          height: '200px',
          borderTop: '1px solid var(--rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            color: 'var(--text-mute)',
            fontSize: 11,
            fontStyle: 'normal',
          }}
        >
          // no prints yet
          <BlinkingCursor />
        </span>
      </div>
    );
  }

  // ── Tape list ───────────────────────────────────────────────────────────────

  return (
    <div
      style={{
        height: '200px',
        borderTop: '1px solid var(--rule)',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Stats summary line — only when > 5 prints */}
      <TapeStatsSummary tape={displayTape} />

      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {displayTape.map((entry, idx) => {
          const volData = volumeMap.get(entry.price);
          const runningVol = volData?.total;
          const directionBias: 'BUY AGGRESSION' | 'SELL AGGRESSION' | null = volData
            ? volData.askVol / volData.total >= 0.5
              ? 'BUY AGGRESSION'
              : 'SELL AGGRESSION'
            : null;

          return (
            <TapeRow
              key={`${entry.ts}-${idx}`}
              entry={entry}
              marker={toMarker(entry.marker)}
              isNew={idx === 0 && prevLengthRef.current !== displayTape.length}
              runningVolumeAtPrice={runningVol}
              directionBias={directionBias}
            />
          );
        })}
      </div>

      {/* Floating "↓ NEW (N)" pill */}
      {userScrolled && newCount > 0 && (
        <button
          onClick={scrollToTop}
          style={{
            position: 'absolute',
            bottom: 8,
            right: 8,
            background: 'var(--surface-2)',
            border: '1px solid var(--rule-bright)',
            borderRadius: 9999,
            padding: '3px 10px',
            fontSize: 11,
            cursor: 'pointer',
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            color: 'var(--text-dim)',
            letterSpacing: '0.04em',
          }}
        >
          <span>↓ NEW</span>
          <span style={{ color: 'var(--lime)', fontWeight: 700 }}>
            ({newCount})
          </span>
        </button>
      )}
    </div>
  );
}
