# Zustand v5 Ring Buffer Reference (DEEP6 Web Executor)

Purpose: give the Wave 1/2 executor a drop-in pattern for a Zustand v5 store that absorbs ~1000 WS msgs/sec (DOM ticks, bar updates, signals, T&S) and feeds Canvas renderers without triggering React re-renders.

## 1. Ring buffer data structure

Three options for the bars (~500 slots, ~1/sec) and tape (~1000 slots, ~1000/sec):

| Option | Push cost | GC pressure | Notes |
|---|---|---|---|
| `Array.prototype.shift/push` | O(n) reindex | high | AVOID for tape — 1000/s × shift = jank |
| Plain JS array + head/tail pointers | O(1) | low | Preserve object identity; supports heterogeneous records |
| Circular TypedArray (Float64 etc.) | O(1) | zero | Fastest, but one slot per scalar; poor fit for FootprintBar/Tape objects with mixed fields |

**Recommendation:** plain fixed-capacity `Array<T>` with a `head` (write index) and a `count`. Pre-allocate `new Array(capacity)` once, overwrite slots in place. O(1) push, no allocation churn, object identity preserved so React `key={bar.id}` works, and iteration via `(head - 1 - i + cap) % cap` is trivial.

Use a TypedArray only for the per-level DOM heatmap (bid/ask size by price offset), not for the bar/tape buffers.

```ts
export class RingBuffer<T> {
  private buf: (T | undefined)[];
  private head = 0;
  private _count = 0;
  constructor(public readonly capacity: number) {
    this.buf = new Array(capacity);
  }
  push(v: T) {
    this.buf[this.head] = v;
    this.head = (this.head + 1) % this.capacity;
    if (this._count < this.capacity) this._count++;
  }
  get size() { return this._count; }
  /** Newest-first snapshot. Allocates — call sparingly (renderer reads slice lazily). */
  toArray(): T[] {
    const out: T[] = new Array(this._count);
    for (let i = 0; i < this._count; i++) {
      out[i] = this.buf[(this.head - 1 - i + this.capacity) % this.capacity] as T;
    }
    return out;
  }
  /** Zero-alloc iteration newest→oldest for Canvas draw loops. */
  forEachNewest(fn: (v: T, i: number) => void, limit = this._count) {
    const n = Math.min(limit, this._count);
    for (let i = 0; i < n; i++) {
      fn(this.buf[(this.head - 1 - i + this.capacity) % this.capacity] as T, i);
    }
  }
}
```

## 2. `subscribeWithSelector` middleware

Zustand v5 ships this middleware; it upgrades `store.subscribe` so you can subscribe to a slice with a custom equality function — the hot path for Canvas renderers.

- `useStore(selector)` — **reactive**, triggers component re-render. Use only for low-frequency UI (status pill, score KPI, connection banner).
- `store.subscribe(selector, listener, { equalityFn, fireImmediately })` — **non-reactive**, runs a listener outside React. Use for Canvas redraw triggers.
- `store.getState()` — **non-reactive read**. Call it inside `requestAnimationFrame` or inside the subscribe listener to pull the ring buffer without any React involvement.

The pattern:
1. WS message arrives → `store.getState().pushBar(bar)` mutates the RingBuffer in place and bumps `barsVersion++`.
2. Canvas component `useEffect`s once on mount: `store.subscribe(s => s.barsVersion, () => scheduleDraw())`.
3. `scheduleDraw` sets a dirty flag read inside an rAF loop; the draw reads `store.getState().bars.toArray()` (or `forEachNewest`) directly.

Result: the React tree never re-renders on bar ticks.

## 3. Mutation strategy

Zustand does **not** require immutability at the buffer level — only the top-level state object returned from `set` must be a new reference for `useStore` subscribers to fire. Two valid styles:

