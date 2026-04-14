# DEEP6 Dashboard — Extending the Dashboard

Six self-contained recipes for common extension tasks. Each recipe shows exactly which files to touch and in what order.

---

## Recipe 1: Adding a New Message Type

Say the backend gains a new `gex` message type that sends GEX surface data.

### Step 1: Define the TypeScript type

**File:** `types/deep6.ts`

```typescript
// Add the payload interface
export interface GexSurface {
  call_wall: number;
  put_wall: number;
  flip_level: number;
  net_gex: number;
}

// Add the message interface
export interface LiveGexMessage {
  type: 'gex';
  surface: GexSurface;
}

// Add to the union
export type LiveMessage =
  | LiveBarMessage
  | LiveSignalMessage
  | LiveScoreMessage
  | LiveStatusMessage
  | LiveTapeMessage
  | LiveGexMessage;   // <-- add here
```

### Step 2: Add a store slice and dispatch case

**File:** `store/tradingStore.ts`

```typescript
// 1. Add a slice interface
export interface GexSlice {
  callWall: number;
  putWall: number;
  flipLevel: number;
  netGex: number;
}

// 2. Add to TradingState
export interface TradingState {
  // ... existing fields ...
  gex: GexSlice;
  setGex: (m: LiveGexMessage) => void;
}

// 3. Add initial value
const INIT_GEX: GexSlice = { callWall: 0, putWall: 0, flipLevel: 0, netGex: 0 };

// 4. Add to create() body
gex: INIT_GEX,
setGex: (m) => set({ gex: { callWall: m.surface.call_wall, ... } }),

// 5. Add dispatch case
case 'gex': {
  const m = msg as LiveGexMessage;
  if (!m.surface || typeof m.surface.call_wall !== 'number') break;
  g.setGex(m);
  break;
}
```

### Step 3: Build a component that reads the slice

```typescript
// components/gex/GexPanel.tsx
'use client';
import { useTradingStore } from '@/store/tradingStore';

export function GexPanel() {
  const { callWall, putWall, flipLevel } = useTradingStore(s => s.gex);
  return (
    <div className="text-sm tnum label-tracked">
      CALL WALL {callWall.toFixed(2)}
    </div>
  );
}
```

### Step 4: Add to layout

Add `<GexPanel />` to the desired column in `app/page.tsx`. The store will populate it as soon as the backend starts sending `gex` messages.

---

## Recipe 2: Adding a New Panel to the Hero Column

The hero column (`app/page.tsx`, the 360px `<aside>`) currently has three slots: ConfluencePulse (360px fixed), KronosBar (88px fixed), ZoneList (flex-1). To add a fourth panel below ZoneList:

**File:** `app/page.tsx`

```tsx
{/* Zone list — shrinks to make room for new panel */}
<div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
  <ZoneList />
</div>

{/* NEW: Market Profile panel — fixed height */}
<div
  style={{
    height: '120px',
    flexShrink: 0,
    position: 'relative',
    borderTop: '1px solid var(--rule)',
  }}
>
  <MarketProfilePanel />
</div>
```

To insert the panel *between* existing slots, change ZoneList from `flex:1` to a fixed `height` and add the new panel with `flex:1`. The hero column is a `flexDirection:'column'` container so any flex or fixed-height combination works.

---

## Recipe 3: Adding a New Zone Type

Zone types are drawn by `lib/lw-charts/zoneDrawer.ts` using a plain string-keyed `Record`. Adding a new type requires only adding to that record — no TypeScript union change needed for the drawer.

### Step 1: Add the type to `types/deep6.ts` (if it will arrive on the wire)

```typescript
export type ZoneType = 'LVN' | 'HVN' | 'ABSORPTION' | 'GEX_CALL' | 'GEX_PUT' | 'SESSION_OPEN';
```

### Step 2: Add a style entry to `zoneDrawer.ts`

**File:** `lib/lw-charts/zoneDrawer.ts`

```typescript
// Find the ZONE_STYLES record and add:
SESSION_OPEN: {
  fill: 'rgba(255, 0, 170, 0.06)',   // --magenta at 6% (ML-derived level)
  stroke: '#ff00aa',                  // --magenta
  strokeWidth: 1,
  dash: [4, 4],                       // dashed
  labelColor: '#ff00aa',
},
```

The drawer looks up zone kind by string at draw time. If the backend sends `kind: 'SESSION_OPEN'`, it will render immediately.

### Step 3: Add a row in ZoneList (optional — for the sidebar table)

**File:** `components/zones/ZoneList.tsx`

The zone list reads from `bars.latest.poc_price` (current stub) and will eventually read from a `zone_registry` store slice. Find the rows array in the component and add:

```typescript
{ code: 'SOPEN', price: sessionOpen, color: 'var(--magenta)', label: 'Session Open' },
```

---

## Recipe 4: Customizing the TYPE_A Flash Animation

All TYPE_A animation constants are in one file.

**File:** `lib/animations.ts`

