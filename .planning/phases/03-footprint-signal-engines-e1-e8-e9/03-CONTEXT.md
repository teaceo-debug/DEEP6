# Phase 3: Footprint Signal Engines (E1, E8, E9) - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

All 25 imbalance, delta, and auction theory signals implemented in E1 (imbalance), E8 (CVD/delta), and E9 (auction FSM). Every signal fires on the correct bar condition. This phase validates, calibrates, and completes the existing engine code — engines already exist and fire on real Databento data.

**Key reality:** `imbalance.py` (189 lines, 11 types), `delta.py` (228 lines, DeltaEngine with process()), and `auction.py` (214 lines, AuctionEngine with FSM) already exist. This phase validates against requirements, extracts thresholds into config, adds missing features (cross-session persistence for unfinished auctions, Pearson correlation matrix), and adds comprehensive tests.

</domain>

<decisions>
## Implementation Decisions

### Config Extraction
- **D-01:** Follow Phase 2 pattern — extract all thresholds into config dataclasses in `signal_config.py` (add `ImbalanceConfig`, `DeltaConfig`, `AuctionConfig`).
- **D-02:** Keep current defaults until Phase 7 vectorbt sweep.

### Imbalance Engine
- **D-03:** Diagonal imbalance must use ask[P] vs bid[P-1] (one tick down) — verify this is correct in existing code.
- **D-04:** Engine already has 11 types (2 more than the 9 required). Keep all — CONSECUTIVE and REVERSAL are useful even if not in original requirements.

### Delta/CVD Engine
- **D-05:** CVD multi-bar regression uses numpy polyfit over 5-20 bar rolling window. Verify existing implementation.
- **D-06:** Delta velocity = rate of change of cumulative delta per unit time. Verify implementation.

### Auction Theory Engine
- **D-07:** Unfinished auction levels MUST persist cross-session in SQLite. Wire into existing SessionPersistence.
- **D-08:** Volume void and market sweep are the two auction types that need verification against requirements.

### Correlation Matrix (ARCH-04)
- **D-09:** Compute pairwise Pearson correlation matrix for all implemented signals using numpy. Run on backtest data. Document any pair with r > 0.7.
- **D-10:** This is a one-time analysis output, not a runtime feature. Create a script that exports the matrix.

### Claude's Discretion
- Test structure and coverage
- Config dataclass field naming
- Correlation matrix output format

</decisions>

<canonical_refs>
## Canonical References

### Signal Specifications
- `.planning/REQUIREMENTS.md` §IMB (IMB-01..09) — Imbalance requirements
- `.planning/REQUIREMENTS.md` §DELT (DELT-01..11) — Delta requirements
- `.planning/REQUIREMENTS.md` §AUCT (AUCT-01..05) — Auction theory requirements

### Existing Engine Code
- `deep6/engines/imbalance.py` — 11 imbalance types, detect_imbalances()
- `deep6/engines/delta.py` — DeltaEngine with process(), CVD history
- `deep6/engines/auction.py` — AuctionEngine with FSM, process()
- `deep6/engines/signal_config.py` — AbsorptionConfig/ExhaustionConfig (Phase 2 pattern)

### Data Pipeline
- `deep6/state/footprint.py` — FootprintBar consumed by all engines
- `deep6/state/persistence.py` — SessionPersistence for cross-session auction levels
- `scripts/backtest_signals.py` — Full signal backtest pipeline

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `signal_config.py` pattern from Phase 2 — frozen dataclasses with defaults
- `backtest_signals.py` already calls all three engines
- `SessionPersistence` ready for auction level storage

### Established Patterns
- Engines return lists of signal dataclasses
- `DeltaEngine` and `AuctionEngine` are stateful (maintain history across bars)
- Imbalance detection is stateless (per-bar)

### Integration Points
- `scoring/scorer.py` already consumes delta_signals, auction_signals, imbalance data from narrative
- `backtest_signals.py` orchestrates all engines — changes must be backward-compatible

</code_context>

<specifics>
## Specific Ideas

- Use the April 10 Databento backtest data for correlation matrix computation
- Correlation matrix script should output both a CSV and a human-readable summary

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-footprint-signal-engines-e1-e8-e9*
*Context gathered: 2026-04-13*
