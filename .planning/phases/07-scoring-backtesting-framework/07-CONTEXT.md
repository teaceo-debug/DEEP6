# Phase 7: Scoring + Backtesting Framework - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Two-layer confluence scorer synthesizes all 44 signal flags into typed ScorerResult; Databento MBO replay generates ground-truth labeled bars; vectorbt parameter sweeps; walk-forward validation. `scorer.py` (269 lines) and `backtest_signals.py` (245 lines) already exist — this phase validates, enhances scoring logic, adds vectorbt sweeps, and walk-forward validation.

**Key reality:** scorer.py already produces ScorerResult with TYPE_A/B/C/QUIET tiers, category counting, confluence multiplier, zone bonus. backtest_signals.py already runs full signal pipeline on Databento data. This phase adds: vectorbt integration, walk-forward validation, threshold sweep, and scoring refinements from Phase 2/3 findings (stacked imbalance dedup, confirmation bonus).

</domain>

<decisions>
## Implementation Decisions

### Scorer Enhancements
- **D-01:** Integrate absorption confirmation bonus (+2 points from ABS-06/D-07 in Phase 2).
- **D-02:** Stacked imbalance dedup — use highest tier only (T3 > T2 > T1) per Phase 3 correlation finding.
- **D-03:** TypeA requires absorption/exhaustion + zone confluence + 5+ category agreement.
- **D-04:** Category-level confluence multiplier 1.25x when 5+ categories agree.
- **D-05:** Zone bonus +6 to +8 points for zone confluence.

### Backtesting
- **D-06:** Databento MBO replay through same engine code — no separate implementation.
- **D-07:** Use April 10 + at least 4 more trading days for sweep validation.
- **D-08:** vectorbt for parameter sweeps via Optuna.

### Walk-Forward
- **D-09:** Walk-forward efficiency (WFE) > 70% gate before any weight file applies.
- **D-10:** Purged splits prevent future leakage.

### Config
- **D-11:** Add `ScorerConfig` to signal_config.py with all threshold values.

### Claude's Discretion
- vectorbt portfolio construction details
- Optuna study configuration
- Number of walk-forward folds

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §SCOR, §TEST — Scoring and testing requirements
- `deep6/scoring/scorer.py` — Existing scorer
- `scripts/backtest_signals.py` — Existing backtest pipeline
- `deep6/engines/signal_config.py` — Config pattern

</canonical_refs>

<code_context>
## Existing Code Insights
- scorer.py has score_bar() returning ScorerResult with total_score, tier, direction, categories
- backtest_signals.py produces per-bar CSV with P&L attribution
- Databento API key live, April 10 data validated
- vectorbt and optuna in requirements but not yet installed

</code_context>

<specifics>
## Specific Ideas
- Backtest already shows TYPE_B/C signals with P&L — use as baseline
- Correlation matrix from Phase 3 informs weight dedup
</specifics>

<deferred>
## Deferred Ideas
None
</deferred>

---
*Phase: 07-scoring-backtesting-framework*
*Context gathered: 2026-04-13*
