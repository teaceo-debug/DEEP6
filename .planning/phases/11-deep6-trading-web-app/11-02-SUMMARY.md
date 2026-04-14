---
phase: 11-deep6-trading-web-app
plan: "02"
subsystem: dashboard-frontend
tags: [nextjs, tailwind, shadcn, zustand, ring-buffer, typescript, vitest]
dependency_graph:
  requires: ["11-01"]
  provides: ["dashboard-scaffold", "store-contract", "ts-types", "design-tokens"]
  affects: ["11-03", "11-04", "11-05", "11-06"]
tech_stack:
  added:
    - "next@16.2.3"
    - "zustand@5.0.12 + subscribeWithSelector"
    - "lightweight-charts@5.1.0 (dependency pinned, not yet wired)"
    - "@tanstack/react-virtual@3.13.23 (dependency pinned, not yet wired)"
    - "vitest@2.1.x + jsdom"
  patterns:
    - "Mutable RingBuffer<T> + version counter (lastBarVersion) for Canvas re-render avoidance"
    - "Zustand v5 subscribeWithSelector middleware for fine-grained Canvas subscriptions"
    - "TDD (RED→GREEN) for ring buffer and store dispatcher"
    - "Tailwind v4 @theme inline for CSS variable mapping (no tailwind.config.ts needed)"
key_files:
  created:
    - dashboard/app/globals.css
    - dashboard/app/layout.tsx
    - dashboard/app/page.tsx
    - dashboard/lib/utils.ts
    - dashboard/vitest.config.ts
    - dashboard/components.json
    - dashboard/types/deep6.ts
    - dashboard/store/ringBuffer.ts
    - dashboard/store/ringBuffer.test.ts
    - dashboard/store/tradingStore.ts
    - dashboard/store/tradingStore.test.ts
  modified:
    - dashboard/package.json
    - dashboard/README.md
    - dashboard/.gitignore
decisions:
  - "Tailwind v4 uses @theme inline CSS directives instead of tailwind.config.ts — no JS config file needed; color tokens mapped via --color-* variables in @theme block"
  - "shadcn CLI flags changed: --base-color and --style flags removed; components.json written manually with new-york style + zinc base"
  - "Rebuilt dashboard/ from scratch: old src/-based scaffold had wrong structure (create-next-app had already created wrong layout); replaced with no-src-dir app/ structure per plan"
  - "RingBuffer toArray() is insertion-order (oldest→newest); Test 12 corrected to check arr[0] for oldest retained item"
metrics:
  duration: "~25 min"
  completed: "2026-04-14"
  tasks_completed: 2
  tasks_total: 2
  files_created: 11
  files_modified: 3
  tests_added: 12
  tests_passing: 12
---

# Phase 11 Plan 02: Next.js Scaffold + Design Tokens + Store Contract Summary

**One-liner:** Next.js 16.2.3 dark-only shell with DEEP6 design tokens, Zustand v5 mutable ring buffer store (500 bars / 200 signals / 50 T&S), and TypeScript LiveMessage union mirroring Python schemas — all 12 TDD tests green.

---

## What Was Built

### Dashboard Directory Tree (top 2 levels)

```
dashboard/
├── app/
│   ├── favicon.ico
│   ├── globals.css         ← UI-SPEC design tokens + TYPE_A pulse keyframes
│   ├── layout.tsx          ← dark class, Inter + JetBrains Mono fonts
│   └── page.tsx            ← 3-column shell (footprint / signals+T&S / score) + header + replay strip
├── lib/
│   └── utils.ts            ← cn() utility
├── store/
│   ├── ringBuffer.ts       ← RingBuffer<T> (O(1) push, head/size/latest/toArray/forEachNewest/clear)
│   ├── ringBuffer.test.ts  ← 5 tests (capacity, push, wrap, eviction, clear)
│   ├── tradingStore.ts     ← Zustand store + dispatchLiveMessage export
│   └── tradingStore.test.ts← 7 tests (all dispatch paths, ring eviction, unknown type safety)
├── types/
│   └── deep6.ts            ← LiveMessage union, FootprintBar, SignalEvent, ZoneRef, TapeEntry
├── components.json         ← shadcn new-york + zinc (dark-only)
├── package.json            ← all deps pinned
├── vitest.config.ts        ← jsdom + @/* alias
└── README.md
```

### Locked Store Contract

Exports from `dashboard/store/tradingStore.ts`:

```typescript
export const BAR_CAPACITY = 500;
export const SIGNAL_CAPACITY = 200;
export const TAPE_CAPACITY = 50;

export interface ScoreSlice { totalScore, tier, direction, categoriesFiring, categoryScores, kronosBias, kronosDirection, gexRegime }
export interface StatusSlice { connected, pnl, circuitBreakerActive, feedStale, lastTs }
export interface TradingState {
  bars: RingBuffer<FootprintBar>;        // 500 capacity — mutable
  signals: RingBuffer<SignalEvent>;      // 200 capacity
  tape: RingBuffer<TapeEntry>;           // 50 capacity
  score: ScoreSlice;
  status: StatusSlice;
  lastBarVersion: number;                // bumped on each pushBar — Canvas trigger
  lastSignalVersion: number;             // bumped on each pushSignal
  pushBar / pushSignal / pushTape / setScore / setStatus / dispatch
}
export const useTradingStore: StoreApi<TradingState>;
export function dispatchLiveMessage(msg: LiveMessage): void;
```

### How Wave 2 Canvas Subscribes Without Re-Rendering

Wave 2 Canvas components subscribe to `lastBarVersion` via `subscribeWithSelector` — this fires the redraw callback exactly once per bar push, never causing a React re-render:

