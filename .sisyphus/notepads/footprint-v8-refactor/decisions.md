# Decisions — footprint-v8-refactor

## Session Start: 2026-05-24

### Architectural Decisions
- **Fork strategy**: V7 → V8 (new file). V7 untouched as rollback. First decision made.
- **MTF deferred**: V7 has zero AddDataSeries() calls. MTF is V9 scope.
- **Bias box output**: Green "LONG" / Red "SHORT" / Gray "NEUTRAL" rectangle replacing exhaustion diamond
- **Arrow policy**: All 4 systems default OFF in V8. Re-enabled only if backtest-validated.
- **Threshold source**: Optimization loop picks thresholds — not hardcoded.

### Open Decisions (to be resolved by task outputs)
- Which Python codebase (v1/v2) is authoritative for V7? → T3 resolves
- Which signal variants KEEP/KILL/INCONCLUSIVE? → T5 resolves
- Which arrow systems to retain? → T6 resolves
- What are the optimal bias box thresholds? → T13 resolves

### 2026-05-24 T10 implementation decisions
- Implemented bias scoring as a rolling average of recent rendered signal directions, capped by `BiasLookback` and normalized to `[-1.0, 1.0]`.
- Kept the legacy exhaustion diamond/percentage path fully intact behind `ShowRawPercentage` instead of deleting it.
- Used the shared tag pattern `"BiasBox_" + CurrentBar` so multiple neutral exhaustion events on the same bar overwrite to a single visible bias box.
- Kept Task 12 scope to configuration only: added `deep6/backtest/v8_config.py` and `data/backtests/v8_parent0.json` without modifying `fitness.py`, `mutation_engine.py`, or `scripts/backtest_loop.py`.
- Encoded convergence as data (`patience=20`, `max_iterations=200`, `max_hours=4`) and exposed a pure helper so Task 13 can wire stop logic without redefining the guardrail.
- Task 13 uses a dedicated `scripts/run_v8_optimization.py` runner instead of `scripts/backtest_loop.py` because the generic discovery loop mutates `StrategyConfig`, while V8 optimization is a flat 16-parameter search over bias thresholds and per-variant toggles.
- Walk-forward selection uses a strict chronological `60/20/20` split on `data/backtests/nq_1yr_1m.csv`: first 60% train, middle 20% validation/OOS for ranking, final 20% test for winner selection.
