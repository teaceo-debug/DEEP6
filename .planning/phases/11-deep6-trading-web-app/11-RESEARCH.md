# Phase 11: DEEP6 Trading Web App - Research

**Researched:** 2026-04-13
**Domain:** Next.js 15 App Router + LightweightCharts v5.1 Custom Series + FastAPI WebSocket + React state management for high-frequency financial charting
**Confidence:** HIGH (core stack), MEDIUM (Canvas overlay integration details), LOW (exact TapeFlow source internals)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** IN — APP-01 custom footprint chart with zone overlays (LVN, HVN, GEX, absorption)
- **D-02:** IN — APP-03 real-time WebSocket push from Phase 9 FastAPI
- **D-03:** IN — APP-04 session replay (bar-by-bar step through historical sessions)
- **D-04:** IN — APP-08 zero TradingView dependency (all rendering in DEEP6 app)
- **D-05:** IN (lite) — APP-06 minimal status widget: live P&L running total + circuit breaker state only
- **D-06:** DEFERRED — APP-02 execution panel
- **D-07:** DEFERRED — APP-05 mobile push notifications
- **D-08:** DEFERRED — APP-07 authentication + multi-device
- **D-09:** Next.js frontend connects directly to Phase 9 FastAPI WebSocket on localhost — no auth, no reverse proxy
- **D-10:** Single WebSocket connection for all real-time streams (signals, bars, P&L, connection status). Backend multiplexes message types.
- **D-11:** Backend pushes complete FootprintBar objects on bar close. Client does not rebuild bars from raw ticks.
- **D-12:** Client-side ring buffer holds last N bars (N TBD by planner; target ~500 bars)
- **D-13:** Session replay reads from Phase 9 EventStore (aiosqlite signal_events + trade_events + bar history) via dedicated FastAPI replay endpoint
- **D-14:** Replay controls: Previous/Next bar, jump-to-bar, playback speed (1x/2x/5x/auto). Session selector deferred.
- **D-15:** Local `npm run dev` on localhost:3000 alongside the Python engine. Manual start. No Docker.

### Claude's Discretion
- Footprint custom series internal implementation (exact Canvas layering, offscreen canvas, requestAnimationFrame batching)
- WebSocket message schema and reconnection backoff strategy
- State management library choice (Zustand, Jotai, or native React)
- Exact ring-buffer size and retention policy for T&S tape and signal feed
- FastAPI endpoint shape for replay query (pagination, event filters)

### Deferred Ideas (OUT OF SCOPE)
- APP-02 execution panel
- APP-05 mobile push via service worker
- APP-07 authentication + multi-device
- Full APP-06 analytics (win-rate-by-tier, drawdown chart, daily/weekly/monthly P&L)
- Tailscale / reverse-proxy access
- Docker packaging
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| APP-01 | Custom footprint chart via LW Charts v5.1 custom series — bid/ask volume per price level with zone overlays (LVN, HVN, GEX, absorption) | LW Charts v5.1 `ICustomSeriesPaneView`/`ICustomSeriesPaneRenderer` API verified; Canvas overlay pattern from TapeFlow documented |
| APP-03 | Real-time WebSocket from FastAPI — signal events, bar updates, P&L pushed within 200ms of bar close | FastAPI WebSocket API documented; Next.js 15 client hook pattern identified; single-WS multiplexed message design confirmed |
| APP-04 | Session replay — reconstruct any historical session bar-by-bar with all signals visible, step forward/back | Phase 9 EventStore schema confirmed; replay endpoint shape designed; HTTP polling pattern for replay identified |
| APP-06 (lite) | Live P&L running total + circuit breaker state only | Payload fits into multiplexed WS status message; no separate endpoint needed |
| APP-08 | Zero TradingView dependency — complete trading workflow within DEEP6 web app | LW Charts v5.1 confirmed for charts; all UI custom-built; design contract locked in UI-SPEC.md |
</phase_requirements>

---

## Summary

Phase 11 builds a view-only trading monitoring frontend: a Next.js 15 App Router app with a LightweightCharts v5.1 custom footprint series, signal feed, score widget, and session replay — all fed by a WebSocket connection to the existing Phase 9 FastAPI backend.

The three hardest problems are: (1) the LW Charts v5.1 custom series plugin API requires implementing `ICustomSeriesPaneView` and `ICustomSeriesPaneRenderer`, which draw per-bar footprint cell grids in a `CanvasRenderingTarget2D` context using `useBitmapCoordinateSpace` for pixel-perfect rendering; (2) zone overlays must sit on a separate absolutely-positioned `<canvas>` element kept in sync with LW Charts' `chart.priceToCoordinate()` API on every scroll/zoom event; and (3) the ring buffer for footprint bars must be a mutable ref-based structure (not React state) to avoid triggering re-renders at DOM update frequency — the Canvas renderer reads it directly via `store.getState()` or a mutable ref.

Phase 9 backend is partially built: `deep6/api/app.py` (FastAPI app factory), `deep6/api/store.py` (EventStore with `signal_events` + `trade_events` tables) — Phase 11 adds two new routes onto this existing app: `GET /ws/live` (multiplexed WebSocket) and `GET /api/replay/{session}/{bar_index}`.