- **Immutable wrapper:** `set({ barsVersion: v + 1 })` after mutating the RingBuffer in place. The buffer itself is mutable, but the `barsVersion` scalar is replaced, so selectors watching `barsVersion` correctly notice.
- **Pure immutable:** rebuild a new array each push. Cheap at 1/sec for bars, wasteful at 1000/sec for tape.

Use the **version counter pattern**: mutate the RingBuffer, then `set(s => ({ barsVersion: s.barsVersion + 1 }))`. Canvas subscribers watching `barsVersion` via `subscribeWithSelector` fire exactly once per push with zero re-renders elsewhere. This is the established Zustand idiom for high-frequency external data.

Critical: never return the RingBuffer instance from a `useStore` selector — its reference is stable so React would miss updates, and if a consumer did `.toArray()` on every render you'd thrash GC. Expose only the version counter reactively; expose the buffer only via `getState()`.

## 4. Store structure sketch

Six slices, one dispatcher. See `tradingStore.ts` below. Actions:

- `pushBar(bar)` — append + bump `barsVersion`
- `pushSignal(sig)` — append + bump `signalsVersion`
- `pushTape(print)` — append + bump `tapeVersion`
- `setScore(score)` — reactive (low freq, drives KPI card)
- `setStatus(status)` — reactive
- `setConnection(state)` — reactive
- `dispatch(msg)` — discriminated union router from WS

## 5. React re-render avoidance

- **`useSyncExternalStore`** — Zustand's `useStore` already uses it internally in v5; if you need a raw subscription to `barsVersion` without pulling in middleware types, `useSyncExternalStore(store.subscribe, () => store.getState().barsVersion)` works.
- **Custom equality** — pass `{ equalityFn: shallow }` (from `zustand/shallow` — note v5 moved it, see breaking changes) when subscribing to compound slices.
- **`useRef` for Canvas** — keep `canvasRef`, `ctxRef`, and `rafIdRef` in refs; never in store state.
- **Bypass from effects** — Canvas component subscribes in a `useEffect(() => store.subscribe(...), [])`, returns the unsubscribe. Never read `store.getState().bars` inside the render body.
- **Selector discipline** — `useStore(s => s.score)` is fine; `useStore(s => s.bars)` is a footgun.

## 6. Testing pattern (vitest)

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { createTradingStore } from './tradingStore';

describe('RingBuffer', () => {
  it('wraps at capacity, newest-first', () => {
    const store = createTradingStore({ barsCap: 3 });
    [1,2,3,4].forEach(i => store.getState().pushBar({ id: i } as any));
    expect(store.getState().bars.toArray().map(b => b.id)).toEqual([4,3,2]);
  });
  it('bumps barsVersion exactly once per push', () => {
    const s = createTradingStore();
    const v0 = s.getState().barsVersion;
    s.getState().pushBar({ id: 1 } as any);
    expect(s.getState().barsVersion).toBe(v0 + 1);
  });
  it('dispatch routes by type', () => {
    const s = createTradingStore();
    s.getState().dispatch({ type: 'signal', payload: { id: 's1' } as any });
    expect(s.getState().signalsVersion).toBe(1);
  });
});
```

## Zustand v5 breaking changes to flag

1. **React 18+ required.** v5 uses `useSyncExternalStore` directly, no `use-sync-external-store` shim.
2. **Default export removed from `zustand`.** Use named `import { create } from 'zustand'`. The bare `create(fn)` pattern still works but `create<T>()(fn)` curried form is now mandatory for TS generics.
3. **`zustand/shallow` moved.** `import { shallow } from 'zustand/shallow'` (not `zustand/react/shallow` — there's also `useShallow` hook at `zustand/react/shallow`).
4. **`subscribe(listener)` no longer accepts a selector directly.** You must wrap with the `subscribeWithSelector` middleware to pass `(selector, listener, opts)`. Without the middleware, `subscribe` gets the whole state.
5. **`getServerState`, `destroy()` removed** (destroy was deprecated in v4, fully gone in v5 — manage lifecycles explicitly).
6. **Context API moved** to `zustand/context` via `createStore` + manual provider; `create` no longer bundles React context.

---

## `tradingStore.ts` skeleton (~80 lines)

```ts
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { RingBuffer } from './ringBuffer';

