# Phase 1: Data Pipeline + Architecture Foundation - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish the Python data pipeline: connect to Rithmic via async-rithmic, receive real-time L2 DOM (40+ levels) and tick data for NQ, build correct FootprintBars at bar close, verify the aggressor field is present, set up session state persistence, handle reconnection safely, and create the Python package structure. This is pure infrastructure — no signals are computed in this phase.

</domain>

<decisions>
## Implementation Decisions

### Rithmic Connection
- **D-01:** User has active Rithmic broker account with API/plugin mode confirmed enabled. No broker setup needed.
- **D-02:** Connect via async-rithmic 1.5.9 using event callbacks (`client.on_order_book`, `client.on_tick`).
- **D-03:** Aggressor field verification is the CRITICAL GATE — must confirm TransactionType.BUY/SELL is present in on_trade callback before writing any footprint accumulator code. If UNKNOWN, escalate immediately.

### Bar Configuration
- **D-04:** Multiple timeframes — primary 1-minute bars + secondary 5-minute bars for higher-timeframe context. BarBuilder manages both independently.
- **D-05:** Each timeframe gets its own FootprintBar accumulator. 1-min fires every 60s at bar boundary, 5-min fires every 300s.

### Session Definition
- **D-06:** RTH only (9:30 AM - 4:00 PM Eastern). IB (Initial Balance) = first 60 minutes from 9:30.
- **D-07:** Session state resets at 9:30 ET each day. VWAP, CVD, IB anchors all start fresh.
- **D-08:** DOM data outside RTH is still received but not processed into FootprintBars or session state.

### Validation Strategy
- **D-09:** Primary validation against TradingView — compare Python footprint output against Bookmap Liquidity Mapper Pine Script indicators running on same NQ 1-min bars.
- **D-10:** Cross-reference methodology: export Python FootprintBar data (bid/ask vol per level) to CSV, compare against TV indicator values at matching timestamps. Acceptable tolerance: <2% divergence per level.
- **D-11:** No ATAS/Quantower/Bookmap available. TradingView + existing Pine Script is the validation reference.

### Architecture
- **D-12:** Python package structure: `deep6/{data, engines, signals, scoring, execution, ml, api}` — created in this phase with `__init__.py` stubs.
- **D-13:** asyncio event loop with uvloop. DOM callbacks update pre-allocated arrays in-place (zero allocation per callback).
- **D-14:** Process boundary established: main asyncio process for I/O + signal computation. Kronos subprocess deferred to Phase 6.
- **D-15:** Session state persisted to SQLite via aiosqlite — survives process restart. Schema: session_id, key, value, timestamp.
- **D-16:** GC disabled during RTH (9:30-16:00 ET) via `gc.disable()`. Manual `gc.collect()` at session open and close only.

### Reconnection Safety
- **D-17:** On disconnect: enter FROZEN state immediately. No new bar processing until reconnection + position reconciliation.
- **D-18:** Sequential plant connection on reconnect (async-rithmic issue #49 workaround — ForcedLogout bug).
- **D-19:** Log all disconnect/reconnect events with timestamps for post-session review.

### Claude's Discretion
- Exact DOM state array sizes and data structures
- SQLite schema details for session persistence
- Logging framework choice (structlog vs standard logging)
- Test framework setup (pytest)
- Which secondary timeframe (5-min recommended, but 3-min or 15-min acceptable)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research
- `.planning/research/STACK.md` — async-rithmic API patterns, connection setup, callback shapes
- `.planning/research/FEATURES.md` — FootprintBar data structure, BarBuilder pattern, tick classification
- `.planning/research/ARCHITECTURE.md` — asyncio event loop design, process boundaries, state management
- `.planning/research/PITFALLS.md` — GC pressure, reconnection bugs, tick classification accuracy risk

### v1 Reference (archived)
- `.planning-v1-nt8/codebase/ARCHITECTURE.md` — Engine data flow from v1 (conceptual reference for Python equivalent)
- `.planning-v1-nt8/research/PYTHON-L2-DOM-OPTIONS.md` — async-rithmic capabilities research

### External
- Pine Script: Bookmap Liquidity Mapper (in user's TradingView) — validation reference for footprint output

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- v1 C# engine logic in `AddOns/DEEP6.*.cs` — conceptual reference for Python ports (not direct code reuse)
- Pine Script Bookmap Liquidity Mapper — validation reference and signal logic reference

### Established Patterns
- None yet — this is greenfield Python. Phase 1 establishes the patterns all future phases follow.

### Integration Points
- `deep6/data/` module created here is consumed by ALL future phases (engines, scoring, execution)
- FootprintBar is the core data type — its correctness gates the entire project
- BarBuilder's on_bar_close callback is the equivalent of NT8's OnBarUpdate — all signal computation attaches here

</code_context>

<specifics>
## Specific Ideas

- Research confirmed FootprintBar should use `defaultdict[int, FootprintLevel]` keyed by price-in-ticks, converting to sorted numpy arrays after bar close
- async-rithmic uses `client.on_order_book += callback` pattern — DOM callback must do O(1) work only
- BarBuilder is an asyncio coroutine that sleeps to bar boundary, not a framework event
- Validation against TradingView Pine Script is less precise than ATAS (Pine uses intrabar sampling, not true footprint) — expect ~5-10% divergence as acceptable rather than 2%

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-data-pipeline-architecture-foundation*
*Context gathered: 2026-04-13*