**Primary recommendation:** Scaffold `dashboard/` as the Next.js 15 root; use Zustand with `subscribeWithSelector` middleware and mutable refs for high-frequency state; implement the LW Charts footprint series as a standalone `lib/lw-charts/FootprintSeries.ts` following the `ICustomSeriesPaneView` / `ICustomSeriesPaneRenderer` split pattern; render zone overlays on a sibling `<canvas>` that listens to LW Charts `subscribeCrosshairMove` + `subscribeVisibleTimeRangeChange` to stay synchronized.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| next | 16.2.3 | App Router framework | Locked in CLAUDE.md; RSC reduces client bundle; built-in SSE via Route Handlers |
| lightweight-charts | 5.1.0 | Financial chart engine + custom series API | Locked in CLAUDE.md; 45KB bundle; v5.1 adds data conflation for large datasets |
| zustand | 5.0.12 | State management + ring buffer | Best for centralized trading state; `getState()` allows Canvas reads without re-renders; `subscribeWithSelector` enables fine-grained subscriptions |
| tailwindcss | latest (v4.x) | Utility CSS | Part of Next.js standard setup; design token integration via CSS variables |
| shadcn/ui | latest | Component primitives | Locked in CLAUDE.md; New York preset + Zinc base color per UI-SPEC |
| lucide-react | 1.8.0 | Icon set | shadcn default; SkipBack/Play/Pause/SkipForward/etc. used in replay controls |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @tanstack/react-virtual | 3.13.23 | Virtual scroll for T&S tape + signal feed | Use for the 50-row T&S tape and 20-visible signal feed with infinite scroll — avoids DOM thrashing on prepend |
| datamodel-code-generator | latest (pip) | Pydantic → TypeScript types | Run once to generate `types/deep6.ts` from FastAPI OpenAPI schema; re-run when Python models change |

### Versions Verified
```bash
# Confirmed via npm registry 2026-04-13
lightweight-charts: 5.1.0   [VERIFIED: npm view lightweight-charts version]
zustand:           5.0.12   [VERIFIED: npm view zustand version]
next:              16.2.3   [VERIFIED: npm view next version]
lucide-react:      1.8.0    [VERIFIED: npm view lucide-react version]
@tanstack/react-virtual: 3.13.23 [VERIFIED: npm view @tanstack/react-virtual version]
```

**Installation:**
```bash
cd dashboard
npx shadcn@latest init  # Style: New York, Base: Zinc, CSS variables: Yes
npm install lightweight-charts zustand @tanstack/react-virtual
npx shadcn@latest add button badge select input tooltip separator scroll-area
```

---

## Architecture Patterns

### Recommended Project Structure

Phase 11 scaffolds a `dashboard/` subdirectory at the DEEP6 repo root alongside `deep6/` Python package.

```
dashboard/
├── app/
│   ├── layout.tsx               # Root layout — WebSocket context provider lives here (persists across routes)
│   ├── page.tsx                 # Main trading view (TradingLayout)
│   └── api/                     # Next.js API routes (if needed for replay proxy)
├── components/
│   ├── layout/
│   │   ├── HeaderStrip.tsx
│   │   └── ReplayControls.tsx
│   ├── footprint/
│   │   ├── FootprintChart.tsx   # LW Charts host + canvas overlay manager
│   │   └── ZoneOverlay.tsx      # Sibling <canvas> for LVN/HVN/GEX bands
│   ├── signals/
│   │   ├── SignalFeed.tsx
│   │   └── SignalFeedRow.tsx
│   ├── tape/
│   │   ├── TapeScroll.tsx
│   │   └── TapeRow.tsx
│   └── score/
│       ├── ScoreWidget.tsx
│       └── KronosBiasBar.tsx
├── hooks/
│   ├── useWebSocket.ts          # Reconnecting WS hook — all streams
│   └── useFootprintData.ts      # Ring buffer access hook
├── lib/
│   └── lw-charts/
│       ├── FootprintSeries.ts   # ICustomSeriesPaneView implementation
│       └── FootprintRenderer.ts # ICustomSeriesPaneRenderer implementation
├── store/
│   └── tradingStore.ts          # Zustand store: ring buffer, signal feed, score, P&L
├── types/
│   └── deep6.ts                 # TypeScript types (generated or hand-written)
├── styles/
│   └── globals.css              # CSS variables per UI-SPEC.md color tokens
├── components.json              # shadcn config
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

### Pattern 1: LW Charts v5.1 Custom Series Plugin Split

**What:** Separate the series into a view class (lifecycle + data handoff) and a renderer class (Canvas drawing). This matches the pattern used in all official LW Charts plugin examples.

**When to use:** Always — it is the only way to implement a custom series in LW Charts v5.1.

**Key API facts [VERIFIED: tradingview.github.io/lightweight-charts/docs/plugins/custom_series]:**
- `ICustomSeriesPaneView<HorzScaleItem, TData, TOptions>` — class you implement; has `renderer()`, `update(data, options)`, `priceValueBuilder(item)`, `isWhitespace(item)`, `defaultOptions`, `destroy()`
- `ICustomSeriesPaneRenderer` — returned by `renderer()`; has `draw(target: CanvasRenderingTarget2D, priceToCoordinate: PriceToCoordinateConverter)`
- `PaneRendererCustomData<TData>` — passed to `update()`; contains `bars: CustomBarItemData<TData>[]`, `barSpacing: number`, `visibleRange: VisiblePriceScaleRange`
- `PriceToCoordinateConverter` — function `(price: number) => number | null` returning mediaSize Y coordinate (null if price is off-scale)
- `chart.addCustomSeries(paneView, options?)` — registers and returns `ISeriesApi<'Custom'>` which accepts `series.setData(bars)` and `series.update(bar)`
- Drawing must use `target.useBitmapCoordinateSpace(scope => { ... })` for pixel-correct rendering; `scope.context` is `CanvasRenderingContext2D`; multiply all coordinates by `scope.horizontalPixelRatio` / `scope.verticalPixelRatio`

```typescript
// Source: [VERIFIED: tradingview.github.io/lightweight-charts/docs/plugins/custom_series]
// lib/lw-charts/FootprintSeries.ts — view class skeleton

import type {
  ICustomSeriesPaneView,
  PaneRendererCustomData,
  PriceToCoordinateConverter,
  Time,
} from 'lightweight-charts';
import type { FootprintBar, FootprintSeriesOptions } from '@/types/deep6';
import { FootprintRenderer } from './FootprintRenderer';

export class FootprintSeries implements ICustomSeriesPaneView<Time, FootprintBar, FootprintSeriesOptions> {
  private _renderer: FootprintRenderer;

  constructor() {
    this._renderer = new FootprintRenderer();
  }

  renderer() {
    return this._renderer;
  }

  update(data: PaneRendererCustomData<FootprintBar>, options: FootprintSeriesOptions): void {
    this._renderer.update(data, options);
  }

