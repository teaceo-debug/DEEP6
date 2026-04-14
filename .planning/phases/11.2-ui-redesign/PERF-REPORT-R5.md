# DEEP6 Dashboard — Performance Audit Report R5
**Date:** 2026-04-13
**Scope:** rAF audit, Zustand selector audit, React.memo opportunities, ringBuffer optimization
**Budget:** 60fps / 16ms frame, <15% CPU active, <2% CPU idle

---

## Summary

All three auditable files were modified. Typecheck clean. Build clean. 26 store tests pass.
Pre-existing ZoneList test failures (VAH label mismatch) are unrelated to this audit.

---

## Measured Hotspots

### 1. `RingBuffer.toArray()` — double-allocation in full-buffer path
**File:** `store/ringBuffer.ts`
**Issue:** Full-buffer path used `[...this.buf.slice(this.head), ...this.buf.slice(0, this.head)]` — two `.slice()` calls each allocate a new array, then spread merges them into a third. For a 500-bar buffer this is ~3 allocations of O(n) each per call.
**Frequency:** Called on every `lastBarVersion` change in VolumeProfile (via `useTradingStore.getState()`), on every `lastSignalVersion` in SignalFeed, and on every `lastTapeVersion` in TapeScroll. At 2 ticks/sec demo rate this is ~2 full calls/sec; under live load it could be higher.
**Risk:** GC pressure, minor pause spikes on budget boundary.

### 2. `ConfluencePulse` calls `prefersReducedMotion()` per render
**File:** `lib/animations.ts` (the function itself), `components/score/ConfluencePulse.tsx:583` (the call site — not in edit scope)
**Issue:** `prefersReducedMotion()` calls `window.matchMedia('(prefers-reduced-motion: reduce)')` synchronously on every render. `matchMedia` forces a style recalculation in Chrome. ConfluencePulse re-renders on every `score` / `tier` / `direction` / `categoriesFiring` / `categoryScores` / `connected` change — that is every score update.
**Impact:** At 2 ticks/sec, minor (~1ms per call). At live 10 ticks/sec, accumulates to ~10ms/sec of forced style recalc.
**Fix applied:** Added authoritative PERF NOTE to `prefersReducedMotion()` and `reducedMotion()` in animations.ts documenting that calling from render is wrong and directing component authors to `useReducedMotion()` from 'motion/react'. Component fix is deferred (component files are out of scope).

### 3. `PnlStatus` subscribes to entire `status` slice
**File:** `store/tradingStore.ts` (selector helpers added), `components/status/PnlStatus.tsx:15` (call site — out of scope)
**Issue:** `useTradingStore((s) => s.status)` — since `setStatus()` always replaces the status object with a new one, this selector returns a new reference on every status push. Zustand's equality check (`Object.is`) always fails, so PnlStatus re-renders on every status message even when `pnl` and `circuitBreakerActive` haven't changed. Status updates arrive on the same WebSocket as bars at potentially high frequency.
**Fix applied:** Exported `selectPnl` and `selectCircuitBreakerActive` (and all other scoped selectors) from tradingStore.ts. Component agent can adopt: `const pnl = useTradingStore(selectPnl)`.

### 4. `HeaderStrip` subscribes to `s.score` and `s.status` slices
**File:** `store/tradingStore.ts` (selector helpers added)
**Issue:** `useTradingStore((s) => s.score)` and `useTradingStore((s) => s.status)` — same problem as PnlStatus. HeaderStrip re-renders on every score and status message. It uses `lastBarVersion` and `lastSignalVersion` (which are primitives — these selectors are already correct). The score/status selectors should be broken into individual field selectors.
**Fix applied:** All fine-grained score and status selectors exported from tradingStore.ts.

### 5. `SignalFeedRow` + `TapeRow` not memoized
**File:** `components/signals/SignalFeedRow.tsx` (out of scope), `components/tape/TapeRow.tsx` (out of scope)
**Issue:** Both components are hot-path renderers (up to 12 SignalFeedRows, up to 50 TapeRows). Neither uses `React.memo`. SignalFeed re-renders all 12 rows on every `lastSignalVersion` bump even if the signal list contents are identical. TapeScroll re-renders all 50 rows on every `lastTapeVersion` bump.
**Impact:** At 2 ticks/sec demo, 12+50=62 component renders per second in the list area. Each TapeRow calls `useReducedMotion()`, `formatTime()`, and computes several style objects. At 10 ticks/sec: 620 renders/sec.
**Fix deferred:** Component files are out of scope. Selector helpers are provided so the component agent can adopt `React.memo` when ready.

### 6. No unbounded arrays found
**All ring buffers** are capped (bars: 500, signals: 200, tape: 50). `SignalFeed` slices to `displaySignals.slice(0,12)`. `TapeScroll` capped by ring. `HeaderStrip` `sparkPrices` is kept via `setSparkPrices(prev => [...prev.slice(-29), newPrice])` — capped at 30. `spmBins` is a fixed 10-element array. No unbounded growth detected.

### 7. Canvas DPR recalculation
**VolumeProfile:** `syncDpr()` is called on every `redraw()` but gates rescaling on `if (el.width !== bitmapW || el.height !== bitmapH)` — so `ctx.scale(dpr, dpr)` is only applied when dimensions actually changed. The `getBoundingClientRect()` call on every rAF is unavoidable for resize detection without a separate ResizeObserver cache. Current pattern is correct.
**ZoneOverlay:** Same pattern — inline DPR check, only rescales on change. Correct.