```typescript
// The main flash for the ConfluencePulse inner core:
export const typeAFlashKeyframes = {
  scale: [1, 1.04, 1.0, 1],           // adjust scale overshoot here
  filter: [
    'drop-shadow(...)',                 // normal glow
    'drop-shadow(...)',                 // white-hot peak (120ms mark)
    'drop-shadow(...)',                 // bright lime settle (400ms mark)
    'drop-shadow(...)',                 // final settled glow (1500ms mark)
  ],
};

export const typeAFlashTransition = {
  duration: 1.5,                        // total duration in seconds
  ease: 'easeOut',
  times: [0, 0.08, 0.267, 1],          // keyframe positions as fractions of duration
};

// The radial bloom circle that expands from center:
export const radialBloomKeyframes = {
  r: [90, 200],                         // SVG radius from → to
  opacity: [0.3, 0],
};

// The aftershock echo (400ms delayed, wider):
export const aftershockBloomKeyframes = {
  r: [100, 300],
  opacity: [0.3, 0],
};
export const aftershockBloomTransition = {
  duration: 1.1,
  ease: 'easeOut',
  delay: 0.4,                           // starts 400ms after the main flash
};
```

The screen-shake is a CSS class in `app/globals.css` (search for `.shake` or `body.shake`). To adjust the shake intensity, change the `@keyframes shake` translation values.

---

## Recipe 5: Adding a New Chart Overlay (Canvas Layer Pattern)

The footprint chart has two sibling canvas overlays: `ZoneOverlay` and `VolumeProfile`. Both follow the same pattern. Here is how to add a third (e.g., VWAP line):

### Step 1: Create the renderer

**File:** `lib/lw-charts/vwapRenderer.ts`

```typescript
export function drawVwap(
  ctx: CanvasRenderingContext2D,
  vwapPrice: number,
  priceToY: (p: number) => number,
  width: number,
) {
  const y = priceToY(vwapPrice);
  ctx.save();
  ctx.strokeStyle = '#ff00aa';   // --magenta (ML-derived price level)
  ctx.lineWidth = 1;
  ctx.setLineDash([6, 3]);
  ctx.beginPath();
  ctx.moveTo(0, y);
  ctx.lineTo(width, y);
  ctx.stroke();
  ctx.restore();
}
```

### Step 2: Create the overlay component

**File:** `components/footprint/VwapOverlay.tsx`

```typescript
'use client';
import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';
import { useTradingStore } from '@/store/tradingStore';
import { drawVwap } from '@/lib/lw-charts/vwapRenderer';

interface Props { chartApi: IChartApi | null }

export function VwapOverlay({ chartApi }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Subscribe to whichever store field holds VWAP price
  const bars = useTradingStore(s => s.bars);

  useEffect(() => {
    if (!chartApi || !canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d')!;
    const { width, height } = canvasRef.current;
    ctx.clearRect(0, 0, width, height);

    const vwap = /* derive from bars */ 0;
    const priceToY = (p: number) => chartApi.priceScale('right').priceToCoordinate(p) ?? 0;
    drawVwap(ctx, vwap, priceToY, width);
  }, [chartApi, bars]);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
    />
  );
}
```

### Step 3: Mount it in FootprintChart

**File:** `components/footprint/FootprintChart.tsx`

```tsx
import { VwapOverlay } from './VwapOverlay';

// Inside the return, alongside ZoneOverlay:
<ZoneOverlay chartApi={chartApi} />
<VwapOverlay chartApi={chartApi} />
<VolumeProfile chartApi={chartApi} />
```

---

## Recipe 6: Changing the Color Palette

All color tokens are CSS custom properties in one place.

**File:** `app/globals.css` (`:root` block, first ~45 lines)

```css
:root {
  --void:        #000000;   /* true-black canvas */
  --surface-1:   #0a0a0a;   /* first elevation — panels */
  --surface-2:   #141414;   /* second elevation — cards */
  --rule:        #1f1f1f;   /* dividers */
  --rule-bright: #2a2a2a;   /* focused borders */

  --text:        #f5f5f5;   /* primary text */
  --text-dim:    #8a8a8a;   /* secondary text */
  --text-mute:   #4a4a4a;   /* decorative / disabled only — fails WCAG AA for body */

  --bid:     #ff2e63;   /* bearish — NEVER use for non-bearish meaning */
  --ask:     #00ff88;   /* bullish — NEVER use for non-bullish meaning */
  --cyan:    #00d9ff;   /* TYPE_C / LVN / replay */
  --amber:   #ffd60a;   /* TYPE_B / HVN/POC / warning */
  --lime:    #a3ff00;   /* TYPE_A / confluence >=80 — the ONLY wow color */
  --magenta: #ff00aa;   /* Kronos / ALL ML attribution */
}
```

The `@theme inline` block immediately below maps these to Tailwind utility classes. If you rename a token in `:root`, update the `@theme inline` block to match.

For SVG-internal use (where CSS vars do not resolve), the same palette is mirrored as hex values in `lib/animations.ts`:

```typescript
export const CATEGORY_COLORS_HEX: Readonly<Record<CategoryKey, string>> = {
  absorption: '#a3ff00',
  exhaustion:  '#a3ff00',
  imbalance:   '#00d9ff',
  delta:       '#ffd60a',
  auction:     '#00d9ff',
  volume:      '#ffd60a',
  trap:        '#ff2e63',
  ml:          '#ff00aa',
};
```

Update both places together when changing neon colors.

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — data flow, store shape, rendering split
- [COMPONENT-INDEX.md](COMPONENT-INDEX.md) — every component with props and subscriptions