```typescript
useEffect(() => {
  const unsub = useTradingStore.subscribe(
    s => s.lastBarVersion,
    () => { dirtyRef.current = true; },
  );
  const loop = () => {
    if (dirtyRef.current) {
      dirtyRef.current = false;
      const bars = useTradingStore.getState().bars; // non-reactive getState()
      draw(ctxRef.current!, bars);
    }
    rafRef.current = requestAnimationFrame(loop);
  };
  rafRef.current = requestAnimationFrame(loop);
  return () => { unsub(); cancelAnimationFrame(rafRef.current!); };
}, []);
```

React components needing reactive bar data use `useTradingStore(s => s.bars.toArray().slice(-30))` and accept the re-render cost (Wave 2 signal feed, score widget).

### Design Token Confirmation

All UI-SPEC §Color tokens wired in `dashboard/app/globals.css`:

| Token | Value | Use |
|-------|-------|-----|
| `--bg-base` | `#0a0a0f` | Page background |
| `--bg-surface` | `#111118` | Panel/card surfaces |
| `--bg-elevated` | `#16161f` | Popovers, tooltips |
| `--border-subtle` | `#1e1e2e` | All borders |
| `--bid` | `#ef4444` | Bid volume / sell pressure |
| `--ask` | `#22c55e` | Ask volume / buy pressure |
| `--type-a` | `#a3e635` | TYPE_A signals |
| `--type-b` | `#facc15` | TYPE_B signals |
| `--type-c` | `#38bdf8` | TYPE_C signals |
| `--zone-lvn` | `rgba(56,189,248,0.12)` | LVN zone band |
| `--lw-bg/grid/crosshair/scale-text` | per spec | LW Charts options |

Tailwind v4 `@theme inline` maps all tokens to `--color-*` utility classes (e.g. `bg-bg-surface`, `text-type-a`).

TYPE_A pulse keyframe (`typeAPulse`) and `.signal-type-a-pulse` class included with `prefers-reduced-motion` guard.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Tailwind v4 has no tailwind.config.ts**
- **Found during:** Task 1
- **Issue:** Plan referenced `tailwind.config.ts` with `theme.extend.colors` block, but Next.js 16 / Tailwind v4 uses CSS `@theme inline` directives exclusively — no JS config file
- **Fix:** Added `@theme inline` block in `globals.css` mapping all design tokens to `--color-*` Tailwind utilities; no `tailwind.config.ts` created
- **Files modified:** `dashboard/app/globals.css`

**2. [Rule 3 - Blocking] shadcn CLI API changed — `--base-color` and `--style` flags removed**
- **Found during:** Task 1
- **Issue:** `npx shadcn@latest init --base-color zinc --style new-york` exited with error "unknown option"
- **Fix:** Created `components.json` manually with `"style": "new-york"` and `"baseColor": "zinc"` — equivalent result
- **Files modified:** `dashboard/components.json`

**3. [Rule 3 - Blocking] Existing dashboard/ had wrong src/ structure**
- **Found during:** Task 1 pre-check
- **Issue:** Prior `dashboard/` used `src/app/` layout with `base-nova` shadcn style — incompatible with plan's `--no-src-dir` + `new-york` requirements
- **Fix:** Deleted entire `dashboard/` and re-scaffolded from scratch with correct structure
- **Files modified:** All dashboard files (rebuild)

**4. [Rule 1 - Bug] Test 12 assertion used wrong array index**
- **Found during:** Task 2 GREEN phase
- **Issue:** Test comment said ring was "newest-first" but `toArray()` is insertion-order (oldest→newest); assertion `arr[arr.length-1]` checked newest (500) instead of oldest (1)
- **Fix:** Corrected to `arr[0].bar_index === 1` (oldest retained) + `arr[arr.length-1].bar_index === 500` (newest)
- **Files modified:** `dashboard/store/tradingStore.test.ts`

---

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| `Footprint (Wave 2)` text | `dashboard/app/page.tsx` | ~20 | LW Charts custom series built in Wave 2 (11-03) |
| `Signals (Wave 2)` text | `dashboard/app/page.tsx` | ~35 | SignalFeed component built in Wave 2 (11-04) |
| `Confluence (Wave 2)` text | `dashboard/app/page.tsx` | ~45 | ScoreWidget built in Wave 2 (11-05) |
| `Tape & Sales (Wave 2)` text | `dashboard/app/page.tsx` | ~38 | TapeScroll built in Wave 2 (11-05) |
| `Replay (Wave 3)` text | `dashboard/app/page.tsx` | ~55 | ReplayControls built in Wave 3 (11-06) |

These stubs are intentional — Plan 11-02 objective is scaffold + store contract only. Wave 2 plans (11-03 through 11-06) replace each placeholder with real components.

---

## Self-Check: PASSED

```
dashboard/app/globals.css    ✓ EXISTS
dashboard/app/layout.tsx     ✓ EXISTS
dashboard/app/page.tsx       ✓ EXISTS
dashboard/lib/utils.ts       ✓ EXISTS
dashboard/types/deep6.ts     ✓ EXISTS
dashboard/store/ringBuffer.ts ✓ EXISTS
dashboard/store/tradingStore.ts ✓ EXISTS
dashboard/vitest.config.ts   ✓ EXISTS
dashboard/components.json    ✓ EXISTS
```

Commits verified:
- `6063b18` feat(11-02): scaffold (Task 1) ✓
- `842954a` feat(11-02): types + store (Task 2) ✓

Tests: 12/12 passing | Build: exit 0 | Typecheck: exit 0
