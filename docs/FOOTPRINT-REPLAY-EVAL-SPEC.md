# DEEP6 Footprint Replay and Evaluation Spec

This document defines how the **Footprint Specialist** is evaluated under realistic conditions.

It covers:

- replay protocol and split strategy
- execution realism model
- evaluation metrics
- parity checks
- promotion gates
- degradation and rollback

This spec depends on:

- `docs/FOOTPRINT-SPECIALIST-PROGRAM.md`
- `docs/FOOTPRINT-PATTERN-ATLAS.md`
- `docs/FOOTPRINT-DATA-CONTRACT.md`
- `docs/FOOTPRINT-LABELING-SPEC.md`
- `docs/VERIFICATION-LADDER.md`

If this document conflicts with `docs/CURRENT-STATE.md`, treat `CURRENT-STATE.md` as authoritative.

---

## 1. Why Evaluation Is Not Just Accuracy

A footprint specialist can have high classification accuracy and still be useless in practice.

The evaluation must answer:

1. does the model detect real footprint events with stable precision?
2. does the model rank high-quality setups above noise?
3. does the model survive realistic execution costs?
4. does the model generalize across regimes and sessions?
5. does the model remain consistent between Python truth and NT8 display?

No single metric answers all five questions. This spec defines the minimum evidence required before any promotion decision.

---

## 2. Replay Protocol

### 2.1 Replay is mandatory

Every model version must be evaluated via replay before any live or paper exposure.

Replay means:

- feed historical T0 events through the full pipeline
- reconstruct T1 footprint state bar by bar
- run T2 engine emissions
- apply model scoring
- measure outcomes against T4 labels

### 2.2 Replay must be deterministic

Given the same input session, the same model version, and the same config:

- the same candidates must be generated
- the same scores must be produced
- the same action labels must be assigned

If replay is not deterministic, the pipeline has a bug. Fix it before evaluating the model.

### 2.3 Replay artifact requirements

Every replay run must produce:

- bar-by-bar candidate log with scores
- event trace with structural and context labels
- outcome resolution log
- MAE / MFE per candidate
- invalidation reason distribution
- session-level summary

---

## 3. Split Strategy

### 3.1 Forbidden split methods

- random bar-level cross-validation
- random session-level cross-validation without temporal ordering
- any split that allows training data to appear after test data in calendar time

### 3.2 Required split methods

#### Purged walk-forward

The primary evaluation method.

Structure:

- train on sessions 1 through N
- purge: skip sessions N+1 through N+P (embargo window)
- test on sessions N+P+1 through N+P+K
- roll forward and repeat

Rules:

- embargo window P must be at least 1 full session
- test window K must be at least 5 sessions
- report results per fold and aggregated

#### Session-based holdout

Reserve specific sessions as permanent holdout:

- at least 2 sessions from each regime type (balance, trend, volatile)
- at least 2 sessions from each session phase distribution (open-heavy, close-heavy, news-impacted)
- holdout sessions must never appear in training

#### Regime-based out-of-sample

Group sessions by regime tag and evaluate:

- train on balance + trend, test on volatile
- train on volatile + balance, test on trend
- train on trend + volatile, test on balance

This tests regime generalization, not just temporal generalization.

---

## 4. Execution Realism Model

Every evaluation report must specify its execution assumptions.

### 4.1 Required assumptions

| Parameter | Must specify | Example default |
|---|---|---|
| Slippage | ticks per entry | 1 tick |
| Spread | assumed spread at entry | 1 tick (NQ RTH) |
| Fill assumption | market / limit / best-effort | best-effort limit |
| Latency budget | decision-to-fill time | 500ms |
| Session-close handling | force exit or carry | force exit at 15:55 ET |
| Overlap suppression | rule for adjacent candidates | minimum 3 bars between entries |

### 4.2 Cost-adjusted expectancy

Every candidate must be scored with:

```
adjusted_excursion = forward_excursion - slippage - spread
adjusted_adverse = adverse_excursion + slippage + spread
net_expectancy = (win_rate * avg_adjusted_excursion) - ((1 - win_rate) * avg_adjusted_adverse)
```

Reports must show both raw and cost-adjusted numbers. Raw-only reports are not accepted.

### 4.3 Latency sensitivity

Test at multiple latency assumptions:

- 0ms (theoretical best)
- 250ms
- 500ms
- 1000ms

If performance degrades sharply between 250ms and 500ms, the signal is too latency-sensitive for the target infrastructure.

---

## 5. Evaluation Metrics

### 5.1 Event detection metrics

- precision: fraction of model-emitted events that are structurally real
- recall: fraction of engine-emitted events that the model also emits
- F1 at configurable thresholds

### 5.2 Ranking metrics

- top-decile precision: precision among the model's highest-confidence candidates
- calibration: predicted confidence vs observed outcome rate
- NDCG or rank correlation between model scores and realized quality

### 5.3 Excursion metrics

- mean / median forward excursion per action label tier
- mean / median adverse excursion per action label tier
- MAE / MFE ratio distribution
- time-to-resolution distribution

### 5.4 Execution-adjusted metrics

- cost-adjusted expectancy per candidate tier
- cost-adjusted Sharpe (if enough candidates per session)
- drawdown profile across replay sessions

### 5.5 Stability metrics

