# Phase 11: DEEP6 Trading Web App - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

View-only monitoring surface for the DEEP6 trading system. The operator uses this frontend to **see trades happening** — live footprint chart, live signal feed, confluence score, zone overlays, Kronos bias, GEX regime, and session replay. Execution, authentication, mobile push, and full portfolio analytics are deferred to a follow-up phase.

Frontend connects to the Phase 9 FastAPI backend via WebSocket on localhost. No TradingView dependency — all chart and signal rendering happens in the DEEP6 app.

</domain>

<decisions>
## Implementation Decisions

### Scope Narrowing (first pass — view-only)
- **D-01:** IN — APP-01 custom footprint chart with zone overlays (LVN, HVN, GEX, absorption)
- **D-02:** IN — APP-03 real-time WebSocket push from Phase 9 FastAPI
- **D-03:** IN — APP-04 session replay (bar-by-bar step through historical sessions)
- **D-04:** IN — APP-08 zero TradingView dependency (all rendering in DEEP6 app)
- **D-05:** IN (lite) — APP-06 minimal status widget: live P&L running total + circuit breaker state. No historical performance view, no drawdown chart, no win-rate-by-tier.
- **D-06:** DEFERRED — APP-02 execution panel (view-only first pass, no order submission)
- **D-07:** DEFERRED — APP-05 mobile push notifications
- **D-08:** DEFERRED — APP-07 authentication + multi-device (localhost trusted-network only)

### Backend Integration
- **D-09:** Next.js frontend connects directly to Phase 9 FastAPI WebSocket on `localhost` — no auth, no reverse proxy, trusted-network-only assumption.
- **D-10:** Single WebSocket connection for all real-time streams (signals, bars, P&L, connection status). Backend multiplexes message types.

### Footprint Data Flow
- **D-11:** Backend pushes complete `FootprintBar` objects on bar close — client does not rebuild bars from raw ticks. Bandwidth tradeoff accepted (~1-2 KB/bar).
- **D-12:** Client-side ring buffer holds last N bars (N TBD by planner based on viewport + scroll buffer; target ~500 bars for performance).

### Replay Data Source
- **D-13:** Session replay reads from Phase 9 EventStore (aiosqlite `signal_events` + `trade_events` + bar history) via a dedicated FastAPI replay endpoint. Reuses existing infrastructure — no separate replay service.
- **D-14:** Replay controls: Previous/Next bar, jump-to-bar, playback speed (1x/2x/5x/auto). Session selector left open for planner.

### Deployment
- **D-15:** Local `npm run dev` on `localhost:3000` alongside the Python engine. Manual start by operator. No Docker, no build-and-serve for this phase.

### Claude's Discretion
- Footprint custom series internal implementation (exact Canvas layering, offscreen canvas, requestAnimationFrame batching) — planner/executor decide per TapeFlow reference pattern.
- WebSocket message schema and reconnection backoff strategy.
- State management library choice (Zustand, Jotai, or native React) — picked during planning.
- Exact ring-buffer size and retention policy for T&S tape and signal feed.
- FastAPI endpoint shape for the replay query (pagination, event filters).

</decisions>

<specifics>
## Specific Ideas

- **Reference image** provided by user: dark terminal aesthetic with neon green/red/yellow, large confluence score on the right, footprint cells with bid×ask per row, signal pill badges.
- **TapeFlow** (https://github.com/ianfigueroa/TapeFlow) is the **primary architectural reference** — Canvas overlay for footprint cells, ring-buffer data pipeline, LW Charts for price axis. Executor must study TapeFlow's Canvas layer and ring-buffer pattern before building the custom series.
- Design contract locked in `11-UI-SPEC.md` — do not re-derive colors, typography, spacing, or layout during planning.
- TYPE_A signals pulse briefly on arrival (1s glow) in addition to lime color. Signal feed is 20 entries visible, infinite-scroll history.
- Footprint chart shows 30 price rows, auto-centers on current price with pan-lock toggle.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design Contract
- `.planning/phases/11-deep6-trading-web-app/11-UI-SPEC.md` — locked design system (colors, typography, spacing, component inventory, footprint series contract, Canvas overlay contract, TYPE_A pulse animation, lucide-react icons, shadcn init config)

### Requirements
- `.planning/REQUIREMENTS.md` §APP-01..APP-08 — original Phase 11 scope (note: view-only narrowing applies per D-01..D-08 above)
- `.planning/ROADMAP.md` Phase 11 section — phase goal + success criteria (apply view-only narrowing)

### Backend Integration Surface
- `.planning/phases/09-ml-backend/09-01-PLAN.md` — FastAPI app factory + EventStore (aiosqlite schema for signal_events + trade_events — replay endpoint reads from here)
- `deep6/ml/` (existing code) — EventStore and FastAPI app where the Phase 11 WebSocket and replay endpoint will be added

### Architectural References
- `CLAUDE.md` — project tech stack, Next.js 15 + Tailwind + shadcn/ui + Tremor + Lightweight Charts v5.1 + WebSocket commitments
- External: https://github.com/ianfigueroa/TapeFlow — Canvas overlay pattern, ring-buffer data flow (READ BEFORE IMPLEMENTING)
- External: https://tradingview.github.io/lightweight-charts/docs/plugins/custom_series — LW Charts v5.1 custom series plugin API
- External: https://github.com/tradingview/lightweight-charts — LW Charts source reference

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 9 FastAPI app factory + EventStore** (aiosqlite `signal_events`, `trade_events`) — Phase 11 adds a WebSocket endpoint and a replay query endpoint onto this existing app.
- **`FootprintBar` Python model** (established Phase 1+) — the on-the-wire payload will mirror this; frontend TypeScript interface derives from it.
- **Signal type enums + narrative strings** (Phase 2-5 engines) — reused in WebSocket payloads; frontend renders them directly.

### Integration Points
- FastAPI WebSocket route → Next.js `useEffect` subscriber → Zustand (or equivalent) store → Canvas renderer.
- FastAPI replay endpoint → Next.js replay-mode controller → same Canvas renderer with time-indexed data.
- No existing Next.js codebase yet — this phase scaffolds `web/` (or `frontend/`) subdirectory. Planner picks exact location.

### Patterns to Establish (no prior precedent in repo)
- TypeScript types shared between Python payload (via Pydantic schema dump → TS codegen, or hand-kept) — planner decides.
- WebSocket auto-reconnect strategy.
- Client-side state management choice.

</code_context>

<deferred>
## Deferred Ideas

Captured here so they aren't lost — belong in a future Phase 12+ or expansion of Phase 11:

- **APP-02 execution panel** — one-click TYPE_A/B confirm + auto-execute toggle, order status, fill alerts
- **APP-05 mobile push via service worker** — TYPE_A alerts to phone < 5s
- **APP-07 authentication + multi-device** — operator monitors from laptop and phone simultaneously; requires auth layer (Neon Auth, NextAuth, or similar)
- **Full APP-06 analytics** — win-rate-by-tier, drawdown chart, daily/weekly/monthly P&L breakdown, ML parameter evolution chart
- **Tailscale / reverse-proxy access** — read-only peek from phone without full auth
- **Docker packaging** — one-command deploy alongside Python engine

</deferred>

---

*Phase: 11-deep6-trading-web-app*
*Context gathered: 2026-04-13 via interactive discuss-phase*
