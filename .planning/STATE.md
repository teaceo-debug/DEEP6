---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
status: executing
stopped_at: Completed 11.2-01-PLAN.md
last_updated: "2026-04-14T12:15:19Z"
last_activity: 2026-04-14
progress:
  total_phases: 16
  completed_phases: 11
  total_plans: 52
  completed_plans: 45
  percent: 87
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-13)

**Core value:** Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades via direct Rithmic orders — all in Python, running on macOS.
**Current focus:** Phase 10 — analytics-dashboard

## Current Position

Phase: 11
Plan: Not started
Status: Ready to execute
Last activity: 2026-04-14

Progress: [░░░░░░░░░░] 2%

## Performance Metrics

**Velocity:**

- Total plans completed: 27
- Average duration: — min
- Total execution time: — hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 (01-01) | 1 | 5 min | 5 min |
| 02 | 3 | - | - |
| 03 | 4 | - | - |
| 05 | 2 | - | - |
| 07 | 3 | - | - |
| 04 | 4 | - | - |
| 08 | 2 | - | - |
| 09 | 4 | - | - |
| 10 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01-data-pipeline-architecture-foundation P02 | 229 | 2 tasks | 4 files |
| Phase 01 P03 | 25 | 2 tasks | 4 files |
| Phase 12 P01 | 12 | 3 tasks | 8 files |
| Phase 12 P02 | 12 | 2 tasks | 4 files |
| Phase 12 P03 | 18 | 3 tasks | 7 files |
| Phase 12 P04 | 45 | 3 tasks | 7 files |
| Phase 12 P05 | 35 | 3 tasks | 8 files |
| Phase 11 P01 | 25 | 3 tasks | 9 files |
| Phase 11 P02 | 25 | 2 tasks | 14 files |
| Phase 11 P03 | 45m | 3 tasks | 23 files |
| Phase 11 P03 | 40 | 3 tasks | 23 files |
| Phase 11 P04 | 251 | 2 tasks | 13 files |
| Phase 15 P01 | 45 | 3 tasks | 8 files |
| Phase 15 P02 | 15 | 2 tasks | 3 files |
| Phase 11.2 P01 | 3 | 3 tasks | 9 files |

## Quick Tasks Completed

