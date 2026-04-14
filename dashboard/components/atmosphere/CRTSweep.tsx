'use client';

import { motion } from 'motion/react';

/**
 * CRTSweep — 1px horizontal bar sweeping top→bottom every 8s (UI-SPEC §6).
 * Respects prefers-reduced-motion: renders null if reduction is preferred.
 * pointer-events: none, z-index: 4.
 */
export function CRTSweep() {
  // Respect prefers-reduced-motion
  if (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ) {
    return null;
  }

  return (
    <motion.div
      aria-hidden="true"
      animate={{ top: ['0%', '100%'] }}
      transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
      style={{
        position: 'fixed',
        left: 0,
        right: 0,
        height: '1px',
        background: 'rgba(255,255,255,0.04)',
        pointerEvents: 'none',
        zIndex: 4,
      }}
    />
  );
}
