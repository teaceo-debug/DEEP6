# DEEP6 Credible Backtesting System Implementation Plan

> For Hermes: use subagent-driven-development to implement this plan task-by-task.

Goal: Build a backtesting and research-validation system for DEEP6 that is credible enough to reject weak ideas early, promote strong ideas through repeatable evidence, and keep replay, paper, and live behavior aligned.

Architecture:
Use one canonical event-driven strategy engine across replay, paper, and live. Historical Databento MBO should flow through the same callback shape already used by the live Rithmic path, with execution simulation upgraded from bar-close approximation to a versioned fill-model pipeline. Every run must produce auditable artifacts: data manifest, code/config hashes, event QA stats, signal traces, fills, and promotion-gate summaries.

Tech Stack: Python 3.12, Databento MBO, async-rithmic, DuckDB, FastAPI, Next.js, vectorbt/Optuna for secondary analytics only, pytest.

---

## 1. What “credible” means for DEEP6

A credible backtest for DEEP6 must satisfy all of these:

1. Same signal path in replay and live.
2. No lookahead in any feature, bias, or fill decision.
3. Market microstructure fidelity is explicit, measured, and versioned.
4. Results are reproducible from code SHA + config hash + data manifest.
5. Strategy claims are based on out-of-sample, walk-forward, regime-aware evidence.
6. Promotion to paper/live uses hard gates, not discretionary optimism.

If any of those are missing, the result can still be useful for idea triage, but it should be labeled exploratory rather than credible.

---

## 2. Current repo truth

Existing strengths already in the repo:
- `deep6/backtest/mbo_adapter.py` replays Databento MBO through the live callback shape.
- `deep6/backtest/session.py` already orchestrates event-time replay with DEEP6 engines.
- `deep6/backtest/result_store.py` persists run/bar/trade artifacts in DuckDB.
- `deep6/backtest/bracket_exit.py` provides a conservative first-pass bracket model.
- `deep6/backtest/vbt_harness.py` and `deep6/backtest/optimizer.py` provide research utilities.

Major credibility gaps to close:
- `deep6/api/routes/backtest.py` still exposes a legacy bar-based script path instead of the replay stack.
- Execution modeling is still too simple for pre-live trust.
- Stored artifacts are not yet rich enough for forensic audit.
- Time/session modeling is not exchange-calendar-grade.
- Walk-forward, confidence, and promotion gates are not yet standardized end-to-end.

---

## 3. Target system design

### 3.1 System layers

1. Data layer
   - Historical: Databento MBO and trades.
   - Live: Rithmic tick/DOM and execution events.
   - Canonical event schema for replay and live parity.

2. Replay engine layer
   - Canonical event clock.
   - Feed adapters: Databento replay adapter and Rithmic live adapter.
   - Session/calendar service.
   - Event QA and tape integrity checks.

3. Strategy/signal layer
   - Shared DEEP6 signal pipeline.
   - Bias inputs with explicit availability timestamps.
   - Decision trace object persisted for every trade candidate.

4. Execution simulation layer
   - Versioned fill model interface.
   - Research-tier models: idealized, base, pessimistic.
   - Latency, slippage, spread, stop-gap, queue approximation.

5. Artifact and analysis layer
   - DuckDB run store.
   - Signal/fill/event trace tables.
   - Walk-forward reports.
   - Regime scorecards.
   - Promotion-gate summaries.

6. Operator/UI layer
   - FastAPI endpoints to launch runs and fetch artifacts.
   - Replay dashboards and experiment comparison views.
   - Promotion decision screen.

### 3.2 Canonical research flow

idea -> replay QA -> event-driven backtest -> execution stress -> walk-forward -> regime report -> paper shadow -> constrained live

### 3.3 One engine rule

The same decision engine must be used in:
- historical replay
- paper trading
- live trading

Only the feed adapter and execution adapter should differ.

### 3.4 Research mode taxonomy

Mode A: Exploratory
- Fast runs.
- Idealized fills.
- For pruning bad ideas.

Mode B: Credible Research
- MBO replay.
- Base/pessimistic fills.
- Walk-forward and regime checks.
- Minimum evidence for paper promotion.

Mode C: Pre-Live Certification
- Replay/live parity checks.
- Empirical latency/slippage distributions.
- Shadow-live drift reporting.

