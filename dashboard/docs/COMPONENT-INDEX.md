# DEEP6 Dashboard — Component Index

Every component in `dashboard/components/`, grouped by directory. Each entry shows file path, one-line purpose, key props, store slices consumed, and where it renders in the layout.

---

## Layout

### HeaderStrip

**File:** `components/layout/HeaderStrip.tsx`

**Purpose:** 44px top bar showing instrument code, live price with flash, E10 bias, GEX regime, ET clock, signals-per-minute sparkline, session stats, and connection dot.

**Key props:** none (reads from store directly)

**Subscribes to:**
- `score.totalScore`, `score.tier`, `score.kronosBias`, `score.kronosDirection`, `score.gexRegime`
- `status.connected`, `status.feedStale`, `status.pnl`, `status.circuitBreakerActive`
- `status.barsReceived`, `status.signalsFired`, `status.uptimeSeconds`, `status.activeClients`
- `bars` ring buffer (for latest close price and price sparkline)
- `signals` ring buffer (for signals-per-minute histogram)

**Renders to:** Top of `app/page.tsx`, full width, 44px height.

**Notable:** Price flashes `--ask` / `--bid` for 300ms on tick direction change, then settles to `--text`. Connection dot pulses with scale + opacity animation when connected, shows `--amber` while reconnecting. SPM histogram (`SpmChart`) buckets signals into 30s bins. `role="img"` on connection dot and SPM chart for AT.

---

## Footprint

### FootprintChart

**File:** `components/footprint/FootprintChart.tsx`

**Purpose:** Container for the LW Charts custom series + sibling Canvas overlays. Manages chart lifecycle, theme sync, and bar data projection.

**Key props:** none

**Subscribes to:** `lastBarVersion` (via `useFootprintData` hook)

**Renders to:** `flex-1` left column of main layout.

**Subcomponents:**

#### ZoneOverlay

**File:** `components/footprint/ZoneOverlay.tsx`

**Purpose:** Absolute-positioned `<canvas>` over the chart that draws zone bands (LVN, HVN, ABSORPTION, GEX_CALL, GEX_PUT, EXHAUSTION, VAH, VAL).

**Key props:** `chartApi` (IChartApi reference)

**Subscribes to:** `bars` (for zone data — currently derives from bar poc_price; full zone_registry in Phase 5+)

**Renders to:** Absolute overlay at `inset:0` inside FootprintChart container.

#### VolumeProfile

**File:** `components/footprint/VolumeProfile.tsx`

**Purpose:** Right-edge canvas (~64px wide) showing cumulative bid/ask volume histogram per price level for the visible bars.

**Key props:** `chartApi`, `priceRange`

**Subscribes to:** `lastBarVersion`

**Renders to:** Right edge of FootprintChart, absolute-positioned.

---

## Score / Hero Column

### ConfluencePulse

**File:** `components/score/ConfluencePulse.tsx`

**Purpose:** 320×320 SVG signature hero. Three concentric rings: 44-arc engine ring (one arc per signal, category-color ignite), 8-sector category ring (score-proportional opacity), and inner core with digit-rolling score number + tier badge + direction glyph.

**Key props:** none

**Subscribes to:**
- `score.totalScore`, `score.tier`, `score.direction`
- `score.categoriesFiring`, `score.categoryScores`

**Renders to:** Top slot of the 360px hero column, 360px tall.

**Notable:** TYPE_A event triggers a 1.5s white-hot flash sequence: arcs snap to `#ffffff`, inner core scales 1→1.08→1 with 3× glow intensity, primary radial bloom (`r:90→200, opacity:0.3→0`), aftershock bloom (`r:100→300, delay:400ms`), ambient background flash, and a `body.shake` CSS class for a 4px screen-shake (80ms, respects `prefers-reduced-motion`). All animations defined in `lib/animations.ts`. Score number uses Motion `useMotionValue` + spring transition for digit roll.

### KronosBar

**File:** `components/score/KronosBar.tsx`

**Purpose:** Kronos E10 ML directional bias capsule. Shows direction label, confidence %, gradient fill bar (magenta → direction-color), bias sparkline, direction history strip, and pulsing connection dot.

**Key props:** none

**Subscribes to:** `score.kronosBias`, `score.kronosDirection`

**Renders to:** Middle slot of hero column, 88px tall.

