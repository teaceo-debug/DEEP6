/**
 * Grain — fixed full-viewport noise grain overlay (UI-SPEC §6).
 * SVG tile at mix-blend-mode: overlay, opacity 0.04.
 * pointer-events: none, z-index: 2.
 */
export function Grain() {
  return (
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 2,
        backgroundImage: 'url(/grain.svg)',
        backgroundRepeat: 'repeat',
        mixBlendMode: 'overlay',
        opacity: 0.04,
      }}
    />
  );
}
