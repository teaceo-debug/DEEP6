# Phase 8: Auto-Execution + Risk Layer - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Direct Rithmic order submission from TYPE_A/B signals with bracket orders (entry + stop + target), circuit breaker risk management, reconnection freeze, GEX regime gate, and mandatory 30-day paper trading gate. This is greenfield — deep6/execution/ is empty.

</domain>

<decisions>
## Implementation Decisions

### Order Submission
- **D-01:** Use async-rithmic OrderPlant for bracket orders: market entry + server-side stop + server-side target. All three legs submitted atomically.
- **D-02:** TYPE_A signals auto-execute (after paper trading gate). TYPE_B signals require operator confirmation (one-click from dashboard). TYPE_C never executes.
- **D-03:** Entry at market price on bar close when signal fires. E5 MicroEngine probability can delay up to 3 seconds for better fill when P(direction) < 0.55.

### Stop Placement
- **D-04:** Stop beyond absorption/exhaustion zone boundary + 2 ticks buffer. For TYPE_A SHORT: stop above the upper wick high of the signal bar + 0.50 pts.
- **D-05:** Maximum stop distance: 2x ATR. If zone boundary exceeds this, reduce position size or skip trade.
- **D-06:** After absorption confirmation (ABS-06, 3 bars), move stop to breakeven.

### Target Placement
- **D-07:** Primary target: next opposing zone (LVN, HVN, or VA level) in signal direction.
- **D-08:** Secondary target: 1.5x risk distance (R:R = 1.5:1 minimum).
- **D-09:** Maximum hold: 10 bars. If neither target nor stop hit, exit at market.

### Circuit Breakers
- **D-10:** Daily loss limit: -$500 per contract (configurable). All new entries halted when hit.
- **D-11:** Consecutive loss limit: 3 consecutive losing trades → pause for 30 minutes.
- **D-12:** Max position: 1 contract during paper trading. Configurable for live.
- **D-13:** Max trades per day: 10 (prevents overtrading on choppy days).

### Reconnection
- **D-14:** TRADING_FROZEN activates immediately on disconnect. Zero new orders.
- **D-15:** On reconnect: query Rithmic position API, reconcile with local state. Only unfreeze when positions match.

### GEX Regime Gate
- **D-16:** In NEGATIVE_AMPLIFYING regime: TYPE_B signals blocked entirely. TYPE_A allowed only with absorption (not exhaustion alone).
- **D-17:** GEX wall conflict (long at call wall, short at put wall): blocked regardless of tier.

### Paper Trading Gate
- **D-18:** 30-day minimum paper trading before live flag enabled. System tracks paper P&L, win rate, max drawdown.
- **D-19:** Paper trading uses real Rithmic data feed but simulated fills (no actual orders). Slippage model: 1 tick + random 0-1 tick.
- **D-20:** Operator cannot bypass the 30-day gate. Counter resets if system code changes materially.

### Position Manager
- **D-21:** Tracks all open positions with entry price, stop, target, bars held, unrealized P&L.
- **D-22:** Emits events on entry, stop hit, target hit, timeout exit, manual exit — consumed by ML backend (Phase 9) and dashboard (Phase 10).

### Claude's Discretion
- Exact async-rithmic order API usage patterns
- Paper trading fill simulation internals
- Position reconciliation algorithm

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §EXEC — EXEC-01..08
- `deep6/data/rithmic.py` — Existing Rithmic connection code
- `deep6/state/connection.py` — FreezeGuard for TRADING_FROZEN state
- `deep6/scoring/scorer.py` — ScorerResult with tier, direction, zone info
- `deep6/engines/gex.py` — GexSignal with regime and wall proximity
- `deep6/engines/signal_config.py` — Config pattern

</canonical_refs>

<code_context>
## Existing Code Insights
- FreezeGuard in connection.py already manages FROZEN state
- async-rithmic has OrderPlant for order submission
- ScorerResult provides tier, direction, score, zone_bonus, categories
- GexSignal provides regime, near_call_wall, near_put_wall

</code_context>

<specifics>
## Specific Ideas
- Paper trading mode should log every decision as if live — complete audit trail
- Position events should be JSON-serializable for Phase 9/10 consumption
</specifics>

<deferred>
## Deferred Ideas
None
</deferred>

---
*Phase: 08-auto-execution-risk-layer*
*Context gathered: 2026-04-13*
