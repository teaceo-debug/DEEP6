---
phase: 10-analytics-dashboard
plan: "02"
subsystem: ui
tags: [next.js, react, zustand, websocket, tailwind, shadcn, typescript, dashboard]

requires:
  - phase: 10-01
    provides: FastAPI /ws WebSocket endpoint + /backtest/run + /backtest/results/{job_id} backend

provides:
  - Next.js 16.2.3 App Router project in dashboard/ with TypeScript + Tailwind + shadcn/ui
  - WsClient class with native WebSocket, exponential backoff reconnect (1s→30s), token auth
  - localStorage token helpers (getToken/setToken/clearToken)
  - useLiveStore — 200-event ring buffer for signals + trades, regime + dailyPnl derived state
  - useBacktestStore — runJob/pollJob with auto-clearing interval on terminal states
  - WsProvider — client component that connects WS on mount, routes messages to stores
  - Two-tab shell page (LIVE | BACKTEST) with top bar + keyboard shortcuts (L/B)
affects: [10-03, 10-04, 10-05]

tech-stack:
  added:
    - next.js 16.2.3 (App Router)
    - react 19 (canary via Next.js)
    - zustand 5.x
    - lightweight-charts 5.1
    - lucide-react
    - shadcn/ui (base-ui based — New York style)
    - tailwindcss 4.x
    - typescript 5.x
  patterns:
    - Zustand stores with ring-buffer pattern (max 200, newest-first prepend + slice)
    - WsClient singleton exported from lib/ws.ts — imported by WsProvider, not components directly
    - Client components in providers/ directory; server components in app/
    - darkMode via html className="dark" (class strategy)

key-files:
  created:
    - dashboard/src/lib/ws.ts
    - dashboard/src/lib/auth.ts
    - dashboard/src/store/live.ts
    - dashboard/src/store/backtest.ts
    - dashboard/src/providers/ws-provider.tsx
    - dashboard/src/app/page.tsx
    - dashboard/src/components/LiveTab.tsx
    - dashboard/src/components/BacktestTab.tsx
  modified:
    - dashboard/src/app/layout.tsx
    - dashboard/src/app/globals.css

key-decisions:
  - "Used Next.js 16.2.3 (not 15 as planned) — create-next-app installed latest; API surface identical for App Router"
  - "shadcn/ui uses @base-ui/react under the hood in v16 era — Tabs API differs from Radix (value/onValueChange, data-active, TabsPrimitive.Panel); wrote page.tsx accordingly"
  - "Removed inner .git created by create-next-app so dashboard/ commits as regular files in the worktree"
  - "WsClient uses encodeURIComponent on token to handle special chars in URL query param"
  - "pollJob interval stored in closure; cleared on complete/error/exception per T-10-07"

patterns-established:
  - "Pattern 1: Zustand ring buffer — [newEvent, ...prev].slice(0, MAX) for newest-first 200-cap"
  - "Pattern 2: WsProvider as leaf client component wrapping children in layout.tsx — safe with RSC"
  - "Pattern 3: Status dot + regime badge in persistent top bar, not inside tab content"

requirements-completed: [DASH-01]

duration: 21min
completed: 2026-04-14
---

# Phase 10 Plan 02: Analytics Dashboard Scaffold Summary

**Next.js 16.2.3 dashboard scaffold with dark theme, Zustand live/backtest stores, native WebSocket client with exponential backoff, and two-tab LIVE/BACKTEST shell wired to FastAPI /ws**

## Performance

- **Duration:** 21 min
- **Started:** 2026-04-14T00:34:58Z
- **Completed:** 2026-04-14T00:55:57Z
- **Tasks:** 2
- **Files modified:** 14 (created + modified)

## Accomplishments
- Full Next.js 16.2.3 App Router project bootstrapped in `dashboard/` with TypeScript, Tailwind v4, shadcn/ui (base-ui)
- WsClient with native WebSocket, 1s→30s exponential backoff, token via `?token=` query param
- Zustand `useLiveStore` ring-buffers up to 200 signal/trade events (newest-first), derives `regime` and `dailyPnl`
- Zustand `useBacktestStore` with `runJob`/`pollJob` using safe `clearInterval` on complete/error
- Two-tab shell page with persistent top bar (status dot, regime badge, P&L, CB state) and L/B keyboard shortcuts

## Task Commits

