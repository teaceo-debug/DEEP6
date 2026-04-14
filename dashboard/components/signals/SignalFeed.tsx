'use client';
/**
 * SignalFeed.tsx — per UI-SPEC v2 §4.3 (11.3-r2 upgrade)
 *
 * Upgrades from 11.3 baseline:
 * - scroll-terminal class applied for 4px custom scrollbar
 * - "loading more..." line when scrolled up
 * - Enriched empty state: ascii divider + "awaiting engine output..." line
 * - Passes narrative field from LiveSignalMessage store through to SignalFeedRow
 *
 * 11.3-r4 upgrade:
 * - selectedSignalKey state for context drawer
 * - Click handler on rows (toggle select / deselect)
 * - SignalContext drawer rendered over feed
 */
import { useRef, useEffect, useState, useCallback } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import { SignalFeedRow } from './SignalFeedRow';
import { SignalContext } from './SignalContext';
import type { SignalEvent } from '@/types/deep6';

// -- Blinking cursor (1Hz, --text-mute) --------------------------------------

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

// -- Component ----------------------------------------------------------------

const SCROLL_TOP_THRESHOLD = 40;

function makeRowKey(sig: SignalEvent): string {
  return `${sig.ts}-${sig.bar_index_in_session}`;
}

export function SignalFeed() {
  const lastSignalVersion = useTradingStore((s) => s.lastSignalVersion);
  const signals: SignalEvent[] = useTradingStore.getState().signals.toArray();

  const prevVersionRef = useRef(lastSignalVersion);
  const justArrivedRef = useRef(false);

  if (lastSignalVersion !== prevVersionRef.current) {
    prevVersionRef.current = lastSignalVersion;
    justArrivedRef.current = true;
  } else {
    justArrivedRef.current = false;
  }

  const displaySignals = [...signals].reverse().slice(0, 12);

  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const prevLengthRef = useRef(displaySignals.length);

  // -- Selected signal state for context drawer -------------------------------
  const [selectedSignalKey, setSelectedSignalKey] = useState<string | null>(null);

  const handleRowClick = useCallback((sig: SignalEvent) => {
    const key = makeRowKey(sig);
    setSelectedSignalKey((prev) => (prev === key ? null : key));
  }, []);

  const handleContextClose = useCallback(() => {
    setSelectedSignalKey(null);
  }, []);

  const selectedSig = selectedSignalKey
    ? displaySignals.find((s) => makeRowKey(s) === selectedSignalKey) ?? null
    : null;

  // Full signal list for related-signals lookup (not just the 12-row display slice)
  const allSignals: SignalEvent[] = useTradingStore.getState().signals.toArray();

  // ---------------------------------------------------------------------------

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atTop = el.scrollTop < SCROLL_TOP_THRESHOLD;
    setUserScrolled(!atTop);
    if (atTop) setNewCount(0);
  }, []);

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

  // -- Empty state ------------------------------------------------------------

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
        <p
          style={{
            color: 'var(--text-mute)',
            fontSize: 11,
            opacity: 0.8,
            margin: '4px 0 0',
            letterSpacing: '0.04em',
            userSelect: 'none',
          }}
        >
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
          {'\u2550'.repeat(23)}
        </p>
        <p
          style={{
            color: 'var(--text-mute)',
            fontSize: 11,
            fontStyle: 'italic',
            margin: 0,
          }}
        >
          awaiting engine output...
        </p>
      </div>
    );
  }

  // -- Signal list ------------------------------------------------------------

  return (
    <div className="flex-1" style={{ position: 'relative', overflow: 'hidden' }}>
      {/* Signal context drawer — absolute right side, 400px wide, full height */}
      <SignalContext
        signal={selectedSig}
        allSignals={allSignals}
        onClose={handleContextClose}
      />

      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="scroll-terminal"
        style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}
      >
        {displaySignals.map((sig, idx) => {
          const key = `${sig.ts}-${sig.bar_index_in_session}-${idx}`;
          const rowKey = makeRowKey(sig);
          return (
            <SignalFeedRow
              key={key}
              sig={sig}
              justArrived={idx === 0 && justArrivedRef.current}
              isSelected={selectedSignalKey === rowKey}
              onClick={() => handleRowClick(sig)}
            />
          );
        })}

        {/* "loading more..." hint when user has scrolled up — purely visual */}
        {userScrolled && (
          <div
            style={{
              padding: '6px 12px',
              color: 'var(--text-mute)',
              fontSize: 11,
              fontStyle: 'italic',
              textAlign: 'center',
              userSelect: 'none',
            }}
          >
            loading more...
          </div>
        )}
      </div>

      {/* Up arrow NEW pill */}
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
          <span>&uarr; NEW</span>
          <span style={{ color: 'var(--lime)', fontWeight: 600 }}>
            ({newCount})
          </span>
        </button>
      )}
    </div>
  );
}