---

## 4. Proposed code architecture

### 4.1 New/updated package layout

Modify or create these files:

Core backtest orchestration
- Modify: `deep6/backtest/session.py`
- Modify: `deep6/backtest/config.py`
- Modify: `deep6/backtest/result_store.py`
- Create: `deep6/backtest/models.py`
- Create: `deep6/backtest/run_manifest.py`
- Create: `deep6/backtest/calendar.py`
- Create: `deep6/backtest/event_qa.py`
- Create: `deep6/backtest/research_runner.py`
- Create: `deep6/backtest/promotion_gates.py`

Execution simulation
- Create: `deep6/backtest/fills/base.py`
- Create: `deep6/backtest/fills/idealized.py`
- Create: `deep6/backtest/fills/research_realistic.py`
- Create: `deep6/backtest/fills/pessimistic.py`
- Create: `deep6/backtest/fills/latency.py`
- Create: `deep6/backtest/fills/slippage.py`
- Create: `deep6/backtest/fills/queue_model.py`

Analytics and validation
- Create: `deep6/backtest/walkforward.py`
- Create: `deep6/backtest/confidence.py`
- Create: `deep6/backtest/regime_report.py`
- Create: `deep6/backtest/parity_report.py`
- Create: `deep6/backtest/stress.py`

API and UI hooks
- Replace implementation in: `deep6/api/routes/backtest.py`
- Create: `deep6/api/routes/experiments.py`
- Create: `deep6/api/routes/promotion.py`

Tests
- Create: `tests/backtest/test_research_runner.py`
- Create: `tests/backtest/test_fill_models.py`
- Create: `tests/backtest/test_event_qa.py`
- Create: `tests/backtest/test_walkforward.py`
- Create: `tests/backtest/test_promotion_gates.py`
- Create: `tests/backtest/test_backtest_api_replay_path.py`

Plan/docs
- Create later: `docs/plans/backtesting-certification-checklist.md`
- Create later: `docs/research/backtest-credibility-standard.md`

### 4.2 Canonical domain objects

Create in `deep6/backtest/models.py`:
- `RunManifest`
- `ReplayRunRequest`
- `EventQAReport`
- `DecisionTrace`
- `ExecutionIntent`
- `ExecutionFill`
- `TradeLifecycle`
- `PromotionGateReport`
- `WalkForwardFoldResult`
- `RegimeSliceResult`

These should be typed Pydantic/dataclass models so the API, DuckDB persistence, and offline reports all share one schema.

### 4.3 DuckDB schema expansion

Extend `deep6/backtest/result_store.py` with new tables:

1. `backtest_run_manifest`
- run_id
- git_sha
- config_hash
- fill_model_version
- feature_schema_version
- scorer_version
- data_manifest_json
- environment_json
- degraded_run
- degraded_reason

2. `backtest_event_qa`
- run_id
- total_events
- dropped_events
- duplicate_events
- out_of_order_events
- unknown_aggressor_events
- contract_rolls
- first_ts
- last_ts

3. `backtest_decisions`
- decision_id
- run_id
- ts_event
- ts_decision
- symbol
- tf
- direction
- score
- tier
- bias_snapshot_json
- signal_trace_json
- state_snapshot_json
- eligible_for_entry

4. `backtest_fills`
- fill_id
- decision_id
- run_id
- fill_model
- order_type
- submit_ts
- exchange_visible_ts
- fill_ts
- requested_qty
- filled_qty
- fill_price
- latency_ms
- slippage_ticks
- fill_quality_bucket

5. `backtest_promotion_gates`
- run_id
- gate_name
- status
- metric_json
- threshold_json
- notes

Keep existing `backtest_runs`, `backtest_bars`, and `backtest_trades`, but enrich them instead of replacing them.

---

## 5. Validation methodology built into the system

### 5.1 Tape integrity gates

Every run must compute and persist:
- total event count
- dropped/invalid/skipped event count
- duplicate count
- out-of-order count
- contract roll transitions
- session resets
- unknown aggressor count

Hard fail conditions:
- out-of-order events above threshold
- unknown aggressor count above threshold
- mismatched session boundaries
- corrupted book state

### 5.2 No-lookahead enforcement

Every feature and bias input must expose `available_at_ts`.

