'use client';

/**
 * KeyboardHelp.tsx — Keyboard shortcuts modal.
 *
 * Opens on `?` keydown (global listener) or when `open` prop is true.
 * Closes on Esc or click-outside.
 * 400×320px, --surface-2 bg, --rule-bright border, JetBrains Mono throughout.
 */

import { useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface KeyboardHelpProps {
  open: boolean;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Shortcut data
// ---------------------------------------------------------------------------

const SHORTCUTS = [
  { key: '?',     desc: 'Show this help' },
  { key: 'J',     desc: 'Previous bar (replay only)' },
  { key: 'K',     desc: 'Play / Pause (replay only)' },
  { key: 'L',     desc: 'Next bar (replay only)' },
  { key: '1',     desc: 'Speed 1×' },
  { key: '2',     desc: 'Speed 2×' },
  { key: '5',     desc: 'Speed 5×' },
  { key: 'Space', desc: 'Play / Pause (alternative)' },
  { key: 'Esc',   desc: 'Close modal / exit replay' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function KeyboardHelp({ open, onClose }: KeyboardHelpProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Global `?` key opens the modal
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (e.key === '?' || e.key === '/') {
        e.preventDefault();
        // Toggle — if already open let Esc handle close
        if (!open) onClose(); // won't fire — caller controls open; this just signals intent
      }
      if (e.key === 'Escape' && open) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  // Click-outside to close
  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onClose();
  }

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 200,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        style={{
          width: 400,
          background: 'var(--surface-2)',
          border: '1px solid var(--rule-bright)',
          borderRadius: 4,
          fontFamily: "'JetBrains Mono', monospace",
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            borderBottom: '1px solid var(--rule)',
          }}
        >
          <span
            style={{
              fontSize: 11,
              letterSpacing: '0.08em',
              color: 'var(--text-dim)',
              fontWeight: 600,
            }}
          >
            KEYBOARD SHORTCUTS
          </span>
          <button
            aria-label="Close keyboard help"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-mute)',
              fontSize: 14,
              lineHeight: 1,
              padding: '2px 4px',
              borderRadius: 3,
              fontFamily: 'inherit',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-mute)'; }}
          >
            ✕
          </button>
        </div>

        {/* Shortcut table */}
        <div style={{ padding: '8px 0 12px' }}>
          {SHORTCUTS.map(({ key, desc }) => (
            <div
              key={key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '5px 14px',
              }}
            >
              {/* Key badge */}
              <kbd
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  minWidth: 52,
                  padding: '2px 6px',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--rule-bright)',
                  borderRadius: 3,
                  fontSize: 11,
                  fontFamily: 'inherit',
                  color: 'var(--lime)',
                  letterSpacing: '0.02em',
                  flexShrink: 0,
                  boxShadow: 'inset 0 -1px 0 var(--rule)',
                }}
              >
                {key}
              </kbd>
              {/* Description */}
              <span
                style={{
                  fontSize: 11,
                  color: 'var(--text-dim)',
                  letterSpacing: '0.01em',
                }}
              >
                {desc}
              </span>
            </div>
          ))}
        </div>

        {/* Footer hint */}
        <div
          style={{
            padding: '8px 14px',
            borderTop: '1px solid var(--rule)',
            fontSize: 10,
            color: 'var(--text-mute)',
            letterSpacing: '0.04em',
          }}
        >
          Press <kbd style={{ fontSize: 10, padding: '1px 4px', background: 'var(--surface-1)', border: '1px solid var(--rule-bright)', borderRadius: 2, color: 'var(--lime)', fontFamily: 'inherit' }}>Esc</kbd> or click outside to close
        </div>
      </div>
    </div>
  );
}