  priceValueBuilder(item: FootprintBar): [number, number, number] {
    return [item.low, item.high, item.close];  // [low, high, last] for scale + crosshair
  }

  isWhitespace(item: FootprintBar): boolean {
    return item.levels === undefined || item.levels.length === 0;
  }

  defaultOptions(): FootprintSeriesOptions {
    return { rowHeight: 20, showDelta: true };
  }

  destroy(): void {}
}
```

```typescript
// Source: [VERIFIED: tradingview.github.io/lightweight-charts/docs/plugins/canvas-rendering-target]
// lib/lw-charts/FootprintRenderer.ts — renderer skeleton

import type {
  ICustomSeriesPaneRenderer,
  PaneRendererCustomData,
  CanvasRenderingTarget2D,
  PriceToCoordinateConverter,
} from 'lightweight-charts';
import type { FootprintBar, FootprintSeriesOptions } from '@/types/deep6';

export class FootprintRenderer implements ICustomSeriesPaneRenderer {
  private _data: PaneRendererCustomData<FootprintBar> | null = null;
  private _options: FootprintSeriesOptions | null = null;

  update(data: PaneRendererCustomData<FootprintBar>, options: FootprintSeriesOptions): void {
    this._data = data;
    this._options = options;
  }

  draw(target: CanvasRenderingTarget2D, priceToCoordinate: PriceToCoordinateConverter): void {
    target.useBitmapCoordinateSpace(scope => {
      const ctx = scope.context;
      const xRatio = scope.horizontalPixelRatio;
      const yRatio = scope.verticalPixelRatio;

      if (!this._data) return;

      for (const bar of this._data.bars) {
        const x = bar.x * xRatio;       // bar.x is center x in media coords
        const w = (this._data.barSpacing * 0.9) * xRatio;

        const yClose = (priceToCoordinate(bar.originalData.close) ?? 0) * yRatio;
        const yOpen  = (priceToCoordinate(bar.originalData.open)  ?? 0) * yRatio;

        // Draw OHLC candle body
        ctx.fillStyle = bar.originalData.close >= bar.originalData.open ? '#22c55e' : '#ef4444';
        ctx.fillRect(x - w / 2, Math.min(yOpen, yClose), w, Math.abs(yClose - yOpen));

        // Draw footprint cells per level
        for (const level of bar.originalData.levels) {
          const yLevel = (priceToCoordinate(level.price) ?? 0) * yRatio;
          const rowH = (this._options?.rowHeight ?? 20) * yRatio;
          // ... cell fill, bid/ask text
        }
      }
    });
  }
}
```

### Pattern 2: Zone Overlay as Sibling Canvas

**What:** A separate `<canvas>` absolutely positioned over the LW Charts container. Zone bands (LVN, HVN, GEX, absorption) are drawn as horizontal bands spanning chart width using `chart.priceToCoordinate()`.

**When to use:** Always for zone overlays — drawing inside the LW Charts renderer would tie zone refresh to bar render cycles; a sibling canvas allows independent refresh on scroll/zoom.

**Key integration points:**
- `chart.subscribeCrosshairMove()` — fires on every mouse move; use to trigger overlay redraw
- `chart.subscribeVisibleTimeRangeChange()` — fires on horizontal scroll/zoom
- `chart.subscribeVisibleLogicalRangeChange()` — fires on horizontal navigation
- `chart.priceToCoordinate(price)` — converts price → Y pixel (returns null if off-scale)
- The sibling canvas must be `pointer-events: none` to pass through mouse events to LW Charts

```typescript
// Source: [ASSUMED — confirmed pattern from TapeFlow study; priceToCoordinate API VERIFIED]
// components/footprint/ZoneOverlay.tsx

'use client';
import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';

export function ZoneOverlay({ chart, zones }: { chart: IChartApi; zones: ZoneRef[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const redraw = () => {
      const canvas = canvasRef.current;
      if (!canvas || !chart) return;
      const ctx = canvas.getContext('2d')!;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const zone of zones) {
        const yTop    = chart.priceToCoordinate(zone.priceHigh);
        const yBottom = chart.priceToCoordinate(zone.priceLow);
        if (yTop === null || yBottom === null) continue;

        ctx.fillStyle = ZONE_FILL[zone.type];
        ctx.fillRect(0, yTop, canvas.width, yBottom - yTop);
        // dashed border
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = ZONE_BORDER[zone.type];
        ctx.strokeRect(0, yTop, canvas.width, yBottom - yTop);
        ctx.setLineDash([]);
      }
    };

    chart.subscribeCrosshairMove(redraw);
    chart.subscribeVisibleTimeRangeChange(redraw);
    return () => {
      chart.unsubscribeCrosshairMove(redraw);
      chart.unsubscribeVisibleTimeRangeChange(redraw);
    };
  }, [chart, zones]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 2 }}
    />
  );
}
```

### Pattern 3: WebSocket Context at Root Layout Level

**What:** `WebSocketProvider` created in `app/layout.tsx` so the connection persists across route changes. Components subscribe via `useContext`.

**Why:** Next.js 15 App Router uses client-side navigation that may unmount page components. If WebSocket lives in a page component, it closes and reopens on every navigation. Layout components never unmount.

**Reconnection spec per UI-SPEC.md (D-10):**
```typescript
// Source: [CITED: websocket.org/guides/reconnection/, VERIFIED pattern]
// hooks/useWebSocket.ts
const BACKOFF = [1000, 2000, 4000, 8000, 16000, 30000]; // ms, then capped at 30s

