# DEEP6 Footprint Specialist Program

This document defines the architecture, training program, validation ladder, and deployment constraints for a **footprint-only AI specialist** built from DEEP6.

It is intentionally narrower than DEEP6 as a whole.
Its purpose is not to be a general trading intelligence.
Its purpose is to become exceptionally strong at reading **footprint auction behavior**:

- absorption
- exhaustion
- delta and CVD behavior
- imbalance and stacked imbalance structure
- effort-versus-result mismatch
- level interaction inside the footprint

If any claim in this document conflicts with `docs/CURRENT-STATE.md`, treat `CURRENT-STATE.md` as authoritative.

---

## 1. Mission

Build a footprint-native expert that:

1. learns from **raw microstructure truth**, not chart pixels alone
2. uses DEEP6's existing signal engines as a teacher system
3. ranks setups by **confluence, actionability, and execution realism**
4. explains its reasoning through a NinjaTrader overlay and replay surfaces
5. earns trust only through replay, parity, paper, and constrained-live evidence

This system is advisory-first.
Execution-facing promotion happens only after the full verification ladder is passed.

---

## 2. Non-Negotiable Principles

### 2.1 Raw event data is ground truth

The specialist must treat market events as canonical truth:

- trade prints
- aggressor side
- depth / L2 updates
- MBO when available
- session boundaries
- exact timestamps

Rendered charts are downstream views of that truth.

### 2.2 Footprint state is the canonical learning representation

The primary model input is not the screenshot.
It is reconstructed footprint state:

- per-price bid/ask volume
- bar delta and intrabar delta path
- max/min intrabar delta
- POC / value area interaction
- wick participation
- imbalance ladders
- stacked runs
- local context around levels

### 2.3 Video is auxiliary, not primary

NinjaTrader screenshots and video are useful for:

- expert review
- synchronized annotation
- explanation alignment
- UI-specific cue recovery

They must not become the sole or primary source of truth.

### 2.4 Rules are not thrown away

Existing DEEP6 engines are domain assets, not temporary scaffolding.

Use them as:

- teacher signals
- candidate generators
- weak-label builders
- interpretable baselines
- parity references

### 2.5 Trust is earned through evidence

This program inherits the verification logic in `docs/VERIFICATION-LADDER.md`.
No accuracy or performance claim is accepted without replay, parity, and execution-aware validation.

---

## 3. Existing Repo Assets to Reuse

### 3.1 Canonical Python signal logic

Primary sources:

- `deep6/state/footprint.py`
- `deep6/engines/absorption.py`
- `deep6/engines/exhaustion.py`
- `deep6/engines/delta.py`
- `deep6/engines/imbalance.py`
- `deep6/engines/signal_config.py`

### 3.2 Test-backed synthetic signal fixtures

Primary sources:

- `tests/test_absorption.py`
- `tests/test_exhaustion.py`
- `tests/test_delta.py`
- `tests/test_imbalance.py`
- `ninjatrader/tests/fixtures/**`

These are early curriculum data and regression assets.

### 3.3 NT8 integration and overlay surfaces

Primary sources:

- `ninjatrader/Custom/BarsTypes/DEEP6/DEEP6FootprintBarsType.cs`
- `ninjatrader/Custom/ChartStyles/DEEP6/DEEP6FootprintStyle.cs`
- `ninjatrader/Custom/AddOns/DEEP6/Bridge/FootprintSharedState.cs`
- `ninjatrader/Custom/AddOns/DEEP6/Bridge/DataBridgeServer.cs`
- `ninjatrader/docs/SIGNALS.md`

### 3.4 Dashboard / replay visualization surfaces

Primary sources:

- `dashboard/lib/lw-charts/FootprintRenderer.ts`
- `dashboard/components/footprint/SignalMarkerOverlay.tsx`
- `dashboard/docs/FOOTPRINT-GUIDE.md`

### 3.5 Microstructure research base

Primary source:

- `.planning/research/pine/deep/microstructure.md`

---

## 4. Canonical Data Hierarchy

All training and evaluation artifacts must preserve this hierarchy.

### T0 — Raw event stream

Minimum fields:

- timestamp
- price
- size
- aggressor side
- order book update type
- bid/ask depth snapshot or delta
- session markers

Preferred sources:

- Databento MBO / L3 for historical truth
- Rithmic / async-rithmic L2 for live path

### T1 — Reconstructed footprint state

Derived from T0.

Minimum fields:

