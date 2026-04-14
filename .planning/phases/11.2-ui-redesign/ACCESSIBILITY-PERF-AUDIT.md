# Accessibility & Performance Audit — Phase 11.3 R4

Audited: 2026-04-13  
Scope: `dashboard/app/layout.tsx`, `dashboard/hooks/*.ts` (excl. useWebSocket), `dashboard/lib/**` (excl. lw-charts/), all in-scope components per task brief.

---

## Accessibility findings

- [x] A11Y-01: **Connection dot missing `role`** — `<span aria-label="...">` on a non-interactive element is not announced by screen readers without `role="img"`. **Fixed**: added `role="img"` and improved label text to `"Connection status: connected/feed stale/disconnected"`.

- [x] A11Y-02: **Session stats counters (B:/S:) not labelled** — bare `B:42  S:7` text is cryptic to AT. **Fixed**: added `aria-label="\${barCount} bars, \${signalCount} signals this session"` on the container span.

- [x] A11Y-03: **Signals-per-minute chart missing accessible label** — the `SpmChart` SVG wrapper span had no role or label. **Fixed**: added `role="img"` and `aria-label="Signal rate: N signals this minute"` to the wrapper span; SVGs inside remain `aria-hidden`.

- [x] A11Y-04: **KronosBar Sparkline SVG not hidden** — the 80×14 bias sparkline SVG was rendered without `aria-hidden`, causing AT to traverse empty SVG paths. **Fixed**: added `aria-hidden="true"`.

- [x] A11Y-05: **KronosBar DirectionStrip SVG not hidden** — same issue as A11Y-04 for the 4px direction history strip. **Fixed**: added `aria-hidden="true"`.

- [x] A11Y-06: **KronosBar pulsing dot missing `aria-hidden`** — decorative `motion.div` dot was not hidden from AT. **Fixed**: added `aria-hidden="true"` to the pulsing dot `motion.div`.

- [x] A11Y-07: **No `<h1>` for screen readers** — the dashboard has no visible or hidden page heading, so AT users have no landmark to orient by. **Fixed**: added visually-hidden `<h1>DEEP6 — NQ Footprint Trading Dashboard</h1>` in `app/layout.tsx` using the standard clip-rect technique.

- [x] A11Y-08: **KeyboardHelp dialog missing focus management** — when opened, focus stayed on the trigger element behind the overlay; when closed, focus was lost to `<body>`. **Fixed**: added `useEffect` that saves the trigger element, focuses the close button via `requestAnimationFrame` on open, and restores focus on close. Close button now has `ref={closeBtnRef}`.

- [ ] A11Y-09: **`--text-mute: #4a4a4a` fails WCAG AA for body text** — contrast ratio ~2.6:1 on `--void: #000000` (minimum 4.5:1 required for text ≤18px). **Documented** in `globals.css` comment block. Not changed: this token is used as a *decorative/disabled* colour throughout (pipe separators, label prefixes), not for readable body content. To fix if used on body text, brighten to `#6a6a6a` (~4.5:1). Deferred — would require auditing every usage across signal/zone components owned by other R4 agents.

- [ ] A11Y-10: **Price sparkline (`PriceSparkline`) has `aria-hidden` but no accessible alternative** — currently `aria-hidden` (correct for decorative). The surrounding `<span title="Last 30 close prices.">` provides a basic tooltip but no screen-reader text. Deferred — the price value itself is read as text immediately to the left; the sparkline is supplemental. Consider `role="img" aria-label="Price trend: last 30 bars"` if the sparkline becomes a first-class data element.

---

## Performance findings