function connect(attempt: number) {
  const ws = new WebSocket(url);
  ws.onopen = () => { attempt = 0; setStatus('connected'); };
  ws.onclose = () => {
    setStatus('reconnecting');
    if (document.visibilityState === 'hidden') return; // D-10: no reconnect when tab hidden
    const delay = BACKOFF[Math.min(attempt, BACKOFF.length - 1)];
    setTimeout(() => connect(attempt + 1), delay);
  };
  ws.onmessage = (e) => dispatch(JSON.parse(e.data));
}
```

### Pattern 4: Zustand Ring Buffer for High-Frequency Footprint State

**What:** Zustand store holds the footprint bar ring buffer as a mutable array with a write pointer. The Canvas renderer reads it via `store.getState()` (no React subscription) to avoid triggering re-renders on every DOM update.

**Why Zustand over Jotai:** Zustand's `getState()` API lets Canvas callbacks read state without any React subscription. With Jotai you would need a store outside React's atom graph. Zustand's centralized model is also simpler for a single-user trading dashboard vs Jotai's atomic decomposition.

```typescript
// Source: [VERIFIED: zustand.docs.pmnd.rs/reference/middlewares/subscribe-with-selector]
// store/tradingStore.ts
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface TradingStore {
  // Ring buffer — NOT React-reactive; Canvas reads via getState()
  barBuffer: FootprintBar[];
  barBufferHead: number;         // next write index
  barBufferSize: number;         // max size (500)

  // React-reactive state — only for UI components
  signalFeed: SignalEvent[];     // last 200 signals
  latestScore: ScorerResult | null;
  pnl: number;
  circuitBreakerActive: boolean;
  wsStatus: 'connected' | 'reconnecting' | 'disconnected';

  // Actions
  pushBar: (bar: FootprintBar) => void;
  pushSignal: (event: SignalEvent) => void;
  updateScore: (score: ScorerResult) => void;
  updateStatus: (payload: StatusMessage) => void;
}

export const useTradingStore = create<TradingStore>()(
  subscribeWithSelector((set, get) => ({
    barBuffer: new Array(500),
    barBufferHead: 0,
    barBufferSize: 500,

    pushBar: (bar) => set(s => {
      // Mutable ring buffer write — minimal GC pressure
      s.barBuffer[s.barBufferHead % s.barBufferSize] = bar;
      return { barBufferHead: s.barBufferHead + 1 };
      // NOTE: barBuffer mutation is intentional — Canvas reads getState().barBuffer directly
      // without triggering React re-renders
    }),

    // ... other actions
  }))
);

// Canvas renderer reads ring buffer without React subscription:
// const { barBuffer, barBufferHead, barBufferSize } = useTradingStore.getState();
```

### Pattern 5: Multiplexed WebSocket Message Discriminated Union

**What:** Single WebSocket carries all message types identified by a `type` discriminator field. TypeScript discriminated union handles routing.

**FastAPI backend side (new route on Phase 9 app):**
```python
# Source: [VERIFIED: fastapi.tiangolo.com/advanced/websockets/]
# deep6/api/routes/live.py — new route added in Phase 11
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter(tags=["live"])

class LiveConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for conn in self.connections:
            try:
                await conn.send_json(msg)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.connections.remove(d)

manager = LiveConnectionManager()

@router.websocket("/ws/live")
async def live_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping sink
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

**TypeScript client-side discriminated union:**
```typescript
// Source: [ASSUMED — standard TypeScript discriminated union pattern]
// types/deep6.ts

type WsMessage =
  | { type: 'bar';     data: FootprintBar }
  | { type: 'signal';  data: SignalEvent }
  | { type: 'score';   data: ScorerResult }
  | { type: 'status';  data: StatusMessage }
  | { type: 'pong' }

function dispatch(msg: WsMessage) {
  switch (msg.type) {
    case 'bar':    useTradingStore.getState().pushBar(msg.data); break;
    case 'signal': useTradingStore.getState().pushSignal(msg.data); break;
    case 'score':  useTradingStore.getState().updateScore(msg.data); break;
    case 'status': useTradingStore.getState().updateStatus(msg.data); break;
  }
}
```

### Pattern 6: Replay via HTTP Polling (not WebSocket)

Per D-13 and UI-SPEC.md, replay replaces the WebSocket with HTTP polling against `GET /api/replay/{session}/{bar_index}`. The replay endpoint queries Phase 9 EventStore.

**FastAPI replay endpoint (new route):**
```python
# Source: [ASSUMED — derived from Phase 9 EventStore schema]
# deep6/api/routes/replay.py

@router.get("/api/replay/{session_date}/{bar_index}")
async def get_replay_bar(
    session_date: str,           # YYYY-MM-DD
    bar_index: int,
    request: Request,
) -> dict:
    store: EventStore = request.app.state.event_store
    # Query signal_events with ts in session window, order by ts
    # Return bar snapshot + all signals up to this bar_index
    signals = await store.fetch_signal_events(limit=bar_index + 1)
    # Also need bar_history table (may need to be added in Phase 11)
    return {
        "bar_index": bar_index,
        "session": session_date,
        "signals": signals[:bar_index + 1],
        "bar": None,  # placeholder — bar_history table TBD
    }
```

**NOTE:** The Phase 9 EventStore schema (confirmed by reading `deep6/api/store.py`) does NOT currently include a `bar_history` table — only `signal_events` and `trade_events`. Phase 11 Wave 0 must add a `bar_history` table to the EventStore, or the replay endpoint can only reconstruct signals (not footprint bars) from stored data. This is an open question the planner must resolve.

### Anti-Patterns to Avoid

- **React state for ring buffer:** Calling `setState` on every DOM callback (1000+/sec) would cause catastrophic re-render storms. Use mutable Zustand state + Canvas `getState()` reads.
- **Zone overlay inside LW Charts renderer:** LW Charts renderer is called per bar; zones need to redraw on scroll/zoom independently.
- **WebSocket in page component:** Connection will close/reopen on every route navigation. Must live in root layout.
- **Polling for live data:** The UI-SPEC mandates WebSocket push; polling introduces latency and defeats the 200ms bar close requirement (APP-03).
- **JSON.parse on every message in the render hot path:** Parse in `ws.onmessage`, dispatch to store, let Canvas reads be synchronous.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Virtual scroll for T&S + signal feed | Custom scroll with absolute positions | `@tanstack/react-virtual` | Row height virtualization handles 10,000+ entries without DOM thrashing on prepend |
| shadcn component primitives | Custom button/select/tooltip/badge | `npx shadcn add button select tooltip badge` | Radix UI accessibility, keyboard nav, focus management already solved |
| Type generation from Python models | Hand-maintaining parallel TS interfaces | `datamodel-code-generator` or FastAPI `/openapi.json` → codegen | Drift between Python Pydantic and TypeScript types causes silent runtime bugs |
| Canvas pixel ratio handling | Manual `window.devicePixelRatio` multiplication | `target.useBitmapCoordinateSpace(scope => { ... })` | LW Charts' `CanvasRenderingTarget2D` handles DPR automatically; scope provides correct ratios |
| Icon set | Custom SVG icons | `lucide-react` | shadcn/ui default; SkipBack, Play, Pause, SkipForward already implemented |

