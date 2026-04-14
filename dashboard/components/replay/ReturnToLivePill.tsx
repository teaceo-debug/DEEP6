/**
 * ReturnToLivePill.tsx — per UI-SPEC v2 §4.8
 *
 * Live mode:   solid --ask pill, ● LIVE, breathing opacity pulse (1.5s loop)
 * Replay mode: outlined --rule-bright border, --text-dim text, ● (grey) LIVE,
 *              click → setMode('live') + setPanned(false)
 *
 * Pill: auto-width, min 90px, 6px 12px padding, 1px --rule-bright border.
 * Dot: exactly 6px × 6px, border-radius 50%, vertically centered via flex.
 * Hover: scale(1.05) 150ms ease.
 * Also renders as absolute top-right pill (12px from edges) when userHasPanned.
 */
'use client';
import { motion, useReducedMotion } from 'motion/react';
import { useReplayStore } from '@/store/replayStore';
import { DURATION, SPRING } from '@/lib/animations';

// ── Shared pill styles ────────────────────────────────────────────────────────

const BASE_PILL: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  fontWeight: 600,
  fontSize: 11,
  padding: '6px 12px',
  borderRadius: 9999,
  letterSpacing: '0.08em',
  fontFamily: 'var(--font-jetbrains-mono)',
  userSelect: 'none',
  minWidth: 90,
  border: '1px solid var(--rule-bright)',
  whiteSpace: 'nowrap',
};

// Exactly 6px dot, vertically centered via flex parent
const DOT_BASE: React.CSSProperties = {
  width: 6,
  height: 6,
  borderRadius: '50%',
  flexShrink: 0,
  display: 'block',
};

// ── Component ─────────────────────────────────────────────────────────────────

export function ReturnToLivePill() {
  const reduced = useReducedMotion();
  const mode = useReplayStore((s) => s.mode);
  const userHasPanned = useReplayStore((s) => s.userHasPanned);
  const isLive = mode === 'live';

  const handleClick = () => {
    const store = useReplayStore.getState();
    if (!isLive) {
      store.setMode('live', null);
    }
    store.setPanned(false);
  };

  return (
    <>
      {/* ── Replay-strip pill ── */}
      {isLive ? (
        // Live: solid --ask with breathing pulse
        <motion.div
          animate={reduced ? { opacity: 1 } : { opacity: [0.7, 1, 0.7] }}
          transition={
            reduced
              ? { duration: 0 }
              : { duration: DURATION.slow / 1000 * 3, repeat: Infinity, ease: 'easeInOut' }
          }
          style={{
            ...BASE_PILL,
            background: 'var(--ask)',
            borderColor: 'var(--ask)',
            color: '#000000',
            cursor: 'default',
          }}
        >
          {/* Green dot — contrasting on --ask fill */}
          <span style={{ ...DOT_BASE, background: 'rgba(0,0,0,0.5)' }} />
          LIVE
        </motion.div>
      ) : (
        // Replay: outlined, click returns to live
        <motion.button
          onClick={handleClick}
          title="Switch to live mode"
          aria-label="Switch to live mode"
          whileHover={reduced ? {} : { scale: 1.05 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
          style={{
            ...BASE_PILL,
            background: 'transparent',
            color: 'var(--text-dim)',
            cursor: 'pointer',
          }}
        >
          {/* Grey dot */}
          <span style={{ ...DOT_BASE, background: 'var(--text-mute)' }} />
          LIVE
        </motion.button>
      )}

      {/* ── Chart overlay pill — appears when user has panned away ── */}
      {userHasPanned && (
        <motion.button
          onClick={handleClick}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.85 }}
          whileHover={reduced ? {} : { scale: 1.05 }}
          transition={
            reduced
              ? { duration: 0 }
              : { type: 'spring', stiffness: 400, damping: 28 }
          }
          style={{
            position: 'fixed',
            top: 56,
            right: 12,
            zIndex: 20,
            ...BASE_PILL,
            background: 'var(--surface-1)',
            color: 'var(--lime)',
            borderColor: 'var(--rule-bright)',
            cursor: 'pointer',
            fontSize: 11,
          }}
        >
          ↘ RETURN TO LIVE
        </motion.button>
      )}
    </>
  );
}
