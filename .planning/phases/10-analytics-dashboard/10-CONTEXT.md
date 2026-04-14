# Phase 10: Analytics Dashboard - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Next.js 15 dashboard with TWO primary tabs: LIVE (real-time trading) and BACKTEST (historical analysis). Real-time WebSocket from FastAPI delivers signals, bar data, positions, P&L. Backtest tab runs Optuna sweeps and displays results. Footprint chart via Lightweight Charts v5.1 custom series. Session replay. No TradingView dependency — this IS the trading interface.

</domain>

<decisions>
## Implementation Decisions

### Stack
- **D-01:** Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui components
- **D-02:** Lightweight Charts v5.1 for OHLC + custom series plugin for footprint rendering
- **D-03:** Tremor v3 for dashboard KPI cards and time-series charts
- **D-04:** WebSocket client via native WebSocket API (no Socket.io)
- **D-05:** State management via Zustand (lightweight, no Redux)

### Tab Structure
- **D-06:** Two primary tabs at top: LIVE | BACKTEST
- **D-07:** LIVE tab contains: Footprint chart, Signal panel, Position tracker, P&L, Regime display, GEX levels overlay
- **D-08:** BACKTEST tab contains: Date range picker, Run backtest button, Results table (tier breakdown), Equity curve, Sweep launcher, Trial results table

### LIVE Tab Layout
- **D-09:** Top bar: Connection status, regime (POSITIVE/NEGATIVE gamma), VPIN toxicity indicator, circuit breaker state
- **D-10:** Main area: Footprint chart (70% height) with GEX levels, absorption zones, LVN/HVN overlaid
- **D-11:** Right panel: Signal feed (live TYPE_A/B/C alerts with category breakdown), Kronos bias gauge
- **D-12:** Bottom panel: Open positions table, today's closed trades, daily P&L

### BACKTEST Tab Layout
- **D-13:** Left column: Config form (date range, thresholds, asset), run/stop controls
- **D-14:** Main area: Equity curve + trade markers + tier distribution pie chart
- **D-15:** Bottom: Full trade table with filters (tier, narrative, P&L range)
- **D-16:** Optuna sweep subtab: trials table, best params display, param importance chart

### Real-Time Updates
- **D-17:** WebSocket endpoint /ws at FastAPI — pushes bar close events, signal events, position events, P&L updates within 200ms of bar close
- **D-18:** Reconnect logic: exponential backoff, display stale data with warning when disconnected

### Backend Changes (FastAPI)
- **D-19:** Add /ws WebSocket endpoint to FastAPI app
- **D-20:** Add /backtest/run endpoint (triggers async backtest job)
- **D-21:** Add /backtest/results/{job_id} endpoint
- **D-22:** Broadcast signal/trade events to all connected WS clients

### Authentication
- **D-23:** Simple bearer token auth (read from localStorage). Token set by operator on first launch.
- **D-24:** No multi-user for v1 — single-operator system.

### Footprint Rendering
- **D-25:** Custom Lightweight Charts series plugin renders bid/ask volume as colored cells at each price level
- **D-26:** Overlays: absorption zones (red), exhaustion zones (orange), LVN (gray bands), HVN (blue bands), GEX levels (dashed lines)

### Claude's Discretion
- Exact shadcn/ui components to use
- Tremor chart configurations
- Color palette (suggest dark theme with amber accents for signals)

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §DASH — DASH-01..07
- `deep6/api/app.py` — FastAPI app to extend with WebSocket
- `deep6/api/store.py` — EventStore for historical data
- `scripts/backtest_signals.py` — Backtest runner to wrap in API
- `scripts/sweep_thresholds.py` — Optuna sweep to trigger from dashboard
- `deep6/execution/paper_trader.py` — Source of live trade events

</canonical_refs>

<code_context>
## Existing Code Insights
- FastAPI app exists with event ingestion endpoints
- EventStore has signal_events + trade_events tables
- PositionEvent dataclass is JSON-serializable
- Polygon API key live for GEX overlay data
- Databento API key live for backtest data

</code_context>

<specifics>
## Specific Ideas
- Dark theme default (institutional feel)
- Amber/orange for TYPE_A alerts (high urgency)
- Green/red only for P&L, never for direction (direction is long/short text)
- Keyboard shortcuts: L for LIVE tab, B for BACKTEST, R for run
</specifics>

<deferred>
## Deferred Ideas
- Mobile responsive — deferred to Phase 11
- Push notifications — deferred to Phase 11

</deferred>

---
*Phase: 10-analytics-dashboard*
*Context gathered: 2026-04-14*
