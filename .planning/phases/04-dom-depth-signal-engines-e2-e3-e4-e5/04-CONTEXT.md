# Phase 4: DOM Depth Signal Engines (E2, E3, E4, E5) - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the four DOM-driven engines (E2 Trespass, E3 CounterSpoof, E4 Iceberg, E5 MicroProb), five trapped trader signals, and six volume pattern signals. These engines operate on live DOM snapshots and trade-vs-DOM comparisons — fundamentally different from footprint engines which analyze completed bars.

**Key reality:** DOMState exists (72 lines) with pre-allocated arrays and snapshot(). No DOM engine code exists yet — this is greenfield. Engines must be testable with synthetic DOM data since live Rithmic isn't available yet. All engines must be non-blocking (DOM callbacks at 1,000/sec).

</domain>

<decisions>
## Implementation Decisions

### E2 Trespass Engine (Queue Imbalance)
- **D-01:** Multi-level weighted imbalance: sum(bid_size * weight) vs sum(ask_size * weight) across top N levels. Weight = 1/level_index (closer levels matter more).
- **D-02:** Logistic regression on (imbalance_ratio, spread, depth_gradient) for direction probability. Use sklearn LogisticRegression trained on historical tick data later; start with heuristic threshold.
- **D-03:** Must run in < 0.1ms — no blocking the event loop.

### E3 CounterSpoof Engine
- **D-04:** Track DOM snapshots every 100ms (not every callback — too expensive). Compare consecutive snapshots.
- **D-05:** Wasserstein-1 distance between bid distributions (sizes by level). Spike > 3σ from rolling mean = anomaly.
- **D-06:** Large order cancel detection: if a level had > 50 contracts and drops to < 10 within 200ms without a trade at that level, flag as potential spoof.
- **D-07:** Alert only — spoofing detection is informational, not a trade signal by itself.

### E4 Iceberg Engine
- **D-08:** Native iceberg: trade fill size > displayed DOM depth at that price at time of fill. Requires comparing trade callback with most recent DOM snapshot.
- **D-09:** Synthetic iceberg: same price level refills to within 20% of previous size within 250ms of being depleted. Track per-level depletion timestamps.
- **D-10:** Iceberg at absorption zone = highest conviction bonus (+3 points in scorer).

### E5 Micro Probability Engine
- **D-11:** Naive Bayes combining: E2 queue imbalance direction, E4 iceberg presence, imbalance direction from narrative. Each feature is binary (bull/bear/neutral).
- **D-12:** Output is probability 0-1 for next-tick direction. Used for execution timing, not signal generation.
- **D-13:** Fallback when DOM unavailable: return 0.5 (neutral). System must work without DOM engines.

### Trapped Trader Signals
- **D-14:** Five variants use FootprintBar data (not DOM) — can be tested with Databento.
- **D-15:** These fire from narrative.py, not from DOM engines. Wire into existing imbalance detection.

### Volume Pattern Signals
- **D-16:** Six variants computed from FootprintBar + bar history. Also testable without live DOM.
- **D-17:** Volume sequencing, bubble, surge use rolling bar history (deque from BarBuilder).

### Claude's Discretion
- Synthetic DOM data generation for tests
- Wasserstein distance implementation (scipy vs manual)
- Logistic regression feature set for E2

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §TRAP, §VOLP, §ENG — Requirement IDs
- `deep6/state/dom.py` — DOMState with pre-allocated arrays
- `deep6/engines/signal_config.py` — Config pattern
- `deep6/engines/imbalance.py` — Trapped signals partially here already
- `deep6/state/footprint.py` — FootprintBar consumed by trapped/volume signals

</canonical_refs>

<code_context>
## Existing Code Insights
- DOMState.snapshot() returns (bid_prices, bid_sizes, ask_prices, ask_sizes) as lists
- DOMState.update() is zero-allocation, called 1000/sec
- Trapped trader signals partially exist in imbalance.py (INVERSE_TRAP)
- Volume patterns partially exist in narrative.py (momentum detection)
- scipy available for Wasserstein distance

</code_context>

<specifics>
## Specific Ideas
- DOM engines get snapshot once per bar close, not per callback
- E3 spoof detection samples DOM every 100ms via asyncio timer
- All engines return signal dataclasses matching existing pattern
</specifics>

<deferred>
## Deferred Ideas
None
</deferred>

---
*Phase: 04-dom-depth-signal-engines-e2-e3-e4-e5*
*Context gathered: 2026-04-13*
