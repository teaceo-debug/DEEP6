/**
 * Grain — fixed full-viewport noise grain overlay (UI-SPEC §6).
 * SVG tile at mix-blend-mode: overlay, opacity 0.035.
 * Animated via grain-shift keyframe (12s, 8 steps) for subtle motion.
 * Amplitudes are ±2px max — keep them small to avoid perceptible flicker.
 * Respects prefers-reduced-motion via CSS media query in globals.css.
 * pointer-events: none, z-index: 2.
 */
export function Grain() {
  return (
    <div
      aria-hidden="true"
      className="grain-animated"
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 2,
        backgroundImage: 'url(/grain.svg)',
        backgroundRepeat: 'repeat',
        mixBlendMode: 'overlay',
        opacity: 0.035,
        // willChange prevents compositor layer thrash on step-animation
        willChange: 'background-position',
      }}
    />
  );
}
