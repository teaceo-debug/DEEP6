# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## footprint-renderer-blank-canvas — Volume bar fills collapse to zero width when barSpacing is small
- **Date:** 2026-04-14
- **Error patterns:** blank canvas, no bars, volume bars invisible, footprint empty, renderer drawing nothing, barSpacing, halfBarW, gutter, bitmap pixels, hpr
- **Root cause:** `halfBarW = halfW - Math.round(2 * hpr)` subtracted a 4-bitmap-px gutter on Retina. With 5 bars, barSpacing ≈ 6 CSS px → halfW = 5 bitmap px → halfBarW = 1 px. Any volume ratio < 0.5 rounded to 0-px fill, so nearly all rows drew nothing. The 1px centerline gap is already implicit in the `xC - 1` / `xC + 1` offsets in fillRect — no explicit subtraction needed.
- **Fix:** Set `halfBarW = halfW` directly (removed the `gutterBitmap` subtraction). One line change in `FootprintRenderer.ts`.
- **Files changed:** dashboard/lib/lw-charts/FootprintRenderer.ts
---