### 8. rAF loops
**VolumeProfile + ZoneOverlay:** Both use a coalescing `scheduleRedraw()` pattern (`if (rafId !== null) return`) — only one rAF pending at a time. No double-scheduling.
**ZoneOverlay with empty bars:** Fires `scheduleRedraw()` on `lastBarVersion` change, enters `redraw()`, calls `deriveZonesFromLatestBar()` which immediately returns `[]`, then returns early. Cost: one `getState()` + one property access per tick. Negligible.
**VolumeProfile with no bars:** `bars.length === 0` check fires early, clears canvas and returns. Correct.
**LW Charts draw loop:** FootprintChart's custom series renderer runs inside LW Charts' own rAF — no separate loop. Correct.
**Background grain / scanlines / CRT sweep:** All CSS animations — zero JS CPU.
**ConfluencePulse breathing:** framer-motion manages rAF internally. `spokeBreathTransition` and `tierBadgePulseTransition` use `repeat: Infinity` — these are always running when TYPE_A is active. Framer-motion's scheduler batches rAF with other animations; no duplicated loops detected.

### 9. SVG arc path caching
`SIGNAL_BIT_CATEGORIES` is a module-level `Object.freeze()` array — computed once at module load, never recomputed. ConfluencePulse uses `Array.from({ length: 44 })` to compute arc positions inside `useMemo` with stable deps — correct.

### 10. `dispatch()` render footprint
`dispatch()` calls `get()` (no render trigger) then calls `pushBar` / `pushSignal` / `pushTape` / `setScore` / `setStatus`. Each of those calls `set()` exactly once, triggering exactly one Zustand state update per dispatch. No double-set. Correct.

---

## Fixes Applied

| File | Change | Benefit |
|------|--------|---------|
| `store/ringBuffer.ts` | `toArray()` rewritten as single-pass O(n) with pre-allocated output array | Eliminates 2 intermediate array allocations in full-buffer path; reduces GC pressure |
| `store/tradingStore.ts` | Exported 22 scoped selector functions (`selectPnl`, `selectConnected`, `selectTotalScore`, etc.) | Enables components to subscribe to exact fields; prevents re-renders from unrelated slice updates |
| `lib/animations.ts` | Added `PERF NOTE` doc comments to `prefersReducedMotion()` and `reducedMotion()` | Guides component authors away from calling `matchMedia` per render; directs to `useReducedMotion()` hook |
| `store/tradingStore.test.ts` | Added 14 new tests: scoped selector coverage (8 tests) + `toArray()` optimization (6 tests) | Full regression coverage for both changes |

---

## Remaining Concerns

### High priority (component agent action needed)
1. **`PnlStatus`**: Switch `useTradingStore((s) => s.status)` to `useTradingStore(selectPnl)` + `useTradingStore(selectCircuitBreakerActive)`.
2. **`HeaderStrip`**: Break `s.score` / `s.status` subscriptions into individual field selectors from the exported set.
3. **`SignalFeedRow`**: Wrap in `React.memo` with a shallow-equal comparator on `sig`, `justArrived`, `isSelected`.
4. **`TapeRow`**: Wrap in `React.memo` with comparator on `entry`, `marker`, `isNew`.
5. **`ConfluencePulse:583`**: Replace `prefersReducedMotion()` call with `useReducedMotion()` from 'motion/react'.

### Medium priority
6. **`TapeScroll` + `SignalFeed` array copy**: Both do `[...tape].reverse()` / `[...signals].reverse()` on every render. A stable `toReversedArray()` helper on RingBuffer would avoid the spread+reverse. Deferred — not in scope.
7. **`SignalFeedRow` age timer**: Each row runs a 1-second `setInterval` independently. With 12 rows, that is 12 intervals all firing at ~1s. A shared clock context provider would coalesce this to 1 timer. Deferred.

### Low priority / Won't fix
8. **`HeaderStrip` clock**: `setInterval(1000)` for clock — only 1 instance, acceptable.
9. **`ZoneOverlay` crosshair proxy**: Uses `subscribeCrosshairMove` as a price scale change proxy since LW Charts has no direct priceScale subscription. Fires on every mouse move — rAF coalescing guards this correctly.

---

## Deferred Optimizations

- `toReversedArray()` on RingBuffer for TapeScroll / SignalFeed — avoids spread + reverse allocation per render.
- Shared clock context for SignalFeedRow age formatters — 12 intervals → 1.
- `React.memo` for `SignalFeedRow` + `TapeRow` — highest-ROI render optimization available; blocked on component agent.
- OffscreenCanvas for VolumeProfile — would push draw work off main thread; overkill for current data volumes.

---

## Verification

```
npm run typecheck  # exit 0 — clean
npm run build      # exit 0 — 15.5s Turbopack compile, all static pages generated
npm run test store/tradingStore.test.ts store/ringBuffer.test.ts  # 26 tests pass
```

Pre-existing failure: `components/zones/ZoneList.test.tsx` — 1 test expects "VAH" but component renders "P+V". Unrelated to this audit; not introduced here.

**Manual verification target:** Run `npm run dev`, open demo at rate 3.0x for 60s, Chrome DevTools Performance tab, record 5s. Confirm no frame drops in main thread. Primary remaining risk is the unmemoized TapeRow/SignalFeedRow re-render cascade — visible as yellow "Recalculate Style" blocks if tape is scrolling rapidly.