- metric variance across walk-forward folds
- metric variance across regime splits
- per-session metric range

If any metric has coefficient of variation above 0.5 across folds, the model is not stable enough.

---

## 6. Parity Checks

### 6.1 Python vs NT8 parity

For any session replayed in both Python and NT8:

- compare structural label counts and subtypes
- compare candidate counts and directions
- compare model scores (if model runs in both)
- measure mismatch rate

Acceptable mismatch:

- structural label count: within 5% per session
- candidate direction: exact match required
- model score: within 0.05 absolute per candidate

### 6.2 Replay vs live capture parity

For sessions where both replay and live capture exist:

- compare event timing
- compare bar state at each candidate
- compare outcome labels

Known divergences must be documented per `ninjatrader/docs/SIGNALS.md` section on known divergences.

### 6.3 Parity failure blocks promotion

If parity mismatch exceeds thresholds:

- do not promote to paper
- investigate and resolve before re-evaluating
- document the resolution

---

## 7. Promotion Gates

This spec inherits and specializes the gates from `docs/VERIFICATION-LADDER.md`.

### 7.1 Gate: Offline replay pass

Required before paper:

- at least 20 sessions replayed
- walk-forward evaluation complete (minimum 3 folds)
- event detection F1 above configured minimum
- top-decile precision above configured minimum
- cost-adjusted expectancy positive after fees
- stability metrics within acceptable variance
- parity checks passing

### 7.2 Gate: Paper pass

Required before constrained live:

- at least 10 full RTH paper sessions
- advisory stream stable without crashes or stalls
- no unexplained invalidation drift
- operator review logs explainable
- no parity regression from replay expectations
- latency within budget for target infrastructure

### 7.3 Gate: Constrained live pass

Required before expanded use:

- advisory-only first (no execution)
- explicit human arming per session
- every live session reviewed post-close
- any anomaly triggers automatic downgrade to paper
- live metrics must not regress from paper metrics by more than 15%

### 7.4 Promotion rule

A higher gate cannot override failure at a lower gate.

- good paper results do not excuse bad replay parity
- good live results do not excuse unstable walk-forward metrics
- impressive accuracy does not excuse missing execution realism

---

## 8. Degradation and Rollback

### 8.1 Monitoring in production

Once the specialist is running in paper or live advisory mode, track:

- event detection rate per session (should be stable)
- candidate quality distribution (should not drift)
- false positive rate in top-decile (should not rise)
- teacher-model agreement rate (should remain within historical range)
- latency distribution (should remain within budget)

### 8.2 Degradation triggers

Automatic downgrade if any of:

- event detection rate drops below 50% of historical average for 3 consecutive sessions
- false positive rate in top-decile rises above 2x historical average
- teacher-model agreement drops below 60%
- parity mismatch exceeds thresholds for 2 consecutive sessions
- latency exceeds budget for more than 10% of candidates in a session

### 8.3 Rollback protocol

When degradation triggers fire:

1. downgrade to paper-only or advisory-only
2. capture evidence from the degraded sessions
3. investigate root cause (data quality, regime shift, model drift, infrastructure)
4. retrain or recalibrate if needed
5. re-enter the replay gate before re-promoting

### 8.4 Retraining cadence

Recommended:

- quarterly retraining at minimum
- immediate retraining if degradation triggers fire and root cause is model drift
- retraining requires full walk-forward evaluation before promotion

---

## 9. Report Format

Every evaluation must produce a structured report containing:

### 9.1 Header

- model version
- dataset version
- label version
- config version
- evaluation date
- evaluator

### 9.2 Split summary

- number of training sessions
- number of embargo sessions
- number of test sessions
- regime distribution in test set

### 9.3 Metric tables

- event detection metrics per family
- ranking metrics
- excursion metrics per action label tier
- execution-adjusted metrics at each latency assumption
- stability metrics across folds

### 9.4 Parity section

- Python vs NT8 mismatch rates
- replay vs live capture mismatch rates (if available)

### 9.5 Gate checklist

- each gate requirement listed with pass/fail/not-tested
- blocking issues listed explicitly

### 9.6 Decision

- promote / hold / retrain / investigate

---

## 10. Forbidden Evaluation Shortcuts

Do not:

1. report accuracy on a random split and call it validated
2. report raw excursion without execution cost adjustment
3. omit regime-split testing
4. skip parity checks between Python and NT8
5. promote directly from offline accuracy to live use
6. hide degradation behind session exclusion
7. evaluate on training data and report it as test performance
8. report metrics without specifying the exact model, dataset, label, and config versions

---

## 11. Relationship to Other Documents

This document completes the Footprint Specialist spec suite:

| Document | Role |
|---|---|
| `FOOTPRINT-SPECIALIST-PROGRAM.md` | Architecture, mission, phases |
| `FOOTPRINT-PATTERN-ATLAS.md` | Pattern vocabulary and taxonomy |
| `FOOTPRINT-DATA-CONTRACT.md` | Machine-readable data shapes |
| `FOOTPRINT-LABELING-SPEC.md` | Label layers and anti-leakage |
| `FOOTPRINT-REPLAY-EVAL-SPEC.md` | Evaluation, promotion, rollback |

Together, these five documents convert the Footprint Specialist Program from architecture into executable build work.
