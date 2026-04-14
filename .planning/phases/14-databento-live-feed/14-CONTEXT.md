# Phase 14: Databento Live Feed - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a live Databento MBO feed adapter that replaces Rithmic market data in the live pipeline. Databento Live API streams the same MBO (Market-by-Order) schema used in backtesting — eliminating data drift between backtest and live. Rithmic continues to handle order execution only.

</domain>

<decisions>
## Implementation Decisions

### Client Library
- **D-01:** Use `databento` Python SDK (0.75.0 already installed) — has both Historical and Live clients sharing the same interface.
- **D-02:** Dataset: `GLBX.MDP3` (CME MDP 3.0), same as historical.
- **D-03:** Schema: `mbo` for full order book + trades. This is the highest resolution CME provides.
- **D-04:** Symbol: `NQ.c.0` continuous contract (front-month auto-roll), same as backtest.

### Architecture
- **D-05:** New file `deep6/data/databento_live.py` with `DatabentoLiveFeed` class.
- **D-06:** Feeds same `DOMState` and `FootprintBar` pipeline as Rithmic. Engines see identical interfaces.
- **D-07:** Data source selection via `DEEP6_DATA_SOURCE` env var: `"databento"` (default) or `"rithmic"`.
- **D-08:** `__main__.py` picks feed based on env var, subscribes, starts asyncio tasks.

### MBO → DOM State Reconstruction
- **D-09:** MBO events include add/modify/cancel/trade actions with price + size + side per order ID.
- **D-10:** Maintain per-level aggregated bid/ask size from order events. When order added → increment level size. When canceled → decrement. When traded → decrement by fill size.
- **D-11:** Top 40 bid + 40 ask levels fed to `DOMState.update()` on each event (or batched every 10ms to reduce callback pressure).

### MBO → Footprint Accumulation
- **D-12:** Trade events (action='T') feed `FootprintBar.add_trade(price, size, aggressor)`.
- **D-13:** Databento provides native aggressor side (`A`=ask aggressor/buyer, `B`=bid aggressor/seller) — same field verified in historical. No gate needed.
- **D-14:** Bar boundaries determined by event timestamp: `int(ts_ns / 1e9) // bar_seconds * bar_seconds`.

### Session Control
- **D-15:** RTH only (9:30-16:00 ET) per existing `SessionContext` — apply before feeding events.
- **D-16:** Overnight events received but skipped (not accumulated into FootprintBars).
- **D-17:** Session boundaries trigger `on_session_reset()` (resets cooldowns, confirmations, session state).

### Reconnection
- **D-18:** Databento Live handles reconnection via WebSocket auto-reconnect with gap replay.
- **D-19:** On disconnect: set `FreezeGuard.state = RECONNECTING`, halt new orders, resume when gap replay completes.
- **D-20:** Log gap duration for post-session review.

### Performance
- **D-21:** MBO callback rate can exceed 10,000/sec during high-volatility opens. Must process in asyncio event loop without blocking.
- **D-22:** Batch DOMState updates every 10ms via asyncio task (not per-callback) to reduce signal engine load.

### Testing
- **D-23:** Unit tests with synthetic MBO events (no live Databento required).
- **D-24:** Integration test with Databento `replay` mode (historical data via Live API interface) — validates end-to-end without live session.

### Claude's Discretion
- Exact order book reconstruction algorithm
- Batching timer implementation
- Error handling specifics

</decisions>

<canonical_refs>
## Canonical References

- `deep6/data/rithmic.py` — reference implementation for live feed pattern
- `deep6/data/databento_feed.py` — historical Databento client (reuse patterns)
- `deep6/state/dom.py` — DOMState target
- `deep6/state/footprint.py` — FootprintBar target
- `deep6/state/connection.py` — FreezeGuard for reconnection state
- `.env.example` — DATABENTO_API_KEY location

</canonical_refs>

<code_context>
## Existing Code Insights
- DatabentoFeed (historical) uses `client.timeseries.get_range()` — returns iterable
- Databento Live uses `client.Live(key=...)` — WebSocket push
- Both share schema — replay code path identical
- async-rithmic has order plant separate from market data plant — can run orders only

</code_context>

<specifics>
## Specific Ideas
- Add `deep6.data.factory.create_feed(source, config)` for clean instantiation
- Keep rithmic.py intact but add a flag to disable market data subs when source=databento
</specifics>

<deferred>
## Deferred Ideas
- Multi-instrument support (ES, YM, RTY) — single instrument v1
- Custom snapshot intervals — use Databento's native snapshot

</deferred>

---
*Phase: 14-databento-live-feed*
*Context gathered: 2026-04-14*