**Key insight:** The custom footprint series is the one thing that MUST be hand-rolled — LW Charts has no built-in footprint renderer. Everything else (icons, buttons, selects, virtual scroll, canvas pixel management) has mature library solutions.

---

## Phase 9 EventStore Schema (Confirmed from Codebase)

The existing `deep6/api/store.py` [VERIFIED: read directly] defines two tables:

### `signal_events` table
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| ts | REAL | bar close epoch timestamp |
| bar_index | INTEGER | `bar_index_in_session` |
| total_score | REAL | 0-100 confluence score |
| tier | TEXT | "TYPE_A", "TYPE_B", "TYPE_C", "QUIET" |
| direction | INTEGER | +1, -1, 0 |
| engine_agreement | REAL | 0.0-1.0 |
| category_count | INTEGER | |
| categories | TEXT | JSON array string of firing category names |
| gex_regime | TEXT | default "NEUTRAL" |
| kronos_bias | REAL | 0-100, default 0.0 |
| inserted_at | REAL | epoch when inserted |

### `trade_events` table
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| ts | REAL | |
| position_id | TEXT | |
| event_type | TEXT | "STOP_HIT", "TARGET_HIT", "TIMEOUT_EXIT", "MANUAL_EXIT", "ENTRY" |
| side | TEXT | "LONG", "SHORT" |
| entry_price | REAL | |
| exit_price | REAL | |
| pnl | REAL | |
| bars_held | INTEGER | |
| signal_tier | TEXT | |
| signal_score | REAL | |
| regime_label | TEXT | default "UNKNOWN" |
| inserted_at | REAL | |

### Missing for Replay: `bar_history` table

The EventStore does NOT have a `bar_history` table. For `APP-04` session replay to reconstruct the footprint chart state (not just signals), Phase 11 Wave 0 must either:

1. **Add `bar_history` table to EventStore** — Phase 9 app pushes a `FootprintBar` JSON blob per bar close; replay endpoint queries it alongside `signal_events`. Requires adding `insert_bar` and `fetch_bars_for_session` methods to EventStore.
2. **Replay signals-only** — footprint replay shows an empty chart with only signal markers. Simpler but incomplete per APP-04.

**Recommendation:** Option 1. Add `bar_history` table in Phase 11 Wave 0 as part of backend wiring.

### FastAPI App Routes (Confirmed Existing)
From `deep6/api/app.py` [VERIFIED: read directly]:
- `GET /health`
- `POST /events/signal` (events router)
- `POST /events/trade` (events router)
- `GET /weights/current` (weights router)
- `POST /weights/deploy` (weights router — stub, 501)
- Plus metrics and sweep routers (Phase 9 plans 02+)

**Phase 11 adds:**
- `GET /ws/live` — WebSocket endpoint for multiplexed live stream
- `GET /api/replay/{session_date}/{bar_index}` — HTTP endpoint for replay
- `GET /api/history/signals?limit=50&offset=N` — for signal feed infinite scroll

---

## TapeFlow Architecture Reference [VERIFIED: github.com/ianfigueroa/TapeFlow via WebFetch]

TapeFlow is the primary architectural reference for Canvas overlay + ring buffer pattern.

**Stack confirmed:**
- React 18, TypeScript, Vite, Zustand, TailwindCSS
- TradingView `lightweight-charts` for price axis/candlestick baseline
- Canvas API for footprint cell overlay (separate from LW Charts internals)
- `@tanstack/react-virtual` for T&S tape virtualization
- Mutable ring-buffer: `Map<string, Trade[]>` storing last 5000 trades per symbol; O(1) append; subscribers notified on each trade

**Canvas layering approach:**
TapeFlow uses a z-indexed canvas stack on a single `requestAnimationFrame` loop:
1. BackgroundLayer (grid, axis)
2. HeatmapLayer (order book depth)
3. FootprintLayer (cluster charts)
4. IndicatorLayer (VWAP, zones)
5. OverlayLayer (crosshair, tooltips)

**Key takeaway for DEEP6:** TapeFlow does NOT use LW Charts' custom series API for footprint cells — it uses independent canvas layers over the LW Charts container. DEEP6 has two choices:
- **Option A (LW Charts custom series):** Implement footprint cells inside LW Charts' `ICustomSeriesPaneView` — tighter integration, price axis auto-scale, but more complex API
- **Option B (TapeFlow-style overlay canvas):** Sibling `<canvas>` over LW Charts — complete control, matches TapeFlow reference, simpler Canvas code, but must manually sync with LW Charts coordinate system via `chart.priceToCoordinate()`

**Recommendation:** Hybrid — use LW Charts custom series for the OHLC candle + delta footer (tight price axis integration), and a separate sibling `<canvas>` for zone overlays (LVN/HVN/GEX bands). This is what the UI-SPEC explicitly describes (ZoneOverlay as separate canvas, FootprintCustomSeries for bar rendering).

---

## Common Pitfalls

