# DEEP6 Dashboard — Architecture

This document covers the full data path from backend wire to screen pixel, the store shape, the rendering split between LW Charts and Canvas, and the replay system.

---

## Data Flow

```
Python FastAPI backend
        |
        | WebSocket  ws://localhost:8000/ws/live
        |            (JSON, discriminated by `type` field)
        v
  useWebSocket.ts       (app/page.tsx mounts this hook)
        |
        | JSON.parse → LiveMessage discriminated union
        |
        v
  tradingStore.dispatch()
        |
        |── type:'bar'    → pushBar()    → bars RingBuffer(500)
        |── type:'signal' → pushSignal() → signals RingBuffer(200)
        |── type:'tape'   → pushTape()   → tape RingBuffer(50)
        |── type:'score'  → setScore()   → score slice
        |── type:'status' → setStatus()  → status slice
        |
        v
  Zustand store (subscribeWithSelector)
        |
        |── FootprintChart     ← subscribes to lastBarVersion (version counter)
        |── ConfluencePulse    ← subscribes to score.*
        |── KronosBar          ← subscribes to score.kronosBias / kronosDirection
        |── ZoneList           ← subscribes to bars (for poc_price)
        |── SignalFeed         ← subscribes to lastSignalVersion
        |── TapeScroll         ← subscribes to lastTapeVersion
        |── HeaderStrip        ← subscribes to score.* + status.*
        |── ErrorBanner        ← subscribes to status.connected + status.feedStale
        v
  React render + Canvas imperative draw
```

### WebSocket reconnection

`useWebSocket` implements a 7-step exponential backoff sequence `[300ms, 1s, 2s, 4s, 8s, 16s, 30s]` with rapid-disconnect detection. If a connection dies within 100ms of opening three times in a row, it switches to a 5s floor to avoid flooding the backend. Tab visibility is respected: reconnect timers are parked when the tab is hidden and reset when it becomes visible again.

---

## Store Shape

Two Zustand stores. Both are created with `subscribeWithSelector` to enable selector-scoped subscriptions.

### `tradingStore` (`store/tradingStore.ts`)

```
TradingState {
  bars:               RingBuffer<FootprintBar>    capacity 500
  signals:            RingBuffer<SignalEvent>     capacity 200
  tape:               RingBuffer<TapeEntry>       capacity 50
  score:              ScoreSlice
  status:             StatusSlice
  lastBarVersion:     number    -- increments on every pushBar(); triggers chart redraw
  lastSignalVersion:  number    -- increments on every pushSignal(); triggers feed render
  lastTapeVersion:    number    -- increments on every pushTape(); triggers tape render
}

ScoreSlice {
  totalScore:         number            0-100
  tier:               string            'TYPE_A' | 'TYPE_B' | 'TYPE_C' | 'QUIET'
  direction:          -1 | 0 | 1
  categoriesFiring:   string[]          category names currently active
  categoryScores:     Record<str,num>   per-category 0-100 score
  kronosBias:         number            -100 to 100; sign = direction, magnitude = confidence
  kronosDirection:    string            'LONG' | 'SHORT' | 'NEUTRAL'
  gexRegime:          string
}

StatusSlice {
  connected:            boolean
  pnl:                  number
  circuitBreakerActive: boolean
  feedStale:            boolean       set by useFeedStaleWatcher (>10s since last tick)
  lastTs:               number        epoch seconds of last received message
  sessionStartTs:       number        epoch when session began
  barsReceived:         number        authoritative backend bar count
  signalsFired:         number        authoritative backend signal count
  lastSignalTier:       string
  uptimeSeconds:        number        backend process uptime
  activeClients:        number        number of currently connected WS clients
}
```

Ring buffers use a fixed-size circular array. `toArray()` returns items newest-last. Version counters (`lastBarVersion` etc.) avoid exposing the mutable buffer reference to React's equality check — components subscribe to the integer, not the buffer object.

### `replayStore` (`store/replayStore.ts`)

```
ReplayState {
  mode:             'live' | 'replay'
  sessionId:        string | null
  currentBarIndex:  number
  totalBars:        number
  speed:            '1x' | '2x' | '5x' | 'auto'
  playing:          boolean
  error:            string | null
  userHasPanned:    boolean
}
```

---

## Message Types

