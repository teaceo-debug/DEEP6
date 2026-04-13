# Phase 9: ML Backend - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

FastAPI backend receives signal/trade events in the same asyncio event loop; stores to SQLite; trains XGBoost meta-learner on signal history; HMM detects market regime; Optuna sweeps thresholds. No weight file deploys without explicit operator approval. This is greenfield — deep6/api/ and deep6/ml/ are empty.

</domain>

<decisions>
## Implementation Decisions

### FastAPI Service
- **D-01:** FastAPI runs in same asyncio event loop as trading engine (not separate process). Uses Uvicorn ASGI server with single worker.
- **D-02:** Endpoints: POST /events/signal (from scorer), POST /events/trade (from PaperTrader), GET /weights/current, POST /weights/deploy (requires confirmation token).
- **D-03:** Event store: SQLite via aiosqlite (reuse Phase 1 pattern). Two tables: signal_events, trade_events.

### XGBoost Meta-Learner
- **D-04:** LightGBM preferred over XGBoost (per ML research finding) — better handles sparse/binary features like our 44 signal flags.
- **D-05:** Input features: 44 signal strengths + GEX regime + bar_index_in_session + Kronos bias = 47 features.
- **D-06:** Target: 3-bar forward return sign (binary classification). Alt: triple barrier label once implemented.
- **D-07:** Training runs in ThreadPoolExecutor to avoid blocking event loop.
- **D-08:** Model persists to disk as pickle + JSON metadata (training date, N samples, features, metrics).

### HMM Regime Detection
- **D-09:** 3-state Gaussian HMM on features: (ATR_ratio, spread, trade_rate, delta_abs_mean, range_to_atr).
- **D-10:** States mapped to: ABSORPTION_FRIENDLY (low vol, balanced), TRENDING (directional delta, expanding), CHAOTIC (high vol, wide spread).
- **D-11:** Online Viterbi decoding per bar. Regime state fed into scorer and risk manager.
- **D-12:** Retrained nightly on rolling 30-day window.

### Optuna Integration
- **D-13:** Reuse existing scripts/sweep_thresholds.py for offline sweeps.
- **D-14:** API endpoint POST /ml/sweep triggers async Optuna run, returns job_id. GET /ml/sweep/{job_id} returns results.
- **D-15:** Weight cap: single-signal weight cannot exceed 3x baseline without manual override.

### Walk-Forward Validation
- **D-16:** Reuse scripts/walk_forward.py. ML weights only deploy if WFE >= 0.70.
- **D-17:** Minimum 200 OOS trades per signal before that signal's weight is updated.
- **D-18:** Combinatorial Purged Cross-Validation (CPCV) from mlfinlab if installed, else fall back to existing purged split.

### Deployment Gate
- **D-19:** POST /weights/deploy requires (a) WFE >= 0.70 pass, (b) operator confirmation token, (c) before/after comparison.
- **D-20:** Deployed weights loaded by scorer at next bar boundary (atomic swap, no mid-bar changes).
- **D-21:** Previous weights kept as fallback for 7 days. Rollback endpoint available.

### Performance Tracking
- **D-22:** Per-signal metrics: win_rate, profit_factor, Sharpe, frequency. Rolling windows: 50, 200, 500 trades.
- **D-23:** Per-regime breakdown: same metrics sliced by HMM regime state.

### Claude's Discretion
- Pickle vs safetensors for model storage
- FastAPI dependency injection patterns
- Job queue for sweep endpoints

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §ML — ML-01..08
- `deep6/scoring/scorer.py` — ScorerResult (feeds signal events)
- `deep6/execution/paper_trader.py` — Trade events source
- `deep6/state/persistence.py` — aiosqlite pattern
- `scripts/sweep_thresholds.py` — existing Optuna sweep
- `scripts/walk_forward.py` — existing WFE validation

</canonical_refs>

<code_context>
## Existing Code Insights
- aiosqlite pattern established in Phase 1
- Optuna + vectorbt already installed
- ScorerResult has all 47 features needed (categories + score + confluence)
- PositionEvent dataclass from Phase 8 is JSON-serializable

</code_context>

<specifics>
## Specific Ideas
- Use river library for online learning (EWMA signal performance + ADWIN drift detection)
- Add SHAP feature importance to /weights/current endpoint for explainability
</specifics>

<deferred>
## Deferred Ideas
None
</deferred>

---
*Phase: 09-ml-backend*
*Context gathered: 2026-04-13*
