/**
 * ReturnToLivePill.tsx — per UI-SPEC v2 §4.8
 *
 * Live mode:   solid --ask pill, ● LIVE, breathing opacity pulse (1.5s loop)
 * Replay mode: outlined --rule-bright border, --text-dim text, ● (grey) LIVE,
 *              click → setMode('live') + setPanned(false)
 *
 * Also renders as absolute top-right pill when userHasPanned is true (ReturnToLive overlay).
 * That overlay uses scale spring on appear, fade+scale on dismiss.
 */
'use client';
import { motion, useReducedMotion } from 'motion/react';
import { useReplayStore } from '@/store/replayStore';
import { DURATION, SPRING } from '@/lib/animations';

// ── Shared pill styles ────────────────────────────────────────────────────────

const BASE_PILL: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  fontWeight: 600,
  fontSize: 11,
  padding: '4px 10px',
  borderRadius: 9999,
  letterSpacing: '0.08em',
  fontFamily: 'var(--font-jetbrains-mono)',
  userSelect: 'none',
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
              : { duration: DURATION.slow / 1000 * 3, repeat: Infinity, ease: 'easeInOut' } // 1500ms live pill breathe
          }
          style={{
            ...BASE_PILL,
            background: 'var(--ask)',
            color: '#000000',
            cursor: 'default',
          }}
        >
          {/* Green dot */}
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#000000',
              opacity: 0.6,
              flexShrink: 0,
            }}
          />
          LIVE
        </motion.div>
      ) : (
        // Replay: outlined, click returns to live
        <button
          onClick={handleClick}
          title="Switch to live mode"
          aria-label="Switch to live mode"
          style={{
            ...BASE_PILL,
            background: 'transparent',
            color: 'var(--text-dim)',
            border: '1px solid var(--rule-bright)',
            cursor: 'pointer',
          }}
        >
          {/* Grey dot */}
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--text-mute)',
              flexShrink: 0,
            }}
          />
          LIVE
        </button>
      )}

      {/* ── Chart overlay pill — appears when user has panned away ── */}
      {userHasPanned && (
        <motion.button
          onClick={handleClick}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.85 }}
          transition={
            reduced
              ? { duration: 0 }
              : { type: 'spring', stiffness: 400, damping: 28 } // intentionally above SPRING.pop — extra-snappy overlay appear
          }
          style={{
            position: 'fixed',
            top: 56,   // below header + small gap
            right: 12,
            zIndex: 20,
            ...BASE_PILL,
            background: 'var(--surface-1)',
            color: 'var(--lime)',
            border: '1px solid var(--rule-bright)',
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