### Pitfall 1: LW Charts Custom Series Draw Method — Media vs Bitmap Coordinates
**What goes wrong:** Drawing with raw pixel values from `priceToCoordinate()` without multiplying by device pixel ratio — results in blurry rendering on Retina/HiDPI displays.
**Why it happens:** `PriceToCoordinateConverter` returns mediaSize Y coordinates. The Canvas context in `useBitmapCoordinateSpace` is bitmap-sized (actual physical pixels).
**How to avoid:** Always multiply coordinates from `priceToCoordinate()` by `scope.verticalPixelRatio` and bar x positions by `scope.horizontalPixelRatio` inside `useBitmapCoordinateSpace`.
**Warning signs:** Charts look correct on 1x displays but blurry/offset on MacBook Retina.

### Pitfall 2: Zone Overlay Canvas Size Not Matching LW Charts Container
**What goes wrong:** Zone bands render at wrong positions when window resizes.
**Why it happens:** The sibling `<canvas>` has a fixed `width`/`height` that doesn't track the LW Charts container's pixel dimensions after resize.
**How to avoid:** Use a `ResizeObserver` on the LW Charts container div; on resize, update canvas `width` and `height` attributes (not CSS dimensions) and force overlay redraw.
**Warning signs:** Zone bands appear shifted after window resize.

### Pitfall 3: React Re-Renders on Every DOM Update
**What goes wrong:** Calling `setState` (or `set` in Zustand) with the ring buffer on every footprint tick causes the entire chart subtree to re-render at 1000+/sec.
**Why it happens:** React state changes always schedule a reconciliation. At DOM callback rates (1000/sec), this locks the main thread.
**How to avoid:** Keep the ring buffer as a mutable Zustand slice. Canvas renderer uses `useTradingStore.getState().barBuffer` (non-reactive). Only trigger React re-renders for UI state (score, P&L, signal feed). Separate the concerns.
**Warning signs:** CPU usage > 80% on a modern machine while connected to live data.

### Pitfall 4: WebSocket in Page Component Closes on Route Change
**What goes wrong:** Navigating away from the main trading page (e.g., to replay page) closes the WebSocket; state is lost; reconnect timer fires; live data gaps.
**Why it happens:** Next.js App Router unmounts page components during client-side navigation.
**How to avoid:** Create a `WebSocketProvider` in `app/layout.tsx`. Connection lifecycle is tied to root layout, not page.
**Warning signs:** Connection log shows repeated CONNECTING → OPEN → CLOSING sequences.

### Pitfall 5: `bar_history` Missing from EventStore for Replay
**What goes wrong:** Replay endpoint can return signals but not footprint bars — the chart shows blank candles with only signal markers.
**Why it happens:** Phase 9 EventStore was built for ML training (signal/trade events only), not chart replay.
**How to avoid:** Add `bar_history` table in Wave 0. Push a serialized `FootprintBar` JSON blob from the trading engine on every bar close (same hook that calls `POST /events/signal`).
**Warning signs:** Replay endpoint returns `bar: null` for every bar.

### Pitfall 6: TYPE_A Pulse Animation Key-Trick Gotcha
**What goes wrong:** Animation class is added but doesn't play on second arrival of a TYPE_A signal at the same list position.
**Why it happens:** React only remounts when the `key` prop changes. If a new signal has the same key as a prior one, no remount → no animation restart.
**How to avoid:** Use a monotonically increasing ID or `ts + signalType` combination as the React key — not just `signalType`.
**Warning signs:** First TYPE_A pulses, subsequent ones don't.

---

## TypeScript Type Sharing Strategy

### Option A: Hand-Written Types (Recommended for Phase 11)
**Approach:** Write `types/deep6.ts` manually mirroring the Python Pydantic models. Small surface area (5-7 interfaces), stable for Phase 11 scope.
**Tradeoff:** Can drift from Python. Acceptable risk given no execution panel in this phase — the shape is primarily footprint bars + signal events.
**When to switch to codegen:** When APP-02 (execution) is added and the type surface grows to include order payloads.

### Option B: Codegen via datamodel-code-generator
**Approach:**
```bash
pip install datamodel-code-generator
datamodel-codegen --url http://localhost:8000/openapi.json --output dashboard/types/deep6.ts --output-model-type typescript
```
**Tradeoff:** Requires FastAPI running to generate. Types are more complete but include all API boilerplate. Good for CI automation.
**Use when:** Multiple developers, larger type surface, or when Phase 11 is verified working and Phase 12+ adds more endpoints.

**Recommendation:** Hand-write `types/deep6.ts` for Phase 11 with 7 core interfaces. Document the Pydantic source for each. Add a comment `// codegen: python -m datamodel_code_generator --url http://localhost:8000/openapi.json ...` at the top for future automation.

---

## Code Examples

### LW Charts Chart Init with Custom Series
```typescript
// Source: [VERIFIED: tradingview.github.io/lightweight-charts/docs]
'use client';
import { createChart } from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import { FootprintSeries } from '@/lib/lw-charts/FootprintSeries';

export function FootprintChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0a0a0f' },
        textColor: '#6b7280',
      },
      grid: {
        vertLines: { color: '#1e1e2e' },
        horzLines: { color: '#1e1e2e' },
      },
      crosshair: { color: '#6b7280' },
    });
    chartRef.current = chart;

    const footprintPaneView = new FootprintSeries();
    const series = chart.addCustomSeries(footprintPaneView, {});

    // Subscribe to Zustand store for bar updates (no React re-render)
    const unsubscribe = useTradingStore.subscribe(
      (state) => state.barBufferHead,
      () => {
        const { barBuffer, barBufferHead, barBufferSize } = useTradingStore.getState();
        const bars = getOrderedBars(barBuffer, barBufferHead, barBufferSize);
        if (bars.length > 0) {
          series.update(bars[bars.length - 1]);
        }
      }
    );

    return () => {
      unsubscribe();
      chart.remove();
    };
  }, []);

  return <div ref={containerRef} className="w-full h-full" />;
}
```