1. **Task 1: Bootstrap Next.js 15 app with all deps, Tailwind dark theme, shadcn/ui init** - `c7242d3` (feat)
2. **Task 2: WebSocket client, auth helpers, Zustand stores, two-tab shell page** - `8dcb61f` (feat)

## Files Created/Modified
- `dashboard/src/lib/ws.ts` — WsClient class: native WebSocket, exponential backoff, token auth, disconnect/send
- `dashboard/src/lib/auth.ts` — getToken/setToken/clearToken via localStorage
- `dashboard/src/store/live.ts` — useLiveStore: signal/trade ring buffer (200), regime + dailyPnl derived
- `dashboard/src/store/backtest.ts` — useBacktestStore: runJob/pollJob with auto-clearing interval
- `dashboard/src/providers/ws-provider.tsx` — "use client" provider; connects WS, prompts token, routes messages
- `dashboard/src/app/page.tsx` — DashboardPage: two-tab shell, top bar, L/B keyboard shortcuts
- `dashboard/src/app/layout.tsx` — Root layout with `dark` class, zinc-950 bg, font-mono, WsProvider wrapper
- `dashboard/src/app/globals.css` — Dark background CSS variable set to deep zinc-950 equivalent
- `dashboard/src/components/LiveTab.tsx` — Placeholder (Plan 03 implements)
- `dashboard/src/components/BacktestTab.tsx` — Placeholder (Plan 05 implements)
- `dashboard/src/components/ui/{tabs,badge,card,table,select,button}.tsx` — shadcn/ui components

## Decisions Made
- **Next.js 16.2.3 installed** — `create-next-app@latest` pulled 16.2.3, not 15. App Router API identical for our usage; no change required.
- **shadcn/ui uses @base-ui/react** — In this version, `Tabs` uses `@base-ui/react/tabs` with `value`/`onValueChange`/`data-active` (not Radix `data-[state=active]`). Read component source before writing page.tsx.
- **Removed embedded .git** — `create-next-app` initializes a `.git` inside `dashboard/`; removed so the directory can be committed as regular files in the worktree.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed embedded .git from dashboard/**
- **Found during:** Task 1 (commit attempt)
- **Issue:** `create-next-app --no-git` still created a `.git` in the dashboard directory, making it an embedded git repo that can't be committed normally
- **Fix:** `rm -rf dashboard/.git` then re-staged all files
- **Files modified:** n/a (structural fix)
- **Verification:** `git add dashboard/` succeeded without submodule warning
- **Committed in:** c7242d3 (Task 1 commit)

**2. [Rule 1 - Bug] shadcn/ui @base-ui Tabs API differs from plan spec**
- **Found during:** Task 2 (page.tsx authoring)
- **Issue:** Plan spec used Radix-based `TabsContent` + `value` on trigger; installed version uses `@base-ui/react/tabs` with `TabsPrimitive.Panel` and `data-active` styling
- **Fix:** Read generated `src/components/ui/tabs.tsx` and base-ui type definitions before writing page.tsx; used correct `value`/`onValueChange` on Root and `value` on Tab components
- **Files modified:** dashboard/src/app/page.tsx
- **Verification:** `npm run build` exits 0 with zero TypeScript errors
- **Committed in:** 8dcb61f (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correctness. No scope creep. Build passes clean.

## Issues Encountered
- `create-next-app@latest` installs Next.js 16.2.3 (not 15); this is fine — the App Router API we need is identical.
- AGENTS.md in the dashboard directory warns that Next.js has breaking changes; reviewing local docs confirmed App Router layout/page conventions are the same but the shadcn/ui Tabs component uses base-ui primitives.

## User Setup Required
None — no external service configuration required for scaffold. WebSocket token defaults to `deep6-dev` (matches server default).

## Known Stubs
- `dashboard/src/components/LiveTab.tsx` — intentional placeholder; Plan 03 implements footprint chart + signal panel
- `dashboard/src/components/BacktestTab.tsx` — intentional placeholder; Plan 05 implements backtest results UI

## Next Phase Readiness
- Plan 03 (live tab: footprint chart + signal panel) can import `useLiveStore` from `@/store/live`
- Plan 05 (backtest tab) can import `useBacktestStore` from `@/store/backtest`
- WsProvider is already wired in layout; Plans 03/05 just need to render into the placeholder tab components
- `wsClient.send()` available for any client→server messages (e.g., ping keepalive)

---
*Phase: 10-analytics-dashboard*
*Completed: 2026-04-14*