**Notable:** All Kronos output is exclusively `--magenta` (#ff00aa). Sparkline and direction strip SVGs are `aria-hidden`. Pulsing dot is `aria-hidden`. `kronosConfidence` is derived as `Math.abs(kronosBias)` (stub — backend does not yet expose a separate confidence field).

### KronosBiasBar

**File:** `components/score/KronosBiasBar.tsx`

**Purpose:** The gradient fill bar sub-component used inside KronosBar. Magenta-to-direction-color gradient at fill width = confidence%.

**Key props:** `confidence: number`, `direction: string`

**Subscribes to:** none (receives props from KronosBar)

**Renders to:** Inside KronosBar.

---

## Zones

### ZoneList

**File:** `components/zones/ZoneList.tsx`

**Purpose:** Compact table of key price levels (POC, VAH, VAL, PDH, PDL, LVN, HVN) with proximity mini-bars, age tracker, reaction counts, hover detail, and profile shape indicator.

**Key props:** none

**Subscribes to:** `bars` (for `poc_price`; full `zone_registry` wiring deferred to Phase 5+)

**Renders to:** Bottom slot of hero column, fills remaining flex-1 space.

**Notable:** Zone codes have strict colors: POC = `--amber`, VAH/VAL = `--text`, LVN = `--cyan`, HVN = `--amber`, PDH/PDL = `--text-dim`. Alert count is hardcoded 0 pending backend session-level tracking.

---

## Signals

### SignalFeed

**File:** `components/signals/SignalFeed.tsx`

**Purpose:** 12-row signal ticker, newest at top. Manages the ring buffer slice and empty state.

**Key props:** none

**Subscribes to:** `lastSignalVersion`, `signals` ring buffer

**Renders to:** Top half of the 320px right column.

**Empty state:** `[ NO SIGNALS ]` with `tail -f /dev/orderflow` subtitle in `--text-mute` italic.

### SignalFeedRow

**File:** `components/signals/SignalFeedRow.tsx`

**Purpose:** Single 44px signal row with 4px tier-color left border, pulsing status dot, tier badge, narrative text, age timestamp, score, agreement string, and hover-expand to 88px revealing engine detail.

**Key props:** `signal: SignalEvent`, `narrative?: string`, `onSelect?: (signal) => void`

**Subscribes to:** none (pure from props)

**Renders to:** Inside SignalFeed, one per signal.

**Notable:** TYPE_A arrival triggers: clip-path reveal (320ms spring), lime background flash (800ms), lime glow filter (1200ms decay). Status dot pulses in tier color for 8s after arrival, then goes steady. Hover uses `motion.div height: 44→88` animate. Click opens SignalContext drawer.

### SignalContext

**File:** `components/signals/SignalContext.tsx`

**Purpose:** Slide-in drawer shown when a signal row is clicked. Displays deep breakdown: full engine agreement %, all categories firing, GEX regime, Kronos bias, tier, direction, and category breakdown bars.

**Key props:** `signal: SignalEvent | null`, `onClose: () => void`

**Subscribes to:** none (receives signal as prop from SignalFeed)

**Renders to:** Absolute overlay within the right column, slides in from right edge.

---

## Tape (Time & Sales)

### TapeScroll

**File:** `components/tape/TapeScroll.tsx`

**Purpose:** Compact T&S scroll area. Auto-scrolls to newest row unless user has scrolled up, in which case a "NEW (N)" pill appears at the bottom.

**Key props:** none

**Subscribes to:** `lastTapeVersion`, `tape` ring buffer

**Renders to:** Bottom half of the 320px right column.

**Empty state:** `// no prints yet` in `--text-mute` `text-xs`.

**Notable:** Uses a plain `<div onScroll>` instead of shadcn ScrollArea — ScrollArea's virtualized inner div does not expose `scrollTop` reliably for the userScrolled detection pattern.

### TapeRow

**File:** `components/tape/TapeRow.tsx`

**Purpose:** Single 18px T&S row with time / price / side / size / marker columns. New rows pulse in with a 100ms side-color background flash.

**Key props:** `entry: TapeEntry`

**Subscribes to:** none (pure from props)

**Renders to:** Inside TapeScroll, one per tape entry.

**Marker column (14px):** `★` for SWEEP, `⊟` for ICEBERG, `ⓘ` for KRONOS-flagged, blank otherwise. Sizes ≥ 50 render at weight 600.

---

## Replay

### ReplayControls

**File:** `components/replay/ReplayControls.tsx`

**Purpose:** 52px bottom strip with session selector, transport buttons (prev/play-pause/next), bar position input, speed selector, and LIVE pill. Keyboard bindings: `Space` play/pause, `ArrowLeft/ArrowRight` prev/next bar.

**Key props:** none

**Subscribes to:** `replayStore.*` (mode, currentBarIndex, totalBars, playing, speed, error)

**Renders to:** Bottom of `app/page.tsx`, full width, 52px.

**Notable:** Transport buttons are 36×36, borderless, using `onMouseEnter/onMouseLeave` inline style for hover background (avoids Tailwind class specificity fights with shadcn Button overrides). Optional 4px scrubber appears below the strip when in replay mode.

### SessionSelector

**File:** `components/replay/SessionSelector.tsx`

**Purpose:** Dark-variant shadcn `<Select>` for choosing a replay session date. Fetches session list from `GET /api/replay/sessions`.

**Key props:** `value: string`, `onChange: (id: string) => void`

**Subscribes to:** none (controlled by ReplayControls)

**Renders to:** Left slot of ReplayControls.

### ReturnToLivePill

**File:** `components/replay/ReturnToLivePill.tsx`

**Purpose:** Two-state element: when live, a solid `--ask` filled pill that breathes with a 1.5s opacity loop. When in replay mode, an outlined button that returns to live on click.

**Key props:** `isLive: boolean`, `onReturnToLive: () => void`

**Subscribes to:** none (controlled by ReplayControls)

**Renders to:** Right slot of ReplayControls.

**Notable:** Split into two separate render paths (live → `motion.div`, replay → `<button>`) to avoid animation state leaking between modes.

---

## Atmosphere

All atmosphere components are mounted in `app/layout.tsx` and are `position:fixed`, `pointer-events:none`.

### Scanlines

**File:** `components/atmosphere/Scanlines.tsx`

**Purpose:** `repeating-linear-gradient` scanline texture at 0.012 opacity. `z-index: 3`.

**Key props:** none | **Subscribes to:** none

### Grain

**File:** `components/atmosphere/Grain.tsx`

**Purpose:** SVG `feTurbulence fractalNoise` 200×200px tile at `mix-blend-mode: overlay`, `opacity: 0.04`. Prevents true-black from looking digitally flat. `z-index: 2`.

**Key props:** none | **Subscribes to:** none

### CRTSweep

**File:** `components/atmosphere/CRTSweep.tsx`

**Purpose:** 1px white horizontal line that sweeps top-to-bottom every 8 seconds at 4% opacity. The CRT signature. Disabled when `prefers-reduced-motion` is active. `z-index: 4`.

**Key props:** none | **Subscribes to:** none

---

## Common

### ErrorBanner

**File:** `components/common/ErrorBanner.tsx`

**Purpose:** Absolute-position banner below the header strip showing connection or staleness errors. Does not push layout content.

**Key props:** none

**Subscribes to:** `status.connected`, `status.feedStale`, `status.lastTs`, `replayStore.error`

**Renders to:** `position:absolute top:44px` in `app/page.tsx`.

**Copy (exact):**
- Disconnected: `LINK DOWN. RETRYING…` in `--bid`
- Feed stale: `STALE — last tick {N}s ago` in `--amber`
- Replay session 404: `SESSION NOT FOUND. SELECT FROM HISTORY.` in `--amber`

**Notable:** Uses `color-mix(in srgb, var(--accent) 40%, transparent)` for border-bottom opacity so the token name stays in CSS and works with any custom property value.

### KeyboardHelp

**File:** `components/common/KeyboardHelp.tsx`

**Purpose:** `?` key overlay showing all keyboard shortcuts. Focus-trapped on open: saves trigger element, focuses close button via `requestAnimationFrame` on open, restores focus on close.

**Key props:** none (triggered by keydown listener in ReplayControls)

**Subscribes to:** none

**Renders to:** Full-screen overlay, `z-index: 50`.

### FpsMeter (if present)

**File:** `components/common/FpsMeter.tsx` (dev-only)

**Purpose:** Frame-rate indicator for performance monitoring during development.

---

## UI Primitives (`components/ui/`)

Thin shadcn wrappers around Radix UI. Used sparingly — most dashboard components are custom.

| File | Primitive |
|------|-----------|
| `badge.tsx` | Radix slot badge |
| `button.tsx` | Radix slot button |
| `input.tsx` | `<input>` with dark variant |
| `scroll-area.tsx` | Radix ScrollArea |
| `select.tsx` | Radix Select (used by SessionSelector, speed selector) |
| `separator.tsx` | Radix Separator |
| `tooltip.tsx` | Radix Tooltip (used by HeaderStrip, ZoneList hover details) |

---

## Hooks

| File | Purpose |
|------|---------|
| `hooks/useWebSocket.ts` | WebSocket lifecycle + exponential backoff reconnect |
| `hooks/useReplayController.ts` | Replay session load, bar projection, auto-advance loop |
| `hooks/useFootprintData.ts` | Subscribes to `lastBarVersion` and returns current bar array for LW Charts |

---

## Lib

| File | Purpose |
|------|---------|
| `lib/animations.ts` | All Motion variants, duration/easing/spring tokens, TYPE_A keyframes, SIGNAL_BIT_CATEGORIES |
| `lib/digit-roll.tsx` | Digit-roll component using Motion `useMotionValue` |
| `lib/lw-charts/FootprintSeries.ts` | LW Charts custom series registration |
| `lib/lw-charts/FootprintRenderer.ts` | Canvas draw loop for volume bars, bloom, POC, signal markers |
| `lib/lw-charts/VolumeProfileRenderer.ts` | Canvas draw loop for right-edge volume profile |
| `lib/lw-charts/zoneDrawer.ts` | Canvas draw loop for zone bands; color config per zone type |
| `lib/replayClient.ts` | HTTP fetch helpers for `/api/replay/*` endpoints |
| `lib/utils.ts` | `cn()` class merge utility (clsx + tailwind-merge) |

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — data flow, store shape, rendering split
- [EXTENDING.md](EXTENDING.md) — recipes for adding features