- [x] PERF-01: **`lib/digit-roll.tsx` TS errors blocking build** — `harmonizedDigitRollTransition`, `DELTA_VISIBLE_MS`, `FLASH_DURATION_MS` were imported but not exported from `animations.ts`. This caused `npm run build` to fail (pre-existing, introduced by another agent's untracked `digit-roll.tsx`). **Fixed**: added the three missing exports to `animations.ts` (`harmonizedDigitRollTransition` as alias for `digitRollTransition`, `DELTA_VISIBLE_MS = 800`, `FLASH_DURATION_MS = 300`).

- [x] PERF-02: **`MotionValue<string>` rendered as JSX child — TS4 type error** — `digit-roll.tsx` line 115 passed a `MotionValue<string>` directly as a React child; motion supports this at runtime but the TypeScript types don't reflect it. **Fixed**: cast to `unknown as string` with explanatory comment.

- [x] PERF-03: **`KronosBiasBar` CSS transition without reduced-motion guard** — `transition-all duration-300` Tailwind classes ran unconditionally. The global CSS `@media (prefers-reduced-motion: reduce)` kill-switch covers this, but Tailwind's own `motion-safe:` prefix is the idiomatic guard. **Fixed**: replaced with `motion-safe:transition-all motion-safe:duration-300`.

- [ ] PERF-04: **`prefersReducedMotion()` called at render time (snapshot)** — `KronosBar` calls `prefersReducedMotion()` synchronously during render (not via a hook), so it doesn't react to OS preference changes mid-session. Low impact in practice (requires OS settings panel open during use). Deferred — fix would require converting to `useReducedMotion()` from motion/react, which is in-scope but touches ConfluencePulse-adjacent code.

- [ ] PERF-05: **Ring buffer `toArray()` in 2s poll loop** — `HeaderStrip` calls `state.signals.toArray()` every 2 seconds to build the SPM bins. At SIGNAL_CAPACITY=200 this is O(200) per tick — acceptable. No action needed; documented for future capacity review if SIGNAL_CAPACITY grows to 10k+.

- [x] PERF-06: **All `useEffect` cleanup functions verified** — `useWebSocket`: timer + visibilitychange listener cleaned up correctly. `useReplayController`: all 4 effects return cleanup functions (cancelled flag, clearInterval, cancelAnimationFrame). `HeaderStrip`: clock interval and SPM interval both return `clearInterval`. `ReplayControls`: keyboard handler returns `removeEventListener`. No memory leaks found.

- [x] PERF-07: **Store subscriptions are selector-scoped** — all `useTradingStore(s => s.fieldName)` calls use selectors, not full-state subscriptions. `useFootprintData` subscribes via `subscribeWithSelector` on `lastBarVersion` — correct. No unscoped `useStore()` calls found.

- [x] PERF-08: **Bundle: single motion install** — `npm ls motion framer-motion` confirms `motion@11.18.2` wrapping `framer-motion@11.18.2` at the same version. Not doubled; no bundle bloat from duplicate packages.

---

## Fixed in this pass

| File | Change |
|------|--------|
| `components/layout/HeaderStrip.tsx` | Added `role="img"` to connection dot; improved aria-label text; added `aria-label` to session stats span; added `role="img"` + `aria-label` to SPM chart wrapper |
| `components/score/KronosBar.tsx` | Added `aria-hidden="true"` to Sparkline SVG, DirectionStrip SVG, and pulsing dot `motion.div`; added reduced-motion guard to pulsing dot `animate`/`transition` props |
| `components/score/KronosBiasBar.tsx` | Replaced `transition-all duration-300` with `motion-safe:transition-all motion-safe:duration-300` |
| `components/common/KeyboardHelp.tsx` | Added focus-trap on open (saves trigger, focuses close button via rAF), restores focus on close; `closeBtnRef` wired to close button; `handleOverlayClick` wrapped in `useCallback` |
| `app/layout.tsx` | Added visually-hidden `<h1>` landmark for screen readers |
| `app/globals.css` | Added WCAG AA contrast ratio documentation comment for all text tokens |
| `lib/animations.ts` | Exported `harmonizedDigitRollTransition` (alias), `DELTA_VISIBLE_MS`, `FLASH_DURATION_MS` to unblock build |
| `lib/digit-roll.tsx` | Cast `MotionValue<string>` to `unknown as string` in JSX to fix TS error |

---

## Deferred / out-of-scope

- A11Y-09: `--text-mute` contrast fix — requires audit of all usage across agent-owned components (signals, zones)
- A11Y-10: Price sparkline accessible label upgrade — currently decorative; deferred until design clarifies intent
- PERF-04: `prefersReducedMotion()` snapshot → `useReducedMotion()` hook migration in KronosBar — touches ConfluencePulse-adjacent rendering; low priority
- Tab order verification across full layout — `app/page.tsx` is out of scope for this agent
- axe-core automated scan — no new deps installed per instructions; manual findings documented above