| ID | Date | Description | Files |
|----|------|-------------|-------|
| 260413-s1d | 2026-04-14 | Fix databento_feed.py attribute bugs (total_vol, tick_size kwarg, open_time/close_time, CVD chain) | deep6/data/databento_feed.py |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Architecture pivot confirmed — Python + async-rithmic replaces NT8/C#
- [Phase 1]: DATA-02 (aggressor field verification) is the critical gate — must resolve before footprint accumulator is written
- [Phase 6]: Kronos + TVMCP can begin after Phase 1 (only needs OHLCV), parallelizable with Phases 2-5
- [01-01]: setuptools build-backend corrected to setuptools.build_meta (legacy backend not available)
- [01-01]: DOMState uses array.array 'd' not numpy for hot-path (numpy reserved for bar-close vectorized ops)
- [01-01]: Aggressor gate is module-level state — safe under single asyncio event loop (T-01-02)
- [01-01]: SignalFlags bit positions 0-43 are STABLE — do not reorder (serialization safety)
- [Phase 01-data-pipeline-architecture-foundation]: BarHistory is a factory function (not class) returning deque(maxlen=200) to avoid mutable default issues
- [Phase 01-data-pipeline-architecture-foundation]: price_to_tick uses round() not int() for floating-point safety at NQ tick boundaries
- [Phase 01-data-pipeline-architecture-foundation]: RTH gate uses zoneinfo America/New_York for DST-correct Eastern time (not hardcoded offset)
- [Phase 01]: aiosqlite with one connection per operation (no pool) — safe for single event loop, avoids connection lifetime complexity
- [Phase 01]: FreezeGuard._state is private string; is_frozen returns True for both FROZEN and RECONNECTING states — no partial bar processing during any part of reconnect cycle
- [Phase 01]: SharedState.build() is the single assembly entry point; persistence.initialize() called separately in async context before first use
- [Phase 12]: VPIN modulates FUSED score only, never stacks with IB multiplier; exact aggressor split replaces BVC per DATA-02
- [Phase 12]: DELT_TAIL (bit 22) rewired in-place to use true intrabar extreme — no new bit
- [Phase 12]: delta_quality_scalar delivered via non-breaking process_with_quality() sibling method
- [Phase 12]: TRAP_SHOT at bit 44 — multi-bar trapped-trader reversal; DELT_SLINGSHOT bit 28 untouched (different pattern)
- [Phase 12]: SlingshotDetector uses 2.0σ z-score over 200-bar session window; resets at RTH open to prevent overnight drift
- [Phase 12]: SetupTracker MANAGING→COOLDOWN is explicit-close-only; reference footgun fixed, 30-bar failsafe added as wedge guard
- [Phase 12]: Setup IDs prefixed by timeframe (1m-/5m-) enable cross-TF close_trade routing on SharedState
- [Phase 11]: INSERT OR REPLACE on UNIQUE(session_id, bar_index) makes insert_bar idempotent
- [Phase 11]: TypeAdapter(LiveMessage) validates test-broadcast payload before fan-out (T-11-01)
- [Phase 11]: WSManager broadcast snapshots active set under lock, sends without lock
- [Phase 11]: Tailwind v4 uses @theme inline CSS directives — no tailwind.config.ts; design tokens mapped via --color-* in @theme block
- [Phase 11]: Zustand v5 mutable RingBuffer + version counter (lastBarVersion) pattern: Canvas reads getState().bars directly, never via reactive selector
- [Phase 11]: ZoneOverlay uses priceScale getVisibleRange not getVisiblePriceRange (corrected from plan pseudocode)
- [Phase 11]: Plan 11-03: LW Charts v5.1 FootprintSeries + FootprintRenderer + Zone overlay canvas + WS reconnect hook — view-only dashboard streams live
- [Phase 11]: Plan 11-03: RingBuffer direction clarified (oldest→newest) and auto-fixed across HeaderStrip/ZoneOverlay/useFootprintData/FootprintChart
- [Phase 11]: replayStore uses plain Zustand create(); FootprintChart uses manual prevPanned tracking for pan-reset subscription
- [Phase 11]: useFeedStaleWatcher polls lastTs every 1s in live mode to drive feedStale flag in tradingStore
- [Phase 11.1]: shrink-0 on ScoreWidget + overflow-hidden on 3-column container prevents flex collapse and child reflow escapes (D-01, D-02)
- [Phase 11.1]: html { font-size: 13px !important } + inline style={{ fontSize: '13px' }} on HeaderStrip as cascade-proof override of Tailwind v4 preflight (D-03)
- [Phase 11.1]: FootprintRenderer ctx.font already scales by vpr at all sites; DPR invariant comment added to draw() (D-04)
- [Phase 15]: Phase 15-01: Unified Level primitive (uid: int stable mutation key via uuid4) with 17 LevelKind variants
- [Phase 15]: Phase 15-01: LevelBus = in-place rename of ZoneRegistry (D-09); ZoneRegistry alias preserved; get_all_active() now returns list[Level]
- [Phase 15]: Phase 15-01: RULES.md canonical table has 38 CR-IDs (47 source rules deduped with lineage audit)
- [Phase 15]: 15-02: narrative signals with strength>=0.4 persisted as Levels via LevelFactory at VPContextEngine.process step 2.5 (D-06, D-31); ABSORB/EXHAUST use full-wick geometry (D-07)
- [Phase 15]: 15-02: cross-session decay — narrative Levels with score>=60 carry over with score*0.70, touches halved, state reset to CREATED; below-60 GC'd at session reset (D-08)
- [Phase 11.2]: 11.2-01: Tailwind v4 CSS-first — color extensions via @theme inline in globals.css; bg-void, text-lime, border-rule work as Tailwind utilities
- [Phase 11.2]: 11.2-01: motion resolved to ^11.18.2; MIT confirmed; npm audit 0 high/critical (T-11.2-01 mitigated)
- [Phase 11.2]: 11.2-01: CRTSweep checks prefers-reduced-motion via window.matchMedia at render time to avoid flash-of-animation
- [Phase 11.2]: 11.2-01: ScoreWidget removed from page.tsx; data-slot=confluence-pulse placeholder for Plan 11.2-02

### Roadmap Evolution

- Phase 12 added: Integrate borrowed orderflow patterns: VPIN confidence modifier, Delta Slingshot, Delta At Extreme, setup state machine, per-regime walk-forward tracker
- Phase 13 added: Backtest Engine Core — Clock + MBO Adapter + DuckDB Store (retroactive roadmap entry for orphan scaffolding from 2026-04-14)
- Phase 14 added: Databento Live Feed (retroactive roadmap entry for orphan context from 2026-04-14)
- Phase 15 added: LevelBus + Confluence Rules + Trade Decision FSM — unifies VP/narrative/GEX levels into single bus, encodes ~47 research-derived confluence rules, replaces bar-close execution with 7-state trade-decision FSM. Basis: .planning/research/pine/ (12,500 words, 35 papers)
- Phase 11.1 inserted after Phase 11: Phase 11 layout and visual polish (URGENT) — ScoreWidget sidebar collapse, SignalFeed overlay bleeding into chart, header-strip font-size cascade, footprint cell DPR scaling

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: async-rithmic aggressor field (DATA-02) is unverified hands-on — async-rithmic docs partially 403; must inspect live on_trade callback before footprint code is written
- [Phase 1]: async-rithmic Issue #49 (ForcedLogout reconnection loop) is open as of March 2026 — pin to v1.5.9, connect plants sequentially with 500ms delay
- [Phase 6]: Kronos CPU/MPS inference latency on M2 Mac is extrapolated, not measured — benchmark must run before inference cadence is finalized

## Session Continuity

Last session: 2026-04-14T12:15:19Z
Stopped at: Completed 11.2-01-PLAN.md
Resume file: None
