'use client';
/**
 * SignalFeed.tsx — per UI-SPEC v2 §4.3 (11.3 upgrade)
 *
 * Upgrades from 11.2 baseline:
 * - Auto-scroll only when scrollTop < 40px (was naive always-top)
 * - "↑ NEW (N)" pill at top-right when user has scrolled down
 * - Blinking cursor after "tail -f /dev/orderflow" empty state
 * - Passes narrative field from LiveSignalMessage store through to SignalFeedRow
 */
import { useRef, useEffect, useState, useCallback } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import { SignalFeedRow } from './SignalFeedRow';
import type { SignalEvent } from '@/types/deep6';

// ── Blinking cursor (1Hz, --text-mute) ───────────────────────────────────────

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

// ── Component ─────────────────────────────────────────────────────────────────

const SCROLL_TOP_THRESHOLD = 40; // px — consider "at top" if scrollTop < this

export function SignalFeed() {
  // Reactive: re-renders when lastSignalVersion changes (new signal arrives)
  const lastSignalVersion = useTradingStore((s) => s.lastSignalVersion);
  // Read the actual signal array non-reactively via getState to avoid extra render
  const signals: SignalEvent[] = useTradingStore.getState().signals.toArray();

  // Track which signal is "just arrived" for TYPE_A animation.
  const prevVersionRef = useRef(lastSignalVersion);
  const justArrivedRef = useRef(false);

  if (lastSignalVersion !== prevVersionRef.current) {
    prevVersionRef.current = lastSignalVersion;
    justArrivedRef.current = true;
  } else {
    justArrivedRef.current = false;
  }

  // RingBuffer.toArray() returns oldest→newest; reverse for newest-first display.
  // Cap at 12 visible rows per UI-SPEC §4.3.
  const displaySignals = [...signals].reverse().slice(0, 12);

  // Scroll tracking
  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const prevLengthRef = useRef(displaySignals.length);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atTop = el.scrollTop < SCROLL_TOP_THRESHOLD;
    setUserScrolled(!atTop);
    if (atTop) setNewCount(0);
  }, []);

  // Auto-scroll new rows into view only when at top
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const added = displaySignals.length - prevLengthRef.current;
    prevLengthRef.current = displaySignals.length;

    if (added > 0) {
      if (!userScrolled) {
        el.scrollTop = 0;
      } else {
        setNewCount((c) => c + added);
      }
    }
  }, [displaySignals.length, userScrolled]);

  const scrollToTop = useCallback(() => {
    const el = containerRef.current;
    if (el) el.scrollTo({ top: 0, behavior: 'smooth' });
    setUserScrolled(false);
    setNewCount(0);
  }, []);

  // ── Empty state ─────────────────────────────────────────────────────────────

  if (displaySignals.length === 0) {
    return (
      <div
        className="flex-1 flex flex-col items-center justify-center gap-1"
        style={{ padding: '16px' }}
      >
        <p style={{ color: 'var(--text-mute)', fontSize: 13, margin: 0 }}>
          [ NO SIGNALS ]
        </p>
        <p
          style={{
            color: 'var(--text-mute)',
            fontSize: 11,
            fontStyle: 'italic',
            margin: 0,
          }}
        >
          tail -f /dev/orderflow
          <BlinkingCursor />
        </p>
      </div>
    );
  }

  // ── Signal list ─────────────────────────────────────────────────────────────

  return (
    <div className="flex-1" style={{ position: 'relative', overflow: 'hidden' }}>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}
      >
        {displaySignals.map((sig, idx) => (
          <SignalFeedRow
            key={`${sig.ts}-${sig.bar_index_in_session}-${idx}`}
            sig={sig}
            justArrived={idx === 0 && justArrivedRef.current}
          />
        ))}
      </div>

      {/* "↑ NEW (N)" pill — shown when user has scrolled down */}
      {userScrolled && newCount > 0 && (
        <button
          onClick={scrollToTop}
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            background: 'var(--surface-2)',
            border: '1px solid var(--rule-bright)',
            borderRadius: 9999,
            padding: '2px 8px',
            fontSize: 11,
            cursor: 'pointer',
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            color: 'var(--text-dim)',
          }}
        >
          <span>↑ NEW</span>
          <span style={{ color: 'var(--lime)', fontWeight: 600 }}>
            ({newCount})
          </span>
        </button>
      )}
    </div>
  );
}