### FastAPI WebSocket Broadcast from Trading Engine
```python
# Source: [VERIFIED: fastapi.tiangolo.com/advanced/websockets/]
# The trading engine calls this to push bar close events:
async def on_bar_close(bar: FootprintBar, app_state):
    manager: LiveConnectionManager = app_state.ws_manager
    await manager.broadcast({
        "type": "bar",
        "data": {
            "time": bar.open_time,
            "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
            "volume": bar.total_volume,
            "delta": bar.net_delta,
            "poc": bar.poc_price,
            "levels": [{"price": l.price, "bidVol": l.bid_vol,
                        "askVol": l.ask_vol, "delta": l.delta,
                        "isImbalance": l.is_imbalance} for l in bar.levels],
            "signalType": bar.signal_type,
            "zoneOverlaps": [],
        }
    })
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LW Charts v3 marker-based custom indicators | v5.1 `addCustomSeries()` + `ICustomSeriesPaneView` plugin API | v4.1 (2023), stable in v5.x | Cleaner separation; custom series gets proper price scale integration |
| LW Charts v5.0 | v5.1 — adds data conflation | Dec 2025 | `enableConflation: true` option for rendering performance on 50k+ bars; not needed for 500-bar ring buffer |
| Redux for React state | Zustand v5 | 2024-2025 | Smaller bundle, no boilerplate, vanilla `getState()` for non-reactive reads |
| Webpack-based Next.js | Next.js 15 (Turbopack) | 2025 | Faster dev server; no impact on runtime behavior |

**Deprecated/outdated:**
- `chart.addLineSeries()` for overlays: Still works in v5.1 but custom series is the correct pattern for footprint cells
- `chart.applyOptions({ priceScale: { ... } })` for zone shading: Use sibling canvas overlay instead

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Next.js 15, npm | ✓ | v25.2.1 | — |
| npm | Package install | ✓ | 11.6.2 | — |
| npx | shadcn init | ✓ | 11.6.2 | — |
| FastAPI (Python) | WebSocket backend | ✓ | 0.135.3 | — |
| pytest | Python test suite | ✓ | 9.0.3 | — |
| Python 3.12 | FastAPI + EventStore | ✓ | (in use throughout project) | — |
| `dashboard/` directory | Next.js root | ✗ | — | Create in Wave 0 |

**Missing dependencies with no fallback:**
- `dashboard/` directory does not exist — Wave 0 must scaffold it with `npx create-next-app@latest dashboard --typescript --tailwind --app --no-src-dir --import-alias "@/*"`

**Missing dependencies with fallback:**
- None identified

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (Python) + Playwright or manual browser smoke test (frontend) |
| Config file | `pyproject.toml` (Python) / none yet for frontend |
| Quick run command | `cd /Users/teaceo/DEEP6 && python -m pytest tests/ -x -q` |
| Full suite command | `cd /Users/teaceo/DEEP6 && python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APP-01 (footprint render) | FootprintSeries.isWhitespace() and priceValueBuilder() return correct values | unit (Python-agnostic TS) | `cd dashboard && npx tsc --noEmit` (type check) | ❌ Wave 0 |
| APP-01 (zone overlay) | ZoneOverlay redraws on chart scroll without throwing | manual smoke | Visual inspection after `npm run dev` | ❌ Wave 0 |
| APP-03 (WebSocket) | `useWebSocket` hook reconnects after server restart | manual smoke | Kill FastAPI, verify dot turns yellow then green | N/A |
| APP-03 (message dispatch) | Discriminated union routes `bar`/`signal`/`score`/`status` types correctly | unit (Zustand store) | `cd dashboard && npx vitest run store/tradingStore.test.ts` | ❌ Wave 0 |
| APP-04 (replay endpoint) | `/api/replay/{session}/{bar_index}` returns correct signal slice | unit (pytest) | `python -m pytest tests/test_replay_endpoint.py -x` | ❌ Wave 0 |
| APP-04 (replay bar_history) | EventStore `insert_bar` + `fetch_bars_for_session` | unit (pytest) | `python -m pytest tests/test_event_store.py::test_bar_history -x` | ❌ Wave 0 |
| APP-06 (lite P&L) | Status message with `pnl` + `circuit_breaker_active` updates ScoreWidget | manual smoke | Verify via browser dev tools + WS monitor | N/A |
| APP-08 (no TV dep) | No `tradingview-widget` or iframe in component tree | unit (grep) | `grep -r "tradingview-widget\|tv.com/widget" dashboard/` should return empty | N/A |

### Sampling Rate
- **Per task commit:** `cd /Users/teaceo/DEEP6 && python -m pytest tests/ -x -q` (Python only; frontend TS type-check via `npx tsc --noEmit`)
- **Per wave merge:** Full pytest suite + `npm run build` in `dashboard/` (build failure = type errors caught)
- **Phase gate:** All tests green + manual browser smoke test of live WS feed + replay step-through before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `dashboard/` — Next.js 15 scaffold with TypeScript + Tailwind + App Router
- [ ] `dashboard/types/deep6.ts` — hand-written TypeScript interfaces for FootprintBar, SignalEvent, ScorerResult, StatusMessage, ZoneRef
- [ ] `dashboard/store/tradingStore.test.ts` — Zustand ring buffer push + discriminated union dispatch tests
- [ ] `tests/test_replay_endpoint.py` — FastAPI replay endpoint: session query, bar_index slicing, 404 on missing session
- [ ] `tests/test_event_store.py::test_bar_history` — EventStore bar_history CRUD (requires bar_history table addition)
- [ ] `deep6/api/routes/live.py` — WebSocket manager + broadcast (Python unit test: broadcast to 2 mock sockets)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Replay endpoint uses HTTP polling (not WebSocket) | Architecture Patterns §Pattern 6 | If WebSocket is preferred for replay, the connection management in useWebSocket.ts needs a separate mode |
| A2 | Zone overlays use sibling canvas (not LW Charts primitive API) | Architecture Patterns §Pattern 2 | If LW Charts v5.1 has a native zone band primitive, the overlay canvas is unnecessary complexity |
| A3 | TapeFlow uses independent canvas layers, not LW Charts custom series, for footprint cells | TapeFlow Reference | If TapeFlow uses addCustomSeries internally, the recommendation to use a hybrid approach may change |
| A4 | `bar_history` table needs to be added to EventStore in Phase 11 | EventStore Schema section | If another Phase 9+ plan adds bar_history before Phase 11 executes, the Wave 0 task is already done |
| A5 | Hand-written TypeScript types are preferred over codegen for Phase 11 | TypeScript Type Sharing | If the Python Pydantic models change frequently between Phase 11 waves, drift risk is higher than estimated |
| A6 | Zustand 5.x `subscribeWithSelector` API is backward compatible with the patterns shown | Standard Stack | If Zustand 5.x changed the subscribe API significantly, the Canvas subscription pattern needs revision |

