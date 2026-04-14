---
phase: 11-deep6-trading-web-app
plan: "04"
subsystem: dashboard-replay
tags: [replay, zustand, pnl, error-handling, ui-components]
dependency_graph:
  requires: ["11-03"]
  provides: [replayStore, useReplayController, ReplayControls, SessionSelector, ReturnToLivePill, PnlStatus, ErrorBanner]
  affects: [FootprintChart, ScoreWidget, app/page.tsx]
tech_stack:
  added: []
  patterns: [zustand-plain-store, replay-loop-useEffect, feed-stale-watcher, pan-detection-lw-charts]
key_files:
  created:
    - dashboard/store/replayStore.ts
    - dashboard/store/replayStore.test.ts
    - dashboard/lib/replayClient.ts
    - dashboard/hooks/useReplayController.ts
    - dashboard/components/replay/ReplayControls.tsx
    - dashboard/components/replay/SessionSelector.tsx
    - dashboard/components/replay/ReturnToLivePill.tsx
    - dashboard/components/status/PnlStatus.tsx
    - dashboard/components/common/ErrorBanner.tsx
    - dashboard/e2e/smoke.md
  modified:
    - dashboard/components/footprint/FootprintChart.tsx
    - dashboard/components/score/ScoreWidget.tsx
    - dashboard/app/page.tsx
decisions:
  - "replayStore uses plain Zustand create() (not subscribeWithSelector) — two-argument subscribe not available; FootprintChart uses manual prevPanned tracking instead"
  - "useFeedStaleWatcher added to page.tsx by linter — polls lastTs vs wall clock every 1s in live mode; improves on inline ErrorBanner check"
  - "Pan detection uses visible time range right-edge vs newest bar ts, with 2-bar tolerance to avoid false positives on minor scroll drift"
  - "useReplayController signal projection fetches fetchReplayBar per bar advance (cached server-side by EventStore); signals_up_to rebuilt into fresh RingBuffer each tick"
metrics:
  duration_seconds: 251
  completed_date: "2026-04-14"
  tasks_completed: 2
  tasks_deferred: 1
  files_created: 10
  files_modified: 3
---

# Phase 11 Plan 04: Replay Controller + UI Components Summary

Replay mode, APP-06 lite P&L widget, error surfaces, and return-to-live pill. After this plan the operator can open `localhost:3000`, watch live data, switch to replay via `?session=YYYY-MM-DD` or the SessionSelector dropdown, step forward/back through any recorded session, and see live P&L + circuit-breaker state.

## What Was Built

### Task 1: replayStore + replayClient + useReplayController (TDD)

**replayStore** (`dashboard/store/replayStore.ts`) — Zustand store separate from tradingStore. Tracks: `mode ('live'|'replay')`, `sessionId`, `currentBarIndex`, `totalBars`, `speed ('1x'|'2x'|'5x'|'auto')`, `playing`, `error`, `userHasPanned`. All 9 plan-specified behaviors verified with unit tests.

**replayClient** (`dashboard/lib/replayClient.ts`) — Three fetch wrappers for Phase 9 endpoints: `fetchSessions()` → `GET /api/replay/sessions`, `fetchSessionRange()` → `GET /api/replay/{session}?start=N&end=M`, `fetchReplayBar()` → `GET /api/replay/{session}/{bar_index}`. Returns typed `SessionMeta[]` / `FootprintBar[]` / `SignalEvent[]`.

**useReplayController** (`dashboard/hooks/useReplayController.ts`) — Hook mounted in `app/page.tsx`. Four duties: URL→mode sync on mount, session load when mode flips to replay (preloads all bars into local ref), bar projection into tradingStore on each barIdx change, auto-advance loop (1x=1000ms, 2x=500ms, 5x=200ms, auto=rAF).

**Tests**: 9/9 pass. Typecheck clean.

### Task 2: UI Components + Wiring

**ReplayControls** (`dashboard/components/replay/ReplayControls.tsx`) — 48px footer strip per UI-SPEC. Contains SessionSelector, SkipBack/Play|Pause/SkipForward (lucide-react, 44×44 touch targets), bar counter (monospace), jump-to-bar Input (80px), speed Select (72px, 1x/2x/5x/auto), LIVE button (56px, lime active state). Replay controls group disabled (opacity-30, pointer-events-none) in live mode; LIVE button always interactive.