All messages are JSON with a `type` discriminator. TypeScript types live in `types/deep6.ts`; Python mirrors live in `deep6/api/schemas.py`.

```typescript
LiveBarMessage    { type:'bar',    session_id, bar_index, bar: FootprintBar }
LiveSignalMessage { type:'signal', event: SignalEvent, narrative: string }
LiveScoreMessage  { type:'score',  total_score, tier, direction,
                    categories_firing[], category_scores{}, kronos_bias,
                    kronos_direction, gex_regime }
LiveStatusMessage { type:'status', connected, pnl, circuit_breaker_active,
                    feed_stale, ts, session_start_ts?, bars_received?,
                    signals_fired?, last_signal_tier?, uptime_seconds?,
                    active_clients? }
LiveTapeMessage   { type:'tape',   event: TapeEntry }
```

`FootprintBar` carries per-price-level bid/ask volume in a `levels: Record<string, {bid_vol, ask_vol}>` map. Keys are stringified tick integers; price = tick × 0.25 (NQ).

---

## Rendering Split

The chart area uses three co-located rendering surfaces:

```
FootprintChart (React container)
  |
  |── LW Charts canvas         (managed by FootprintSeries.ts custom series)
  |     FootprintRenderer.ts   draws volume bars, POC glow, signal markers
  |
  |── ZoneOverlay <canvas>     (sibling, positioned absolute, pointer-events:none)
  |     zoneDrawer.ts          draws zone bands: LVN/HVN/ABSORPTION/GEX_CALL/GEX_PUT
  |
  |── VolumeProfile <canvas>   (sibling, right edge, ~64px wide)
        VolumeProfileRenderer.ts  cumulative bid/ask histogram per price level
```

React renders everything outside the chart (header, hero column, signal feed, tape, replay strip) in the normal component tree.

### FootprintRenderer drawing model

- Uses `useBitmapCoordinateSpace` for Retina DPR-correct pixel ops (`hpr`/`vpr` scale factors).
- Volume normalization: `max(bid_vol + ask_vol)` across all rows in a bar sets the 100% width reference.
- Imbalance bloom (ratio ≥ 3.0×): two-draw technique — glow layer first (`globalAlpha` + `shadowBlur`), then crisp bar on top. Avoids `filter` state leaking across the draw cycle.
- Stacked imbalance runs: 3+ consecutive same-side imbalanced rows get a vertical lime line on the imbalance side.
- POC amber glow: `shadowBlur` + `shadowColor` on a 1px horizontal line at `poc_price`.
- Signal markers: tier-color vertical line from bar row top + 6×6 square terminus, one per TYPE_A/B/C signal on that bar.
- Empty state: `AWAITING NQ FOOTPRINT` centered, `text-xs`, `--text-mute`, letter-spaced 0.16em. No spinner.

---

## Atmosphere Layers

Three fixed overlays mounted in `app/layout.tsx`, rendered above all content (`z-index 2-4`, `pointer-events:none`):

```
z-index 2  Grain.tsx
           200×200px SVG feTurbulence fractalNoise tile, mix-blend-mode:overlay, opacity 0.04
           Makes true-black #000000 not look digitally flat.

z-index 3  Scanlines.tsx
           repeating-linear-gradient 3px rows at 0.012 opacity
           Barely-perceptible horizontal scan texture.

z-index 4  CRTSweep.tsx
           Single 1px white horizontal line sweeping top→bottom every 8 seconds at 4% opacity.
           Respects prefers-reduced-motion (disabled when active).
```

A vignette (`body::before`, `z-index 1`) pulls focus to center via `radial-gradient(ellipse at center, transparent 0%, rgba(0,0,0,0.5) 100%)`.

---

## Color System

All colors are CSS custom properties defined in `app/globals.css`. Tailwind v4 maps them via `@theme inline` so utility classes like `bg-void`, `text-lime`, `border-rule` all work.

```
Surface:   --void #000000  --surface-1 #0a0a0a  --surface-2 #141414
           --rule #1f1f1f  --rule-bright #2a2a2a

Text:      --text #f5f5f5  --text-dim #8a8a8a  --text-mute #4a4a4a

Neons (strict semantic owners — never swap these):
  --bid     #ff2e63   bearish / sellers / SHORT / loss P&L
  --ask     #00ff88   bullish / buyers / LONG / win P&L / OK
  --cyan    #00d9ff   TYPE_C signal / LVN zone / replay active
  --amber   #ffd60a   TYPE_B signal / HVN/POC / warning state
  --lime    #a3ff00   TYPE_A signal / confluence >=80 / THE wow color
  --magenta #ff00aa   Kronos E10 / ALL ML attribution exclusively
```