---

## Open Questions (RESOLVED)

1. **Does bar_history table already exist or is it in a later Phase 9 plan?**
   - What we know: Phase 9 plans 03-04 are not yet executed; `deep6/api/store.py` only has `signal_events` + `trade_events`
   - What's unclear: Plan 09-04 (PerformanceTracker + E7 wiring) might add it
   - Recommendation: Check 09-04-PLAN.md before creating the table in Phase 11; if it exists, skip
   - **RESOLVED:** Plan 11-01 adds `bar_history` via `INSERT OR REPLACE` — idempotent whether or not the table pre-exists. No coordination needed with Phase 9.

2. **Where does `dashboard/` live: at repo root or inside `deep6/`?**
   - What we know: CONTEXT.md says "no existing Next.js codebase yet — this phase scaffolds `web/` (or `frontend/`) subdirectory" — planner picks exact location
   - What's unclear: Whether the Python package install scripts expect a specific path
   - Recommendation: Use `dashboard/` at repo root alongside `deep6/`; matches CLAUDE.md reference to "Next.js 15 + FastAPI backend"
   - **RESOLVED:** `dashboard/` is at repo root (`/Users/teaceo/DEEP6/dashboard/`), confirmed by all four Phase 11 plans.

3. **Should the WebSocket manager be a singleton in `app.state` or injected differently?**
   - What we know: Phase 9 uses `app.state.event_store`; the same pattern works for `app.state.ws_manager`
   - What's unclear: If Phase 9 plans 03-04 already add other lifespan resources that may conflict
   - Recommendation: Add `ws_manager` to lifespan in the same pattern as `event_store`
   - **RESOLVED:** `ws_manager` is stored in `app.state.ws_manager` per FastAPI lifespan pattern, mirroring `app.state.event_store`. Plan 11-01 Task 2 implements this.

4. **Replay session selector UI (date picker) is deferred — how does operator trigger replay?**
   - What we know: UI-SPEC says "replay triggered via URL param `?session=YYYY-MM-DD`"
   - What's unclear: How operator discovers available sessions; no session list endpoint defined
   - Recommendation: Add `GET /api/sessions` endpoint listing distinct dates from `signal_events.ts`; render as a simple dropdown above the replay controls (not deferred — needed for ANY replay use)
   - **RESOLVED:** Path A adopted. Plan 11-04 Task 2 now includes a `<SessionSelector>` component (shadcn `<Select>`) rendered in `ReplayControls`, calling the existing `fetchSessions()` from `replayClient.ts` to populate the dropdown.

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: npm registry 2026-04-13] — lightweight-charts@5.1.0, zustand@5.0.12, next@16.2.3, lucide-react@1.8.0, @tanstack/react-virtual@3.13.23
- [VERIFIED: read directly] `deep6/api/app.py`, `deep6/api/store.py` — exact EventStore schema, FastAPI app factory, existing routes
- [VERIFIED: read directly] `11-CONTEXT.md`, `11-UI-SPEC.md`, `09-01-PLAN.md` — locked decisions, design contract, backend integration surface
- [CITED: tradingview.github.io/lightweight-charts/docs/plugins/custom_series] — ICustomSeriesPaneView, ICustomSeriesPaneRenderer, PaneRendererCustomData, addCustomSeries
- [CITED: tradingview.github.io/lightweight-charts/docs/plugins/canvas-rendering-target] — CanvasRenderingTarget2D, useBitmapCoordinateSpace, BitmapCoordinatesRenderingScope
- [CITED: fastapi.tiangolo.com/advanced/websockets/] — WebSocket endpoint, ConnectionManager, WebSocketDisconnect, send_json

### Secondary (MEDIUM confidence)
- [CITED: github.com/ianfigueroa/TapeFlow via WebFetch] — Canvas layer stack, ring buffer Map<string, Trade[]>, React + Zustand + @tanstack/react-virtual + lightweight-charts stack
- [CITED: websocket.org/guides/reconnection/] — exponential backoff pattern (1s→2s→4s→8s→16s→30s cap)
- [CITED: zustand.docs.pmnd.rs/reference/middlewares/subscribe-with-selector] — subscribeWithSelector middleware, getState() for non-reactive reads

### Tertiary (LOW confidence — training knowledge, not session-verified)
- [ASSUMED] TapeFlow sibling canvas vs LW Charts custom series split — WebFetch confirmed TapeFlow uses separate canvas layers but source files not read directly
- [ASSUMED] TypeScript discriminated union dispatch pattern for WebSocket messages
- [ASSUMED] Replay HTTP polling implementation details (endpoint shape, session date query against EventStore)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified via npm registry 2026-04-13
- LW Charts custom series API: HIGH — interface names and draw() signature verified via official docs
- Canvas overlay sync pattern: MEDIUM — confirmed LW Charts APIs (priceToCoordinate, subscribeCrosshairMove); canvas sync code is [ASSUMED]
- TapeFlow internals: MEDIUM — stack and ring buffer pattern confirmed via WebFetch; source code not directly readable
- FastAPI WebSocket: HIGH — verified via official docs; existing app.py confirms app factory pattern
- Phase 9 EventStore schema: HIGH — read directly from source code
- Zustand ring buffer pattern: MEDIUM — API confirmed via docs; specific ring buffer usage pattern is [ASSUMED]
- Replay endpoint design: LOW — inferred from EventStore schema and UI-SPEC requirements; no reference implementation exists

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (stable ecosystem; LW Charts releases infrequently)