export interface FootprintBar { id: number; t: number; /* ... */ }
export interface Signal { id: string; name: string; conf: number; t: number }
export interface TapePrint { t: number; px: number; sz: number; side: 'B'|'S' }
export type ConnState = 'disconnected' | 'connecting' | 'live' | 'error';

export type WsMsg =
  | { type: 'bar'; payload: FootprintBar }
  | { type: 'signal'; payload: Signal }
  | { type: 'tape'; payload: TapePrint }
  | { type: 'score'; payload: number }
  | { type: 'status'; payload: string }
  | { type: 'conn'; payload: ConnState };

export interface TradingState {
  bars: RingBuffer<FootprintBar>;
  signals: RingBuffer<Signal>;
  tape: RingBuffer<TapePrint>;
  score: number;
  status: string;
  connection: ConnState;
  barsVersion: number;
  signalsVersion: number;
  tapeVersion: number;
  pushBar: (b: FootprintBar) => void;
  pushSignal: (s: Signal) => void;
  pushTape: (p: TapePrint) => void;
  setScore: (n: number) => void;
  setStatus: (s: string) => void;
  setConnection: (c: ConnState) => void;
  dispatch: (m: WsMsg) => void;
}

export const createTradingStore = (opts?: {
  barsCap?: number; signalsCap?: number; tapeCap?: number;
}) => create<TradingState>()(subscribeWithSelector((set, get) => ({
  bars: new RingBuffer<FootprintBar>(opts?.barsCap ?? 500),
  signals: new RingBuffer<Signal>(opts?.signalsCap ?? 200),
  tape: new RingBuffer<TapePrint>(opts?.tapeCap ?? 1000),
  score: 0, status: 'idle', connection: 'disconnected',
  barsVersion: 0, signalsVersion: 0, tapeVersion: 0,
  pushBar: (b) => { get().bars.push(b); set(s => ({ barsVersion: s.barsVersion + 1 })); },
  pushSignal: (s) => { get().signals.push(s); set(st => ({ signalsVersion: st.signalsVersion + 1 })); },
  pushTape: (p) => { get().tape.push(p); set(s => ({ tapeVersion: s.tapeVersion + 1 })); },
  setScore: (n) => set({ score: n }),
  setStatus: (s) => set({ status: s }),
  setConnection: (c) => set({ connection: c }),
  dispatch: (m) => {
    const g = get();
    switch (m.type) {
      case 'bar':    return g.pushBar(m.payload);
      case 'signal': return g.pushSignal(m.payload);
      case 'tape':   return g.pushTape(m.payload);
      case 'score':  return g.setScore(m.payload);
      case 'status': return g.setStatus(m.payload);
      case 'conn':   return g.setConnection(m.payload);
    }
  },
})));

export const useTradingStore = createTradingStore();
```

**Canvas consumer pattern:**

```ts
useEffect(() => {
  const unsub = useTradingStore.subscribe(
    s => s.barsVersion,
    () => { dirtyRef.current = true; },
  );
  const loop = () => {
    if (dirtyRef.current) {
      dirtyRef.current = false;
      const bars = useTradingStore.getState().bars;   // non-reactive
      draw(ctxRef.current!, bars);
    }
    rafRef.current = requestAnimationFrame(loop);
  };
  rafRef.current = requestAnimationFrame(loop);
  return () => { unsub(); cancelAnimationFrame(rafRef.current!); };
}, []);
```

This combination — mutable RingBuffer + version counter + `subscribeWithSelector` + `getState()` in rAF — is what keeps React out of the 1000 Hz hot path.