Rules:
- decision logic may only consume state with `available_at_ts <= decision_ts`
- fill simulation may only consume market state available at `submit_ts + modeled latency`
- Kronos and options-map signals must be explicitly lagged to production availability

Tests required:
- future-nullification test
- availability timestamp audit test
- replay/live decision parity test on frozen input slices

### 5.3 Execution realism tiers

Fill model ladder:

1. `idealized_v1`
- next eligible price / minimal cost
- fast hypothesis pruning only

2. `research_realistic_v1`
- spread aware
- latency aware
- stop-gap aware
- partial fill approximation
- queue approximation at top levels
- commissions and fees

3. `pessimistic_v1`
- added latency stress
- added adverse slippage
- lower passive fill odds
- wider stop slippage assumptions

Required reporting:
- strategy metrics under all 3 models
- edge decay from idealized -> base -> pessimistic

Promotion rule:
- an idea cannot advance if profitability disappears entirely outside the idealized model.

### 5.4 Walk-forward standard

Canonical walk-forward engine in `deep6/backtest/walkforward.py`:
- rolling contiguous folds
- purged/embargoed boundaries
- train/validate/test or train/test depending on run type
- parameter selection only from training data
- untouched OOS reporting

Primary metrics per fold:
- net pnl
- expectancy
- max drawdown
- profit factor
- MAE/MFE
- trade count
- win rate
- calibration of score vs realized outcome

Primary acceptance metrics:
- percent profitable OOS folds
- walk-forward efficiency
- parameter stability score
- degradation from IS to OOS

### 5.5 Regime segmentation

Every credible run must slice results by:
- time of day
- volatility bucket
- trend/range state
- dealer gamma regime / options-map regime
- Kronos alignment bucket
- liquidity bucket
- news proximity bucket

This becomes `deep6/backtest/regime_report.py`.

### 5.6 Statistical confidence

Implement in `deep6/backtest/confidence.py`:
- bootstrap confidence intervals for expectancy and drawdown
- parameter perturbation stability checks
- jackknife fold-removal checks
- permutation sanity test for false-discovery detection
- deflated-Sharpe-style summary or equivalent “multiple testing penalty” metric

---

## 6. API design

### 6.1 Replace legacy route behavior

`deep6/api/routes/backtest.py` should stop calling ad hoc script-based bar backtests.

New route behavior:
- POST `/backtest/run`
  - accepts a `ReplayRunRequest`
  - launches `ResearchRunner`
  - returns `run_id`
- GET `/backtest/runs/{run_id}`
  - returns status, manifest, QA summary, gate summary
- GET `/backtest/runs/{run_id}/metrics`
- GET `/backtest/runs/{run_id}/trades`
- GET `/backtest/runs/{run_id}/decisions`
- GET `/backtest/runs/{run_id}/promotion`

### 6.2 Experiment comparison endpoints

Create `deep6/api/routes/experiments.py`:
- compare multiple runs by metric bundle
- surface OOS-only comparisons by default
- filter by fill model, symbol, date range, regime

### 6.3 Promotion endpoints

Create `deep6/api/routes/promotion.py`:
- fetch promotion packet
- mark approved/rejected for paper promotion
- enforce minimum gate conditions before approval state can be set

---

## 7. Research runner behavior

Create `deep6/backtest/research_runner.py`.

Responsibilities:
1. Build and persist run manifest.
2. Run event QA before strategy evaluation.
3. Run replay session with configured fill model.
4. Persist bars, decisions, fills, trades, and QA stats.
5. Run walk-forward and regime analysis if requested.
6. Run promotion gates.
7. Emit a single machine-readable summary object.

Pseudo-flow:

1. load config
2. resolve data manifest
3. compute config hash
4. run event QA
5. if QA fail -> mark run failed/degraded
6. run replay with selected fill model
7. persist decisions/fills/trades
8. compute analytics
9. evaluate promotion gates
10. persist reports
11. return run summary

---

## 8. Promotion gate design

Create `deep6/backtest/promotion_gates.py` with hard gates.

Suggested initial gates:

Gate 1: Data Integrity
- max dropped-event rate
- max unknown aggressor rate
- session/calendar correctness

Gate 2: Replay Determinism
- repeated run on same manifest must match decision/fill hashes

Gate 3: Execution Robustness
- base model positive expectancy
- pessimistic model not catastrophic

