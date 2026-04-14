/**
 * Scanlines — fixed full-viewport scanline overlay (UI-SPEC §6).
 * Two layers:
 *   1. Primary horizontal lines — 0.015 opacity, 3px period (2px gap + 1px line)
 *   2. Secondary vertical lines — 0.008 opacity, 5px period (4px gap + 1px line)
 *
 * 3px/5px periods are coprime — no moiré on integer-scaled Retina displays.
 * pointer-events: none, z-index: 3.
 * No animation needed — static pattern.
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
        backgroundImage: [
          // Primary: horizontal lines, 3px period (2px transparent + 1px line)
          'repeating-linear-gradient(0deg, transparent 0px, transparent 2px, rgba(255,255,255,0.015) 2px, rgba(255,255,255,0.015) 3px)',
          // Secondary: vertical lines, 5px period (4px transparent + 1px line)
          'repeating-linear-gradient(90deg, transparent 0px, transparent 4px, rgba(255,255,255,0.008) 4px, rgba(255,255,255,0.008) 5px)',
        ].join(', '),
        // Explicit pixel sizing prevents browser from scaling the pattern
        backgroundSize: '100% 3px, 5px 100%',
      }}
    />
  );
}
