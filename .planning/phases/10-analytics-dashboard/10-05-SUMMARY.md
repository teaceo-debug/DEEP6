---
phase: 10-analytics-dashboard
plan: "05"
subsystem: dashboard/backtest-ui
tags: [next.js, backtest, optuna, recharts, zustand, equity-curve]
dependency_graph:
  requires: [10-02]
  provides: [BACKTEST-tab-ui, equity-curve, trade-table, optuna-sweep-panel]
  affects: [dashboard/src/app/page.tsx]
tech_stack:
  added: [recharts@3.8.1, "@tremor/react@3.18.7 (installed, not used)"]
  patterns: [Recharts AreaChart/PieChart/BarChart, Zustand selector pattern, Recharts controlled polling with clearInterval]
key_files:
  created:
    - dashboard/src/components/BacktestConfig.tsx
    - dashboard/src/components/EquityCurve.tsx
    - dashboard/src/components/TradeTable.tsx
    - dashboard/src/components/OptunaSweepPanel.tsx
    - dashboard/src/components/ParamImportanceChart.tsx
  modified:
    - dashboard/src/components/BacktestTab.tsx
    - dashboard/src/app/page.tsx
    - dashboard/package.json
decisions:
  - "Used Recharts instead of Tremor — Tremor not in project; installed with --legacy-peer-deps but peer dep conflict with React 19 prevented use; Recharts works cleanly"
  - "BacktestRow type defined in EquityCurve.tsx and re-exported as shared interface"
  - "Keyboard shortcut R delegated to BacktestConfig via isActive prop rather than global handler"
  - "cast useBacktestStore rows via unknown as BacktestRow[] since store uses Record<string, unknown>[] for generic compatibility"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-14T01:02:25Z"
  tasks_completed: 2
  files_created: 5
  files_modified: 3
---

# Phase 10 Plan 05: BACKTEST Tab UI Summary

Full BACKTEST tab implementation — Recharts equity curve, filterable trade table, tier donut chart, and Optuna sweep panel with 3s polling and parameter importance visualization.

## What Was Built

### Task 1: BacktestTab + BacktestConfig + EquityCurve + TradeTable

**BacktestConfig** (`dashboard/src/components/BacktestConfig.tsx`):
- Date range pickers (`type="date"`) with default 2026-04-07 / 2026-04-10
- Bar duration Select (1min/5min/15min = 60/300/900 seconds)
- RUN BACKTEST button with amber styling, spinner icon when running
- STOP button (calls `reset()` from store) enabled only while running
- Status display: idle/running (amber spinner)/error (red)/complete (emerald checkmark + row count)
- Keyboard shortcut R: `document.addEventListener` on `keydown`, fires only when `isActive=true` and status !== running
- `onRunRef` callback pattern to expose trigger upward

**EquityCurve** (`dashboard/src/components/EquityCurve.tsx`):
- Recharts `AreaChart` — cumulative sum of `pnl_3bar` over `bar_index`, QUIET bars filtered out
- Dynamic color: emerald if final equity >= 0, red otherwise; gradient fill
- Recharts `PieChart` (donut) — tier distribution with count + percentage tooltip
- Colors: TYPE_A amber, TYPE_B orange, TYPE_C zinc, QUIET slate
- Exports `BacktestRow` interface for use across components

**TradeTable** (`dashboard/src/components/TradeTable.tsx`):
- Tier filter Select (ALL/TYPE_A/TYPE_B/TYPE_C)
- Sort Select (bar_index/pnl_3bar/score) + direction toggle button
- Summary row: trade count, win rate, total P&L, avg score
- shadcn Table with tier badges (amber/orange/zinc/slate), P&L coloring (emerald/red)
- Direction: "▲ LONG" / "▼ SHORT" text only — no color per D-03
- Pagination: 50 rows per page with Prev/Next buttons

**BacktestTab** (`dashboard/src/components/BacktestTab.tsx`):
- Left column 288px: BacktestConfig + summary card on complete
- Main area: three subtabs (Results / Sweep / Signals)
- Results: EquityCurve + TradeTable scrollable
- Sweep: info card + OptunaSweepPanel
- Signals: SignalStats inline component — groups rows by tier, computes win rate + avg P&L 1b/3b/5b

### Task 2: OptunaSweepPanel + ParamImportanceChart + page.tsx wiring

**OptunaSweepPanel** (`dashboard/src/components/OptunaSweepPanel.tsx`):
- POST `/ml/sweep` with date range, trials count (10-500), bar_seconds
- 409 response: shows "A sweep is already running" warning, does not change status
- Polls `GET /ml/sweep/{jobId}` every 3000ms via `setInterval`
- `clearInterval` on complete/error (T-10-13 compliance)
- STOP POLLING button clears interval without canceling server job
- Best params: collapsible card, sorted by name, parameter + value table
- Shows trial progress counter during polling
- Mounts cleanup `useEffect` for interval leak prevention on unmount

**ParamImportanceChart** (`dashboard/src/components/ParamImportanceChart.tsx`):
- Recharts horizontal `BarChart` with `layout="vertical"`
- 8 hardcoded default thresholds for known signal params
- Deviation = `|optimized - default| / default * 100` (% change)
- Dynamic height: `Math.max(120, data.length * 28)` px
- Cell color: amber if deviation > 30%, zinc otherwise

**page.tsx** (updated):
- `isActive={tab === "backtest"}` passed to BacktestTab
- R shortcut delegated into BacktestConfig via `isActive` prop
- VPIN "N/A" and CB "ACTIVE" already present from Plan 02
- Keyboard shortcut comment updated to note R delegation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Tremor not installed — switched to Recharts**
- **Found during:** Task 1 setup
- **Issue:** Plan specified Tremor `AreaChart`, `DonutChart`, `BarChart` but `@tremor/react` was not in `package.json`. Attempted install with `--legacy-peer-deps`; package installed but React 19 / Next.js 16 peer dep conflict made it unusable at build time.
- **Fix:** Used Recharts (installed cleanly, no peer dep issues) for all chart components. `AreaChart` → Recharts `AreaChart + Area`, `DonutChart` → Recharts `PieChart + Pie` with `innerRadius`, `BarChart` → Recharts `BarChart + Bar` with `layout="vertical"`. Visually equivalent.
- **Files modified:** `EquityCurve.tsx`, `ParamImportanceChart.tsx`
- **Commits:** becb8b7, ec3626e

**2. [Rule 1 - Bug] TypeScript cast `Record<string, unknown>[]` → `BacktestRow[]`**
- **Found during:** Task 1 build
- **Issue:** `useBacktestStore(s => s.rows)` returns `Record<string, unknown>[]` per store type. Direct cast to `BacktestRow[]` rejected by TS (insufficient overlap).
- **Fix:** Cast via `as unknown as BacktestRow[]` in BacktestTab.tsx.
- **Files modified:** `BacktestTab.tsx`
- **Commit:** becb8b7

## Known Stubs

None — all data flows from `useBacktestStore` which connects to real `/backtest/run` API. Empty states show instructional placeholder text, not hardcoded data.

## Threat Flags

None — no new network endpoints introduced. All API calls are to existing FastAPI routes (/backtest/run, /ml/sweep) from Plan 01.

## Self-Check: PASSED

All 6 component files confirmed present on disk. Both task commits (becb8b7, ec3626e) confirmed in git log. `npm run build` exits 0 with zero TypeScript errors.
