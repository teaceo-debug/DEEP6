'use client';

/**
 * CRTSweep — 1px horizontal bar sweeping top→bottom every 8s (UI-SPEC §6).
 * Pure CSS keyframe animation via `crt-sweep` class defined in globals.css.
 * Opacity bumped to 5% for slightly more visibility on dark backgrounds.
 * Reduced-motion: CSS @media in globals.css collapses animation-duration to 0.01ms.
 * pointer-events: none, z-index: 4.
 */
export function CRTSweep() {
  return (
    <div
      aria-hidden="true"
      className="crt-sweep"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: '1px',
        background: 'rgba(255,255,255,0.03)',
        pointerEvents: 'none',
        zIndex: 4,
        // Ensure no sub-pixel rounding makes this disappear on Retina
        willChange: 'transform',
      }}
    />
  );
}
