/**
 * ReturnToLivePill.tsx — per UI-SPEC v2 §4.8
 *
 * Live mode:   solid --ask pill, white text, breathing opacity pulse (1.5s loop)
 * Replay mode: outlined --text-dim button, no fill, click returns to live
 * Text:        ● LIVE in both states
 */
'use client';
import { motion, useReducedMotion } from 'motion/react';
import { useReplayStore } from '@/store/replayStore';

export function ReturnToLivePill() {
  const reduced = useReducedMotion();
  const mode = useReplayStore((s) => s.mode);
  const isLive = mode === 'live';

  const handleClick = () => {
    if (!isLive) {
      useReplayStore.getState().setMode('live', null);
    }
  };

  if (isLive) {
    // Solid --ask filled pill with breathing pulse
    return (
      <motion.div
        animate={reduced ? { opacity: 1 } : { opacity: [0.7, 1, 0.7] }}
        transition={
          reduced
            ? { duration: 0 }
            : { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }
        }
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          background: 'var(--ask)',
          color: '#000000',
          fontWeight: 600,
          fontSize: 11,
          padding: '4px 10px',
          borderRadius: 9999,
          letterSpacing: '0.08em',
          userSelect: 'none',
          cursor: 'default',
        }}
      >
        ● LIVE
      </motion.div>
    );
  }

  // Replay mode: outlined button
  return (
    <button
      onClick={handleClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: 'transparent',
        color: 'var(--text-dim)',
        border: '1px solid var(--text-dim)',
        fontWeight: 600,
        fontSize: 11,
        padding: '4px 10px',
        borderRadius: 9999,
        letterSpacing: '0.08em',
        cursor: 'pointer',
      }}
    >
      ● LIVE
    </button>
  );
}