- per-level bid/ask volume
- total volume
- bar delta
- cumulative delta
- running delta path
- intrabar max/min delta
- wick/body segmentation
- POC / VAH / VAL interaction
- imbalance map
- stacked imbalance runs

### T2 — Deterministic expert emissions

Derived from T1 using DEEP6 engines.

Minimum event families:

- absorption
- exhaustion
- delta / CVD
- imbalance
- trap / slingshot / divergence where applicable

### T3 — Visual sync layer

Derived from T0-T2 and platform state.

Artifacts:

- synchronized NT8 screenshots
- NT8 video segments
- overlay state snapshots
- chart viewport / zoom / panel metadata

### T4 — Outcome and execution labels

Derived from replay and execution simulation.

Minimum fields:

- forward excursion
- adverse excursion
- time-to-resolution
- invalidation event
- fillability assumptions
- slippage assumption
- session-end expiry
- trade/no-trade label

---

## 5. Labeling Framework

The specialist needs more than pattern labels.
It needs labels for **quality** and **actionability**.

### 5.1 Structural labels

These answer: what pattern is present?

Examples:

- classic absorption
- passive absorption
- stopping volume
- effort vs result
- zero print
- exhaustion print
- thin print
- fat print
- delta divergence
- stacked imbalance

Primary generation source:

- DEEP6 deterministic engines

### 5.2 Context labels

These answer: what market context surrounds the pattern?

Examples:

- at structure / free space
- at POC / VAH / VAL / session extreme
- open / midday / close / post-news
- balance day / trend day / volatile regime
- absorption building / confirmed / failed

### 5.3 Action labels

These answer: should this be acted on?

Allowed labels:

- no-trade
- watch
- candidate
- executable
- expired
- invalidated

### 5.4 Human review targets

Human review should focus on:

- teacher/model disagreement
- rare regime cases
- visually convincing but structurally weak patterns
- structurally strong but visually ugly patterns
- false positives near news and volatility shocks

---

## 6. Model Program

### Phase A — Rule-backed baseline

Goal:
Create a deterministic baseline with replay-grade evidence.

Outputs:

- candidate event stream
- confluence features
- execution-aware labels

This phase must exist before any learned model is trusted.

### Phase B — Meta-labeler / ranker

Goal:
Learn which rule-emitted candidates are real, high quality, and actionable.

Recommended first model class:

- calibrated gradient-boosted trees over structured footprint features

Primary targets:

- candidate validity
- reversal / continuation quality
- expected forward excursion
- expected adverse excursion
- execution viability after costs

Reason:
This gives interpretability, speed, and a strong baseline before sequence models.

### Phase C — Temporal footprint specialist

Goal:
Learn sequence intelligence that fixed rules and tabular features miss.

Recommended second model class:

- compact temporal encoder over structured footprint tensors

Input sketch:

- time × price-level × feature-channel

Candidate channels:

- bid volume
- ask volume
- delta
- imbalance ratio
- POC flag
- wick/body flag
- local depth pressure
- event markers from teacher rules

### Phase D — Visual alignment model

Goal:
Teach the system to reconcile structured truth with what the operator sees in NT8.

Allowed uses:

- explanation alignment
- overlay consistency
- screenshot audit
- optional weak supervision on visual layout states

Forbidden use:

- replacing event-native truth with screenshots alone

---

## 7. Feature Families

At minimum, the learned system should expose features from these families.

### 7.1 Bar-internal footprint features

- total volume
- bar delta
- delta quality scalar
- delta slope / fade
- wick volume fractions
- bar range vs ATR
- POC location
- thin/fat level counts

### 7.2 Level-interaction features

- aggression at level vs ticks moved
- imbalance density around level
- stacked imbalance persistence
- top/bottom zone pressure
- POC-in-wick behavior
- value-area proximity

### 7.3 Sequence features

- prior N-bar absorption persistence
- divergence persistence
- repeated failed auctions
- multi-bar delta compression / release
- local CVD drift
- pace of failed attempts at the same level

### 7.4 Execution realism features

- spread regime
- depth available near decision point
- estimated slippage bucket
- time-of-day liquidity regime
- signal age / staleness

---

## 8. Backtesting and Replay Protocol

This program must never be evaluated by random split alone.

### 8.1 Allowed evaluation styles

- purged walk-forward replay
- session-based splits
- regime-based out-of-sample splits
- paper/live parity comparison

### 8.2 Required replay evidence

