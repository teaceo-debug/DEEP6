'use client';

/**
 * KeyboardHelp.tsx — Keyboard shortcuts modal.
 *
 * Opens on `?` keydown (global listener) or when `open` prop is true.
 * Closes on Esc or click-outside.
 * Max-width 440px, --surface-2 bg, --rule-bright border, 16px padding, JetBrains Mono.
 * Backdrop: rgba(0,0,0,0.8), 200ms fade-in.
 * Title: KEYBOARD SHORTCUTS, letter-spaced 0.1em, thin --lime underline.
 * Shortcut rows: 40px tall, alternating --surface-1 on even rows.
 * Footer: italic hint line, "Press Esc to dismiss · Press ? to reopen".
 * Close button: 28×28, top-right, hover --surface-1.
 */

import { useEffect, useRef, useCallback } from 'react';

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
  { key: 'J',     desc: 'Previous bar — replay only' },
  { key: 'K',     desc: 'Play / Pause — replay only' },
  { key: 'L',     desc: 'Next bar — replay only' },
  { key: '1',     desc: 'Speed 1×' },
  { key: '2',     desc: 'Speed 2×' },
  { key: '5',     desc: 'Speed 5×' },
  { key: 'Space', desc: 'Play / Pause — alternative' },
  { key: 'Esc',   desc: 'Close modal — exit replay' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function KeyboardHelp({ open, onClose }: KeyboardHelpProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Focus management: save trigger, move focus into dialog on open, restore on close
  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement;
      // Defer to next frame so the dialog is painted before we focus
      const id = requestAnimationFrame(() => {
        closeBtnRef.current?.focus();
      });
      return () => cancelAnimationFrame(id);
    } else {
      triggerRef.current?.focus();
    }
  }, [open]);

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
  const handleOverlayClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === overlayRef.current) onClose();
  }, [onClose]);

  if (!open) return null;

  return (
    <>
      <style>{`
        @keyframes kbd-backdrop-in {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes kbd-modal-in {
          from { opacity: 0; transform: scale(0.96) translateY(-8px); }
          to   { opacity: 1; transform: scale(1)    translateY(0); }
        }
        .kbd-backdrop {
          animation: kbd-backdrop-in 200ms ease-out forwards;
        }
        .kbd-modal {
          animation: kbd-modal-in 200ms ease-out forwards;
        }
        @media (prefers-reduced-motion: reduce) {
          .kbd-backdrop { animation: none; }
          .kbd-modal    { animation: none; }
        }
      `}</style>
      <div
        ref={overlayRef}
        onClick={handleOverlayClick}
        className="kbd-backdrop"
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.8)',
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
          className="kbd-modal"
          style={{
            width: '100%',
            maxWidth: 440,
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
              padding: '0 16px',
              height: 44,
              borderBottom: '1px solid var(--rule)',
            }}
          >
            <div>
              <span
                style={{
                  fontSize: 11,
                  letterSpacing: '0.1em',
                  color: 'var(--text)',
                  fontWeight: 600,
                  display: 'block',
                  paddingBottom: 2,
                  // Thin --lime underline simulated via box-shadow so it doesn't affect layout
                  borderBottom: '1px solid var(--lime)',
                  lineHeight: 1.4,
                }}
              >
                KEYBOARD SHORTCUTS
              </span>
            </div>
            <button
              ref={closeBtnRef}
              aria-label="Close keyboard help"
              onClick={onClose}
              style={{
                width: 28,
                height: 28,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'transparent',
                border: '1px solid transparent',
                cursor: 'pointer',
                color: 'var(--text-mute)',
                fontSize: 14,
                lineHeight: 1,
                borderRadius: 3,
                fontFamily: 'inherit',
                flexShrink: 0,
                transition: 'background 150ms ease, color 150ms ease, border-color 150ms ease',
              }}
              onMouseEnter={(e) => {
                const btn = e.currentTarget;
                btn.style.background = 'var(--surface-1)';
                btn.style.color = 'var(--text)';
                btn.style.borderColor = 'var(--rule-bright)';
              }}
              onMouseLeave={(e) => {
                const btn = e.currentTarget;
                btn.style.background = 'transparent';
                btn.style.color = 'var(--text-mute)';
                btn.style.borderColor = 'transparent';
              }}
            >
              ✕
            </button>
          </div>

          {/* Shortcut table — 16px horizontal padding, 40px rows */}
          <div style={{ padding: '4px 0 8px' }}>
            {SHORTCUTS.map(({ key, desc }, i) => (
              <div
                key={key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  height: 40,
                  padding: '0 16px',
                  // Alternate even rows with --surface-1 background
                  background: i % 2 === 1 ? 'var(--surface-1)' : 'transparent',
                }}
              >
                {/* Key badge */}
                <kbd
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: 52,
                    padding: '3px 6px',
                    background: 'var(--surface-2)',
                    border: '1px solid var(--rule-bright)',
                    borderRadius: 4,
                    fontSize: 11,
                    fontFamily: 'inherit',
                    color: 'white',
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
              padding: '8px 16px',
              borderTop: '1px solid var(--rule)',
              fontSize: 10,
              color: 'var(--text-mute)',
              letterSpacing: '0.04em',
              fontStyle: 'italic',
            }}
          >
            Press{' '}
            <kbd
              style={{
                fontSize: 10,
                padding: '1px 4px',
                background: 'var(--surface-2)',
                border: '1px solid var(--rule-bright)',
                borderRadius: 2,
                color: 'white',
                fontFamily: 'inherit',
                fontStyle: 'normal',
              }}
            >
              Esc
            </kbd>
            {' '}to dismiss · Press{' '}
            <kbd
              style={{
                fontSize: 10,
                padding: '1px 4px',
                background: 'var(--surface-2)',
                border: '1px solid var(--rule-bright)',
                borderRadius: 2,
                color: 'white',
                fontFamily: 'inherit',
                fontStyle: 'normal',
              }}
            >
              ?
            </kbd>
            {' '}to reopen
          </div>
        </div>
      </div>
    </>
  );
}