Gate 4: Walk-Forward Robustness
- minimum OOS fold pass rate
- minimum OOS trade count
- bounded IS->OOS degradation

Gate 5: Regime Honesty
- no hidden concentration beyond threshold unless explicitly labeled strategy regime

Gate 6: Statistical Confidence
- bootstrap CI and stability checks pass thresholds

Gate 7: Shadow-Live Readiness
- only for later phases when live shadow logs are available

Outputs:
- PASS / WARN / FAIL per gate
- overall promotion recommendation
- blocking reasons

---

## 9. Phased implementation plan

### Phase 1: Unify on one replay path

Objective: make the public backtest system use the existing event-driven replay core instead of the legacy script path.

Files:
- Modify: `deep6/api/routes/backtest.py`
- Create: `deep6/backtest/research_runner.py`
- Create: `deep6/backtest/models.py`
- Test: `tests/backtest/test_backtest_api_replay_path.py`
- Test: `tests/backtest/test_research_runner.py`

Tasks:
1. Define `ReplayRunRequest` and `RunSummary` models.
2. Implement `ResearchRunner.run()` around `ReplaySession`.
3. Refactor `/backtest/run` to launch `ResearchRunner`, not scripts.
4. Expose persisted run metadata/status endpoints.
5. Add tests that prove the API path uses replay, not bar scripts.

Acceptance:
- The API and CLI both run the same replay engine.
- Legacy script path is clearly demoted to exploratory-only tooling.

### Phase 2: Add manifest and artifact lineage

Objective: make every result reproducible.

Files:
- Modify: `deep6/backtest/result_store.py`
- Create: `deep6/backtest/run_manifest.py`
- Test: `tests/backtest/test_result_store_manifest.py`

Tasks:
1. Add config hashing and data manifest capture.
2. Persist git SHA, feature/schema versions, fill model version.
3. Persist run-level degraded/failure flags.
4. Add tests for manifest persistence and deterministic hashing.

Acceptance:
- Every run can be reproduced from persisted metadata.

### Phase 3: Event QA and session/calendar realism

Objective: trust the tape before trusting the PnL.

Files:
- Create: `deep6/backtest/event_qa.py`
- Create: `deep6/backtest/calendar.py`
- Modify: `deep6/backtest/mbo_adapter.py`
- Modify: `deep6/backtest/session.py`
- Test: `tests/backtest/test_event_qa.py`

Tasks:
1. Add tape integrity checks and counters.
2. Add calendar/session boundary logic.
3. Handle empty-bar/session edge cases explicitly.
4. Persist event QA report.

Acceptance:
- Runs can fail or be marked degraded based on tape quality.

### Phase 4: Decision trace persistence

Objective: make every trade explainable.

Files:
- Modify: `deep6/backtest/session.py`
- Modify: `deep6/backtest/result_store.py`
- Test: `tests/backtest/test_decision_trace.py`

Tasks:
1. Emit `DecisionTrace` for every eligible candidate.
2. Persist exact fired signal details and bias snapshot.
3. Persist state snapshot needed for forensic replay.

Acceptance:
- For any trade, we can inspect why it was or was not taken.

### Phase 5: Versioned fill models

Objective: separate exploratory fills from credible execution assumptions.

Files:
- Create: `deep6/backtest/fills/base.py`
- Create: `deep6/backtest/fills/idealized.py`
- Create: `deep6/backtest/fills/research_realistic.py`
- Create: `deep6/backtest/fills/pessimistic.py`
- Create: `deep6/backtest/fills/latency.py`
- Create: `deep6/backtest/fills/slippage.py`
- Create: `deep6/backtest/fills/queue_model.py`
- Modify: `deep6/backtest/config.py`
- Modify: `deep6/backtest/session.py`
- Test: `tests/backtest/test_fill_models.py`

Tasks:
1. Replace simple fill toggle with pluggable fill model interface.
2. Add latency/slippage distributions.
3. Add marketable vs passive execution logic.
4. Add partial-fill and queue approximation.
5. Produce model-comparison metrics.

Acceptance:
- The same replay can be evaluated under multiple execution assumptions.

### Phase 6: Walk-forward framework

Objective: stop trusting single-period backtests.

Files:
- Create: `deep6/backtest/walkforward.py`
- Test: `tests/backtest/test_walkforward.py`

