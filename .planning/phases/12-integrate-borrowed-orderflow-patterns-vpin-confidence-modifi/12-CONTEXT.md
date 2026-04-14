# Phase 12: Integrate Borrowed Orderflow Patterns — Context

**Gathered:** 2026-04-13
**Status:** Ready for planning
**Source:** Discuss-phase (inline, post-research)

<domain>
## Phase Boundary

Integrate five orderflow patterns borrowed from kronos-tv-autotrader into DEEP6's existing async signal engine, LightGBM meta-learner, and HMM regime detector. This is an **integration phase**, not greenfield research — reference implementation at `/Users/teaceo/Downloads/kronos-tv-autotrader` is already vetted.

Five patterns, in integration order:

1. **VPIN confidence modifier** — continuous position-size scalar (0.2×–1.2×) based on flow-toxicity percentile
2. **Intrabar delta tracking + fix existing `DELT_TAIL` (bit 22)** — enables proper Delta-At-Extreme quality check; NOT a new signal
3. **`TRAP_SHOT` Slingshot (new bit 44)** — 2/3/4-bar trapped-trader reversal; bypasses DEVELOPING state at GEX walls
4. **Setup state machine** — SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN with soaking bonus, on 1-min AND 5-min
5. **Per-regime walk-forward tracker** — 5/10/20-bar outcome logging per category (8 groups), auto-disable on rolling Sharpe drop

</domain>

<decisions>
## Implementation Decisions

### VPIN
- **Bucket size:** Fixed 1,000 contracts (volume clock). Tune with live data in later phase if needed.
- **Bucket count (N):** 50 (standard Easley window)
- **Aggressor classification:** Use DEEP6's exact aggressor field (DATA-02 verified), NOT BVC/normal-CDF from reference. Strictly more accurate.
- **Output:** continuous multiplier 0.2×–1.2× based on rolling percentile of VPIN series
- **Compounding guard:** Do NOT multiply VPIN scalar into IB multiplier (reference-impl footgun). VPIN modulates the final fused confidence from the LightGBM meta-learner, not per-signal scores.

### Delta-At-Extreme / `DELT_TAIL` fix
- Add intrabar `max_delta` / `min_delta` tracking to `FootprintBar.add_trade()`
- **Do NOT add a new signal bit** — fix existing bit 22 `DELT_TAIL` to use real running max/min
- Emit a bar-quality scalar alongside: closing-at-max → 1.15×; peaked-early-then-faded → 0.7×
- Bar-quality scalar is orthogonal to VPIN — applies to delta-based signals only

### `TRAP_SHOT` Slingshot
- **New signal flag:** bit 44, name `TRAP_SHOT` (existing bit 28 `DELT_SLINGSHOT` is a DIFFERENT pattern — do not repurpose)
- 2/3/4-bar variants
- "Extreme delta" threshold: rolling z-score > 2.0 over session window
- **Reset `delta_history` at session boundary** (locked; prevents threshold drift across sessions)
- When firing at a GEX wall (distance < threshold), bypass DEVELOPING state → immediate TRIGGERED

### Setup state machine
- States: SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN
- **Timeframes:** BOTH 1-min (tactical) AND 5-min (strategic) simultaneously
- Soaking bonus: 10-bar soak weighted 5× a 1-bar signal (linear ramp)
- Slingshot-at-GEX-wall bypasses DEVELOPING
- **`MANAGING → COOLDOWN` is NOT auto** — explicit close signal required (reference-impl footgun fixed)
- Lives in `SharedState.on_bar_close` as its own component, consumes `ScorerResult`

### Walk-forward tracker
- **Granularity:** per-category (8 groups, matches `WeightFile.weights` structure from phase 09-02)
- **Horizons:** 5, 10, 20 bars
- **Outcome labels:** CORRECT / INCORRECT / NEUTRAL / **EXPIRED** (EXPIRED for signals fired <20 bars before RTH close — excluded from win-rate stats)
- **Persistence:** reuse phase 09-01 `EventStore` (async SQLite) — query-aggregate, NOT a new JSON-on-disk sink
- **Auto-disable:** rolling Sharpe < threshold on 200-signal window → category weight → 0 until recovery
- Feeds back into LightGBM meta-learner fusion weights per regime

### Integration order (ship sequence)
1. VPIN (orthogonal, cleanest)
2. Intrabar delta tracking + `DELT_TAIL` fix
3. `TRAP_SHOT` @ bit 44
4. Setup state machine (1m + 5m)
5. Walk-forward tracker

### Claude's Discretion
- Specific class/module names (follow existing phase 01/09 conventions)
- Test fixtures & data generators
- Metrics emitted to dashboard (phase 11) — but MUST emit something for each pattern

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Reference implementation
- `/Users/teaceo/Downloads/kronos-tv-autotrader/python/` — complete reference; 1.4 KLOC reviewed by researcher
- `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md` — full research doc with code citations

### DEEP6 integration surfaces
- `.planning/phases/09-02-*` — 47-signal feature builder + LightGBM meta-learner + HMM regime detector (WeightFile.weights structure lives here)
- `.planning/phases/09-01-*` — FastAPI foundation + EventStore (async SQLite) — reuse for tracker persistence
- `.planning/phases/01-data-pipeline-architecture-foundation/` — `SignalFlags` bit positions 0-43 STABLE, `SharedState`, `FootprintBar`, `on_bar_close`
- `.planning/STATE.md` — bit position lock + DATA-02 aggressor verification
- Paper: Easley, López de Prado, O'Hara (2011) "The Volume Clock: Insights into the High Frequency Paradigm"

</canonical_refs>

<specifics>
## Specific Ideas

- VPIN scalar must NOT stack with IB multiplier (reference-impl footgun — can blow past tier thresholds)
- `TRAP_SHOT` name reserved to avoid collision with existing `DELT_SLINGSHOT` (bit 28, different pattern)
- State machine transitions must be logged via EventStore for post-session debugging
- Walk-forward tracker auto-disable is per-category AND per-regime (HMM regime × category matrix)

</specifics>

<deferred>
## Deferred Ideas

- Session-adaptive VPIN bucket sizing (future tune phase if fixed 1000 underperforms)
- Per-signal (44-bit) walk-forward granularity (may revisit if per-category proves too coarse)
- 15-min strategic setup state machine layer
- VPIN as a direct hard-filter circuit breaker (kept as multiplier only per research)

</deferred>

---

*Phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi*
*Context gathered: 2026-04-13 via inline discuss + research synthesis*
