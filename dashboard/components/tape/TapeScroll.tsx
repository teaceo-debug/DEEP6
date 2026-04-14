'use client';
/**
 * TapeScroll.tsx — per UI-SPEC v2 §4.4
 *
 * - 18px rows (TapeRow)
 * - Auto-scroll to top on new rows UNLESS user has scrolled up
 * - "↓ NEW (N)" pill at bottom-right when user has scrolled up
 * - Empty state: // no prints yet
 */
import { useRef, useEffect, useState, useCallback } from 'react';
import { useTradingStore } from '@/store/tradingStore';
import { TapeRow } from './TapeRow';
import type { TapeEntry } from '@/types/deep6';

// ── Component ─────────────────────────────────────────────────────────────────

const SCROLL_THRESHOLD = 8; // px — if scrollTop > this, user has scrolled up

export function TapeScroll() {
  const _lastBarVersion = useTradingStore((s) => s.lastBarVersion);
  void _lastBarVersion;

  const tape: TapeEntry[] = useTradingStore.getState().tape.toArray();
  // newest first
  const displayTape = [...tape].reverse();

  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const prevLengthRef = useRef(displayTape.length);

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
    if (el) el.scrollTop = 0;
    setUserScrolled(false);
    setNewCount(0);
  }, []);

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
          className="text-xs"
          style={{ color: 'var(--text-mute)', fontStyle: 'normal' }}
        >
          // no prints yet
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        height: '200px',
        borderTop: '1px solid var(--rule)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          height: '100%',
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {displayTape.map((entry, idx) => (
          <TapeRow
            key={`${entry.ts}-${idx}`}
            entry={entry}
            isNew={idx === 0 && prevLengthRef.current !== displayTape.length}
          />
        ))}
      </div>

      {/* "↓ NEW (N)" pill */}
      {userScrolled && newCount > 0 && (
        <button
          onClick={scrollToTop}
          style={{
            position: 'absolute',
            bottom: 8,
            right: 8,
            background: 'var(--surface-2)',
            color: 'var(--text)',
            border: '1px solid var(--rule-bright)',
            borderRadius: 9999,
            padding: '2px 8px',
            fontSize: 11,
            cursor: 'pointer',
            zIndex: 10,
          }}
        >
          ↓ NEW ({newCount})
        </button>
      )}
    </div>
  );
}