Tasks:
1. Implement purged rolling folds.
2. Support train/validate/test splits.
3. Generate fold-level OOS metrics and summaries.
4. Make OOS metrics the default comparison output.

Acceptance:
- Any serious experiment has fold-level OOS evidence.

### Phase 7: Regime and confidence reporting

Objective: understand where the edge lives and how fragile it is.

Files:
- Create: `deep6/backtest/regime_report.py`
- Create: `deep6/backtest/confidence.py`
- Test: `tests/backtest/test_regime_report.py`
- Test: `tests/backtest/test_confidence.py`

Tasks:
1. Compute regime buckets and slice metrics.
2. Add bootstrap confidence intervals.
3. Add perturbation stability and jackknife checks.
4. Add permutation/false-discovery sanity test.

Acceptance:
- Every credible report shows regime dependence and uncertainty, not just headline PnL.

### Phase 8: Promotion gates and operator workflow

Objective: formalize idea -> paper -> live promotion.

Files:
- Create: `deep6/backtest/promotion_gates.py`
- Create: `deep6/api/routes/promotion.py`
- Test: `tests/backtest/test_promotion_gates.py`

Tasks:
1. Implement gate definitions and thresholds.
2. Persist gate results by run.
3. Expose promotion packets through the API.
4. Prevent approval if blocking gates fail.

Acceptance:
- Promotion decisions are evidence-backed and machine-auditable.

### Phase 9: Replay/live parity and shadow-live certification

Objective: align research assumptions with real execution behavior.

Files:
- Create: `deep6/backtest/parity_report.py`
- Create: `deep6/backtest/stress.py`
- Extend later: live logging hooks in `deep6/execution/`

Tasks:
1. Compare replay decisions with live shadow decisions.
2. Compare modeled fills with real observed fills.
3. Track latency/slippage drift.
4. Define automatic downgrade criteria.

Acceptance:
- We can measure when live reality diverges from research assumptions.

---

## 10. Testing strategy

### 10.1 Minimum required tests

Unit
- event ordering
- aggressor mapping
- session/calendar boundaries
- fill-model latency/slippage behavior
- config/manifest hashing
- promotion-gate logic

Integration
- replay session produces deterministic outputs
- API launches replay runner and returns persisted artifacts
- same run manifest produces same decision/fill hashes

Regression
- certification fixtures with expected run summaries
- golden OOS fold outputs for known sessions
- parity drift thresholds between versions

### 10.2 Performance validation

Add timed replay tests to ensure the system can process realistic session sizes with acceptable throughput. Persist run duration, event throughput, and memory-watermark stats for each run.

---

## 11. What should remain non-canonical

These existing tools can still be useful, but should be labeled secondary:
- `deep6/backtest/vbt_harness.py`
- `deep6/backtest/optimizer.py`
- legacy script-based backtest helpers

Use them for:
- exploratory ranking
- quick sensitivity scans
- visualization

Do not use them as the primary source of truth for promotion decisions.

---

## 12. Recommended immediate next build order

If we want maximum leverage quickly, do this first:

1. Phase 1: unify API on `ReplaySession`
2. Phase 2: run manifest + lineage
3. Phase 5: pluggable fill models
4. Phase 6: walk-forward framework
5. Phase 8: promotion gates
6. Phase 7: confidence and regime reporting
7. Phase 3/9 hardening and parity certification

That order gives us a usable credible research loop fastest.

---

## 13. Verification commands once implementation starts

From repo root:

- `pytest tests/backtest -q`
- `pytest tests/api/test_backtest.py -q`
- `python -m deep6.backtest.research_runner --help`
- `python -m deep6.backtest.walkforward --help`

Expected verification milestones:
- API run route stores a manifest-backed replay run.
- Run artifacts appear in DuckDB with decisions/fills/gates.
- Same manifest produces deterministic hashes.
- Base and pessimistic fill models both report metrics.
- Walk-forward report defaults to OOS metrics.

---

## 14. Final recommendation

The right design for DEEP6 is not “one more backtest script.”
It is a certification pipeline:
- one engine
- one event schema
- versioned fill realism
- mandatory walk-forward
- regime truthfulness
- hard promotion gates
- replay/live parity tracking

That is the system I would build for us.
