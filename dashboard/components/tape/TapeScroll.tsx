'use client';
/**
 * TapeScroll.tsx — per UI-SPEC v2 §4.4 (11.3 upgrade)
 *
 * Upgrades from 11.2 baseline:
 * - 20px rows via TapeRow upgrade
 * - Floating "↓ NEW (N)" pill styled as surface-2 / rule-bright / lime count
 * - Empty state with blinking cursor: // no prints yet_
 * - Scroll pill right-aligned, floats above content
 */
import { useRef, useEffect, useState, useCallback } from 'react';
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

// ── Component ─────────────────────────────────────────────────────────────────

const SCROLL_THRESHOLD = 8; // px — if scrollTop > this, user has scrolled up

export function TapeScroll() {
  // Subscribe to lastTapeVersion so this component re-renders on every new tape entry
  const _lastTapeVersion = useTradingStore((s) => s.lastTapeVersion);
  void _lastTapeVersion;

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
            marker={toMarker(entry.marker)}
            isNew={idx === 0 && prevLengthRef.current !== displayTape.length}
          />
        ))}
      </div>

      {/* Floating "↓ NEW (N)" pill — styled per spec: surface-2 bg, rule-bright border, lime N */}
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