- deterministic event traces
- bar-by-bar candidate logs
- model score traces
- MAE / MFE summaries
- invalidation reason counts
- execution-adjusted expectancy

### 8.3 Required realism constraints

Every serious report must specify:

- slippage model
- fill assumptions
- latency budget
- spread assumptions
- session-close handling
- rule for overlap suppression between adjacent candidates

### 8.4 Disallowed evaluation shortcuts

- random cross-validation over overlapping bars
- training on finalized-bar features for intrabar decisions
- PnL-only labels with no structural event labels
- reporting raw hit rate without execution assumptions

---

## 9. Verification Ladder for the Specialist

This program inherits the main DEEP6 ladder and specializes it.

### Gate 0 — Structural correctness

- dataset contracts are versioned
- synchronized timestamps are verifiable
- feature generation is reproducible

### Gate 1 — Unit correctness

- signal engines remain green
- label generators remain green
- feature builders remain green

### Gate 2 — Integration correctness

- raw feed → footprint state → teacher labels is stable
- replay pipeline produces complete artifacts
- NT8 overlay schema matches Python outputs

### Gate 3 — Replay correctness

- historical sessions replay deterministically
- candidate traces are explainable
- known deviations are measured

### Gate 4 — Parity correctness

- Python inference vs NT8 display match within explicit thresholds
- replay output vs live-captured output mismatch is measured

### Gate 5 — Paper correctness

- advisory stream is stable for full RTH sessions
- no unresolved invalidation drift
- operator review logs are explainable

### Gate 6 — Constrained live correctness

- advisory-only first
- live anomalies trigger downgrade to paper-only
- promotion requires explicit human arming and session review

---

## 10. Deployment Architecture

### 10.1 Python is canonical

Python owns:

- data ingestion and replay truth
- feature generation
- label generation
- training
- offline validation
- online inference
- evidence generation

### 10.2 NinjaTrader is the execution-facing surface

NT8 owns:

- chart rendering
- operator visibility
- video/screenshot synchronization
- advisory display
- optional downstream execution consumption later

### 10.3 Signal schema

The live specialist should publish a compact schema containing at least:

- timestamp
- instrument
- event family
- event subtype
- direction
- confidence
- action label
- invalidation condition
- expected horizon
- concise explanation

---

## 11. Program Phases

### Phase 0 — Ontology lock

Deliver:

- footprint pattern atlas
- regime taxonomy
- invalidation taxonomy
- action taxonomy

### Phase 1 — Canonical data build

Deliver:

- synchronized T0-T4 dataset contract
- replayable session store
- screenshot/video sync strategy

### Phase 2 — Weak labels and curation

Deliver:

- teacher-generated event labels
- review queues
- curated disagreement sets

### Phase 3 — Baseline ranker

Deliver:

- calibrated meta-labeler
- replay reports
- feature importance and calibration evidence

### Phase 4 — Temporal specialist

Deliver:

- sequence model over footprint tensors
- incremental lift study vs baseline ranker

### Phase 5 — Overlay integration

Deliver:

- NT8 advisory overlay
- replay visualization hooks
- operator explanations tied to signal schema

### Phase 6 — Paper promotion

Deliver:

- live advisory session evidence
- drift monitoring
- degradation behavior and rollback gates

---

## 12. Explicit Do-Not-Do List

Do not:

1. train a screenshot-only model and call it footprint expertise
2. use future-known information in decision-time labels
3. drop failed setups and null bars from the training corpus
4. accept win-rate claims without replay and execution realism
5. allow Python truth and NT8 display logic to drift silently
6. promote the system directly from offline accuracy to live usage

---

## 13. Definition of Success

This program succeeds when the specialist can:

- detect footprint events with stable precision across regimes
- rank high-quality setups above visually similar noise
- explain why a setup is valid or invalid in footprint terms
- survive replay and out-of-sample testing after realistic execution costs
- remain consistent between Python truth, NT8 overlay, and paper-trading behavior

It does **not** succeed merely because:

- screenshots look convincing
- model accuracy is high on a random split
- isolated backtests show attractive raw hit rates

---

## 14. Immediate Next Artifacts

The next documents to produce from this program are:

1. `docs/FOOTPRINT-PATTERN-ATLAS.md`
2. `docs/FOOTPRINT-DATA-CONTRACT.md`
3. `docs/FOOTPRINT-LABELING-SPEC.md`
4. `docs/FOOTPRINT-REPLAY-EVAL-SPEC.md`

Those four documents convert this program from architecture into executable build work.