Glow is implemented as `filter: drop-shadow()` (clips to glyph edges), not `box-shadow`. See `.glow-lime`, `.glow-amber`, `.glow-cyan` in `globals.css`.

---

## Replay Mode

`useReplayController` (`hooks/useReplayController.ts`) mounts in `app/page.tsx` alongside `useWebSocket`. It has four duties:

1. **URL sync** — if `?session=<id>` is present on mount, calls `replayStore.setMode('replay', id)`.
2. **Session load** — when `mode` flips to `'replay'`, fetches all bars from `GET /api/replay/{sessionId}/range?from=0&to=10000` and caches them in a local `barsCacheRef`.
3. **Bar projection** — on every `currentBarIndex` change, slices `cache[0..barIdx]` into a fresh RingBuffer and writes it into `tradingStore.bars`. This gives components the illusion of receiving bars one by one.
4. **Signal projection** — fetches `GET /api/replay/{sessionId}/{barIdx}` for `signals_up_to` array, writes into `tradingStore.signals`.
5. **Auto-advance loop** — when `playing=true`, either `setInterval` at `1x:1000ms / 2x:500ms / 5x:200ms` or `requestAnimationFrame` for `auto` speed.

In replay mode `useWebSocket` is still mounted and retrying, but `useFeedStaleWatcher` ignores the stale-feed check (`mode !== 'live'` short-circuits).

---

## Animation System

All Motion animations are defined in `lib/animations.ts` as named export constants:

- `DURATION`, `EASING`, `SPRING` — shared tokens
- `digitRollTransition` / `harmonizedDigitRollTransition` — spring physics for score/price digit rolls
- `typeAFlashKeyframes` / `typeAFlashTransition` — 1.5s white-hot flash for TYPE_A events
- `radialBloomKeyframes`, `aftershockBloomKeyframes` — expanding SVG circle for TYPE_A
- `signalRowArrivalInitial` / `signalRowArrivalAnimate` / `signalRowArrivalTransition` — clip-path reveal for new signal rows
- `arcIgniteTransition`, `arcStagger()` — 200ms arc ignite with 15ms index stagger
- `SIGNAL_BIT_CATEGORIES` — frozen 44-element array mapping bit index → `CategoryKey`
- `CATEGORY_COLORS` / `CATEGORY_COLORS_HEX` — CSS var and hex color per category
- `prefersReducedMotion()` — snapshot check; gates all animation code paths

All motion respects `prefers-reduced-motion`. Durations collapse to 0; breathing pulses are disabled.

---

## Layout Shell

`app/page.tsx` is a `'use client'` component that owns the outermost flex layout:

```
┌───────────────────────────────────────────────────────────┐
│ HeaderStrip (44px fixed height)                            │
├────────────────┬──────────────────┬───────────────────────┤
│                │                  │                       │
│ FootprintChart │ ConfluencePulse  │ SignalFeed             │
│ (flex-1)       │ (360px hero)     │ (320px right, flex-1) │
│                │                  │                       │
│                │ KronosBar (88px) ├───────────────────────┤
│                │                  │                       │
│                │ ZoneList         │ TapeScroll             │
│                │ (flex-1)         │ (flex-1)              │
│                │                  │                       │
├────────────────┴──────────────────┴───────────────────────┤
│ ReplayControls (52px strip)                                │
└───────────────────────────────────────────────────────────┘
```

Column separators (`ColSep`) are 9px wide: 4px surface-1 gutter + 1px gradient rule + 4px surface-1 gutter. The rule fades at top and bottom so it never hard-stops.

---

## See Also

- [COMPONENT-INDEX.md](COMPONENT-INDEX.md) — every component with props and store subscriptions
- [EXTENDING.md](EXTENDING.md) — recipes for adding message types, panels, overlays, and animations
- [UI-SPEC v2](../../.planning/phases/11.2-ui-redesign/UI-SPEC-v2.md) — design contract (TERMINAL NOIR)
