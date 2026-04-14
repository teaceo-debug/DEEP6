/**
 * Scanlines — fixed full-viewport scanline overlay (UI-SPEC §6).
 * Pure CSS: no client directive needed. pointer-events: none, z-index: 3.
 */
export function Scanlines() {
  return (
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 3,
        backgroundImage:
          'repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(255,255,255,0.012) 2px, rgba(255,255,255,0.012) 3px)',
      }}
    />
  );
}