**SessionSelector** (`dashboard/components/replay/SessionSelector.tsx`) — Compact w-[140px] shadcn Select populated by `fetchSessions()` on mount. Silently hidden when backend unavailable. Always visible so operator can switch sessions without URL editing.

**ReturnToLivePill** (`dashboard/components/replay/ReturnToLivePill.tsx`) — Absolute top-right pill inside FootprintChart container. Visible when `mode='live' && userHasPanned`. Click calls `setPanned(false)` which triggers `scrollToRealTime()` via FootprintChart subscriber.

**PnlStatus** (`dashboard/components/status/PnlStatus.tsx`) — APP-06 lite widget appended to ScoreWidget bottom. Shows P&L in green/red/muted (monospace, +/- prefix) and circuit breaker dot (green=off, red=active) from `tradingStore.status`.

**ErrorBanner** (`dashboard/components/common/ErrorBanner.tsx`) — Top-of-page `role="alert"` banner. Three locked error strings from UI-SPEC §Copywriting: replay error → "Session not found. Select a date from history.", disconnected → "Connection lost. Reconnecting...", stale feed → "Feed stalled — no updates in 10s. Check backend."

**FootprintChart updates** — Pan detection via `subscribeVisibleTimeRangeChange`: when visible right edge lags newest bar by >2 bars, sets `userHasPanned=true`. Subscriber on `useReplayStore` calls `scrollToRealTime()` when `userHasPanned` flips false. Auto-scroll on bar update now guarded by `!userHasPanned`.

**app/page.tsx** — Mounts `useReplayController()` and `useFeedStaleWatcher()` (1s poll: sets `feedStale` when `lastTs` is >10s stale in live mode). Renders `<ErrorBanner />` between header and main region. Replaces placeholder footer with `<ReplayControls />`.

**dashboard/e2e/smoke.md** — 8-scenario operator checklist: live streaming, TYPE_A pulse, confluence score widget, connection recovery, replay step-through, P&L/circuit breaker, session-not-found error, 28px uniqueness check.

**Build**: `npm run build` exits 0. `npm run typecheck` clean. All 9 replayStore tests pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] replayStore.subscribe two-argument form not available**
- **Found during:** Task 2 — FootprintChart pan-reset subscriber
- **Issue:** `useReplayStore` uses plain `create()` without `subscribeWithSelector` middleware, so the `(selector, listener)` two-argument subscribe form doesn't compile.
- **Fix:** Replaced with a single-argument subscribe that manually tracks `prevPanned` and calls `scrollToRealTime()` on the `true→false` transition.
- **Files modified:** `dashboard/components/footprint/FootprintChart.tsx`
- **Commit:** d0498cb

**2. [Rule 2 - Missing functionality] Feed-stale detection not wired**
- **Found during:** Task 2 — ErrorBanner references `status.feedStale` but the plan only described checking `status.lastTs` inline in the component; the linter added a proper `useFeedStaleWatcher` hook in `page.tsx` that polls every 1s and updates `feedStale` in the store — necessary for the ErrorBanner to work correctly.
- **Fix:** `useFeedStaleWatcher` in `page.tsx` — polls `lastTs` vs `Date.now()/1000` every second in live mode; updates `tradingStore.status.feedStale`.
- **Files modified:** `dashboard/app/page.tsx`
- **Commit:** d0498cb

## Task 3 Status — DEFERRED TO OPERATOR

Task 3 (`type="checkpoint:operator"`) is a manual smoke-test gate. The operator must run all 8 scenarios in `dashboard/e2e/smoke.md` and return APPROVED before Phase 11 is marked complete. Automated pre-conditions required before the operator gate:

```bash
cd /Users/teaceo/DEEP6/dashboard && npm run typecheck && npm run test && npm run build
```

All three currently pass.

## Known Stubs

None — all components read from live store state or replay API data. No hardcoded placeholder values flow to the UI.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. All new code is frontend-only, reading from existing Phase 9 FastAPI endpoints.

## Self-Check: PASSED

All 10 created files confirmed present on disk. Both task commits (`6d39c3e`, `d0498cb`) confirmed in git log. `npm run test` 9/9 pass. `npm run typecheck` clean. `npm run build` exits 0.
